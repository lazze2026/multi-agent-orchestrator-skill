#!/usr/bin/env python3
"""Validate dashboard state.json for the multi-agent-orchestrator skill."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

REQUIRED_FIELDS = ["generated_at", "project", "summary", "task_groups"]
LIST_FIELDS = ["task_groups", "agents", "blockers", "flow_timeline", "dispatch_actions", "recent_events", "checkpoints"]


def validate_state(state: dict[str, Any]) -> list[str]:
    """Validate state.json against the dashboard's minimal schema."""
    errors: list[str] = []
    for field in REQUIRED_FIELDS:
        if field not in state:
            errors.append(f"Missing required field: {field}")
    if state.get("read_only") is not True:
        errors.append("Field read_only must be true")
    if "refresh_interval_seconds" in state and not isinstance(state["refresh_interval_seconds"], int):
        errors.append("Field refresh_interval_seconds must be an integer")
    for field in LIST_FIELDS:
        if field in state and not isinstance(state[field], list):
            errors.append(f"Field {field} must be a list")
    if "project" in state and not isinstance(state["project"], dict):
        errors.append("Field project must be an object")
    if "summary" in state and not isinstance(state["summary"], dict):
        errors.append("Field summary must be an object")
    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate multi-agent dashboard state.json")
    parser.add_argument("state_json", type=Path)
    args = parser.parse_args()
    state = json.loads(args.state_json.read_text(encoding="utf-8-sig"))
    errors = validate_state(state)
    if errors:
        for error in errors:
            print(error)
        return 1
    print("state.json is valid")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())