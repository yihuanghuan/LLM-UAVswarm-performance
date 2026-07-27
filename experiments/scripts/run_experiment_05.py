#!/usr/bin/env python3
"""Run experiment 05 with an independent PX4/Gazebo cold start per trial."""

from __future__ import annotations

import argparse
import json
import os
import random
import shutil
import signal
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, TextIO


REPO_ROOT = Path(__file__).resolve().parents[2]
WORKSPACE_ROOT = REPO_ROOT.parents[1]
PX4_ROOT = Path(os.environ.get("PX4_AUTOPILOT_ROOT", "/home/yihuang/PX4-Autopilot"))
PROFILES = ["step", "linear", "trapezoidal", "minimum_jerk"]
SEED = 20260727
TARGETS = {
    1: (11.23606798, 5.19577393, 5.0),
    2: (6.76393202, 6.64885899, 5.0),
    3: (14.0, 9.0, 5.0),
    4: (6.76393202, 11.35114101, 5.0),
    5: (11.23606798, 12.80422607, 5.0),
}
TOPICS = [
    *(f"/uav{uid}/{suffix}" for uid in range(1, 6)
      for suffix in ("swarm_command", "status", "odom", "trajectory_metrics")),
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--output-dir",
        default=str(REPO_ROOT / "experiments/results/experiments_05"),
    )
    parser.add_argument("--repeats", type=int, default=3)
    parser.add_argument("--profiles", nargs="+", choices=PROFILES, default=PROFILES)
    parser.add_argument("--smoke", action="store_true")
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--startup-timeout", type=float, default=100.0)
    return parser.parse_args()


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def process_is_running(pattern: str) -> bool:
    result = subprocess.run(
        ["pgrep", "-f", pattern], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
    )
    return result.returncode == 0


def ensure_environment() -> None:
    required = {
        "ros2": shutil.which("ros2"),
        "MicroXRCEAgent": shutil.which("MicroXRCEAgent"),
    }
    missing = [name for name, path in required.items() if path is None]
    if missing:
        raise RuntimeError(f"missing commands: {', '.join(missing)}")
    if not (PX4_ROOT / "build/px4_sitl_default/bin/px4").is_file():
        raise RuntimeError(f"PX4 SITL build is missing under {PX4_ROOT}")
    if not (WORKSPACE_ROOT / "install/setup.bash").is_file():
        raise RuntimeError("workspace install/setup.bash is missing; build first")
    conflicts = [
        pattern
        for pattern in (
            "[p]x4 -i",
            "[g]zserver",
            "[M]icroXRCEAgent udp4",
            "ladrc_position_controller_node",
        )
        if process_is_running(pattern)
    ]
    if conflicts:
        raise RuntimeError(
            "refusing to cold-start while experiment processes are already running: "
            + ", ".join(conflicts)
        )


class ManagedProcess:
    def __init__(
        self,
        name: str,
        command: List[str],
        log_path: Path,
        env: Dict[str, str] | None = None,
    ):
        self.name = name
        log_path.parent.mkdir(parents=True, exist_ok=True)
        self.log_handle: TextIO = log_path.open("w", encoding="utf-8")
        self.process = subprocess.Popen(
            command,
            cwd=REPO_ROOT,
            stdout=self.log_handle,
            stderr=subprocess.STDOUT,
            env=env,
            start_new_session=True,
            text=True,
        )

    def stop(self, interrupt: bool = False, timeout: float = 12.0) -> None:
        if self.process.poll() is None:
            os.killpg(
                self.process.pid,
                signal.SIGINT if interrupt else signal.SIGTERM,
            )
            try:
                self.process.wait(timeout=timeout)
            except subprocess.TimeoutExpired:
                os.killpg(self.process.pid, signal.SIGKILL)
                self.process.wait(timeout=5.0)
        self.log_handle.close()


