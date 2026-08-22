#!/usr/bin/env python3
"""One instrumented 8-UAV C0-B handoff probe for the C0-E harness."""
from __future__ import annotations
import argparse
import os
import signal
import subprocess
import time
from pathlib import Path

PIPELINE = Path(__file__).resolve().parent
REPO = PIPELINE.parents[3]
WORKSPACE = REPO.parents[1]
PX4 = Path("/home/yihuang/PX4-Autopilot")
PYTHON = WORKSPACE / "llm_env/bin/python"
READY = REPO / "experiments-legacy/system_8uav/scripts/wait_swarm_ready.py"
PROBE = REPO / "experiments_v2/Calibration Experiments/C0-B-state-freshness/state_freshness_pipeline/phase_probe.py"


def start(command, log, cwd=None):
    stream = log.open("w")
    return subprocess.Popen(command, cwd=cwd, stdout=stream,
                            stderr=subprocess.STDOUT, start_new_session=True), stream


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
    parser = argparse.ArgumentParser()
    parser.add_argument("--policy", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--command", required=True)
    args = parser.parse_args()
    output = args.output.resolve(); output.mkdir(parents=True, exist_ok=False)
    policy = args.policy.resolve()
    processes, logs = [], []
    record = {"control_mode": "ladrc_acceleration", "readiness": None,
              "probe_returncode": None, "failure": None}
    try:
        process, log = start(["MicroXRCEAgent", "udp4", "-p", "8888"], output / "agent.log")
        processes.append(process); logs.append(log)
        process, log = start(["bash", str(PX4 / "Tools/simulation/gazebo-classic/sitl_multiple_run.sh"), "-n", "8", "-m", "iris"], output / "sitl.log", PX4)
        processes.append(process); logs.append(log); time.sleep(18)
        if process.poll() is not None: raise RuntimeError("PX4/Gazebo exited during startup")
        process, log = start(["ros2", "launch", "ladrc_controller", "swarm_launch.py", "uav_ids:=[1,2,3,4,5,6,7,8]", "control_mode:=ladrc_acceleration", f"lfs_policy_file:={policy}"], output / "controllers.log", WORKSPACE)
        processes.append(process); logs.append(log)
        ready = subprocess.run([str(PYTHON), str(READY), "--uav-ids", "1,2,3,4,5,6,7,8", "--timeout", "150"], cwd=REPO, text=True, capture_output=True, timeout=165)
        (output / "readiness.log").write_text(ready.stdout + ready.stderr)
        record["readiness"] = ready.returncode == 0
        if ready.returncode: raise RuntimeError("controller readiness failed")
        probe = subprocess.run([str(PYTHON), str(PROBE), "--uav-ids", "1,2,3,4,5,6,7,8", "--policy", str(policy), "--duration-s", "0.25", "--output-dir", str(output / "phase_probe"), "--command", args.command], cwd=REPO, text=True, capture_output=True, timeout=330)
        (output / "phase_probe.log").write_text(probe.stdout + probe.stderr)
        record["probe_returncode"] = probe.returncode
    except Exception as exc:
        record["failure"] = f"{type(exc).__name__}: {exc}"
    finally:
        for process in reversed(processes): stop(process)
        for log in logs: log.close()
    (output / "runner_result.txt").write_text(str(record) + "\n")
    if record["failure"]: raise SystemExit(record["failure"])


if __name__ == "__main__":
    main()
