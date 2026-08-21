#!/usr/bin/env python3
"""Run one 4-UAV cold-start semantic motion-style validation trial."""

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import signal
import subprocess
import time


REPOSITORY = Path(__file__).resolve().parents[2]
WORKSPACE = REPOSITORY.parents[1]
PX4 = Path("/home/yihuang/PX4-Autopilot")
VENV_PYTHON = WORKSPACE / "llm_env" / "bin" / "python"
READINESS = (
    REPOSITORY
    / "experiments-legacy"
    / "system_8uav"
    / "scripts"
    / "wait_swarm_ready.py"
)
FULL_COMMAND = (
    "First, have UAVs 1 and 2 form a line centered at [4, 4.5, 3] with "
    "radius 1 meter in exactly 8 seconds using {style} motion and safety "
    "factor 1.0. After they are stable, have UAVs 1 and 2 form a line "
    "centered at [-4, 4.5, 3] with radius 1 meter with automatic duration, "
    "still using {style} motion and safety factor 1.0. After that is stable, "
    "have UAVs 1 through 4 form a circle centered at [0, 7.5, 3] with radius "
    "3 meters with automatic duration, using {style} motion and safety "
    "factor 1.0."
)
EXPLICIT_ISOLATION_COMMAND = (
    "Have UAVs 1 through 3 form a triangle centered at [4, 6, 3] with "
    "radius 3 meters in exactly 8 seconds using {style} motion and safety "
    "factor 1.0."
)


def start(command, log_path, *, cwd=None):
    log = log_path.open("w", encoding="utf-8")
    process = subprocess.Popen(
        command,
        cwd=cwd,
        stdout=log,
        stderr=subprocess.STDOUT,
        start_new_session=True,
        text=True,
    )
    return process, log


def stop(process, first_signal=signal.SIGINT, timeout=20.0):
    if process is None or process.poll() is not None:
        return
    os.killpg(process.pid, first_signal)
    try:
        process.wait(timeout=timeout)
    except subprocess.TimeoutExpired:
        os.killpg(process.pid, signal.SIGTERM)
        try:
            process.wait(timeout=10.0)
        except subprocess.TimeoutExpired:
            os.killpg(process.pid, signal.SIGKILL)
            process.wait(timeout=5.0)


def assert_clean_start():
    for name in ("px4", "gzserver", "MicroXRCEAgent"):
        result = subprocess.run(
            ["pgrep", "-x", name],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
        )
        if result.returncode == 0:
            raise RuntimeError(f"refusing cold start while {name} is running")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--style", choices=("smooth", "normal", "aggressive"),
                        required=True)
    parser.add_argument("--trial", type=int, required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument(
        "--scenario", choices=("full", "explicit-isolation"), default="full"
    )
    args = parser.parse_args()

    output = (args.output_root / f"{args.style}_trial_{args.trial}").resolve()
    output.mkdir(parents=True, exist_ok=False)
    command_template = (
        FULL_COMMAND if args.scenario == "full" else EXPLICIT_ISOLATION_COMMAND
    )
    command = command_template.format(style=args.style)
    manifest = {
        "style": args.style,
        "scenario": args.scenario,
        "trial": args.trial,
        "cold_start": True,
        "uav_ids": [1, 2, 3, 4],
        "control_mode": "ladrc_acceleration",
        "command": command,
        "started_utc": datetime.now(timezone.utc).isoformat(),
        "readiness": False,
        "candidate_completed": False,
    }
    processes = {"agent": None, "sitl": None, "controllers": None, "bag": None}
    logs = []
    try:
        assert_clean_start()
        processes["agent"], log = start(
            ["MicroXRCEAgent", "udp4", "-p", "8888"], output / "agent.log"
        )
        logs.append(log)
        processes["sitl"], log = start(
            [
                "bash",
                str(PX4 / "Tools/simulation/gazebo-classic/sitl_multiple_run.sh"),
                "-n", "4", "-m", "iris",
            ],
            output / "sitl.log",
            cwd=PX4,
        )
        logs.append(log)
        time.sleep(18.0)
        if processes["sitl"].poll() is not None:
            raise RuntimeError("PX4/Gazebo exited during startup")

        processes["controllers"], log = start(
            [
                "ros2", "launch", "ladrc_controller", "swarm_launch.py",
                "uav_ids:=[1,2,3,4]",
                "control_mode:=ladrc_acceleration",
            ],
            output / "controllers.log",
            cwd=WORKSPACE,
        )
        logs.append(log)
        readiness = subprocess.run(
            [
                str(VENV_PYTHON), str(READINESS), "--uav-ids", "1,2,3,4",
                "--timeout", "150",
            ],
            cwd=REPOSITORY,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            timeout=165,
            check=False,
        )
        (output / "readiness.log").write_text(
            readiness.stdout, encoding="utf-8"
        )
        if readiness.returncode != 0:
            raise RuntimeError("4/4 readiness gate failed")
        manifest["readiness"] = True

        topics = []
        for uid in range(1, 5):
            topics.extend([
                f"/uav{uid}/status",
                f"/uav{uid}/startup_event",
                f"/uav{uid}/execution_command",
                f"/uav{uid}/trajectory_metrics",
                f"/uav{uid}/control_adaptation",
                f"/uav{uid}/control_tracking_debug",
                f"/uav{uid}/iapf_debug",
                f"/px4_{uid}/fmu/out/vehicle_status",
            ])
        processes["bag"], log = start(
            [
                "ros2", "bag", "record", "-o", str(output / "rosbag"),
                *topics,
            ],
            output / "rosbag.log",
            cwd=WORKSPACE,
        )
        logs.append(log)
        time.sleep(2.0)
        if processes["bag"].poll() is not None:
            raise RuntimeError("rosbag exited before mission")

        scheduler = subprocess.run(
            [
                str(VENV_PYTHON), "-m",
                "location_allocate.location_allocate", "--ros-args",
                "-p", "lfs_runtime_mode:=candidate_v2",
                "-p", "uav_ids:=[1,2,3,4]",
                "-p", "candidate_completion_timeout:=180.0",
            ],
            cwd=REPOSITORY,
            input=command + "\nq\n",
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            timeout=300,
            check=False,
        )
        (output / "scheduler.log").write_text(
            scheduler.stdout, encoding="utf-8"
        )
        manifest["scheduler_returncode"] = scheduler.returncode
        manifest["candidate_completed"] = (
            "Candidate mission" in scheduler.stdout
            and "completed" in scheduler.stdout
        )
        if not manifest["candidate_completed"]:
            raise RuntimeError("Candidate mission did not complete")
        return 0
    except Exception as error:
        manifest["error"] = f"{type(error).__name__}: {error}"
        return 2
    finally:
        stop(processes["bag"])
        stop(processes["controllers"])
        stop(processes["sitl"], timeout=25.0)
        stop(processes["agent"])
        for log in logs:
            log.close()
        manifest["finished_utc"] = datetime.now(timezone.utc).isoformat()
        (output / "manifest.json").write_text(
            json.dumps(manifest, indent=2, sort_keys=True), encoding="utf-8"
        )


if __name__ == "__main__":
    raise SystemExit(main())
