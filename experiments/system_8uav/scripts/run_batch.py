#!/usr/bin/env python3
"""Run managed experiment-10 attempts until every task has its execution quota."""

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
from typing import Any, Dict, List

from system_common import (
    CONFIG_PATH, REPO_ROOT, TASK_NAMES, WORKSPACE_ROOT, config_checksum,
    load_task, load_yaml, utc_now, write_json,
)

SCRIPT_DIR = Path(__file__).resolve().parent


@dataclass(frozen=True)
class Trial:
    task: str
    trial: int
    phase: str


def trial_schedule(config: dict, phase: str):
    """Compatibility view of the deterministic target schedule."""
    rows = initial_schedule(config, phase, TASK_NAMES)
    return [
        Trial(row["task_type"], row["target_execution_index"], phase)
        for row in rows
    ]


class SimulatorSupervisor:
    """Own one complete simulator process tree for exactly one attempt."""

    def __init__(self, log_dir: Path, px4_root: Path, config: dict):
        self.log_dir = log_dir
        self.px4_root = px4_root
        self.config = config
        self.processes: List[tuple[subprocess.Popen, object]] = []

    @staticmethod
    def _stack_processes_present():
        checks = [
            ["pgrep", "-x", "MicroXRCEAgent"],
            ["pgrep", "-x", "gzserver"],
            ["pgrep", "-x", "px4"],
            ["pgrep", "-f", "[l]adrc_position_controller_node"],
            ["pgrep", "-f", "[r]os2 launch ladrc_controller swarm_launch.py"],
        ]
        return any(
            subprocess.run(
                command, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                check=False).returncode == 0
            for command in checks)

    @classmethod
    def cleanup_stale_stack(cls):
        """Stop only processes belonging to the managed 8-UAV stack."""
        patterns = [
            (["pkill", "-INT", "-x"], "px4"),
            (["pkill", "-INT", "-x"], "gzclient"),
            (["pkill", "-INT", "-x"], "gzserver"),
            (["pkill", "-INT", "-x"], "MicroXRCEAgent"),
            (["pkill", "-INT", "-f"], "[l]adrc_position_controller_node"),
            (["pkill", "-INT", "-f"],
             "[r]os2 launch ladrc_controller swarm_launch.py"),
        ]
        for prefix, pattern in patterns:
            subprocess.run(
                [*prefix, pattern], stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL, check=False)
        deadline = time.monotonic() + 15
        while cls._stack_processes_present() and time.monotonic() < deadline:
            time.sleep(0.25)
        if cls._stack_processes_present():
            for prefix, pattern in patterns:
                force = [value.replace("-INT", "-TERM") for value in prefix]
                subprocess.run(
                    [*force, pattern], stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL, check=False)
            time.sleep(2)
        if cls._stack_processes_present():
            raise RuntimeError("managed stack processes survived cleanup")

    @staticmethod
    def _px4_count():
        result = subprocess.run(
            ["pgrep", "-x", "px4"], text=True, stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL, check=False)
        return len(result.stdout.splitlines()) if result.returncode == 0 else 0

    def start_process(self, name: str, command: str, cwd=None):
        self.log_dir.mkdir(parents=True, exist_ok=True)
        handle = (self.log_dir / f"{name}.log").open("a", encoding="utf-8")
        process = subprocess.Popen(
            ["bash", "-lc", command], cwd=cwd, stdout=handle,
            stderr=subprocess.STDOUT, start_new_session=True)
        self.processes.append((process, handle))
        return process

    def start(self):
        self.stop()
        self.cleanup_stale_stack()
        experiment = self.config["experiment"]
        ids = ",".join(str(value) for value in experiment["uav_ids"])
        self.start_process("micro_xrce_agent", "MicroXRCEAgent udp4 -p 8888")
        time.sleep(1)
        headless_bin = SCRIPT_DIR / "headless_bin"
        self.start_process(
            "px4_gazebo",
            f"export PATH={headless_bin}:/usr/bin:/bin:/usr/local/bin:$PATH && "
            "source Tools/simulation/gazebo-classic/setup_gazebo.bash "
            "$(pwd) $(pwd)/build/px4_sitl_default && "
            f"./Tools/simulation/gazebo-classic/sitl_multiple_run.sh "
            f"-m iris -n {len(experiment['uav_ids'])}",
            self.px4_root)
        deadline = time.monotonic() + float(
            experiment["stack_start_timeout"])
        while time.monotonic() < deadline:
            if self._px4_count() == len(experiment["uav_ids"]):
                break
            if self.processes[-1][0].poll() is not None:
                raise RuntimeError("PX4/Gazebo launcher exited during startup")
            time.sleep(0.5)
        else:
            raise RuntimeError(
                f"PX4 startup count {self._px4_count()}/"
                f"{len(experiment['uav_ids'])}")
        time.sleep(5)
        self.start_process(
            "controllers",
            "source /opt/ros/humble/setup.bash && "
            f"source {WORKSPACE_ROOT}/install/setup.bash && "
            f"ros2 launch ladrc_controller swarm_launch.py uav_ids:=[{ids}] "
            f"avoidance_mode:={experiment['avoidance_mode']} "
            f"iapf_escape_mode:={experiment['iapf_escape_mode']} "
            f"hover_position_enter_tolerance:={experiment['stable_position_enter']} "
            f"hover_velocity_enter_tolerance:={experiment['stable_speed_enter']} "
            f"hover_position_exit_tolerance:={experiment['stable_position_exit']} "
            f"hover_velocity_exit_tolerance:={experiment['stable_speed_exit']} "
            f"hover_stable_hold_time:={experiment['stable_hold_time']}")
        time.sleep(8)
        failed = [p.pid for p, _ in self.processes if p.poll() is not None]
        if failed:
            raise RuntimeError(f"simulator startup process exited: {failed}")

    def stop(self):
        for process, _ in reversed(self.processes):
            try:
                os.killpg(process.pid, signal.SIGINT)
            except ProcessLookupError:
                pass
        deadline = time.monotonic() + 15
        for process, handle in reversed(self.processes):
            try:
                process.wait(timeout=max(0.0, deadline - time.monotonic()))
            except subprocess.TimeoutExpired:
                for sig in (signal.SIGTERM, signal.SIGKILL):
                    try:
                        os.killpg(process.pid, sig)
                        process.wait(timeout=5)
                        break
                    except (ProcessLookupError, subprocess.TimeoutExpired):
                        continue
            handle.close()
        self.processes.clear()
        self.cleanup_stale_stack()
        time.sleep(float(
            self.config["experiment"].get("stack_cooldown_seconds", 5.0)))


