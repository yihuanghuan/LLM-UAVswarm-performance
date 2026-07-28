#!/usr/bin/env python3
"""Orchestrate cold-start Gazebo trials for experiment 07."""

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

from experiment_07_config import METHODS, REPEATS, SEED, validate


REPO_ROOT = Path(__file__).resolve().parents[2]
WORKSPACE_ROOT = REPO_ROOT.parents[1]
PX4_ROOT = Path(os.environ.get("PX4_AUTOPILOT_ROOT", "/home/yihuang/PX4-Autopilot"))
TOOLS_DIR = REPO_ROOT / "tools/trajectory_metrics"
sys.path.insert(0, str(TOOLS_DIR))
from rosbag_to_csv import convert_bag  # noqa: E402

STYLES = ("smooth", "normal", "aggressive")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--repeats", type=int, default=REPEATS)
    parser.add_argument("--methods", nargs="+", choices=METHODS, default=list(METHODS))
    parser.add_argument("--styles", nargs="+", choices=STYLES, default=list(STYLES))
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--startup-timeout", type=float, default=110.0)
    parser.add_argument("--max-attempts", type=int, default=5)
    return parser.parse_args()


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def process_is_running(pattern: str) -> bool:
    return subprocess.run(
        ["pgrep", "-f", pattern],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    ).returncode == 0


def ensure_environment() -> None:
    missing = [
        name for name in ("ros2", "MicroXRCEAgent")
        if shutil.which(name) is None
    ]
    if missing:
        raise RuntimeError("missing commands: " + ", ".join(missing))
    if not (PX4_ROOT / "build/px4_sitl_default/bin/px4").is_file():
        raise RuntimeError(f"PX4 SITL build missing under {PX4_ROOT}")
    if not (WORKSPACE_ROOT / "install/setup.bash").is_file():
        raise RuntimeError("workspace install/setup.bash is missing")
    if not (os.getenv("LLM_API_KEY") or os.getenv("MINIMAX_API_KEY")):
        raise RuntimeError("LLM_API_KEY or MINIMAX_API_KEY is required")
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


def write_trial_config(
    trial_dir: Path, trial_id: str, method: str, style: str, repeat: int
) -> None:
    method_config = METHODS[method]
    config = {
        "trial_id": trial_id,
        "method": method,
        "motion_style": style,
        "repeat": repeat,
        "uav_id": 1,
        "target": [6.0, 3.0, 5.0],
        "duration_s": 3.0,
        "observation_s": 15.0,
        "semantic_gain_mode": method_config["semantic_gain_mode"],
        "fixed_gain_multiplier": method_config["fixed_gain_multiplier"],
        "enable_ladrc_accel_feedforward": True,
        "enable_iapf_accel_feedforward": False,
        "position_threshold_m": 0.3,
        "velocity_threshold_mps": 0.3,
        "settling_dwell_s": 1.0,
        "cold_start": True,
        "readiness_gate": "PX4 armed, OFFBOARD, and not failsafe",
    }
    (trial_dir / "trial_config.json").write_text(
        json.dumps(config, indent=2), encoding="utf-8"
    )


def topic_list() -> List[str]:
    return [
        "/uav1/swarm_command",
        "/uav1/status",
        "/uav1/odom",
        "/uav1/trajectory_metrics",
        "/uav1/control_adaptation",
        "/px4_1/fmu/out/vehicle_odometry",
        "/px4_1/fmu/out/vehicle_status",
    ]


