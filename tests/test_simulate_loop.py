from __future__ import annotations

import importlib.util
import json
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SIMULATOR_PATH = ROOT / "scripts" / "simulate_loop.py"


def load_simulator():
    spec = importlib.util.spec_from_file_location("simulate_loop", SIMULATOR_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


class LoopSimulatorTests(unittest.TestCase):
    def setUp(self) -> None:
        self.simulator = load_simulator()
        self.tmp = tempfile.TemporaryDirectory()
        self.workspace = Path(self.tmp.name) / "workspace"
        (self.workspace / "queue").mkdir(parents=True)
        (self.workspace / "events").mkdir()
        (self.workspace / "loop").mkdir()
        (self.workspace / "loop" / "checkpoints").mkdir()
        (self.workspace / "loop" / "checkpoints" / "old.json").write_text("{}", encoding="utf-8")
        (self.workspace / "dashboard").mkdir()
        (self.workspace / "dashboard" / "state.json").write_text("{}", encoding="utf-8")
        (self.workspace / "queue" / "tasks.jsonl").write_text(
            json.dumps(
                {
                    "task_id": "task_001",
                    "status": "queued",
                    "risk": "low",
                    "loop_autorun": True,
                    "loop_safe_actions": ["status_update_to_running"],
                    "depends_on": [],
                },
                ensure_ascii=False,
            )
            + "\n",
            encoding="utf-8",
        )

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_simulator_outputs_cycles_without_mutating_source_workspace(self) -> None:
        output = Path(self.tmp.name) / "simulation.json"

        result = self.simulator.simulate(self.workspace, cycles=2, output=output)

        self.assertEqual(len(result["cycles"]), 2)
        self.assertEqual(result["cycles"][0]["last_cycle_summary"]["auto_advanced"], 1)
        self.assertTrue(output.exists())
        original_queue = (self.workspace / "queue" / "tasks.jsonl").read_text(encoding="utf-8")
        self.assertIn('"status": "queued"', original_queue)
        self.assertFalse((self.workspace / "events" / "loop-events.jsonl").exists())
        self.assertFalse(result["copied_dashboard"])
        self.assertFalse(result["copied_loop_checkpoints"])


if __name__ == "__main__":
    unittest.main()
