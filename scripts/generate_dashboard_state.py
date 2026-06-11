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
import re
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any


DEFAULT_DISPLAY_DICTIONARY = {
    "status": {
        "active": "活跃",
        "running": "进行中",
        "done": "已完成",
        "partially_completed": "部分完成",
        "blocked": "阻塞",
        "queued": "排队",
        "verifying": "验证中",
        "failed": "失败",
        "warning": "预警",
        "read_only": "只读",
        "needs_human_decision": "待人工决策",
        "passed": "验证通过",
        "current": "当前",
        "resumable": "可恢复",
        "needs_decision": "待决策",
        "pending": "待处理",
        "unknown": "未知",
    },
    "risk": {
        "none": "无风险",
        "api_rate_limit": "API 限流",
        "rate_window": "限流窗口",
        "write_lock": "写锁占用",
        "read_lock": "读锁占用",
        "manual_disposition": "人工处置",
        "data_source_unavailable": "数据源不可用",
    },
    "phase": {
        "planning": "规划",
        "execution": "执行",
        "verification": "验证",
        "monitoring": "监控",
        "dispatch": "调度",
    },
    "priority": {
        "critical": "紧急",
        "high": "高",
        "normal": "普通",
        "low": "低",
        "medium": "中",
    },
}

DEFAULT_EVENT_DISPLAY_RULES = [
    {"pattern": r"^worker\.resumed$", "label": "Worker 从检查点恢复"},
    {"pattern": r"^worker\.partially_completed$", "label": "Worker 部分完成"},
    {"pattern": r"^verification\.failed$", "label": "验证失败"},
    {"pattern": r"^verification\.passed$", "label": "验证通过"},
    {"pattern": r"^dashboard\.snapshot\.created$", "label": "看板快照已生成"},
    {"pattern": r"^checkpoint\.created$", "label": "检查点已创建"},
    {"pattern": r"^monitor\.warning$", "label": "监控预警"},
]


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


