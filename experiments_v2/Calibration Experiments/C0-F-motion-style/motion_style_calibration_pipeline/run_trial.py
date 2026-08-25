#!/usr/bin/env python3
"""Run one cold-start C0-F trial on the production Candidate runtime."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import signal
import subprocess
import time

from common import (
    CANONICAL_POLICY, PIPELINE, PX4, PYTHON, RAW, REPO, SCENES_FILE,
    STYLES, WORKSPACE, load_yaml, materialize_scene, materialize_style_switch,
    sha256, write_json,
)


READY = REPO / "experiments-legacy/system_8uav/scripts/wait_swarm_ready.py"
EXTRACT = PIPELINE / "extract_trial_metrics.py"


def ros_environment() -> dict[str, str]:
    command = (
        "source /opt/ros/humble/setup.bash && "
        f"source {WORKSPACE}/install/setup.bash && env -0"
    )
    output = subprocess.check_output(["bash", "-lc", command])
    env = {
        item.split(b"=", 1)[0].decode(): item.split(b"=", 1)[1].decode()
        for item in output.split(b"\0") if b"=" in item
    }
    # Ensure the production Python implementation comes from this exact worktree.
    source_paths = f"{REPO / 'lfs_policy'}:{REPO / 'location_allocate'}"
    env["PYTHONPATH"] = source_paths + (":" + env["PYTHONPATH"] if env.get("PYTHONPATH") else "")
    return env


def start(command, log_path: Path, *, cwd=None, env=None):
    stream = log_path.open("w", encoding="utf-8")
    process = subprocess.Popen(
        command, cwd=cwd, env=env, stdout=stream, stderr=subprocess.STDOUT,
        start_new_session=True, text=True,
    )
    return process, stream


def stop(process) -> None:
    if process is None or process.poll() is not None:
        return
    try:
        os.killpg(process.pid, signal.SIGINT)
    except ProcessLookupError:
        return
    try:
        process.wait(20)
    except subprocess.TimeoutExpired:
        os.killpg(process.pid, signal.SIGKILL)
        process.wait(10)


def topics(ids: list[int]) -> list[str]:
    result = []
    for uid in ids:
        result.extend([
            f"/uav{uid}/execution_command",
            f"/uav{uid}/control_adaptation",
            f"/uav{uid}/iapf_debug",
            f"/uav{uid}/control_tracking_debug",
            f"/uav{uid}/trajectory_metrics",
            f"/uav{uid}/status",
            f"/uav{uid}/swarm_state",
            f"/px4_{uid}/fmu/out/vehicle_attitude",
        ])
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--stage", required=True)
    parser.add_argument("--scene", choices=("S1", "S2", "S3", "S4", "SWITCH"), required=True)
    parser.add_argument("--style", choices=STYLES + ("style_switch",), required=True)
    parser.add_argument("--cold-start", type=int, required=True)
    parser.add_argument("--seed", required=True)
    parser.add_argument("--policy", type=Path, default=CANONICAL_POLICY)
    parser.add_argument("--root", type=Path, default=RAW)
    args = parser.parse_args()
    args.policy = args.policy.resolve()
    if (args.scene == "SWITCH") != (args.style == "style_switch"):
        parser.error("SWITCH and style_switch must be selected together")

    definitions = load_yaml(SCENES_FILE)
    if args.scene == "SWITCH":
        scene = definitions["style_switch"]
        mission, score_ids = materialize_style_switch()
    else:
        scene = definitions["scenes"][args.scene]
        mission, score_ids = materialize_scene(args.scene, args.style)
    ids = [int(value) for value in scene["participants"]]
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    trial_id = f"{args.stage}_{args.scene}_{args.style}_cold{args.cold_start}_{stamp}_{os.getpid()}"
    trial_dir = args.root.resolve() / trial_id
    trial_dir.mkdir(parents=True, exist_ok=False)
    mission_path = trial_dir / "candidate_mission.json"
    write_json(mission_path, mission)
    policy = load_yaml(args.policy)
    iapf_alpha = float(policy["iapf_runtime"]["filter_alpha"])
    manifest = {
        "schema_version": "c0f-runtime-trial-v1",
        "trial_id": trial_id,
        "stage": args.stage,
        "scene": args.scene,
        "scene_family": scene["family"],
        "style": args.style,
        "cold_start": args.cold_start,
        "seed": args.seed,
        "participants": ids,
        "score_task_ids": score_ids,
        "control_mode": "ladrc_acceleration",
        "dispatch": "location_allocate.candidate_dispatch",
        "runtime": "UAVFormationNode/PaperMissionRuntime",
        "policy": str(args.policy),
        "policy_sha256": sha256(args.policy),
        "configuration_id": policy["configuration_id"],
        "scene_definitions_sha256": sha256(SCENES_FILE),
        "mission_sha256": sha256(mission_path),
        "iapf_filter_alpha": iapf_alpha,
        "staging_scored": False,
        "candidate_completed": False,
        "mission_success": False,
        "failure_reason": "",
        "started_utc": datetime.now(timezone.utc).isoformat(),
    }
    env = ros_environment()
    processes, logs, bag = [], [], None
    try:
        process, log = start(
            ["MicroXRCEAgent", "udp4", "-p", "8888"],
            trial_dir / "agent.log", env=env,
        )
        processes.append(process); logs.append(log)
        process, log = start(
            ["bash", str(PX4 / "Tools/simulation/gazebo-classic/sitl_multiple_run.sh"),
             "-n", str(max(ids)), "-m", "iris"],
            trial_dir / "sitl.log", cwd=PX4, env=env,
        )
        processes.append(process); logs.append(log)
        time.sleep(18)
        if process.poll() is not None:
            raise RuntimeError("PX4/Gazebo exited during startup")
        ids_arg = "[" + ",".join(map(str, ids)) + "]"
        process, log = start(
            ["ros2", "launch", "ladrc_controller", "swarm_launch.py",
             f"uav_ids:={ids_arg}", "control_mode:=ladrc_acceleration",
             f"lfs_policy_file:={args.policy}", f"iapf_filter_alpha:={iapf_alpha:.2f}"],
            trial_dir / "controllers.log", cwd=WORKSPACE, env=env,
        )
        processes.append(process); logs.append(log)
        ready = subprocess.run(
            [str(PYTHON), str(READY), "--uav-ids", ",".join(map(str, ids)),
             "--timeout", "120"], cwd=REPO, env=env, text=True,
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=135,
        )
        (trial_dir / "readiness.log").write_text(ready.stdout, encoding="utf-8")
        if ready.returncode:
            raise RuntimeError("readiness gate failed")
        bag, log = start(
            ["ros2", "bag", "record", "-o", str(trial_dir / "rosbag"), *topics(ids)],
            trial_dir / "rosbag.log", cwd=REPO, env=env,
        )
        logs.append(log)
        time.sleep(1)
        scheduler = subprocess.run(
            [str(PYTHON), "-m", "location_allocate.candidate_dispatch",
             "--uav-ids", ",".join(map(str, ids)), "--policy", str(args.policy),
             "--mission-json", str(mission_path)],
            cwd=REPO, env=env, text=True, stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT, timeout=420,
        )
        (trial_dir / "scheduler.log").write_text(scheduler.stdout, encoding="utf-8")
        if scheduler.returncode or '"candidate_completed": true' not in scheduler.stdout:
            raise RuntimeError("Candidate mission did not complete")
        manifest["candidate_completed"] = True
        manifest["mission_success"] = True
    except Exception as error:
        manifest["failure_reason"] = f"{type(error).__name__}: {error}"
    finally:
        stop(bag)
        for process in reversed(processes):
            stop(process)
        for stream in logs:
            stream.close()
        manifest["finished_utc"] = datetime.now(timezone.utc).isoformat()
        write_json(trial_dir / "manifest.json", manifest)

    metric_ok = False
    if (trial_dir / "rosbag/metadata.yaml").is_file():
        extracted = subprocess.run(
            [str(PYTHON), str(EXTRACT), str(trial_dir)], cwd=REPO, env=env,
            text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
        )
        (trial_dir / "extract.log").write_text(extracted.stdout, encoding="utf-8")
        metric_ok = extracted.returncode == 0
    print(json.dumps({
        "trial_id": trial_id,
        "mission_success": manifest["mission_success"],
        "metrics_success": metric_ok,
        "failure_reason": manifest["failure_reason"],
        "raw_dir": str(trial_dir),
    }, sort_keys=True))
    return 0 if manifest["mission_success"] and metric_ok else 2


if __name__ == "__main__":
    raise SystemExit(main())
