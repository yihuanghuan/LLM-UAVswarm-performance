#!/usr/bin/env python3
"""Run one immutable, cold-start C0-E trial on the production Candidate path."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import signal
import subprocess
import time

import yaml

PIPE = Path(__file__).resolve().parent
REPO = PIPE.parents[3]
WORKSPACE = REPO.parents[1]
RESULTS = PIPE.parent / "results" / "C0-E_iapf_freeze"
SCENES_FILE = RESULTS / "scene_definitions.yaml"
PX4 = Path("/home/yihuang/PX4-Autopilot")
PYTHON = WORKSPACE / "llm_env/bin/python"
READY = REPO / "experiments-legacy/system_8uav/scripts/wait_swarm_ready.py"
EXTRACT = PIPE / "extract_trial_metrics.py"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def ros_environment() -> dict[str, str]:
    command = (
        "source /opt/ros/humble/setup.bash && "
        f"source {WORKSPACE}/install/setup.bash && env -0"
    )
    output = subprocess.check_output(["bash", "-lc", command])
    return {
        item.split(b"=", 1)[0].decode(): item.split(b"=", 1)[1].decode()
        for item in output.split(b"\0") if b"=" in item
    }


def start(command, log_path, *, cwd=None, env=None):
    log = log_path.open("w", encoding="utf-8")
    process = subprocess.Popen(
        command, cwd=cwd, env=env, stdout=log, stderr=subprocess.STDOUT,
        start_new_session=True, text=True,
    )
    return process, log


def stop(process):
    if process is None or process.poll() is not None:
        return
    os.killpg(process.pid, signal.SIGINT)
    try:
        process.wait(25)
    except subprocess.TimeoutExpired:
        os.killpg(process.pid, signal.SIGKILL)
        process.wait(10)


def task(task_id, entry, safety_factor, *, stage=False):
    return {
        "task_id": task_id,
        "U": entry["ids"],
        "F": {"type": entry["formation"]},
        "c": {"mode": "absolute", "value": entry["center"]},
        "r": {"mode": "explicit", "value": 0.9},
        "T": {"mode": "explicit", "value": 8.0},
        "m": "normal",
        "s": 1.0 if stage else safety_factor,
        "q": {"mode": "direct"},
    }


def materialize_scene(scene, safety_factor):
    nodes, task_id = [], 1
    # Staging is sequential and explicitly excluded from scoring.
    for entry in scene["staging"]:
        nodes.append({"type": "task", "task": task(task_id, entry, 1.0, stage=True)})
        task_id += 1
    score_task_ids = []
    interaction = []
    for entry in scene["interaction"]:
        interaction.append(task(task_id, entry, safety_factor))
        score_task_ids.append(task_id)
        task_id += 1
    nodes.append({
        "type": "parallel", "completion_mode": "synchronized",
        "tasks": interaction,
    })
    return {"lfs_version": "2.1", "mission": {"nodes": nodes}}, score_task_ids


def topics(ids):
    result = []
    for uid in ids:
        result.extend([
            f"/uav{uid}/execution_command", f"/uav{uid}/iapf_debug",
            f"/uav{uid}/control_tracking_debug",
            f"/uav{uid}/trajectory_metrics", f"/uav{uid}/status",
            f"/uav{uid}/swarm_state",
        ])
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--stage", required=True)
    parser.add_argument("--candidate", required=True)
    parser.add_argument("--policy", type=Path, required=True)
    parser.add_argument("--scene", choices=("S1", "S2", "S3", "S4", "S5"), required=True)
    parser.add_argument("--s", type=float, required=True)
    parser.add_argument("--cold-start", type=int, default=1)
    parser.add_argument("--seed", help="provenance seed label")
    parser.add_argument("--root", type=Path, default=RESULTS / "runtime_raw_semantic_v1")
    args = parser.parse_args()
    seed = args.seed or (
        "c0e-confirm-20260822"
        if args.stage == "confirmation"
        else "c0e-screen-20260822"
    )

    args.policy = args.policy.resolve()
    definitions = yaml.safe_load(SCENES_FILE.read_text(encoding="utf-8"))
    scene = definitions["scenes"][args.scene]
    mission, score_task_ids = materialize_scene(scene, args.s)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    trial_id = (
        f"{args.stage}_{args.candidate}_{args.scene}_s{args.s:g}_"
        f"cold{args.cold_start}_{stamp}_{os.getpid()}"
    )
    trial_dir = args.root.resolve() / trial_id
    trial_dir.mkdir(parents=True, exist_ok=False)
    mission_path = trial_dir / "candidate_mission.json"
    mission_path.write_text(json.dumps(mission, indent=2) + "\n", encoding="utf-8")
    policy = yaml.safe_load(args.policy.read_text(encoding="utf-8"))
    alpha = float(policy.get("iapf_runtime", {}).get("filter_alpha", 0.20))
    ids = [int(value) for value in scene["participants"]]
    manifest = {
        "trial_id": trial_id, "stage": args.stage,
        "candidate": args.candidate, "scene": args.scene,
        "scene_family": scene["family"], "s": args.s,
        "cold_start": args.cold_start, "seed": seed,
        "control_mode": "ladrc_acceleration",
        "dispatch": "location_allocate.candidate_dispatch",
        "runtime": "UAVFormationNode/PaperMissionRuntime",
        "policy": str(args.policy), "policy_sha256": sha256(args.policy),
        "scene_definitions_sha256": sha256(SCENES_FILE),
        "mission_sha256": sha256(mission_path),
        "score_task_ids": score_task_ids,
        "iapf_filter_alpha": alpha, "participants": ids,
        "staging_scored": False, "candidate_completed": False,
        "result": "FAIL", "failure_reason": "",
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
        ids_arg = "[" + ",".join(str(uid) for uid in ids) + "]"
        process, log = start(
            ["ros2", "launch", "ladrc_controller", "swarm_launch.py",
             f"uav_ids:={ids_arg}", "control_mode:=ladrc_acceleration",
             f"lfs_policy_file:={args.policy}",
             f"iapf_filter_alpha:={alpha:.2f}"],
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
            ["ros2", "bag", "record", "-o", str(trial_dir / "rosbag"),
             *topics(ids)], trial_dir / "rosbag.log", cwd=REPO, env=env,
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
        manifest["result"] = "PASS"
    except Exception as error:
        manifest["failure_reason"] = f"{type(error).__name__}: {error}"
    finally:
        stop(bag)
        for process in reversed(processes):
            stop(process)
        for log in logs:
            log.close()
        manifest["finished_utc"] = datetime.now(timezone.utc).isoformat()
        (trial_dir / "manifest.json").write_text(
            json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )

    if (trial_dir / "rosbag" / "metadata.yaml").is_file():
        subprocess.run(
            [str(PYTHON), str(EXTRACT), str(trial_dir),
             "--scene-definitions", str(SCENES_FILE)],
            cwd=REPO, env=env, check=False,
        )
    print(json.dumps({
        "trial_id": trial_id, "result": manifest["result"],
        "failure_reason": manifest["failure_reason"],
        "raw_dir": str(trial_dir.relative_to(RESULTS)),
    }, sort_keys=True))
    return 0 if manifest["result"] == "PASS" else 2


if __name__ == "__main__":
    raise SystemExit(main())
