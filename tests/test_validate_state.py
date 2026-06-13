from __future__ import annotations

import importlib.util
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
VALIDATOR_PATH = ROOT / "scripts" / "validate_state.py"


def load_validator():
    spec = importlib.util.spec_from_file_location("validate_state", VALIDATOR_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


class ValidateStateTests(unittest.TestCase):
    def setUp(self) -> None:
        self.validator = load_validator()

    def valid_state(self) -> dict:
        return {
            "schema_version": "1.4.0",
            "generated_at": "2026-06-13T10:00:00+00:00",
            "read_only": True,
            "project": {"name": "demo"},
            "summary": {},
            "task_groups": [],
            "loop": {
                "status": "running",
                "iteration": 1,
                "last_cycle_summary": {
                    "stale_detected": 0,
                    "blocked_detected": 0,
                    "auto_advanced": 1,
                    "rebuild_warnings": 0,
                    "duration_ms": 12,
                },
                "health": {
                    "consecutive_failures": 0,
                    "last_failure_reason": "",
                    "queue_rebuild_ok": True,
                    "events_processed": 3,
                },
                "recent_loop_events": [],
            },
        }

    def test_accepts_loop_state_schema_1_4_0(self) -> None:
        self.assertEqual(self.validator.validate_state(self.valid_state()), [])

    def test_rejects_unknown_schema_version(self) -> None:
        state = self.valid_state()
        state["schema_version"] = "1.4.0-loop-v1"

        errors = self.validator.validate_state(state)

        self.assertIn("Unsupported schema_version: 1.4.0-loop-v1", errors)

    def test_rejects_invalid_loop_fields(self) -> None:
        state = self.valid_state()
        state["loop"]["iteration"] = "1"
        state["loop"]["health"]["queue_rebuild_ok"] = "yes"

        errors = self.validator.validate_state(state)

        self.assertIn("loop.iteration must be an integer", errors)
        self.assertIn("loop.health.queue_rebuild_ok must be a boolean", errors)


if __name__ == "__main__":
    unittest.main()
