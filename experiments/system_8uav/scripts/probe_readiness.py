#!/usr/bin/env python3
"""Repeatedly restart the complete stack and test readiness without LLM/missions."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

from run_batch import SCRIPT_DIR, SimulatorSupervisor
from system_common import CONFIG_PATH, REPO_ROOT, load_yaml, write_json


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--batch-id", required=True)
    parser.add_argument("--count", type=int, default=5)
    parser.add_argument("--config", default=str(CONFIG_PATH))
    args = parser.parse_args()
    config_path = Path(args.config).resolve()
    config = load_yaml(config_path)
    results_root = (REPO_ROOT / config["paths"]["results_root"]).resolve()
    batch = results_root / args.batch_id
    px4_root = Path(os.environ.get(
        "PX4_AUTOPILOT_DIR", config["paths"]["px4_root"]))
    outcomes = []
    for index in range(1, args.count + 1):
        attempt = f"attempt_{index:04d}"
        supervisor = SimulatorSupervisor(
            batch / "runtime_logs" / attempt, px4_root, config)
        error = ""
        returncode = 3
        try:
            supervisor.start()
            command = [
                sys.executable, str(SCRIPT_DIR / "run_trial.py"),
                "--task", "task_a_simple", "--trial", str(index),
                "--attempt-id", attempt,
                "--target-execution-index", str(index),
                "--batch-id", args.batch_id, "--phase", "formal",
                "--config", str(config_path),
                "--results-root", str(results_root),
                "--readiness-only", "--no-rosbag",
            ]
            returncode = subprocess.run(
                command, cwd=REPO_ROOT, check=False).returncode
        except Exception as exc:
            error = f"{type(exc).__name__}: {exc}"
        finally:
            try:
                supervisor.stop()
            except Exception as exc:
                error += f"; cleanup={type(exc).__name__}: {exc}"
        outcomes.append({
            "attempt_id": attempt, "returncode": returncode,
            "readiness_success": returncode == 0, "error": error,
        })
        write_json(batch / "readiness_probe_outcomes.json", outcomes)
        print(json.dumps(outcomes[-1], ensure_ascii=False), flush=True)
    successes = sum(row["readiness_success"] for row in outcomes)
    print(f"readiness probe: {successes}/{len(outcomes)}")
    return 0 if successes == len(outcomes) else 2


if __name__ == "__main__":
    raise SystemExit(main())
