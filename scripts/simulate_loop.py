#!/usr/bin/env python3
"""Simulate future Loop cycles without mutating the source workspace."""
from __future__ import annotations

import argparse
import importlib.util
import json
import shutil
import tempfile
from datetime import timedelta
from pathlib import Path
from typing import Any


SCRIPT_DIR = Path(__file__).resolve().parent


def load_runner():
    path = SCRIPT_DIR / "loop_runner.py"
    spec = importlib.util.spec_from_file_location("loop_runner", path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def simulate(workspace: Path | str, cycles: int, output: Path | str | None = None) -> dict[str, Any]:
    workspace = Path(workspace).resolve()
    runner = load_runner()
    with tempfile.TemporaryDirectory() as tmpdir:
        simulated_workspace = Path(tmpdir) / "workspace"
        shutil.copytree(workspace, simulated_workspace, ignore=shutil.ignore_patterns("dashboard"))
        old_checkpoints = simulated_workspace / "loop" / "checkpoints"
        copied_dashboard = (simulated_workspace / "dashboard").exists()
        copied_loop_checkpoints = old_checkpoints.exists()
        if old_checkpoints.exists():
            shutil.rmtree(old_checkpoints)
        removed_loop_checkpoints = copied_loop_checkpoints and not old_checkpoints.exists()
        now = runner.utc_now()
        results = []
        for _ in range(cycles):
            result = runner.run_cycle(simulated_workspace, dry_run=False, now=now)
            results.append(
                {
                    "iteration": result["iteration"],
                    "loop_status": result["loop_status"],
                    "last_cycle_summary": result["last_cycle_summary"],
                    "health": result["health"],
                }
            )
            now = now + timedelta(seconds=runner.load_config(simulated_workspace).get("interval_seconds", 300))
        simulation = {
            "source_workspace": str(workspace),
            "cycles_requested": cycles,
            "cycles": results,
            "mutates_source_workspace": False,
            "copied_dashboard": copied_dashboard,
            "copied_loop_checkpoints": copied_loop_checkpoints,
            "removed_loop_checkpoints": removed_loop_checkpoints,
        }
    if output:
        output_path = Path(output)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(json.dumps(simulation, ensure_ascii=False, indent=2), encoding="utf-8")
    return simulation


def main() -> int:
    parser = argparse.ArgumentParser(description="Simulate future multi-agent-orchestrator Loop cycles")
    parser.add_argument("workspace", type=Path)
    parser.add_argument("--cycles", type=int, default=10)
    parser.add_argument("--output", type=Path, default=None)
    args = parser.parse_args()
    result = simulate(args.workspace, cycles=args.cycles, output=args.output)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