def run_trial(
    output_dir: Path,
    method: str,
    style: str,
    repeat: int,
    startup_timeout: float,
) -> None:
    trial_id = f"{method}__{style}__r{repeat:02d}"
    trial_dir = output_dir / "trials" / trial_id
    if trial_dir.exists():
        raise FileExistsError(f"will not overwrite trial: {trial_dir}")
    trial_dir.mkdir(parents=True)
    write_trial_config(trial_dir, trial_id, method, style, repeat)

    env = os.environ.copy()
    headless_path = REPO_ROOT / "experiments/scripts/headless"
    env["PATH"] = f"{headless_path}:{env['PATH']}"
    env["LLM_PARSE_LOG_PATH"] = str(trial_dir / "llm_parse_log.csv")
    sitl_env = env.copy()
    sitl_env["PATH"] = (
        f"{headless_path}:/opt/ros/humble/bin:/usr/local/sbin:/usr/local/bin:"
        "/usr/sbin:/usr/bin:/sbin:/bin"
    )
    method_config = METHODS[method]
    processes: List[ManagedProcess] = []

    try:
        subprocess.run(["ros2", "daemon", "stop"], check=False, timeout=10)
        processes.append(ManagedProcess(
            "xrce",
            ["MicroXRCEAgent", "udp4", "-p", "8888"],
            trial_dir / "xrce.log",
            env,
        ))
        time.sleep(1.0)
        processes.append(ManagedProcess(
            "sitl",
            [
                "bash",
                str(PX4_ROOT / "Tools/simulation/gazebo-classic/sitl_multiple_run.sh"),
                "-m", "iris", "-n", "1",
            ],
            trial_dir / "sitl.log",
            sitl_env,
            PX4_ROOT,
        ))
        wait_for_topics(["/px4_1/fmu/out/vehicle_odometry"], startup_timeout)

        processes.append(ManagedProcess(
            "controller",
            [
                "ros2", "launch", "ladrc_controller", "swarm_launch.py",
                "uav_ids:=[1]",
                "enable_ladrc_accel_feedforward:=true",
                "enable_iapf_accel_feedforward:=false",
                f"semantic_gain_mode:={method_config['semantic_gain_mode']}",
                "fixed_gain_multiplier:=1.0",
                f"control_adaptation_log_path:={trial_dir / 'control_adaptation.csv'}",
            ],
            trial_dir / "controller.log",
            env,
        ))
        wait_for_topics(["/uav1/swarm_command", "/uav1/control_adaptation"], startup_timeout)
        time.sleep(16.0)

        bag_dir = trial_dir / "rosbag"
        processes.append(ManagedProcess(
            "rosbag",
            ["ros2", "bag", "record", "-o", str(bag_dir), *topic_list()],
            trial_dir / "rosbag.log",
            env,
        ))
        time.sleep(2.0)
        completed = subprocess.run(
            [
                sys.executable,
                str(REPO_ROOT / "experiments/scripts/experiment_07_trial.py"),
                "--method", method,
                "--style", style,
                "--repeat", str(repeat),
                "--trial-id", trial_id,
                "--output", str(trial_dir / "trial_status.json"),
                "--parse-output", str(trial_dir / "llm_parse_result.json"),
            ],
            env=env,
            timeout=190.0,
        )
        if completed.returncode != 0:
            raise RuntimeError(f"trial process returned {completed.returncode}")
        processes[-1].stop(interrupt=True)
        processes.pop()
        if not (bag_dir / "metadata.yaml").is_file():
            raise RuntimeError("rosbag metadata missing")

        counts = convert_bag(
            bag_dir,
            trial_dir / "bag_csv",
            topic_list(),
        )
        missing = [topic for topic in topic_list() if counts.get(topic, 0) == 0]
        if missing:
            raise RuntimeError("empty rosbag topics: " + ", ".join(missing))
        (trial_dir / "completed.json").write_text(
            json.dumps(
                {"trial_id": trial_id, "completed_at_utc": utc_now(), "topic_counts": counts},
                indent=2,
            ),
            encoding="utf-8",
        )
    finally:
        for process in reversed(processes):
            process.stop(interrupt=process.name == "rosbag")
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
    (output_dir / "trials").mkdir(exist_ok=True)
    (output_dir / "rejected").mkdir(exist_ok=True)

    schedule = [
        (method, style, repeat)
        for repeat in range(1, args.repeats + 1)
        for method in args.methods
        for style in args.styles
    ]
    random.Random(SEED).shuffle(schedule)
    run_config = {
        "experiment": "experiments_07",
        "seed": SEED,
        "repeats": args.repeats,
        "methods": args.methods,
        "styles": args.styles,
        "schedule": [
            {"method": method, "motion_style": style, "repeat": repeat}
            for method, style, repeat in schedule
        ],
        "started_at_utc": utc_now(),
    }
    config_path = output_dir / "run_config.json"
    if not config_path.exists():
        config_path.write_text(json.dumps(run_config, indent=2), encoding="utf-8")

    for index, (method, style, repeat) in enumerate(schedule, start=1):
        trial_id = f"{method}__{style}__r{repeat:02d}"
        trial_dir = output_dir / "trials" / trial_id
        if args.resume and (trial_dir / "completed.json").is_file():
            print(f"[{index}/{len(schedule)}] skip completed {trial_id}", flush=True)
            continue
        print(f"[{index}/{len(schedule)}] run {trial_id}", flush=True)
        for attempt in range(1, args.max_attempts + 1):
            try:
                run_trial(output_dir, method, style, repeat, args.startup_timeout)
                break
            except Exception as exc:
                failed_dir = output_dir / "trials" / trial_id
                reason = type(exc).__name__.lower()
                rejected = (
                    output_dir / "rejected"
                    / f"{trial_id}__attempt{attempt:02d}__{reason}"
                )
                if failed_dir.exists():
                    shutil.move(str(failed_dir), str(rejected))
                    (rejected / "rejection.json").write_text(
                        json.dumps(
                            {
                                "trial_id": trial_id,
                                "attempt": attempt,
                                "reason": repr(exc),
                                "rejected_at_utc": utc_now(),
                            },
                            indent=2,
                        ),
                        encoding="utf-8",
                    )
                print(f"  rejected attempt {attempt}: {exc}", flush=True)
                if attempt == args.max_attempts:
                    raise

    completed = list((output_dir / "trials").glob("*/completed.json"))
    expected = len(schedule)
    if len(completed) != expected:
        raise RuntimeError(f"expected {expected} completed trials, found {len(completed)}")
    (output_dir / "run_complete.json").write_text(
        json.dumps(
            {
                "completed_at_utc": utc_now(),
                "formal_trials": len(completed),
                "rejected_attempts": len(list((output_dir / "rejected").iterdir())),
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
