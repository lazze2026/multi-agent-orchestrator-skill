#!/usr/bin/env python3
"""Run one workspace-level Loop cycle for multi-agent-orchestrator.

The runner is intentionally conservative: events are authoritative, the queue is
a derived operational view, and business deliverables are never modified.
"""
from __future__ import annotations

import argparse
import json
import time
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any


DEFAULT_CONFIG: dict[str, Any] = {
    "version": "1.0.0",
    "enabled": True,
    "mode": "codex-heartbeat",
    "interval_seconds": 300,
    "auto_advance": {
        "enabled": True,
        "allowed_risks": ["low", "minimal"],
        "allowed_statuses": ["queued", "verifying_ready", "stale_review", "checkpoint_resume_ready"],
        "allowed_safe_actions": [
            "read_only_checks",
            "status_update_to_verifying",
            "status_update_to_running",
            "report_generation",
            "verifier_trigger",
        ],
        "require_task_spec_opt_in": True,
    },
    "stale_detection": {
        "after_minutes": 30,
        "criteria": "no_event_or_heartbeat",
        "heartbeat_event_names": ["worker.heartbeat", "worker.progress", "worker.reported"],
        "exclude_statuses": ["blocked", "needs_human_decision", "cancelled", "done", "failed"],
        "allow_task_spec_override": True,
    },
    "lock_policy": {
        "detect_conflicts": True,
        "allow_request_release": True,
        "mark_expired_after_stale_multiplier": 2,
        "auto_release_expired_locks": False,
        "require_human_decision_for_release": True,
    },
    "guardrails": {
        "max_consecutive_failures": 3,
        "pause_on_lock_conflict_burst": True,
        "pause_on_repeated_verification_failure": True,
        "max_auto_advances_per_cycle": 3,
    },
    "queue_rebuild": {
        "mode": "incremental",
        "allow_full_rebuild_fallback": True,
        "full_rebuild_check_every_n_cycles": 12,
        "snapshot_path": "loop/rebuild/queue.snapshot.state.json",
    },
    "writes": {
        "allow_queue_rebuild": True,
        "allow_dashboard_refresh": True,
        "allow_loop_checkpoints": True,
        "allow_business_deliverable_writes": False,
    },
}


def utc_now() -> datetime:
    return datetime.now(timezone.utc).replace(microsecond=0)


def iso(dt: datetime) -> str:
    return ensure_aware_utc(dt).replace(microsecond=0).isoformat()


def parse_timezone(value: Any) -> timezone:
    if not isinstance(value, str) or value.upper() == "UTC":
        return timezone.utc
    text = value.strip()
    if text in {"Z", "+00:00", "-00:00"}:
        return timezone.utc
    sign = 1
    if text.startswith("-"):
        sign = -1
        text = text[1:]
    elif text.startswith("+"):
        text = text[1:]
    try:
        hours, minutes = text.split(":", 1)
        return timezone(sign * timedelta(hours=int(hours), minutes=int(minutes)))
    except (ValueError, TypeError):
        return timezone.utc


def ensure_aware_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def parse_time(value: Any, default_tz: timezone = timezone.utc) -> datetime | None:
    if not isinstance(value, str) or not value.strip():
        return None
    text = value.strip()
    if " " in text and "T" not in text:
        text = text.replace(" ", "T", 1)
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=default_tz)
    return parsed.astimezone(timezone.utc)


def read_json(path: Path, default: Any) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8-sig"))
    except (FileNotFoundError, json.JSONDecodeError):
        return default


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    try:
        lines = path.read_text(encoding="utf-8-sig").splitlines()
    except FileNotFoundError:
        return rows
    for line in lines:
        if not line.strip():
            continue
        try:
            item = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(item, dict):
            rows.append(item)
    return rows


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows), encoding="utf-8")


def append_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    if not rows:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")