def parse_args():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--batch-id", required=True)
    parser.add_argument("--phase", choices=["pilot", "formal"], required=True)
    parser.add_argument("--config", default=str(CONFIG_PATH))
    parser.add_argument("--manage-sim", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--task", action="append", choices=TASK_NAMES)
    parser.add_argument("--no-rosbag", action="store_true")
    parser.add_argument("--max-attempts", type=int, default=0)
    return parser.parse_args()


def initial_schedule(config: dict, phase: str, selected_tasks) -> List[Dict[str, Any]]:
    count = 1 if phase == "pilot" else int(config["experiment"]["trial_count"])
    rng = random.Random(int(config["experiment"]["block_randomization_seed"]))
    rows = []
    for target_index in range(1, count + 1):
        block = list(selected_tasks)
        rng.shuffle(block)
        for task in block:
            rows.append({
                "task_type": task,
                "target_execution_index": target_index,
                "replacement_for": "",
                "randomization_seed": int(
                    config["experiment"]["block_randomization_seed"]),
            })
    return rows


def assign_attempt_ids(rows, start=1):
    for number, row in enumerate(rows, start=start):
        row["attempt_id"] = f"attempt_{number:04d}"
        row["run_order"] = number
    return rows


def trial_command(row, args, config_path, results_root):
    command = [
        sys.executable, str(SCRIPT_DIR / "run_trial.py"),
        "--task", row["task_type"],
        "--trial", str(row["target_execution_index"]),
        "--attempt-id", row["attempt_id"],
        "--target-execution-index", str(row["target_execution_index"]),
        "--replacement-for", row.get("replacement_for", ""),
        "--batch-id", args.batch_id, "--phase", args.phase,
        "--config", str(config_path), "--results-root", str(results_root),
    ]
    if args.dry_run:
        command.append("--dry-run")
    if args.no_rosbag:
        command.append("--no-rosbag")
    return command


def main():
    args = parse_args()
    config_path = Path(args.config).resolve()
    config = load_yaml(config_path)
    results_root = (REPO_ROOT / config["paths"]["results_root"]).resolve()
    batch_root = results_root / args.batch_id
    batch_root.mkdir(parents=True, exist_ok=True)
    config_root = batch_root / "configuration"
    config_root.mkdir(parents=True, exist_ok=True)
    shutil.copy2(config_path, config_root / "full_system.yaml")
    for path in sorted((SCRIPT_DIR.parent / "commands").glob("*.json")):
        shutil.copy2(path, config_root / path.name)

    tasks = [task for task in TASK_NAMES if not args.task or task in args.task]
    plan_path = batch_root / f"{args.phase}_batch_plan.json"
    outcomes_path = batch_root / f"{args.phase}_batch_outcomes.json"
    if plan_path.exists():
        if not args.resume:
            raise FileExistsError(f"batch plan already exists: {plan_path}")
        plan = json.loads(plan_path.read_text(encoding="utf-8"))
        schedule = plan["schedule"]
        outcomes = (
            json.loads(outcomes_path.read_text(encoding="utf-8"))
            if outcomes_path.exists() else [])
    else:
        schedule = assign_attempt_ids(initial_schedule(config, args.phase, tasks))
        outcomes = []
        plan = {
            "batch_id": args.batch_id, "phase": args.phase,
            "created_at": utc_now(), "manage_sim": args.manage_sim,
            "dry_run": args.dry_run, "config_checksum": config_checksum(),
            "randomization_seed": int(
                config["experiment"]["block_randomization_seed"]),
            "schedule": schedule,
        }
        write_json(plan_path, plan)

    if args.dry_run:
        for row in schedule:
            result = subprocess.run(
                trial_command(row, args, config_path, results_root),
                cwd=REPO_ROOT, check=False)
            if result.returncode:
                return result.returncode
        print(json.dumps(plan, indent=2, ensure_ascii=False))
        return 0

    raw_root = batch_root / ("pilot/raw" if args.phase == "pilot" else "raw")
    completed_ids = {row["attempt_id"] for row in outcomes}
    if args.resume:
        orphaned = [
            row for row in schedule
            if row["attempt_id"] not in completed_ids
            and (batch_root / "runtime_logs" / row["attempt_id"]).exists()
        ]
        for row in orphaned:
            destination = raw_root / row["task_type"] / row["attempt_id"]
            destination.mkdir(parents=True, exist_ok=True)
            write_json(destination / "manifest.json", {
                "experiment_id": config["experiment"]["experiment_id"],
                "batch_id": args.batch_id, "task_type": row["task_type"],
                "attempt_id": row["attempt_id"], "trial_id": None,
                "target_execution_index": row["target_execution_index"],
                "replacement_for": row.get("replacement_for", ""),
                "phase": args.phase, "entered_execution": False,
                "semantic_success": False, "execution_success": False,
                "safety_success": False, "overall_success": False,
                "failure_reason": "interrupted_startup",
                "start_time": utc_now(), "end_time": utc_now(),
                "config_checksum": config_checksum(),
            })
            outcomes.append({
                **row, "returncode": 130, "entered_execution": False,
                "status": "failed", "failure_reason": "interrupted_startup",
                "path": str(destination),
            })
            replacement = assign_attempt_ids([{
                "task_type": row["task_type"],
                "target_execution_index": row["target_execution_index"],
                "replacement_for": row["attempt_id"],
                "randomization_seed": int(
                    config["experiment"]["block_randomization_seed"]),
            }], len(schedule) + 1)[0]
            schedule.append(replacement)
            plan["schedule"] = schedule
        if orphaned:
            write_json(plan_path, plan)
            write_json(outcomes_path, outcomes)
    completed_ids = {row["attempt_id"] for row in outcomes}
    queue = [row for row in schedule if row["attempt_id"] not in completed_ids]
    for outcome in outcomes:
        actual = raw_root / outcome["task_type"] / outcome["attempt_id"]
        outcome["path"] = str(actual)
        manifest_path = actual / "manifest.json"
        if manifest_path.exists():
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            outcome["entered_execution"] = bool(
                manifest.get("entered_execution"))
            outcome["failure_reason"] = manifest.get("failure_reason", "")
    if outcomes:
        write_json(outcomes_path, outcomes)
    px4_root = Path(os.environ.get(
        "PX4_AUTOPILOT_DIR", config["paths"]["px4_root"]))
    while queue:
        row = queue.pop(0)
        if args.max_attempts and len(outcomes) >= args.max_attempts:
            raise RuntimeError("max_attempts reached before execution quota")
        attempt_id = row["attempt_id"]
        task = row["task_type"]
        destination = raw_root / task / attempt_id
        print(f"[{len(outcomes) + 1}] {attempt_id} {task} "
              f"target={row['target_execution_index']}", flush=True)
        supervisor = None
        startup_error = ""
        try:
            if args.manage_sim:
                supervisor = SimulatorSupervisor(
                    batch_root / "runtime_logs" / attempt_id, px4_root, config)
                supervisor.start()
            result = subprocess.run(
                trial_command(row, args, config_path, results_root),
                cwd=REPO_ROOT, check=False)
            returncode = result.returncode
        except Exception as exc:
            returncode = 3
            startup_error = f"{type(exc).__name__}: {exc}"
            destination.mkdir(parents=True, exist_ok=True)
            task_definition = load_task(task)
            write_json(destination / "manifest.json", {
                "experiment_id": config["experiment"]["experiment_id"],
                "batch_id": args.batch_id, "task_type": task,
                "attempt_id": attempt_id, "trial_id": None,
                "target_execution_index": row["target_execution_index"],
                "replacement_for": row.get("replacement_for", ""),
                "phase": args.phase, "command_text": task_definition.command_text,
                "llm_model": config["experiment"]["llm_model"],
                "entered_execution": False, "semantic_success": False,
                "execution_success": False, "safety_success": False,
                "overall_success": False,
                "failure_reason": "simulator_startup_failure",
                "exception": startup_error, "start_time": utc_now(),
                "end_time": utc_now(), "config_checksum": config_checksum(),
            })
        finally:
            if supervisor:
                supervisor.stop()

        manifest_path = destination / "manifest.json"
        manifest = (
            json.loads(manifest_path.read_text(encoding="utf-8"))
            if manifest_path.exists() else {})
        entered = bool(manifest.get("entered_execution"))
        outcome = {
            **row, "returncode": returncode, "entered_execution": entered,
            "status": "completed" if returncode == 0 else "failed",
            "failure_reason": manifest.get("failure_reason", startup_error),
            "path": str(destination),
        }
        outcomes.append(outcome)
        if not entered:
            replacement = assign_attempt_ids([{
                "task_type": task,
                "target_execution_index": row["target_execution_index"],
                "replacement_for": attempt_id,
                "randomization_seed": int(
                    config["experiment"]["block_randomization_seed"]),
            }], len(schedule) + 1)[0]
            schedule.append(replacement)
            queue.append(replacement)
            plan["schedule"] = schedule
            write_json(plan_path, plan)
        write_json(outcomes_path, outcomes)

    counts = {
        task: sum(
            row["task_type"] == task and row["entered_execution"]
            for row in outcomes)
        for task in tasks
    }
    print(f"batch complete: attempts={len(outcomes)}, execution_counts={counts}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
