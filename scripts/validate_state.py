#!/usr/bin/env python3
"""Validate dashboard state.json for the multi-agent-orchestrator skill."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

REQUIRED_FIELDS = ["generated_at", "project", "summary", "task_groups"]
LIST_FIELDS = [
    "task_groups",
    "agents",
    "blockers",
    "flow_timeline",
    "dispatch_actions",
    "recent_events",
    "checkpoints",
    "event_display_rules",
]
OPTIONAL_OBJECT_FIELDS = ["freshness", "policy", "entity_grid", "display_dictionary", "domain_extensions"]


def validate_metric(metric: dict[str, Any], index: int) -> list[str]:
    errors: list[str] = []
    if not isinstance(metric.get("id"), str):
        errors.append(f"summary.metrics[{index}].id must be a string")
    if not isinstance(metric.get("label"), str):
        errors.append(f"summary.metrics[{index}].label must be a string")
    if "value" not in metric:
        errors.append(f"summary.metrics[{index}].value is required")
    return errors


def validate_entity_grid(entity_grid: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    for field in ["title", "entity_type", "columns", "rows"]:
        if field not in entity_grid:
            errors.append(f"entity_grid missing field: {field}")
    if "columns" in entity_grid and not isinstance(entity_grid["columns"], list):
        errors.append("entity_grid.columns must be a list")
    if "rows" in entity_grid and not isinstance(entity_grid["rows"], list):
        errors.append("entity_grid.rows must be a list")
    return errors


def validate_state(state: dict[str, Any]) -> list[str]:
    """Validate state.json against the dashboard schema."""
    errors: list[str] = []
    for field in REQUIRED_FIELDS:
        if field not in state:
            errors.append(f"Missing required field: {field}")
    if state.get("read_only") is not True:
        errors.append("Field read_only must be true")
    if "refresh_interval_seconds" in state and not isinstance(state["refresh_interval_seconds"], int):
        errors.append("Field refresh_interval_seconds must be an integer")
    if "schema_version" in state and not isinstance(state["schema_version"], str):
        errors.append("Field schema_version must be a string")
    for field in LIST_FIELDS:
        if field in state and not isinstance(state[field], list):
            errors.append(f"Field {field} must be a list")
    if "project" in state and not isinstance(state["project"], dict):
        errors.append("Field project must be an object")
    if "summary" in state and not isinstance(state["summary"], dict):
        errors.append("Field summary must be an object")
    for field in OPTIONAL_OBJECT_FIELDS:
        if field in state and not isinstance(state[field], dict):
            errors.append(f"Field {field} must be an object")

    summary = state.get("summary")
    if isinstance(summary, dict) and "metrics" in summary:
        if not isinstance(summary["metrics"], list):
            errors.append("Field summary.metrics must be a list")
        else:
            for index, metric in enumerate(summary["metrics"]):
                if not isinstance(metric, dict):
                    errors.append(f"summary.metrics[{index}] must be an object")
                    continue
                errors.extend(validate_metric(metric, index))

    entity_grid = state.get("entity_grid")
    if isinstance(entity_grid, dict):
        errors.extend(validate_entity_grid(entity_grid))

    display_dictionary = state.get("display_dictionary")
    if isinstance(display_dictionary, dict):
        for key in ["status", "risk", "phase"]:
            if key in display_dictionary and not isinstance(display_dictionary[key], dict):
                errors.append(f"display_dictionary.{key} must be an object")

    event_display_rules = state.get("event_display_rules")
    if isinstance(event_display_rules, list):
        for index, rule in enumerate(event_display_rules):
            if not isinstance(rule, dict):
                errors.append(f"event_display_rules[{index}] must be an object")
                continue
            if "pattern" not in rule or not isinstance(rule["pattern"], str):
                errors.append(f"event_display_rules[{index}].pattern must be a string")
            if "label" not in rule or not isinstance(rule["label"], str):
                errors.append(f"event_display_rules[{index}].label must be a string")

    domain_extensions = state.get("domain_extensions")
    if isinstance(domain_extensions, dict) and "allowed_sections" in domain_extensions:
        if not isinstance(domain_extensions["allowed_sections"], list):
            errors.append("domain_extensions.allowed_sections must be a list")

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