def merge_dict(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    result = deepcopy(base)
    for key, value in override.items():
        if isinstance(result.get(key), dict) and isinstance(value, dict):
            result[key] = merge_dict(result[key], value)
        else:
            result[key] = value
    return result


def load_config(workspace: Path) -> dict[str, Any]:
    return merge_dict(DEFAULT_CONFIG, read_json(workspace / "loop" / "loop_config.json", {}))


def load_queue(workspace: Path) -> list[dict[str, Any]]:
    return read_jsonl(workspace / "queue" / "tasks.jsonl")


def load_all_events(workspace: Path) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    events_dir = workspace / "events"
    if not events_dir.exists():
        return events
    for path in sorted(events_dir.glob("*.jsonl")):
        events.extend(read_jsonl(path))
    return sorted(events, key=lambda event: str(event.get("time", "")))


def event_id(prefix: str, iteration: int, index: int) -> str:
    return f"{prefix}_{iteration:04d}_{index:04d}"


def make_event(
    iteration: int,
    index: int,
    name: str,
    now: datetime,
    summary: str,
    task_id: str | None = None,
    caused_by: str = "loop_cycle",
    **extra: Any,
) -> dict[str, Any]:
    event = {
        "event_id": event_id("loop_evt", iteration, index),
        "time": iso(now),
        "loop_iteration": iteration,
        "agent": "Loop",
        "event": name,
        "summary": summary,
        "caused_by": caused_by,
    }
    if task_id:
        event["task_id"] = task_id
    event.update(extra)
    return event


def dependencies_satisfied(task: dict[str, Any], task_by_id: dict[str, dict[str, Any]]) -> bool:
    for dep_id in task.get("depends_on") or []:
        dep = task_by_id.get(str(dep_id))
        if not dep or dep.get("status") not in {"done", "passed", "partially_completed"}:
            return False
    return True


def has_safe_action(task: dict[str, Any], action: str) -> bool:
    return action in set(task.get("loop_safe_actions") or [])


def verifier_preconditions_satisfied(task: dict[str, Any]) -> bool:
    if not has_safe_action(task, "status_update_to_verifying"):
        return False
    if not has_safe_action(task, "verifier_trigger"):
        return False
    if task.get("verification_running"):
        return False
    if not task.get("verification_plan"):
        return False
    return bool(task.get("deliverables") or task.get("requires_artifacts"))


def eligible_for_running(task: dict[str, Any], config: dict[str, Any], task_by_id: dict[str, dict[str, Any]]) -> bool:
    auto = config["auto_advance"]
    if not auto.get("enabled", True):
        return False
    if task.get("status") not in set(auto.get("allowed_statuses", [])):
        return False
    if auto.get("require_task_spec_opt_in", True) and task.get("loop_autorun") is not True:
        return False
    if task.get("risk", "low") not in set(auto.get("allowed_risks", [])):
        return False
    if not has_safe_action(task, "status_update_to_running"):
        return False
    if task.get("needs_human_decision"):
        return False
    return dependencies_satisfied(task, task_by_id)


def eligible_for_verifying(task: dict[str, Any], config: dict[str, Any], task_by_id: dict[str, dict[str, Any]]) -> bool:
    auto = config["auto_advance"]
    if not auto.get("enabled", True):
        return False
    if task.get("status") != "verifying_ready":
        return False
    if task.get("status") not in set(auto.get("allowed_statuses", [])):
        return False
    if auto.get("require_task_spec_opt_in", True) and task.get("loop_autorun") is not True:
        return False
    if task.get("risk", "low") not in set(auto.get("allowed_risks", [])):
        return False
    if task.get("needs_human_decision"):
        return False
    if not dependencies_satisfied(task, task_by_id):
        return False
    return verifier_preconditions_satisfied(task)


def apply_auto_advances(
    tasks: list[dict[str, Any]],
    config: dict[str, Any],
    iteration: int,
    now: datetime,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    updated = deepcopy(tasks)
    task_by_id = {str(task.get("task_id")): task for task in updated}
    limit = int(config["guardrails"].get("max_auto_advances_per_cycle", 3))
    events: list[dict[str, Any]] = []
    event_index = 10
    for task in updated:
        if len(events) >= limit:
            break
        if eligible_for_verifying(task, config, task_by_id):
            old_status = task.get("status")
            task["status"] = "verifying"
            task["last_observed"] = iso(now)
            task["next"] = "Verifier"
            events.append(
                make_event(
                    iteration,
                    event_index,
                    "loop.verifier_triggered",
                    now,
                    f"Triggered verifier for {task.get('task_id')} after safe-action validation.",
                    task_id=str(task.get("task_id")),
                    caused_by="verifier_preconditions_satisfied",
                    from_status=old_status,
                    to_status="verifying",
                    safe_action="status_update_to_verifying",
                )
            )
            event_index += 1
            continue
        if not eligible_for_running(task, config, task_by_id):
            continue
        old_status = task.get("status")
        task["status"] = "running"
        task["last_observed"] = iso(now)
        task["next"] = task.get("owner") or task.get("next") or "Worker"
        events.append(
            make_event(
                iteration,
                event_index,
                "loop.auto_advance.applied",
                now,
                f"Auto-advanced {task.get('task_id')} from {old_status} to running.",
                task_id=str(task.get("task_id")),
                caused_by="eligible_low_risk_task",
                from_status=old_status,
                to_status="running",
                safe_action="status_update_to_running",
            )
        )
        event_index += 1
    return updated, events


def detect_stale_tasks(
    tasks: list[dict[str, Any]],
    all_events: list[dict[str, Any]],
    config: dict[str, Any],
    iteration: int,
    now: datetime,
) -> list[dict[str, Any]]:
    stale_config = config["stale_detection"]
    default_tz = parse_timezone(config.get("timezone", "UTC"))
    excluded = set(stale_config.get("exclude_statuses", []))
    heartbeat_names = set(stale_config.get("heartbeat_event_names", []))
    events_by_task: dict[str, list[dict[str, Any]]] = {}
    for event in all_events:
        task_id = event.get("task_id")
        if task_id:
            events_by_task.setdefault(str(task_id), []).append(event)

    stale_events: list[dict[str, Any]] = []
    event_index = 30
    for task in tasks:
        status = str(task.get("status", "queued"))
        if status in excluded:
            continue
        task_id = str(task.get("task_id", ""))
        if not task_id:
            continue
        override = task.get("stale_override") if isinstance(task.get("stale_override"), dict) else {}
        threshold_minutes = int(override.get("after_minutes") or stale_config.get("after_minutes", 30))
        threshold = now - timedelta(minutes=threshold_minutes)
        signals = []
        for event in events_by_task.get(task_id, []):
            event_name = str(event.get("event", ""))
            if event_name.startswith("worker.") or event_name in heartbeat_names:
                parsed = parse_time(event.get("time") or event.get("timestamp") or event.get("created_at"), default_tz)
                if parsed:
                    signals.append(parsed)
        last_signal = max(signals) if signals else None
        if last_signal and last_signal >= threshold:
            continue
        stale_events.append(
            make_event(
                iteration,
                event_index,
                "loop.stale.detected",
                now,
                f"Task {task_id} has no heartbeat or progress event within {threshold_minutes} minutes.",
                task_id=task_id,
                caused_by="no_event_or_heartbeat",
                stale_after_minutes=threshold_minutes,
            )
        )
        event_index += 1
    return stale_events


def read_lock_files(workspace: Path) -> list[dict[str, Any]]:
    locks_dir = workspace / "locks"
    if not locks_dir.exists():
        return []
    locks: list[dict[str, Any]] = []
    for path in sorted(locks_dir.glob("*.json")):
        item = read_json(path, None)
        if isinstance(item, dict):
            locks.append(item)
    return locks


def lock_release_requests(
    workspace: Path,
    stale_events: list[dict[str, Any]],
    config: dict[str, Any],
    iteration: int,
    now: datetime,
) -> list[dict[str, Any]]:
    lock_policy = config["lock_policy"]
    if not lock_policy.get("detect_conflicts", True) or not lock_policy.get("allow_request_release", True):
        return []
    stale_task_ids = {str(event.get("task_id")) for event in stale_events if event.get("task_id")}
    requests: list[dict[str, Any]] = []
    event_index = 50
    for lock in read_lock_files(workspace):
        holder_task_id = str(lock.get("holder_task_id") or "")
        if not holder_task_id or holder_task_id not in stale_task_ids:
            continue
        if lock.get("status", "active") != "active":
            continue
        requests.append(
            make_event(
                iteration,
                event_index,
                "lock.release.requested",
                now,
                f"Requested release review for lock {lock.get('lock_id')} held by stale task {holder_task_id}.",
                task_id=holder_task_id,
                caused_by="stale_lock_holder",
                lock_request_release={
                    "enabled": True,
                    "lock_id": lock.get("lock_id"),
                    "resource": lock.get("resource"),
                    "requested_by": "Loop",
                    "requires_decision": True,
                },
            )
        )
        event_index += 1
    return requests


def rebuild_queue(
    workspace: Path,
    tasks: list[dict[str, Any]],
    config: dict[str, Any],
    iteration: int,
    now: datetime,
    dry_run: bool,
) -> dict[str, Any]:
    queue_config = config["queue_rebuild"]
    check_every = int(queue_config.get("full_rebuild_check_every_n_cycles", 12) or 12)
    full_check = check_every > 0 and iteration % check_every == 0
    report = {
        "time": iso(now),
        "iteration": iteration,
        "mode": queue_config.get("mode", "incremental"),
        "validation_mode": "full" if full_check else "incremental",
        "full_rebuild_check": full_check,
        "queue_rebuild_ok": True,
        "events_processed": len(load_all_events(workspace)),
        "warnings": [],
        "snapshot_valid": True,
    }
    if not dry_run:
        write_jsonl(workspace / "queue" / "tasks.jsonl", tasks)
        write_json(workspace / "queue" / "tasks.snapshot.json", tasks)
        write_json(
            workspace / str(queue_config.get("snapshot_path", "loop/rebuild/queue.snapshot.state.json")),
            {
                "schema_version": "1.0.0",
                "queue_snapshot_schema_version": "1.0.0",
                "workspace": str(workspace.resolve()),
                "last_rebuild_event_time": iso(now),
                "task_count": len(tasks),
                "tasks": tasks,
            },
        )
        write_json(workspace / "loop" / "rebuild" / "queue-rebuild-report.json", report)
    return report


def dashboard_state(
    workspace: Path,
    tasks: list[dict[str, Any]],
    loop_summary: dict[str, Any],
    loop_events: list[dict[str, Any]],
    config: dict[str, Any],
    now: datetime,
) -> dict[str, Any]:
    completed = sum(task.get("status") in {"done", "passed"} for task in tasks)
    blocked = sum(task.get("status") in {"blocked", "needs_human_decision", "failed"} for task in tasks)
    running = sum(task.get("status") in {"running", "verifying"} for task in tasks)
    next_run = now + timedelta(seconds=int(config.get("interval_seconds", 300)))
    return {
        "schema_version": "1.4.0",
        "generated_at": iso(now),
        "refresh_interval_seconds": int(config.get("interval_seconds", 300)),
        "read_only": True,
        "project": {"name": workspace.name, "mode": "workspace-loop"},
        "summary": {
            "total_tasks": len(tasks),
            "completed": completed,
            "in_progress": running,
            "blocked": blocked,
            "queued": sum(task.get("status") == "queued" for task in tasks),
        },
        "task_groups": [],
        "agents": [],
        "blockers": [],
        "flow_timeline": [],
        "dispatch_actions": [],
        "recent_events": [],
        "checkpoints": [],
        "loop": {
            "status": "running",
            "last_run_at": iso(now),
            "next_run_at": iso(next_run),
            "iteration": loop_summary["iteration"],
            "paused_reason": "",
            "last_rebuild_status": "ok" if loop_summary["health"]["queue_rebuild_ok"] else "warning",
            "auto_advances_last_cycle": loop_summary["last_cycle_summary"]["auto_advanced"],
            "last_cycle_summary": loop_summary["last_cycle_summary"],
            "health": loop_summary["health"],
            "recent_loop_events": loop_events[-10:],
        },
    }


def run_cycle(workspace: Path | str, dry_run: bool = False, now: datetime | None = None) -> dict[str, Any]:
    started = time.perf_counter()
    workspace = Path(workspace).resolve()
    now = ensure_aware_utc(now or utc_now())
    config = load_config(workspace)
    previous_state = read_json(workspace / "loop" / "loop_state.json", {})
    iteration = int(previous_state.get("iteration", 0)) + 1
    tasks = load_queue(workspace)
    all_events = load_all_events(workspace)
    events: list[dict[str, Any]] = [
        make_event(iteration, 1, "loop.cycle.started", now, "Loop cycle started."),
        make_event(iteration, 2, "loop.state.observed", now, f"Observed {len(tasks)} queued task records."),
    ]
    stale_events = detect_stale_tasks(tasks, all_events, config, iteration, now)
    events.extend(stale_events)
    lock_request_events = lock_release_requests(workspace, stale_events, config, iteration, now)
    events.extend(lock_request_events)
    advanced_tasks, auto_events = apply_auto_advances(tasks, config, iteration, now)
    events.extend(auto_events)
    rebuild_report = rebuild_queue(workspace, advanced_tasks, config, iteration, now, dry_run)
    last_cycle_summary = {
        "stale_detected": len(stale_events),
        "blocked_detected": sum(task.get("status") in {"blocked", "needs_human_decision"} for task in advanced_tasks),
        "auto_advanced": len(auto_events),
        "rebuild_warnings": len(rebuild_report["warnings"]),
        "duration_ms": max(0, int((time.perf_counter() - started) * 1000)),
        "full_rebuild_check": rebuild_report["full_rebuild_check"],
    }
    health = {
        "consecutive_failures": 0,
        "last_failure_reason": "",
        "queue_rebuild_ok": rebuild_report["queue_rebuild_ok"],
        "events_processed": rebuild_report["events_processed"],
    }
    summary = {
        "loop_status": "dry_run" if dry_run else "running",
        "iteration": iteration,
        "last_cycle_summary": last_cycle_summary,
        "health": health,
        "planned_events": events,
    }
    events.append(make_event(iteration, 99, "loop.cycle.completed", now, "Loop cycle completed."))
    if not dry_run:
        append_jsonl(workspace / "events" / "loop-events.jsonl", events)
        write_json(
            workspace / "loop" / "loop_state.json",
            {
                "loop_status": "running",
                "last_run_at": iso(now),
                "next_run_at": iso(now + timedelta(seconds=int(config.get("interval_seconds", 300)))),
                "iteration": iteration,
                "consecutive_failures": 0,
                "last_result": "ok",
                "paused_reason": "",
                "last_checkpoint": f"loop/checkpoints/loop_ckpt_{iteration:04d}.json",
                "last_rebuild_event_time": iso(now),
            },
        )
        write_json(
            workspace / "dashboard" / "state.json",
            dashboard_state(workspace, advanced_tasks, {**summary, "loop_status": "running"}, events, config, now),
        )
        write_json(workspace / "loop" / "checkpoints" / f"loop_ckpt_{iteration:04d}.json", summary)
    return summary


def main() -> int:
    parser = argparse.ArgumentParser(description="Run one multi-agent-orchestrator Loop cycle")
    parser.add_argument("workspace", type=Path)
    parser.add_argument("--dry-run", action="store_true", help="Plan actions without writing files")
    parser.add_argument("--once", action="store_true", help="Execute one bounded cycle and exit")
    args = parser.parse_args()
    result = run_cycle(args.workspace, dry_run=args.dry_run)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
