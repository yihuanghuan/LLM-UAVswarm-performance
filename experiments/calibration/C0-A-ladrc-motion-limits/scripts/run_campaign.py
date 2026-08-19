#!/usr/bin/env python3
"""Resume the complete staged C0-A-prereg-v2 campaign without manual choices."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import subprocess
import sys

from run_trial import REPOSITORY, VENV_PYTHON, ros_environment


ROOT = Path(__file__).resolve().parents[1]
SCHEDULE_PATH = ROOT / "trial_order_v2.json"
RUN_TRIAL = ROOT / "scripts" / "run_trial.py"
EXTRACT = ROOT / "scripts" / "extract_metrics.py"
SELECT = ROOT / "scripts" / "select_candidates.py"
ALGORITHM_CHECK = REPOSITORY / "experiments" / "calibration" / "scripts" / "check_algorithm_freeze.py"
OWNERSHIP_CHECK = REPOSITORY / "experiments" / "calibration" / "scripts" / "check_parameter_ownership.py"
STAGES = (
    "A1_SCREENING", "A1_CONFIRMATION", "A2_SCREENING",
    "A2_CONFIRMATION", "A3_VALIDATION", "SCALE_VALIDATION",
)


def utc_now():
    return datetime.now(timezone.utc).isoformat()


def sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def git_value(*args):
    return subprocess.check_output(["git", *args], cwd=REPOSITORY, text=True).strip()


def write_state(path, state):
    path.write_text(json.dumps(state, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def initialize(artifact_root, state_path):
    artifact_root.mkdir(parents=True, exist_ok=True)
    for directory in ("raw", "metrics", "figures", "logs", "manifests"):
        (artifact_root / directory).mkdir(exist_ok=True)
    if state_path.exists():
        return json.loads(state_path.read_text(encoding="utf-8"))
    state = {
        "calibration_id": "C0-A",
        "protocol_version": "C0-A-prereg-v2",
        "dataset_class": "calibration",
        "campaign_status": "NOT_STARTED",
        "formal_trials_started": False,
        "formal_trials_executed": 0,
        "source_commit": git_value("rev-parse", "HEAD"),
        "branch": git_value("branch", "--show-current"),
        "protocol_sha256": sha256(ROOT / "CALIBRATION_PROTOCOL.md"),
        "schedule_sha256": sha256(SCHEDULE_PATH),
        "artifact_root": str(artifact_root.resolve()),
        "initialized_utc": utc_now(),
        "completed_stages": [],
        "failures": [],
    }
    write_state(state_path, state)
    return state


def active_entries(schedule, stage, state):
    entries = [entry for entry in schedule["entries"] if entry["stage"] == stage]
    if stage == "A1_CONFIRMATION":
        active = set(state["a1_confirmation_mapping"])
        return [entry for entry in entries if entry["candidate_id"] in active]
    if stage == "A2_CONFIRMATION":
        active = set(state["a2_confirmation_mapping"])
        return [entry for entry in entries if entry["candidate_id"] in active]
    return entries


def run_gate_audit(artifact_root, stage):
    commands = (
        [sys.executable, str(ALGORITHM_CHECK)],
        [
            sys.executable, str(OWNERSHIP_CHECK), "--calibration", "C0-A",
            "--baseline-ref", "origin/paper/calibration",
        ],
    )
    records = []
    for command in commands:
        result = subprocess.run(
            command, cwd=REPOSITORY, text=True,
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, check=False,
        )
        records.append({"command": command, "returncode": result.returncode, "output": result.stdout})
        if result.returncode != 0:
            raise RuntimeError(f"post-stage freeze gate failed after {stage}")
    path = artifact_root / "logs" / f"post_{stage.lower()}_freeze_gates.json"
    path.write_text(json.dumps(records, indent=2) + "\n", encoding="utf-8")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--artifact-root", type=Path, required=True)
    parser.add_argument("--initialize-only", action="store_true")
    args = parser.parse_args()
    artifact_root = args.artifact_root.resolve()
    state_path = artifact_root / "campaign_state.json"
    state = initialize(artifact_root, state_path)
    if args.initialize_only:
        print(json.dumps(state, indent=2, sort_keys=True))
        return 0
    preflight_path = artifact_root / "logs" / "preflight_v2.json"
    if not preflight_path.is_file():
        raise SystemExit("formal execution refused: preflight_v2.json is missing")
    preflight = json.loads(preflight_path.read_text(encoding="utf-8"))
    if preflight.get("status") != "PASS" or preflight.get("source_commit") != git_value("rev-parse", "HEAD"):
        raise SystemExit("formal execution refused: preflight is stale or failed")
    schedule = json.loads(SCHEDULE_PATH.read_text(encoding="utf-8"))
    if sha256(SCHEDULE_PATH) != state["schedule_sha256"]:
        raise SystemExit("formal execution refused: schedule hash changed")
    ros_env = ros_environment()
    state["campaign_status"] = "RUNNING"
    write_state(state_path, state)
    for stage in STAGES:
        if stage in state["completed_stages"]:
            continue
        if state.get("campaign_status") in {"NO_ACCEPTABLE_CONFIGURATION", "FREEZE_FAIL"}:
            break
        entries = active_entries(schedule, stage, state)
        for entry in entries:
            trial_dir = artifact_root / "raw" / entry["trial_id"]
            metrics_path = trial_dir / "metrics.json"
            if metrics_path.is_file():
                continue
            if trial_dir.exists():
                manifest_path = trial_dir / "manifest.json"
                if not manifest_path.is_file():
                    raise SystemExit(
                        f"interrupted formal trial {entry['trial_id']} cannot be rerun under the same ID"
                    )
            else:
                command = [
                    str(VENV_PYTHON), str(RUN_TRIAL),
                    "--trial-id", entry["trial_id"],
                    "--state", str(state_path),
                    "--artifact-root", str(artifact_root),
                ]
                trial = subprocess.run(
                    command, cwd=REPOSITORY, text=True,
                    stdout=subprocess.PIPE, stderr=subprocess.STDOUT, check=False,
                )
                (artifact_root / "logs" / "campaign_trials.jsonl").open(
                    "a", encoding="utf-8"
                ).write(json.dumps({
                    "timestamp_utc": utc_now(),
                    "trial_id": entry["trial_id"],
                    "returncode": trial.returncode,
                    "output": trial.stdout,
                }, sort_keys=True) + "\n")
            extraction = subprocess.run(
                [str(VENV_PYTHON), str(EXTRACT), str(trial_dir)],
                cwd=REPOSITORY, env=ros_env, text=True,
                stdout=subprocess.PIPE, stderr=subprocess.STDOUT, check=False,
            )
            if not metrics_path.is_file():
                raise SystemExit(f"metric extractor did not preserve a result for {entry['trial_id']}")
            metrics = json.loads(metrics_path.read_text(encoding="utf-8"))
            state["formal_trials_started"] = True
            state["formal_trials_executed"] += 1
            if not metrics["hard_pass"]:
                state["failures"].append({
                    "trial_id": entry["trial_id"],
                    "hard_failures": metrics["hard_failures"],
                })
            state["last_trial_id"] = entry["trial_id"]
            state["updated_utc"] = utc_now()
            write_state(state_path, state)
            print(json.dumps({
                "stage": stage,
                "completed": state["formal_trials_executed"],
                "trial_id": entry["trial_id"],
                "hard_pass": metrics["hard_pass"],
            }, sort_keys=True), flush=True)
        selection = subprocess.run(
            [
                sys.executable, str(SELECT), "--stage", stage,
                "--artifact-root", str(artifact_root), "--state", str(state_path),
            ],
            cwd=REPOSITORY,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            check=False,
        )
        if selection.returncode != 0:
            raise SystemExit(selection.stdout)
        state = json.loads(state_path.read_text(encoding="utf-8"))
        state["completed_stages"].append(stage)
        write_state(state_path, state)
        run_gate_audit(artifact_root, stage)
        print(selection.stdout, end="", flush=True)
    print(json.dumps({
        "campaign_status": state.get("campaign_status"),
        "formal_trials_executed": state["formal_trials_executed"],
        "completed_stages": state["completed_stages"],
    }, sort_keys=True))
    return 0 if state.get("campaign_status") == "PASS" else 2


if __name__ == "__main__":
    raise SystemExit(main())
