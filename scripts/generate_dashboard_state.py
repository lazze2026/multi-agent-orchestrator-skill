#!/usr/bin/env python3
"""Generate dashboard/state.json for the multi-agent-orchestrator skill.

The collector is read-only against the orchestrator workspace. It summarizes
queue, events, reports, checkpoints, and locks into one static snapshot that a
local HTML dashboard can refresh safely. It uses only the Python standard
library and supports Python 3.9+.
"""
from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path
from typing import Any


def parse_time(value: Any) -> str:
    """Normalize common timestamp strings to an ISO-8601-like format."""
    if value is None:
        return ""
    if isinstance(value, datetime):
        return value.astimezone().replace(microsecond=0).isoformat()
    if not isinstance(value, str):
        return ""
    text = value.strip()
    if not text:
        return ""
    if " " in text and "T" not in text:
        text = text.replace(" ", "T", 1)
    text = text.replace("T+", "+")
    return text


def read_json(path: Path, default: Any) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8-sig"))
    except (FileNotFoundError, json.JSONDecodeError):
        return default


def read_jsonl_files(directory: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    if not directory.exists():
        return rows
    for path in sorted(directory.glob("*.jsonl")):
        for line in path.read_text(encoding="utf-8-sig").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                value = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(value, dict):
                rows.append(value)
    return rows


def read_json_files(directory: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    if not directory.exists():
        return rows
    for path in sorted(directory.glob("*.json")):
        value = read_json(path, None)
        if isinstance(value, dict):
            rows.append(value)
        elif isinstance(value, list):
            rows.extend(item for item in value if isinstance(item, dict))
    return rows


def task_title(task: dict[str, Any]) -> str:
    return str(task.get("title") or task.get("task_title") or task.get("summary") or task.get("task_id") or "未命名任务")


def group_tasks(tasks: list[dict[str, Any]]) -> list[dict[str, Any]]:
    groups = [
        ("已完成", "done", {"done", "passed"}),
        ("正在进行", "running", {"running", "verifying", "active"}),
        ("已部分完成", "partially_completed", {"partially_completed"}),
        ("排队等待", "queued", {"queued"}),
        ("卡住/待决策", "blocked", {"blocked", "needs_human_decision", "failed"}),
    ]
    result: list[dict[str, Any]] = []
    for name, group_status, statuses in groups:
        group_items = []
        for task in tasks:
            status = str(task.get("status", "queued"))
            if status not in statuses:
                continue
            group_items.append({
                "task_id": task.get("task_id", "unknown"),
                "title": task_title(task),
                "owner": task.get("owner", task.get("agent", "unassigned")),
                "priority": task.get("priority", "normal"),
                "progress": task.get("progress", "0%"),
                "next": task.get("next") or task.get("next_action") or "待调度",
                "result": task.get("result", ""),
                "blocker": task.get("blocker") or task.get("blocked_by") or "",
            })
        result.append({"name": name, "status": group_status, "tasks": group_items})
    return result


def summarize(tasks: list[dict[str, Any]], agents: list[dict[str, Any]], blockers: list[dict[str, Any]], actions: list[dict[str, Any]]) -> dict[str, int]:
    statuses = [str(t.get("status", "queued")) for t in tasks]
    return {
        "total_tasks": len(tasks),
        "completed": sum(s in {"done", "passed"} for s in statuses),
        "in_progress": sum(s in {"running", "verifying", "active"} for s in statuses),
        "blocked": sum(s in {"blocked", "needs_human_decision", "failed"} for s in statuses),
        "queued": sum(s == "queued" for s in statuses),
        "needs_dispatch": len(actions),
        "open_risks": len(blockers),
        "active_agents": sum(str(a.get("status")) in {"active", "running", "verifying", "warning"} for a in agents),
        "stale_agents": sum(bool(a.get("stale")) for a in agents),
    }


def normalize_events(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    def event_time(event: dict[str, Any]) -> str:
        return parse_time(event.get("time") or event.get("timestamp") or event.get("created_at"))
    sorted_events = sorted(events, key=event_time, reverse=True)
    return [{
        "event_id": e.get("event_id", e.get("id", "evt_unknown")),
        "time": event_time(e),
        "agent": e.get("agent", e.get("owner", "unknown")),
        "event": e.get("event", e.get("type", "event")),
        "summary": e.get("summary", e.get("message", "")),
        "caused_by": e.get("caused_by", "unknown"),
        "task_id": e.get("task_id", "unknown"),
    } for e in sorted_events[:10]]


def normalize_checkpoints(raw: list[dict[str, Any]]) -> list[dict[str, Any]]:
    checkpoints = []
    for i, c in enumerate(raw, 1):
        checkpoints.append({
            "checkpoint_id": c.get("checkpoint_id", c.get("id", f"ckpt_{i:03d}")),
            "created_at": parse_time(c.get("created_at", c.get("time", ""))),
            "status": c.get("status", "resumable"),
            "completed_tasks": c.get("completed_tasks", 0),
            "partially_completed_tasks": c.get("partially_completed_tasks", 0),
            "blocked_tasks": c.get("blocked_tasks", 0),
            "can_resume": c.get("can_resume", True),
            "resume_from": c.get("resume_from", c.get("next_owner", "")),
            "evidence": c.get("evidence", c.get("resume", "")),
        })
    return checkpoints


def first_task(group: dict[str, Any]) -> dict[str, Any]:
    tasks = group.get("tasks") or []
    return tasks[0] if tasks else {}


def infer_timeline(task_groups: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Infer a gantt-style timeline from actual task groups."""
    by_name = {str(group.get("name")): group for group in task_groups}

    def item(group_name: str, phase: str, start: int, span: int, owner: str, title: str, fallback_status: str) -> dict[str, Any]:
        group = by_name.get(group_name, {})
        task = first_task(group)
        return {
            "phase": phase,
            "start": start,
            "span": span,
            "owner": task.get("owner", owner),
            "title": task.get("title", title),
            "status": group.get("status", fallback_status),
            "tasks": [t.get("task_id", "unknown") for t in group.get("tasks", [])[:3]],
        }

    return [
        item("已完成", "规划", 1, 2, "Coordinator", "任务拆解与授权", "queued"),
        item("正在进行", "执行", 3, 3, "Worker", "任务执行", "queued"),
        item("已部分完成", "执行", 4, 2, "Worker", "部分完成与恢复点", "queued"),
        item("正在进行", "验证", 6, 2, "Verifier", "独立验证", "queued"),
        item("卡住/待决策", "验证", 6, 2, "Verifier", "验证失败处理", "queued"),
        item("正在进行", "监控", 2, 6, "Monitor", "风险监控与瓶颈预测", "queued"),
        item("卡住/待决策", "调度", 8, 2, "Coordinator", "调度决策", "queued"),
        item("排队等待", "调度", 9, 1, "Coordinator", "排队任务安排", "queued"),
    ]


def generate_state(workspace: Path, refresh_interval: int) -> dict[str, Any]:
    queue_tasks = read_jsonl_files(workspace / "queue")
    if not queue_tasks:
        queue_tasks = read_json(workspace / "queue" / "tasks.json", [])
    if not isinstance(queue_tasks, list):
        queue_tasks = []
    agents = read_json_files(workspace / "agents") or read_json(workspace / "agents.json", [])
    if not isinstance(agents, list):
        agents = []
    blockers = read_json_files(workspace / "blockers") or read_json(workspace / "blockers.json", [])
    if not isinstance(blockers, list):
        blockers = []
    actions = read_json_files(workspace / "dispatch") or read_json(workspace / "dispatch_actions.json", [])
    if not isinstance(actions, list):
        actions = []
    task_groups = group_tasks(queue_tasks)
    explicit_timeline = read_json(workspace / "flow_timeline.json", None)
    state = {
        "generated_at": parse_time(datetime.now()),
        "refresh_interval_seconds": refresh_interval,
        "read_only": True,
        "freshness": {"status": "current", "age": "0s", "next_refresh_at": ""},
        "project": read_json(workspace / "project.json", {"name": workspace.name, "goal": "", "mode": "parallel-planning-serial-execution", "current_focus": ""}),
        "policy": read_json(workspace / "orchestrator.json", {}).get("policy", {}),
        "summary": summarize(queue_tasks, agents, blockers, actions),
        "task_groups": task_groups,
        "agents": agents,
        "blockers": blockers,
        "flow_timeline": explicit_timeline if isinstance(explicit_timeline, list) else infer_timeline(task_groups),
        "dispatch_actions": actions,
        "recent_events": normalize_events(read_jsonl_files(workspace / "events")),
        "checkpoints": normalize_checkpoints(read_json_files(workspace / "checkpoints")),
    }
    return state


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate multi-agent dashboard state.json")
    parser.add_argument("workspace", type=Path, help="Orchestrator workspace containing queue/, events/, reports/, checkpoints/, locks/")
    parser.add_argument("--output", type=Path, default=None, help="Output state.json path. Defaults to <workspace>/dashboard/state.json")
    parser.add_argument("--refresh-interval", type=int, default=180, help="Dashboard refresh interval in seconds")
    args = parser.parse_args()
    workspace = args.workspace.resolve()
    output = args.output or workspace / "dashboard" / "state.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(generate_state(workspace, args.refresh_interval), ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"wrote {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())