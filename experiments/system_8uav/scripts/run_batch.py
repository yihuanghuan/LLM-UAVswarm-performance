#!/usr/bin/env python3
"""Run pilot or block-randomized formal experiment 10 trials."""

from __future__ import annotations

import argparse
import json
import os
import random
import signal
import shutil
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import List

from system_common import (
    CONFIG_PATH,
    REPO_ROOT,
    TASK_NAMES,
    WORKSPACE_ROOT,
    config_checksum,
    load_task,
    load_yaml,
    utc_now,
    write_json,
)


SCRIPT_DIR = Path(__file__).resolve().parent


@dataclass(frozen=True)
class Trial:
    task: str
    trial: int
    phase: str


class SimulatorSupervisor:
    """Own one complete simulator process tree for exactly one trial."""

    def __init__(self, log_dir: Path, px4_root: Path, uav_count: int = 8):
        self.log_dir = log_dir
        self.px4_root = px4_root
        self.uav_count = uav_count
        self.processes: List[tuple[subprocess.Popen, object]] = []

    def start_process(
        self, name: str, command: str, cwd: Path | None = None
    ) -> subprocess.Popen:
        self.log_dir.mkdir(parents=True, exist_ok=True)
        handle = (self.log_dir / f"{name}.log").open("a", encoding="utf-8")
        process = subprocess.Popen(
            ["bash", "-lc", command], cwd=cwd, stdout=handle,
            stderr=subprocess.STDOUT, start_new_session=True)
        self.processes.append((process, handle))
        return process

    def start(self) -> None:
        self.stop()
        self.start_process(
            "micro_xrce_agent", "MicroXRCEAgent udp4 -p 8888")
        self.start_process(
            "px4_gazebo",
            "source Tools/simulation/gazebo-classic/setup_gazebo.bash "
            "$(pwd) $(pwd)/build/px4_sitl_default && "
            f"./Tools/simulation/gazebo-classic/sitl_multiple_run.sh "
            f"-m iris -n {self.uav_count}",
            self.px4_root)
        time.sleep(18)
        ids = ",".join(str(value) for value in range(1, self.uav_count + 1))
        self.start_process(
            "controllers",
            "source /opt/ros/humble/setup.bash && "
            f"source {WORKSPACE_ROOT}/install/setup.bash && "
            f"ros2 launch ladrc_controller swarm_launch.py uav_ids:=[{ids}]")
        time.sleep(18)
        failed = [
            process.pid for process, _ in self.processes
            if process.poll() is not None
        ]
        if failed:
            raise RuntimeError(f"simulator startup process exited: {failed}")

    def stop(self) -> None:
        for process, _ in reversed(self.processes):
            if process.poll() is None:
                try:
                    os.killpg(process.pid, signal.SIGINT)
                except ProcessLookupError:
                    pass
        deadline = time.monotonic() + 15
        for process, handle in reversed(self.processes):
            try:
                process.wait(timeout=max(0.0, deadline - time.monotonic()))
            except subprocess.TimeoutExpired:
                try:
                    os.killpg(process.pid, signal.SIGTERM)
                except ProcessLookupError:
                    pass
                try:
                    process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    try:
                        os.killpg(process.pid, signal.SIGKILL)
                    except ProcessLookupError:
                        pass
            handle.close()
        self.processes.clear()
        time.sleep(3)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--batch-id", required=True)
    parser.add_argument("--phase", choices=["pilot", "formal"], required=True)
    parser.add_argument("--config", default=str(CONFIG_PATH))
    parser.add_argument("--manage-sim", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--task", action="append", choices=TASK_NAMES)
    parser.add_argument("--no-rosbag", action="store_true")
    return parser.parse_args()


def trial_schedule(config: dict, phase: str) -> List[Trial]:
    if phase == "pilot":
        return [Trial(task, 1, phase) for task in TASK_NAMES]
    count = int(config["experiment"]["trial_count"])
    randomizer = random.Random(
        int(config["experiment"]["block_randomization_seed"]))
    trials: List[Trial] = []
    for trial_id in range(1, count + 1):
        block = list(TASK_NAMES)
        randomizer.shuffle(block)
        trials.extend(Trial(task, trial_id, phase) for task in block)
    return trials


def trial_dir(results_root: Path, batch_id: str, trial: Trial) -> Path:
    root = results_root / batch_id
    if trial.phase == "pilot":
        root = root / "pilot"
    return root / "raw" / trial.task / f"trial_{trial.trial:02d}"


def run_trial_command(
    trial: Trial, batch_id: str, config_path: Path,
    results_root: Path, dry_run: bool, no_rosbag: bool,
) -> List[str]:
    command = [
        sys.executable, str(SCRIPT_DIR / "run_trial.py"),
        "--task", trial.task, "--trial", str(trial.trial),
        "--batch-id", batch_id, "--phase", trial.phase,
        "--config", str(config_path), "--results-root", str(results_root),
    ]
    if dry_run:
        command.append("--dry-run")
    if no_rosbag:
        command.append("--no-rosbag")
    return command


def main() -> int:
    args = parse_args()
    config_path = Path(args.config).resolve()
    config = load_yaml(config_path)
    results_root = (
        REPO_ROOT / config["paths"]["results_root"]).resolve()
    selected = trial_schedule(config, args.phase)
    if args.task:
        allowed = set(args.task)
        selected = [trial for trial in selected if trial.task in allowed]
    batch_root = results_root / args.batch_id
    batch_root.mkdir(parents=True, exist_ok=True)
    configuration_root = batch_root / "configuration"
    configuration_root.mkdir(parents=True, exist_ok=True)
    shutil.copy2(config_path, configuration_root / "full_system.yaml")
    for command_path in sorted((SCRIPT_DIR.parent / "commands").glob("*.json")):
        shutil.copy2(command_path, configuration_root / command_path.name)
    metadata = {
        "batch_id": args.batch_id,
        "phase": args.phase,
        "created_at": utc_now(),
        "manage_sim": args.manage_sim,
        "dry_run": args.dry_run,
        "config_checksum": config_checksum(),
        "schedule": [trial.__dict__ for trial in selected],
    }
    write_json(batch_root / f"{args.phase}_batch_plan.json", metadata)
    if args.dry_run:
        for trial in selected:
            result = subprocess.run(
                run_trial_command(
                    trial, args.batch_id, config_path, results_root, True,
                    args.no_rosbag),
                cwd=REPO_ROOT, check=False)
            if result.returncode:
                return result.returncode
        print(json.dumps(metadata, indent=2, ensure_ascii=False))
        return 0

    px4_root = Path(
        os.environ.get("PX4_AUTOPILOT_DIR", config["paths"]["px4_root"]))
    outcomes = []
    for index, trial in enumerate(selected, start=1):
        destination = trial_dir(results_root, args.batch_id, trial)
        if destination.exists() and any(destination.iterdir()):
            if args.resume:
                outcomes.append({
                    **trial.__dict__, "status": "skipped_existing",
                    "path": str(destination)})
                continue
            raise FileExistsError(f"trial already exists: {destination}")
        print(
            f"[{index}/{len(selected)}] {trial.phase} "
            f"{trial.task} trial {trial.trial}", flush=True)
        supervisor = None
        startup_error = ""
        try:
            if args.manage_sim:
                supervisor = SimulatorSupervisor(
                    batch_root / "runtime_logs"
                    / f"{trial.task}_trial_{trial.trial:02d}",
                    px4_root)
                supervisor.start()
            result = subprocess.run(
                run_trial_command(
                    trial, args.batch_id, config_path, results_root, False,
                    args.no_rosbag),
                cwd=REPO_ROOT, check=False)
            returncode = result.returncode
        except Exception as exc:
            startup_error = f"{type(exc).__name__}: {exc}"
            returncode = 3
            destination.mkdir(parents=True, exist_ok=True)
            task_definition = load_task(trial.task)
            write_json(destination / "manifest.json", {
                "experiment_id": config["experiment"]["experiment_id"],
                "batch_id": args.batch_id,
                "task_type": trial.task,
                "trial_id": trial.trial,
                "phase": trial.phase,
                "command_text": task_definition.command_text,
                "llm_model": config["experiment"]["llm_model"],
                "assignment_mode": config["experiment"]["assignment_mode"],
                "avoidance_mode": config["experiment"]["avoidance_mode"],
                "iapf_escape_mode": config["experiment"]["iapf_escape_mode"],
                "iapf_parameters": config["iapf"],
                "motion_styles": [
                    stage.motion_style for stage in task_definition.stages],
                "start_time": utc_now(),
                "end_time": utc_now(),
                "timeout": 0,
                "semantic_success": False,
                "execution_success": False,
                "safety_success": False,
                "overall_success": False,
                "failure_reason": "simulator_startup_failure",
                "rosbag_path": "",
                "exception": startup_error,
                "config_checksum": config_checksum(),
            })
            write_json(destination / "startup_failure.json", {
                "task_type": trial.task, "trial_id": trial.trial,
                "phase": trial.phase, "failure_reason": "simulator_startup_failure",
                "exception": startup_error, "timestamp": utc_now(),
            })
        finally:
            if supervisor:
                supervisor.stop()
        outcomes.append({
            **trial.__dict__, "returncode": returncode,
            "status": "completed" if returncode == 0 else "failed",
            "startup_error": startup_error, "path": str(destination),
        })
        write_json(batch_root / f"{args.phase}_batch_outcomes.json", outcomes)
    failures = sum(row["status"] == "failed" for row in outcomes)
    print(f"batch complete: {len(outcomes)} trials, {failures} failed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
