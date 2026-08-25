#!/usr/bin/env python3
"""Run the C0-D-deferred smokes against the frozen integrated C0-E policy."""
from __future__ import annotations
import argparse
import csv
from datetime import datetime, timezone
import hashlib
import os
import signal
import subprocess
import time
from pathlib import Path

import yaml

PIPELINE = Path(__file__).resolve().parent
REPO = PIPELINE.parents[3]
WORKSPACE = REPO.parents[1]
RESULTS = PIPELINE.parent / "results" / "C0-E_iapf_freeze"
PX4 = Path("/home/yihuang/PX4-Autopilot")
PYTHON = WORKSPACE / "llm_env/bin/python"
READY = REPO / "experiments-legacy/system_8uav/scripts/wait_swarm_ready.py"
CASES = (
    ("compact_s1", 1.0, "Have UAVs 1 through 8 form a line with compact qualitative scale centered at [0, 12, 3] with automatic duration, using normal motion and safety factor 1.0."),
    ("crossing_prone_s1", 1.0, "Have UAVs 1 through 8 form a circle with normal qualitative scale centered at [0, 12, 3] with automatic duration, using normal motion and safety factor 1.0."),
    ("normal_spacious_s2", 2.0, "Have UAVs 1 through 8 form a line with spacious qualitative scale centered at [0, 12, 3] with automatic duration, using normal motion and safety factor 2.0."),
)


def sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def ros_environment():
    command = (
        "source /opt/ros/humble/setup.bash && "
        f"source {WORKSPACE}/install/setup.bash && env -0"
    )
    output = subprocess.check_output(["bash", "-lc", command])
    return {
        item.split(b"=", 1)[0].decode(): item.split(b"=", 1)[1].decode()
        for item in output.split(b"\0") if b"=" in item
    }


def start(command, log, cwd=None, env=None):
    stream = log.open("w", encoding="utf-8")
    return subprocess.Popen(command, cwd=cwd, stdout=stream,
                            stderr=subprocess.STDOUT, start_new_session=True,
                            env=env), stream


def stop(process):
    if process is None or process.poll() is not None:
        return
    os.killpg(process.pid, signal.SIGINT)
    try:
        process.wait(25)
    except subprocess.TimeoutExpired:
        os.killpg(process.pid, signal.SIGKILL)
        process.wait(10)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--policy", type=Path, required=True)
    args = parser.parse_args()
    policy = args.policy.resolve()
    policy_raw = yaml.safe_load(policy.read_text(encoding="utf-8"))
    alpha = float(policy_raw["iapf_runtime"]["filter_alpha"])
    policy_hash = sha256(policy)
    configuration_id = policy_raw["configuration_id"]
    env = ros_environment()
    # Preserve every earlier attempt; reruns must never overwrite evidence.
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    raw_root = RESULTS / f"integrated_runtime_raw_locked_{stamp}_{os.getpid()}"
    raw_root.mkdir(parents=True, exist_ok=True)
    rows = []
    for name, safety_factor, command in CASES:
        output = raw_root / name
        output.mkdir(exist_ok=False)
        processes, logs, text, failure = [], [], "", ""
        started = datetime.now(timezone.utc).isoformat()
        try:
            process, log = start(
                ["MicroXRCEAgent", "udp4", "-p", "8888"],
                output / "agent.log", env=env,
            )
            processes.append(process); logs.append(log)
            process, log = start(
                ["bash", str(PX4 / "Tools/simulation/gazebo-classic/sitl_multiple_run.sh"),
                 "-n", "8", "-m", "iris"],
                output / "sitl.log", PX4, env,
            )
            processes.append(process); logs.append(log); time.sleep(18)
            if process.poll() is not None:
                raise RuntimeError("PX4/Gazebo exited during startup")
            process, log = start(
                ["ros2", "launch", "ladrc_controller", "swarm_launch.py",
                 "uav_ids:=[1,2,3,4,5,6,7,8]",
                 "control_mode:=ladrc_acceleration",
                 f"lfs_policy_file:={policy}",
                 f"iapf_filter_alpha:={alpha:.2f}"],
                output / "controllers.log", WORKSPACE, env,
            )
            processes.append(process); logs.append(log)
            ready = subprocess.run(
                [str(PYTHON), str(READY), "--uav-ids", "1,2,3,4,5,6,7,8",
                 "--timeout", "150"], cwd=REPO, env=env, text=True,
                capture_output=True, timeout=165,
            )
            (output / "readiness.log").write_text(
                ready.stdout + ready.stderr, encoding="utf-8"
            )
            if ready.returncode:
                raise RuntimeError("readiness gate failed")
            job = subprocess.run(
                [str(PYTHON), "-m", "location_allocate.candidate_dispatch",
                 "--uav-ids", "1,2,3,4,5,6,7,8", "--policy", str(policy),
                 "--command", command],
                cwd=REPO, env=env, text=True, capture_output=True, timeout=300,
            )
            text = job.stdout + job.stderr
            (output / "scheduler.log").write_text(text, encoding="utf-8")
            if job.returncode or '"candidate_completed": true' not in text:
                raise RuntimeError("Candidate mission did not complete")
        except Exception as exc:
            failure = f"{type(exc).__name__}: {exc}"
        finally:
            for process in reversed(processes): stop(process)
            for log in logs: log.close()
        finished = datetime.now(timezone.utc).isoformat()
        row = {
            "attempt": name, "uav_count": 8, "s": safety_factor,
            "control_mode": "ladrc_acceleration",
            "dispatch": "location_allocate.candidate_dispatch",
            "runtime": "UAVFormationNode/PaperMissionRuntime",
            "paper_runtime_readiness": True,
            "c0_c_prewarm_dependency": False,
            "configuration_id": configuration_id,
            "policy_sha256": policy_hash,
            "iapf_filter_alpha": alpha,
            "d_hard_m": policy_raw["safety"]["d_hard"],
            "d_plan_base_m": policy_raw["safety"]["d_plan_base"],
            "candidate_completed": not bool(failure),
            "integration_result": "PASS" if not failure else "FAIL",
            "failure_reason": failure,
            "started_utc": started, "finished_utc": finished,
            "raw_log_dir": str(output.relative_to(RESULTS)),
        }
        rows.append(row)
        (output / "manifest.yaml").write_text(
            yaml.safe_dump(row, sort_keys=False), encoding="utf-8"
        )
    with (RESULTS / "integrated_runtime_smokes.csv").open(
        "w", newline="", encoding="utf-8"
    ) as handle:
        writer = csv.DictWriter(
            handle, fieldnames=rows[0].keys(), lineterminator="\n"
        )
        writer.writeheader(); writer.writerows(rows)
    if any(row["integration_result"] != "PASS" for row in rows):
        raise SystemExit("C0-E integrated smoke failure recorded")


if __name__ == "__main__":
    main()