def wait_for_topics(required: List[str], timeout: float) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        result = subprocess.run(
            ["ros2", "topic", "list"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        topics = set(result.stdout.splitlines())
        if all(topic in topics for topic in required):
            return
        time.sleep(2.0)
    raise TimeoutError(f"topics not discovered: {required}")


def run_trial(profile: str, repeat: int, output_dir: Path, timeout: float) -> None:
    trial_id = f"{profile}_r{repeat:02d}"
    trial_dir = output_dir / "trials" / trial_id
    if trial_dir.exists():
        raise FileExistsError(f"will not overwrite existing trial: {trial_dir}")
    trial_dir.mkdir(parents=True)
    processes: List[ManagedProcess] = []
    env = os.environ.copy()
    headless_path = REPO_ROOT / "experiments/scripts/headless"
    env["PATH"] = f"{headless_path}:{env['PATH']}"

    try:
        subprocess.run(["ros2", "daemon", "stop"], check=False, timeout=10)
        processes.append(
            ManagedProcess(
                "xrce",
                ["MicroXRCEAgent", "udp4", "-p", "8888"],
                trial_dir / "xrce.log",
                env,
            )
        )
        time.sleep(1.0)
        processes.append(
            ManagedProcess(
                "sitl",
                [
                    "bash",
                    str(PX4_ROOT / "Tools/simulation/gazebo-classic/sitl_multiple_run.sh"),
                    "-m",
                    "iris",
                    "-n",
                    "5",
                ],
                trial_dir / "sitl.log",
                env,
            )
        )
        wait_for_topics(
            [f"/px4_{uid}/fmu/out/vehicle_odometry" for uid in range(1, 6)],
            timeout,
        )
        processes.append(
            ManagedProcess(
                "controller",
                [
                    "ros2",
                    "launch",
                    "ladrc_controller",
                    "swarm_launch.py",
                    "uav_ids:=[1,2,3,4,5]",
                    f"trajectory_profile:={profile}",
                    "enable_iapf_accel_feedforward:=false",
                ],
                trial_dir / "controller.log",
                env,
            )
        )
        wait_for_topics(
            [f"/uav{uid}/swarm_command" for uid in range(1, 6)],
            timeout,
        )
        # Controller state machine needs 13 seconds after node construction.
        time.sleep(16.0)

        bag_dir = trial_dir / "rosbag"
        processes.append(
            ManagedProcess(
                "rosbag",
                [
                    "ros2",
                    "bag",
                    "record",
                    "-o",
                    str(bag_dir),
                    *TOPICS,
                ],
                trial_dir / "rosbag.log",
                env,
            )
        )
        time.sleep(2.0)
        subprocess.run(
            [
                sys.executable,
                str(REPO_ROOT / "experiments/scripts/experiment_05_trial.py"),
                "--profile",
                profile,
                "--trial-id",
                trial_id,
                "--output",
                str(trial_dir / "trial_status.json"),
            ],
            check=True,
            env=env,
            timeout=50,
        )
        processes[-1].stop(interrupt=True)
        processes.pop()
        status = json.loads(
            (trial_dir / "trial_status.json").read_text(encoding="utf-8")
        )
        missing = [
            uav_id
            for uav_id, data in status["uavs"].items()
            if data["last_elapsed_time_s"] is None
        ]
        if missing:
            raise RuntimeError(
                f"{trial_id} has no trajectory metrics for UAVs: {', '.join(missing)}"
            )
        if not (bag_dir / "metadata.yaml").is_file():
            raise RuntimeError(f"{trial_id} rosbag metadata is missing")
        (trial_dir / "completed.json").write_text(
            json.dumps({"trial_id": trial_id, "completed_at_utc": utc_now()}, indent=2),
            encoding="utf-8",
        )
    finally:
        for process in reversed(processes):
            process.stop(interrupt=process.name == "rosbag")
        # sitl_multiple_run.sh starts background children. The preflight guard
        # guarantees they belong to this trial, so remove any child that did
        # not exit with its process group.
        for process_name in ("px4", "gzserver", "gzclient"):
            subprocess.run(
                ["pkill", "-9", "-x", process_name],
                check=False,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        subprocess.run(["ros2", "daemon", "stop"], check=False, timeout=10)
        time.sleep(2.0)


def main() -> int:
    args = parse_args()
    ensure_environment()
    output_dir = Path(args.output_dir).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    repeats = 1 if args.smoke else args.repeats
    profiles = [args.profiles[0]] if args.smoke else args.profiles
    schedule = [(profile, repeat) for repeat in range(1, repeats + 1) for profile in profiles]
    random.Random(SEED).shuffle(schedule)
    config = {
        "experiment": "experiments_05",
        "created_at_utc": utc_now(),
        "seed": SEED,
        "profiles": profiles,
        "repeats_per_profile": repeats,
        "schedule": [{"profile": profile, "repeat": repeat} for profile, repeat in schedule],
        "uav_ids": [1, 2, 3, 4, 5],
        "duration_s": 8.0,
        "trial_timeout_s": 28.0,
        "control_frequency_hz": 50.0,
        "motion_style": "normal",
        "safety_factor": 0.0,
        "iapf_accel_feedforward": False,
        "cold_start_each_trial": True,
        "targets": {str(uid): list(target) for uid, target in TARGETS.items()},
    }
    config_path = output_dir / "run_config.json"
    if not (args.resume and config_path.is_file()):
        config_path.write_text(json.dumps(config, indent=2), encoding="utf-8")
    for index, (profile, repeat) in enumerate(schedule, start=1):
        trial_id = f"{profile}_r{repeat:02d}"
        completed = output_dir / "trials" / trial_id / "completed.json"
        if args.resume and completed.is_file():
            print(f"[{index}/{len(schedule)}] keeping completed {trial_id}")
            continue
        print(f"[{index}/{len(schedule)}] cold-starting {profile} repeat {repeat}")
        for attempt in range(1, 4):
            try:
                run_trial(profile, repeat, output_dir, args.startup_timeout)
                break
            except (RuntimeError, TimeoutError, subprocess.CalledProcessError) as error:
                trial_id = f"{profile}_r{repeat:02d}"
                trial_dir = output_dir / "trials" / trial_id
                rejected = output_dir / "rejected" / f"{trial_id}_attempt{attempt}"
                rejected.parent.mkdir(parents=True, exist_ok=True)
                if trial_dir.exists():
                    shutil.move(str(trial_dir), str(rejected))
                if attempt == 3:
                    raise
                print(f"Rejected incomplete {trial_id}: {error}; retrying")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
