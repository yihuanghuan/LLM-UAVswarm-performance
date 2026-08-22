#!/usr/bin/env python3
"""Execute the nine predeclared C0-C cold-start smoke cases.

The candidate overlay is temporary.  This script never writes the canonical
Paper policy and records one compact result row for every completed attempt.
"""
from __future__ import annotations

import csv
import argparse
import json
import os
from pathlib import Path
import signal
import subprocess
import tempfile
import time

import yaml

PIPELINE = Path(__file__).resolve().parent
REPO = PIPELINE.parents[3]
WORKSPACE = REPO.parents[1]
RESULTS = PIPELINE.parent / "results" / "C0-C_geometry_scale_freeze"
PX4 = Path("/home/yihuang/PX4-Autopilot")
PYTHON = WORKSPACE / "llm_env" / "bin" / "python"
READY = REPO / "experiments-legacy/system_8uav/scripts/wait_swarm_ready.py"

CASES = [("Triangle", 3, [0, 6, 3]), ("Line", 8, [0, 12, 3]),
         ("Sphere", 8, [0, 18, 5])]
LABELS = ("compact", "normal", "spacious")


def start(command, log, cwd=None):
    handle = log.open("w", encoding="utf-8")
    return subprocess.Popen(command, cwd=cwd, stdout=handle,
                            stderr=subprocess.STDOUT, text=True,
                            start_new_session=True), handle


def stop(process):
    if process and process.poll() is None:
        os.killpg(process.pid, signal.SIGINT)
        try:
            process.wait(25)
        except subprocess.TimeoutExpired:
            os.killpg(process.pid, signal.SIGKILL)
            process.wait(10)


def command(formation, count, center, label):
    ids = f"1 through {count}"
    return (f"Have UAVs {ids} form a {formation.lower()} with {label} qualitative scale centered at "
            f"[{center[0]}, {center[1]}, {center[2]}] with automatic duration, "
            "using normal motion and safety factor 1.0.")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--only", help="formation:label; rerun one diagnosed smoke case")
    args = parser.parse_args()
    RESULTS.mkdir(parents=True, exist_ok=True)
    baseline = yaml.safe_load((REPO / "lfs_policy/config/lfs_policy.paper_current.yaml").read_text())
    baseline["geometry"]["nominal_spacing"] = 2.25
    baseline["geometry"]["qualitative_multipliers"] = {"compact": .8, "normal": 1., "spacious": 1.25}
    baseline["configuration_id"] = "paper-current-v8-c0-b-frozen+c0-c-candidate"
    rows = []
    with tempfile.TemporaryDirectory(prefix="c0c-policy-") as temp:
        policy = Path(temp) / "candidate.yaml"
        policy.write_text(yaml.safe_dump(baseline, sort_keys=False), encoding="utf-8")
        for index, (formation, count, center) in enumerate(CASES, 1):
            formation_failure = False
            for label in LABELS:
                if args.only and args.only != f"{formation.lower()}:{label}":
                    continue
                name = f"{index}_{formation.lower()}_{count}u_{label}"
                output = RESULTS / "runtime_raw" / (name + ("_prewarm2" if args.only else ""))
                output.mkdir(parents=True, exist_ok=False)
                procs, logs, failure, scheduler_text = [], [], "", ""
                try:
                    agent, log = start(["MicroXRCEAgent", "udp4", "-p", "8888"], output / "agent.log")
                    procs.append(agent); logs.append(log)
                    sitl, log = start(["bash", str(PX4 / "Tools/simulation/gazebo-classic/sitl_multiple_run.sh"), "-n", str(count), "-m", "iris"], output / "sitl.log", PX4)
                    procs.append(sitl); logs.append(log); time.sleep(18)
                    if sitl.poll() is not None: raise RuntimeError("PX4/Gazebo exited during startup")
                    ids = ",".join(map(str, range(1, count + 1)))
                    ctl, log = start(["ros2", "launch", "ladrc_controller", "swarm_launch.py", f"uav_ids:=[{ids}]", "control_mode:=ladrc_acceleration", f"lfs_policy_file:={policy}"], output / "controllers.log", WORKSPACE)
                    procs.append(ctl); logs.append(log)
                    ready = subprocess.run([str(PYTHON), str(READY), "--uav-ids", ids, "--timeout", "150"], cwd=REPO, text=True, capture_output=True, timeout=165)
                    (output / "readiness.log").write_text(ready.stdout + ready.stderr, encoding="utf-8")
                    if ready.returncode: raise RuntimeError("readiness gate failed")
                    result = subprocess.run([str(PYTHON), str(PIPELINE / "candidate_owned_prewarm.py"), "--uav-ids", ids, "--policy", str(policy), "--command", command(formation,count,center,label)], cwd=REPO, text=True, capture_output=True, timeout=300)
                    scheduler_text = result.stdout + result.stderr
                    (output / "scheduler.log").write_text(scheduler_text, encoding="utf-8")
                    if result.returncode or '"candidate_completed": true' not in scheduler_text:
                        raise RuntimeError("Candidate mission did not complete")
                except Exception as exc:
                    failure = f"{type(exc).__name__}: {exc}"
                finally:
                    for proc in reversed(procs): stop(proc)
                    for log in logs: log.close()
                trace = next((line for line in scheduler_text.splitlines() if "r_exec" in line), "")
                rows.append({"formation":formation,"uav_count":count,"label":label,
                             "candidate_completed":not failure,"geometry_valid":not failure,
                             "workspace_rejection":"workspace" in scheduler_text.lower(),
                             "resolution_trace":trace,"r_requested":2.25*{"compact":.8,"normal":1,"spacious":1.25}[label],
                             "r_safe":2.0,"r_exec":"see resolution_trace","freshness_failures":"stale" in scheduler_text.lower(),
                             "controller_saturation_or_unexpected_failure":failure or "none",
                             "raw_log_dir":str(output.relative_to(RESULTS))})
                if failure:
                    formation_failure = True
                    break
            if formation_failure: break
    fields = list(rows[0])
    with (RESULTS / "runtime_smoke_metrics.csv").open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields, lineterminator="\n"); writer.writeheader(); writer.writerows(rows)
    if any(row["controller_saturation_or_unexpected_failure"] != "none" for row in rows):
        raise SystemExit("C0-C runtime smoke failed; see runtime_smoke_metrics.csv")

if __name__ == "__main__": main()
