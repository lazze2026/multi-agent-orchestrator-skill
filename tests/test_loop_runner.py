from __future__ import annotations

import importlib.util
import json
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
RUNNER_PATH = ROOT / "scripts" / "loop_runner.py"


def load_runner():
    spec = importlib.util.spec_from_file_location("loop_runner", RUNNER_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


class LoopRunnerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.runner = load_runner()
        self.tmp = tempfile.TemporaryDirectory()
        self.workspace = Path(self.tmp.name)
        (self.workspace / "queue").mkdir()
        (self.workspace / "events").mkdir()
        (self.workspace / "loop").mkdir()
        self.now = datetime(2026, 6, 13, 10, 0, tzinfo=timezone.utc)

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def write_queue(self, *tasks: dict) -> None:
        path = self.workspace / "queue" / "tasks.jsonl"
        path.write_text(
            "".join(json.dumps(task, ensure_ascii=False) + "\n" for task in tasks),
            encoding="utf-8",
        )

    def read_json(self, relative: str) -> dict:
        return json.loads((self.workspace / relative).read_text(encoding="utf-8"))

    def read_jsonl(self, relative: str) -> list[dict]:
        return [
            json.loads(line)
            for line in (self.workspace / relative).read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]

    def test_dry_run_does_not_write_loop_files(self) -> None:
        self.write_queue(
            {
                "task_id": "task_001",
                "status": "queued",
                "risk": "low",
                "loop_autorun": True,
                "loop_safe_actions": ["status_update_to_running"],
                "depends_on": [],
            }
        )

        result = self.runner.run_cycle(self.workspace, dry_run=True, now=self.now)

        self.assertEqual(result["loop_status"], "dry_run")
        self.assertEqual(result["last_cycle_summary"]["auto_advanced"], 1)
        self.assertFalse((self.workspace / "events" / "loop-events.jsonl").exists())
        self.assertFalse((self.workspace / "loop" / "loop_state.json").exists())
        self.assertFalse((self.workspace / "dashboard" / "state.json").exists())

    def test_once_writes_loop_events_queue_dashboard_and_state(self) -> None:
        self.write_queue(
            {
                "task_id": "task_001",
                "owner": "Worker-1",
                "status": "queued",
                "risk": "low",
                "loop_autorun": True,
                "loop_safe_actions": ["status_update_to_running"],
                "depends_on": [],
                "title": "Export remaining records",
            }
        )

        result = self.runner.run_cycle(self.workspace, dry_run=False, now=self.now)

        self.assertEqual(result["loop_status"], "running")
        queue_rows = self.read_jsonl("queue/tasks.jsonl")
        self.assertEqual(queue_rows[0]["status"], "running")
        events = self.read_jsonl("events/loop-events.jsonl")
        event_names = [event["event"] for event in events]
        self.assertIn("loop.cycle.started", event_names)
        self.assertIn("loop.auto_advance.applied", event_names)
        self.assertIn("loop.cycle.completed", event_names)
        loop_state = self.read_json("loop/loop_state.json")
        self.assertEqual(loop_state["iteration"], 1)
        dashboard = self.read_json("dashboard/state.json")
        self.assertEqual(dashboard["loop"]["last_cycle_summary"]["auto_advanced"], 1)
        self.assertTrue(dashboard["loop"]["health"]["queue_rebuild_ok"])

    def test_full_rebuild_validation_runs_on_configured_cycle(self) -> None:
        self.write_queue({"task_id": "task_001", "status": "queued"})
        (self.workspace / "loop" / "loop_state.json").write_text(
            json.dumps({"iteration": 11}, ensure_ascii=False),
            encoding="utf-8",
        )
        (self.workspace / "loop" / "loop_config.json").write_text(
            json.dumps(
                {
                    "queue_rebuild": {
                        "mode": "incremental",
                        "allow_full_rebuild_fallback": True,
                        "full_rebuild_check_every_n_cycles": 12,
                    }
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )

        result = self.runner.run_cycle(self.workspace, dry_run=False, now=self.now)

        self.assertTrue(result["last_cycle_summary"]["full_rebuild_check"])
        report = self.read_json("loop/rebuild/queue-rebuild-report.json")
        self.assertEqual(report["validation_mode"], "full")

    def test_detects_stale_running_task_from_missing_heartbeat(self) -> None:
        self.write_queue({"task_id": "task_001", "status": "running", "owner": "Worker-1"})
        (self.workspace / "events" / "task_001.jsonl").write_text(
            json.dumps(
                {
                    "event_id": "evt_001",
                    "time": "2026-06-13T09:00:00+00:00",
                    "task_id": "task_001",
                    "agent": "Worker-1",
                    "event": "worker.started",
                },
                ensure_ascii=False,
            )
            + "\n",
            encoding="utf-8",
        )

        result = self.runner.run_cycle(self.workspace, dry_run=False, now=self.now)

        self.assertEqual(result["last_cycle_summary"]["stale_detected"], 1)
        events = self.read_jsonl("events/loop-events.jsonl")
        self.assertIn("loop.stale.detected", [event["event"] for event in events])

    def test_status_update_to_verifying_requires_safe_action(self) -> None:
        self.write_queue(
            {
                "task_id": "task_001",
                "status": "verifying_ready",
                "risk": "low",
                "loop_autorun": True,
                "loop_safe_actions": ["status_update_to_verifying", "verifier_trigger"],
                "deliverables": ["output/result.json"],
                "verification_plan": "reports/verification.md",
            }
        )

        result = self.runner.run_cycle(self.workspace, dry_run=False, now=self.now)

        self.assertEqual(result["last_cycle_summary"]["auto_advanced"], 1)
        queue_rows = self.read_jsonl("queue/tasks.jsonl")
        self.assertEqual(queue_rows[0]["status"], "verifying")
        events = self.read_jsonl("events/loop-events.jsonl")
        self.assertIn("loop.verifier_triggered", [event["event"] for event in events])

    def test_stale_lock_holder_requests_release_without_releasing_lock(self) -> None:
        (self.workspace / "locks").mkdir()
        self.write_queue({"task_id": "task_001", "status": "running", "owner": "Worker-1"})
        (self.workspace / "events" / "task_001.jsonl").write_text(
            json.dumps(
                {
                    "event_id": "evt_001",
                    "time": "2026-06-13T08:30:00+00:00",
                    "task_id": "task_001",
                    "agent": "Worker-1",
                    "event": "worker.started",
                },
                ensure_ascii=False,
            )
            + "\n",
            encoding="utf-8",
        )
        lock_path = self.workspace / "locks" / "lock_backend_config_write.json"
        lock_path.write_text(
            json.dumps(
                {
                    "lock_id": "lock_backend_config_write",
                    "resource": "backend/config.py",
                    "lock_type": "write",
                    "holder_task_id": "task_001",
                    "holder": "Worker-1",
                    "status": "active",
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )

        self.runner.run_cycle(self.workspace, dry_run=False, now=self.now)

        events = self.read_jsonl("events/loop-events.jsonl")
        self.assertIn("lock.release.requested", [event["event"] for event in events])
        lock = self.read_json("locks/lock_backend_config_write.json")
        self.assertEqual(lock["status"], "active")


if __name__ == "__main__":
    unittest.main()
