#!/usr/bin/env python3
"""Run experiment 06 with an independent PX4/Gazebo cold start per trial."""

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

from analyze_tracking_performance import analyze_trial
from experiment_06_config import METHODS, REPEATS, SCENARIOS, SEED, validate


REPO_ROOT = Path(__file__).resolve().parents[2]
WORKSPACE_ROOT = REPO_ROOT.parents[1]
PX4_ROOT = Path(os.environ.get("PX4_AUTOPILOT_ROOT", "/home/yihuang/PX4-Autopilot"))
TOOLS_DIR = REPO_ROOT / "tools/trajectory_metrics"
sys.path.insert(0, str(TOOLS_DIR))
from rosbag_to_csv import convert_bag  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--repeats", type=int, default=REPEATS)
    parser.add_argument("--scenarios", nargs="+", choices=SCENARIOS, default=list(SCENARIOS))
    parser.add_argument("--methods", nargs="+", choices=METHODS, default=list(METHODS))
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--startup-timeout", type=float, default=110.0)
    parser.add_argument("--max-attempts", type=int, default=3)
    return parser.parse_args()


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def process_is_running(pattern: str) -> bool:
    result = subprocess.run(
        ["pgrep", "-f", pattern],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    return result.returncode == 0


def ensure_environment() -> None:
    missing = [
        name for name in ("ros2", "MicroXRCEAgent")
        if shutil.which(name) is None
    ]
    if missing:
        raise RuntimeError(f"missing commands: {', '.join(missing)}")
    if not (PX4_ROOT / "build/px4_sitl_default/bin/px4").is_file():
        raise RuntimeError(f"PX4 SITL build missing under {PX4_ROOT}")
    if not (WORKSPACE_ROOT / "install/setup.bash").is_file():
        raise RuntimeError("workspace install/setup.bash is missing")
    conflicts = [
        pattern for pattern in (
            "[p]x4 -i", "[g]zserver", "[M]icroXRCEAgent udp4",
            "ladrc_position_controller_node",
        )
        if process_is_running(pattern)
    ]
    if conflicts:
        raise RuntimeError("experiment processes already running: " + ", ".join(conflicts))


class ManagedProcess:
    def __init__(
        self,
        name: str,
        command: List[str],
        log_path: Path,
        env: Dict[str, str],
        cwd: Path = REPO_ROOT,
    ) -> None:
        self.name = name
        log_path.parent.mkdir(parents=True, exist_ok=True)
        self.log_handle: TextIO = log_path.open("w", encoding="utf-8")
        self.process = subprocess.Popen(
            command,
            cwd=cwd,
            stdout=self.log_handle,
            stderr=subprocess.STDOUT,
            env=env,
            start_new_session=True,
            text=True,
        )

    def stop(self, interrupt: bool = False, timeout: float = 15.0) -> None:
        if self.process.poll() is None:
            os.killpg(self.process.pid, signal.SIGINT if interrupt else signal.SIGTERM)
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
        if all(topic in set(result.stdout.splitlines()) for topic in required):
            return
        time.sleep(2.0)
    raise TimeoutError(f"topics not discovered: {required}")


def topic_list(scenario: str) -> List[str]:
    ids = SCENARIOS[scenario]["uav_ids"]
    topics = [
        f"/uav{uid}/{suffix}"
        for uid in ids
        for suffix in ("swarm_command", "status", "odom", "trajectory_metrics")
    ]
    if ids == [0]:
        topics.append("/fmu/out/vehicle_odometry")
    else:
        topics.extend(f"/px4_{uid}/fmu/out/vehicle_odometry" for uid in ids)
    return topics


def write_trial_config(
    trial_dir: Path, trial_id: str, scenario: str, method: str, repeat: int
) -> None:
    scene = SCENARIOS[scenario]
    method_config = METHODS[method]
    config = {
        "trial_id": trial_id,
        "scenario": scenario,
        "method": method,
        "repeat": repeat,
        "num_uav": len(scene["uav_ids"]),
        "uav_ids": scene["uav_ids"],
        "targets": {str(key): list(value) for key, value in scene["targets"].items()},
        "duration_s": scene["duration_s"],
        "trajectory_profile": method_config["trajectory_profile"],
        "enable_ladrc_accel_feedforward":
            method_config["enable_ladrc_accel_feedforward"],
        "motion_style": "normal",
        "safety_factor": 0.0,
        "enable_iapf_accel_feedforward": False,
        "position_threshold_m": 0.3,
        "velocity_threshold_mps": 0.3,
        "settling_dwell_s": 1.0,
        "cold_start": True,
    }
    (trial_dir / "trial_config.json").write_text(
        json.dumps(config, indent=2), encoding="utf-8"
    )


def run_trial(
    scenario: str,
    method: str,
    repeat: int,
    output_dir: Path,
    startup_timeout: float,
) -> None:
    trial_id = f"{scenario}__{method}__r{repeat:02d}"
    trial_dir = output_dir / "trials" / trial_id
    if trial_dir.exists():
        raise FileExistsError(f"will not overwrite trial: {trial_dir}")
    trial_dir.mkdir(parents=True)
    write_trial_config(trial_dir, trial_id, scenario, method, repeat)

    scene = SCENARIOS[scenario]
    ids = list(scene["uav_ids"])
    method_config = METHODS[method]
    processes: List[ManagedProcess] = []
    env = os.environ.copy()
    headless_path = REPO_ROOT / "experiments/scripts/headless"
    env["PATH"] = f"{headless_path}:{env['PATH']}"
    # PX4's jinja_gen.py depends on the distro jinja2 package. The experiment
    # analysis runs in llm_env, but SITL must not inherit that venv's python3.
    sitl_env = env.copy()
    sitl_env["PATH"] = (
        f"{headless_path}:/opt/ros/humble/bin:/usr/local/sbin:/usr/local/bin:"
        "/usr/sbin:/usr/bin:/sbin:/bin"
    )

    try:
        subprocess.run(["ros2", "daemon", "stop"], check=False, timeout=10)
        processes.append(ManagedProcess(
            "xrce", ["MicroXRCEAgent", "udp4", "-p", "8888"],
            trial_dir / "xrce.log", env,
        ))
        time.sleep(1.0)
        if ids == [0]:
            sitl_command = ["make", "px4_sitl", "gazebo-classic"]
            required_px4_topics = ["/fmu/out/vehicle_odometry"]
        else:
            sitl_command = [
                "bash",
                str(PX4_ROOT / "Tools/simulation/gazebo-classic/sitl_multiple_run.sh"),
                "-m", "iris", "-n", str(len(ids)),
            ]
            required_px4_topics = [
                f"/px4_{uid}/fmu/out/vehicle_odometry" for uid in ids
            ]
        processes.append(ManagedProcess(
            "sitl", sitl_command, trial_dir / "sitl.log", sitl_env, PX4_ROOT,
        ))
        wait_for_topics(required_px4_topics, startup_timeout)

        ids_arg = "[" + ",".join(str(uid) for uid in ids) + "]"
        processes.append(ManagedProcess(
            "controller",
            [
                "ros2", "launch", "ladrc_controller", "swarm_launch.py",
                f"uav_ids:={ids_arg}",
                f"trajectory_profile:={method_config['trajectory_profile']}",
                "enable_ladrc_accel_feedforward:="
                + str(method_config["enable_ladrc_accel_feedforward"]).lower(),
                "enable_iapf_accel_feedforward:=false",
            ],
            trial_dir / "controller.log", env,
        ))
        wait_for_topics(
            [f"/uav{uid}/swarm_command" for uid in ids], startup_timeout
        )
        # Controller state machine reaches RUNNING_TRAJECTORY after about 13 s.
        time.sleep(16.0)

        bag_dir = trial_dir / "rosbag"
        processes.append(ManagedProcess(
            "rosbag",
            ["ros2", "bag", "record", "-o", str(bag_dir), *topic_list(scenario)],
            trial_dir / "rosbag.log", env,
        ))
        time.sleep(2.0)
        subprocess.run(
            [
                sys.executable,
                str(REPO_ROOT / "experiments/scripts/experiment_06_trial.py"),
                "--scenario", scenario,
                "--method", method,
                "--trial-id", trial_id,
                "--repeat", str(repeat),
                "--output", str(trial_dir / "trial_status.json"),
            ],
            check=True,
            env=env,
            timeout=float(scene["duration_s"]) + 125.0,
        )
        processes[-1].stop(interrupt=True)
        processes.pop()
        if not (bag_dir / "metadata.yaml").is_file():
            raise RuntimeError("rosbag metadata missing")

        convert_bag(bag_dir, trial_dir / "bag_csv", [
            "/uav*/trajectory_metrics", "/uav*/swarm_command",
            "/uav*/status", "/uav*/odom",
            "/px4_*/fmu/out/vehicle_odometry",
            "/fmu/out/vehicle_odometry",
        ])
        uav_rows, _ = analyze_trial(trial_dir)
        if len(uav_rows) != len(ids):
            raise RuntimeError("offline completeness check returned wrong UAV count")
        (trial_dir / "completed.json").write_text(
            json.dumps({"trial_id": trial_id, "completed_at_utc": utc_now()}, indent=2),
            encoding="utf-8",
        )
    finally:
        for process in reversed(processes):
            process.stop(interrupt=process.name == "rosbag")
        # The preflight guard establishes ownership of these experiment-only
        # processes; PX4's shell launcher may leave children outside its group.
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
    validate()
    args = parse_args()
    ensure_environment()
    output_dir = args.output_dir.resolve()
    if output_dir.exists() and not args.resume:
        raise FileExistsError(f"refusing to overwrite output directory: {output_dir}")
    output_dir.mkdir(parents=True, exist_ok=True)

    schedule = [
        (scenario, method, repeat)
        for repeat in range(1, args.repeats + 1)
        for scenario in args.scenarios
        for method in args.methods
    ]
    random.Random(SEED).shuffle(schedule)
    config = {
        "experiment": "experiments_06",
        "created_at_utc": utc_now(),
        "base_tag": "gazebo-experiment-v1",
        "seed": SEED,
        "repeats_per_cell": args.repeats,
        "scenarios": SCENARIOS,
        "methods": METHODS,
        "schedule": [
            {"scenario": scenario, "method": method, "repeat": repeat}
            for scenario, method, repeat in schedule
        ],
        "control_frequency_hz": 50.0,
        "motion_style": "normal",
        "iapf_disabled": True,
        "cold_start_each_trial": True,
        "scheduled_start_delay_s": 2.0,
        "command_publish_repetitions": 10,
    }
    config_path = output_dir / "run_config.json"
    if not (args.resume and config_path.is_file()):
        config_path.write_text(json.dumps(config, indent=2), encoding="utf-8")

    for index, (scenario, method, repeat) in enumerate(schedule, start=1):
        trial_id = f"{scenario}__{method}__r{repeat:02d}"
        completed = output_dir / "trials" / trial_id / "completed.json"
        if args.resume and completed.is_file():
            print(f"[{index}/{len(schedule)}] keeping completed {trial_id}", flush=True)
            continue
        print(f"[{index}/{len(schedule)}] cold-starting {trial_id}", flush=True)
        for attempt in range(1, args.max_attempts + 1):
            try:
                run_trial(
                    scenario, method, repeat, output_dir, args.startup_timeout
                )
                break
            except (
                RuntimeError, TimeoutError, subprocess.CalledProcessError,
                subprocess.TimeoutExpired,
            ) as error:
                trial_dir = output_dir / "trials" / trial_id
                rejected = output_dir / "rejected" / f"{trial_id}__attempt{attempt}"
                rejected.parent.mkdir(parents=True, exist_ok=True)
                if trial_dir.exists():
                    shutil.move(str(trial_dir), str(rejected))
                if attempt == args.max_attempts:
                    raise
                print(f"Rejected {trial_id}: {error}; retrying", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
