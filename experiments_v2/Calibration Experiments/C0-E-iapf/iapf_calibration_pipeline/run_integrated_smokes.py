#!/usr/bin/env python3
"""Run the C0-D-deferred smokes against the frozen integrated C0-E policy."""
from __future__ import annotations
import csv
import os
import signal
import subprocess
import time
from pathlib import Path

PIPELINE = Path(__file__).resolve().parent
REPO = PIPELINE.parents[3]
WORKSPACE = REPO.parents[1]
RESULTS = PIPELINE.parent / "results" / "C0-E_iapf_freeze"
PX4 = Path("/home/yihuang/PX4-Autopilot")
PYTHON = WORKSPACE / "llm_env/bin/python"
READY = REPO / "experiments-legacy/system_8uav/scripts/wait_swarm_ready.py"
PREWARM = REPO / "experiments_v2/Calibration Experiments/C0-C-geometry-scale/geometry_scale_pipeline/candidate_owned_prewarm.py"
POLICY = REPO / "lfs_policy/config/lfs_policy.paper_current.yaml"
CASES = (
    ("compact_s1", 1.0, "Have UAVs 1 through 8 form a line with compact qualitative scale centered at [0, 12, 3] with automatic duration, using normal motion and safety factor 1.0."),
    ("crossing_prone_s1", 1.0, "Have UAVs 1 through 8 form a circle with normal qualitative scale centered at [0, 12, 3] with automatic duration, using normal motion and safety factor 1.0."),
    ("normal_spacious_s2", 2.0, "Have UAVs 1 through 8 form a line with spacious qualitative scale centered at [0, 12, 3] with automatic duration, using normal motion and safety factor 2.0."),
)


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
    # Preserve the pre-fix failed attempt; reruns must never overwrite it.
    raw_root = RESULTS / "integrated_runtime_raw_post_idle_baseline_fix"
    raw_root.mkdir(parents=True, exist_ok=True)
    rows = []
    for name, safety_factor, command in CASES:
        output = raw_root / name
        output.mkdir(exist_ok=False)
        processes, logs, text, failure = [], [], "", ""
        try:
            process, log = start(["MicroXRCEAgent", "udp4", "-p", "8888"], output / "agent.log")
            processes.append(process); logs.append(log)
            process, log = start(["bash", str(PX4 / "Tools/simulation/gazebo-classic/sitl_multiple_run.sh"), "-n", "8", "-m", "iris"], output / "sitl.log", PX4)
            processes.append(process); logs.append(log); time.sleep(18)
            if process.poll() is not None:
                raise RuntimeError("PX4/Gazebo exited during startup")
            process, log = start(["ros2", "launch", "ladrc_controller", "swarm_launch.py", "uav_ids:=[1,2,3,4,5,6,7,8]", "control_mode:=ladrc_acceleration", f"lfs_policy_file:={POLICY}"], output / "controllers.log", WORKSPACE)
            processes.append(process); logs.append(log)
            ready = subprocess.run([str(PYTHON), str(READY), "--uav-ids", "1,2,3,4,5,6,7,8", "--timeout", "150"], cwd=REPO, text=True, capture_output=True, timeout=165)
            (output / "readiness.log").write_text(ready.stdout + ready.stderr)
            if ready.returncode:
                raise RuntimeError("readiness gate failed")
            job = subprocess.run([str(PYTHON), str(PREWARM), "--uav-ids", "1,2,3,4,5,6,7,8", "--policy", str(POLICY), "--command", command], cwd=REPO, text=True, capture_output=True, timeout=300)
            text = job.stdout + job.stderr; (output / "scheduler.log").write_text(text)
            if job.returncode or '"candidate_completed": true' not in text:
                raise RuntimeError("Candidate mission did not complete")
        except Exception as exc:
            failure = f"{type(exc).__name__}: {exc}"
        finally:
            for process in reversed(processes): stop(process)
            for log in logs: log.close()
        rows.append({"attempt": name, "uav_count": 8, "s": safety_factor,
                     "control_mode": "ladrc_acceleration", "candidate_completed": not bool(failure),
                     "integration_result": "PASS" if not failure else "FAIL",
                     "failure_reason": failure, "raw_log_dir": str(output.relative_to(RESULTS))})
    with (RESULTS / "integrated_runtime_smokes.csv").open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=rows[0].keys())
        writer.writeheader(); writer.writerows(rows)
    if any(row["integration_result"] != "PASS" for row in rows):
        raise SystemExit("C0-E integrated smoke failure recorded")


if __name__ == "__main__":
    main()
