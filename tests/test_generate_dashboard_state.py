from __future__ import annotations

import importlib.util
import unittest
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
GENERATOR_PATH = ROOT / "scripts" / "generate_dashboard_state.py"


def load_generator():
    spec = importlib.util.spec_from_file_location("generate_dashboard_state", GENERATOR_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


class GenerateDashboardStateTests(unittest.TestCase):
    def setUp(self) -> None:
        self.generator = load_generator()

    def test_format_age_handles_naive_timestamp_as_utc(self) -> None:
        now = datetime(2026, 6, 13, 10, 30, tzinfo=timezone.utc)

        self.assertEqual(self.generator.format_age("2026-06-13T10:00:00", now), "30m 0s")

    def test_parse_time_outputs_schema_utc_iso(self) -> None:
        self.assertEqual(self.generator.parse_time("2026-06-13 10:00:00"), "2026-06-13T10:00:00+00:00")


if __name__ == "__main__":
    unittest.main()