def merge_dict(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    result = dict(base)
    for key, value in override.items():
        if isinstance(result.get(key), dict) and isinstance(value, dict):
            result[key] = merge_dict(result[key], value)
        else:
            result[key] = value
    return result


def task_title(task: dict[str, Any]) -> str:
    return str(
        task.get("title")
        or task.get("task_title")
        or task.get("summary")
        or task.get("task_id")
        or "未命名任务"
    )


def task_description(task: dict[str, Any]) -> str:
    return str(
        task.get("task_description")
        or task.get("description")
        or task.get("detail")
        or task.get("result")
        or task.get("summary")
        or ""
    )


def event_time(event: dict[str, Any]) -> str:
    return parse_time(event.get("time") or event.get("timestamp") or event.get("created_at"))


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
            group_items.append(
                {
                    "task_id": task.get("task_id", "unknown"),
                    "title": task_title(task),
                    "owner": task.get("owner", task.get("agent", "unassigned")),
                    "priority": task.get("priority", "normal"),
                    "progress": task.get("progress", "0%"),
                    "next": task.get("next") or task.get("next_action") or "待调度",
                    "result": task.get("result", ""),
                    "blocker": task.get("blocker") or task.get("blocked_by") or "",
                    "task_description": task_description(task),
                }
            )
        result.append({"name": name, "status": group_status, "tasks": group_items})
    return result


def summarize(
    tasks: list[dict[str, Any]],
    agents: list[dict[str, Any]],
    blockers: list[dict[str, Any]],
    actions: list[dict[str, Any]],
) -> dict[str, Any]:
    statuses = [str(t.get("status", "queued")) for t in tasks]
    completed = sum(s in {"done", "passed"} for s in statuses)
    in_progress = sum(s in {"running", "verifying", "active"} for s in statuses)
    blocked = sum(s in {"blocked", "needs_human_decision", "failed"} for s in statuses)
    queued = sum(s == "queued" for s in statuses)
    total_tasks = len(tasks)
    summary = {
        "total_tasks": total_tasks,
        "completed": completed,
        "in_progress": in_progress,
        "blocked": blocked,
        "queued": queued,
        "needs_dispatch": len(actions),
        "open_risks": len(blockers),
        "active_agents": sum(str(a.get("status")) in {"active", "running", "verifying", "warning"} for a in agents),
        "stale_agents": sum(bool(a.get("stale")) for a in agents),
    }
    summary["metrics"] = [
        {
            "id": "task_completion",
            "label": "任务完成率",
            "value": f"{completed}/{total_tasks}",
            "note": "已完成任务 / 总任务数",
            "status": "running" if completed < total_tasks else "done",
        },
        {
            "id": "active_agents",
            "label": "活跃 Agent",
            "value": str(summary["active_agents"]),
            "note": "包含执行、验证、监控角色",
            "status": "active",
        },
        {
            "id": "blockers",
            "label": "当前卡点",
            "value": str(len(blockers)),
            "note": "含授权、锁冲突、验证失败",
            "status": "blocked" if blockers else "done",
        },
        {
            "id": "dispatch",
            "label": "待调度事项",
            "value": str(len(actions)),
            "note": "需要 Coordinator 或用户处理",
            "status": "warning" if actions else "done",
        },
    ]
    return summary


def format_age(from_iso: str, now: datetime) -> str:
    if not from_iso:
        return "未知"
    try:
        dt = datetime.fromisoformat(from_iso)
    except ValueError:
        return "未知"
    seconds = max(0, int((now - dt).total_seconds()))
    if seconds < 60:
        return f"{seconds}s"
    minutes, rem = divmod(seconds, 60)
    if minutes < 60:
        return f"{minutes}m {rem}s"
    hours, rem_minutes = divmod(minutes, 60)
    return f"{hours}h {rem_minutes}m"


def normalize_events(events: list[dict[str, Any]], event_rules: list[dict[str, Any]]) -> list[dict[str, Any]]:
    sorted_events = sorted(events, key=event_time, reverse=True)

    def event_label(name: str) -> str:
        text = str(name or "event")
        for rule in event_rules:
            pattern = rule.get("pattern")
            if pattern and re.search(pattern, text):
                return str(rule.get("label") or text)
        return text

    normalized = []
    for e in sorted_events[:10]:
        normalized.append(
            {
                "event_id": e.get("event_id", e.get("id", "evt_unknown")),
                "time": event_time(e),
                "agent": e.get("agent", e.get("owner", "unknown")),
                "event": e.get("event", e.get("type", "event")),
                "event_label": event_label(e.get("event", e.get("type", "event"))),
                "summary": e.get("summary", e.get("message", "")),
                "caused_by": e.get("caused_by", "unknown"),
                "task_id": e.get("task_id", "unknown"),
                "trigger_event_id": e.get("trigger_event_id", ""),
                "blocked_by": e.get("blocked_by", ""),
                "conflicting_resource": e.get("conflicting_resource", ""),
            }
        )
    return normalized


def normalize_checkpoints(raw: list[dict[str, Any]]) -> list[dict[str, Any]]:
    checkpoints = []
    for i, c in enumerate(raw, 1):
        checkpoints.append(
            {
                "checkpoint_id": c.get("checkpoint_id", c.get("id", f"ckpt_{i:03d}")),
                "created_at": parse_time(c.get("created_at", c.get("time", ""))),
                "status": c.get("status", "resumable"),
                "completed_tasks": c.get("completed_tasks", 0),
                "partially_completed_tasks": c.get("partially_completed_tasks", 0),
                "blocked_tasks": c.get("blocked_tasks", 0),
                "can_resume": c.get("can_resume", True),
                "resume_from": c.get("resume_from", c.get("next_owner", "")),
                "evidence": c.get("evidence", c.get("resume", "")),
            }
        )
    return checkpoints


def first_task(group: dict[str, Any]) -> dict[str, Any]:
    tasks = group.get("tasks") or []
    return tasks[0] if tasks else {}


def infer_timeline(task_groups: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Infer a gantt-style timeline from actual task groups."""
    by_name = {str(group.get("name")): group for group in task_groups}

    def item(
        group_name: str,
        phase: str,
        start: int,
        span: int,
        owner: str,
        title: str,
        fallback_status: str,
    ) -> dict[str, Any]:
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


def infer_entity_grid(task_groups: list[dict[str, Any]]) -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
    for group in task_groups:
        for task in group.get("tasks", []):
            rows.append(
                {
                    "id": task.get("task_id", "unknown"),
                    "label": task.get("title", task.get("task_id", "unknown")),
                    "stage": task.get("status", group.get("status", "queued")),
                    "owner": task.get("owner", "unassigned"),
                    "count": task.get("progress", ""),
                    "verification": task.get("next", ""),
                    "risk": task.get("blocker", "") or task.get("result", ""),
                }
            )
            if len(rows) >= 8:
                break
        if len(rows) >= 8:
            break
    return {
        "title": "任务实体状态矩阵",
        "entity_type": "task",
        "columns": ["实体", "阶段", "负责人", "进度", "下一步/验证", "风险"],
        "rows": rows,
    }


def normalize_agents(agents: list[dict[str, Any]]) -> list[dict[str, Any]]:
    normalized = []
    for agent in agents:
        current_work = (
            agent.get("current_work")
            or agent.get("task_title")
            or agent.get("task_description")
            or agent.get("task_id")
            or ""
        )
        detail = agent.get("detail") or agent.get("task_description") or agent.get("next_action") or ""
        last_seen = parse_time(agent.get("last_seen") or agent.get("last_observed") or agent.get("updated_at"))
        normalized.append(
            {
                **agent,
                "current_work": current_work,
                "detail": detail,
                "last_seen": last_seen,
                "last_observed": parse_time(agent.get("last_observed") or last_seen),
            }
        )
    return normalized


def build_policy(orchestrator: dict[str, Any]) -> dict[str, Any]:
    if isinstance(orchestrator.get("policy"), dict):
        return orchestrator["policy"]
    execution = orchestrator.get("execution", {})
    agents = orchestrator.get("agents", {})
    dashboard = agents.get("dashboard", {}) if isinstance(agents, dict) else {}
    authorization = orchestrator.get("authorization", {})
    return {
        "execution_mode": execution.get("default_mode", "parallel-planning-serial-execution"),
        "priority_policy": execution.get("priority_policy", "priority-then-fifo"),
        "verification": "risk-based sampling",
        "locks": "read/write/exclusive",
        "auto_fix": authorization.get("auto_fix", False),
        "write_authorization": "task-spec-required" if authorization.get("require_task_spec_for_write", True) else "direct-write-allowed",
        "refresh_interval_seconds": dashboard.get("refresh_interval_seconds", 180),
    }


def generate_state(workspace: Path, refresh_interval: int) -> dict[str, Any]:
    orchestrator = read_json(workspace / "orchestrator.json", {})
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
    entity_grid = read_json(workspace / "entity_grid.json", None)
    display_dictionary = merge_dict(
        DEFAULT_DISPLAY_DICTIONARY,
        read_json(workspace / "display_dictionary.json", {}),
    )
    event_display_rules = read_json(workspace / "event_display_rules.json", DEFAULT_EVENT_DISPLAY_RULES)
    if not isinstance(event_display_rules, list):
        event_display_rules = DEFAULT_EVENT_DISPLAY_RULES

    now = datetime.now().astimezone().replace(microsecond=0)
    generated_at = parse_time(now)
    next_refresh_at = parse_time(now + timedelta(seconds=refresh_interval))
    summary = summarize(queue_tasks, agents, blockers, actions)
    normalized_agents = normalize_agents(agents)
    policy = build_policy(orchestrator)

    state = {
        "schema_version": "1.3.0",
        "generated_at": generated_at,
        "refresh_interval_seconds": refresh_interval,
        "read_only": True,
        "freshness": {"status": "current", "age": "0s", "next_refresh_at": next_refresh_at},
        "project": read_json(
            workspace / "project.json",
            {
                "name": workspace.name,
                "goal": "",
                "mode": policy.get("execution_mode", "parallel-planning-serial-execution"),
                "current_focus": "",
            },
        ),
        "policy": policy,
        "summary": summary,
        "task_groups": task_groups,
        "agents": normalized_agents,
        "blockers": blockers,
        "flow_timeline": explicit_timeline if isinstance(explicit_timeline, list) else infer_timeline(task_groups),
        "dispatch_actions": actions,
        "recent_events": normalize_events(read_jsonl_files(workspace / "events"), event_display_rules),
        "checkpoints": normalize_checkpoints(read_json_files(workspace / "checkpoints")),
        "entity_grid": entity_grid if isinstance(entity_grid, dict) else infer_entity_grid(task_groups),
        "display_dictionary": display_dictionary,
        "event_display_rules": event_display_rules,
        "domain_extensions": read_json(
            workspace / "domain_extensions.json",
            {
                "enabled": False,
                "description": "用于业务看板扩展字段；核心协议不绑定具体业务。",
                "allowed_sections": [
                    "summary.metrics",
                    "entity_grid",
                    "display_dictionary",
                    "event_display_rules",
                ],
            },
        ),
    }

    freshness = state["freshness"]
    freshness["age"] = format_age(state["generated_at"], now)
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
    output.write_text(
        json.dumps(generate_state(workspace, args.refresh_interval), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(f"wrote {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
