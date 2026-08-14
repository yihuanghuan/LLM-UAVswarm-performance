#!/usr/bin/env python3
"""Gate readiness, start rosbag, then submit one English NL mission."""

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import time


SCRIPT_DIR = Path(__file__).resolve().parent
DEFAULT_RESULTS = SCRIPT_DIR.parents[1] / "results" / "reliability_regression"


def stop(process):
    if process is None or process.poll() is not None:
        return
    os.killpg(process.pid, signal.SIGINT)
    try:
        process.wait(timeout=15)
    except subprocess.TimeoutExpired:
        os.killpg(process.pid, signal.SIGTERM)
        process.wait(timeout=5)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--command", required=True)
    parser.add_argument("--uav-ids", default="1,2,3,4,5,6,7,8")
    parser.add_argument("--control-mode", required=True,
                        choices=("px4_position", "ladrc_acceleration"))
    parser.add_argument("--timeout", type=float, default=300.0)
    parser.add_argument("--output-dir")
    args = parser.parse_args()
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    output = Path(args.output_dir) if args.output_dir else (
        DEFAULT_RESULTS / f"trial_{stamp}_{os.getpid()}"
    )
    output = output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    manifest = {
        "started_utc": stamp,
        "command": args.command,
        "uav_ids": args.uav_ids,
        "control_mode": args.control_mode,
        "readiness_before_rosbag": False,
        "candidate_completed": False,
    }
    bag = None
    try:
        readiness = subprocess.run([
            sys.executable, str(SCRIPT_DIR / "wait_swarm_ready.py"),
            "--uav-ids", args.uav_ids,
        ], text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
           timeout=150, check=False)
        (output / "readiness.log").write_text(
            readiness.stdout, encoding="utf-8"
        )
        if readiness.returncode != 0:
            raise RuntimeError("8/N readiness gate failed")
        manifest["readiness_before_rosbag"] = True
        ids = [int(value) for value in args.uav_ids.split(",")]
        topics = []
        for uid in ids:
            topics.extend([
                f"/uav{uid}/status", f"/uav{uid}/startup_event",
                f"/uav{uid}/swarm_state",
                f"/uav{uid}/control_tracking_debug",
                f"/uav{uid}/iapf_debug", f"/uav{uid}/execution_command",
                f"/px4_{uid}/fmu/out/vehicle_status",
            ])
        bag_log = (output / "rosbag.log").open("w", encoding="utf-8")
        bag = subprocess.Popen(
            ["ros2", "bag", "record", "-o", str(output / "rosbag"), *topics],
            stdout=bag_log, stderr=subprocess.STDOUT, start_new_session=True,
        )
        time.sleep(2.0)
        if bag.poll() is not None:
            raise RuntimeError("rosbag exited before natural-language input")
        scheduler = subprocess.run(
            [sys.executable, "-m", "location_allocate.location_allocate",
             "--ros-args", "-p", "lfs_runtime_mode:=candidate_v2",
             "-p", f"uav_ids:=[{args.uav_ids}]"],
            input=args.command + "\nq\n", text=True,
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            timeout=args.timeout, check=False,
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
        stop(bag)
        manifest["finished_utc"] = datetime.now(timezone.utc).isoformat()
        (output / "manifest.json").write_text(
            json.dumps(manifest, indent=2, sort_keys=True), encoding="utf-8"
        )


if __name__ == "__main__":
    raise SystemExit(main())
