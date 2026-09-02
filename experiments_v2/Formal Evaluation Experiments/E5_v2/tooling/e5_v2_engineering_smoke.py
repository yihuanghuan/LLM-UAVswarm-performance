#!/usr/bin/env python3
"""Run one non-formal spawn/hover/readiness/cleanup smoke for registered N."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import re
import signal
import subprocess
import time
from pathlib import Path

from e5_v2_common import E5_DIR, REPO_ROOT, load_yaml, sha256_file, uav_ids


PROTOCOL = E5_DIR / "E5_v2_engineering_scale_smoke_protocol.yaml"
READY = Path(__file__).with_name("e5_v2_wait_ready.py")


def sourced_environment(install: Path, ros_domain_id: int, output: Path):
    command = (
        "source /opt/ros/humble/setup.bash && "
        f"source {install}/setup.bash && env -0"
    )
    raw = subprocess.check_output(["bash", "-lc", command])
    environment = {}
    for item in raw.split(b"\0"):
        if b"=" in item:
            key, value = item.split(b"=", 1)
            environment[key.decode()] = value.decode()
    environment.update({
        "ROS_DOMAIN_ID": str(ros_domain_id),
        "RMW_IMPLEMENTATION": "rmw_fastrtps_cpp",
        "ROS_HOME": str(output / "ros_home"),
        "PYTHONPATH": (
            str(REPO_ROOT / "location_allocate") + ":" +
            str(REPO_ROOT / "lfs_policy") + ":" +
            environment.get("PYTHONPATH", "")
        ),
    })
    return environment


def start(command, log_path: Path, *, cwd: Path | None, environment):
    handle = log_path.open("w", encoding="utf-8")
    process = subprocess.Popen(
        command,
        cwd=None if cwd is None else str(cwd),
        env=environment,
        stdout=handle,
        stderr=subprocess.STDOUT,
        start_new_session=True,
        text=True,
    )
    return process, handle


def pids(pattern: str, exact: bool = False):
    command = ["pgrep", "-x" if exact else "-f", pattern]
    completed = subprocess.run(command, capture_output=True, text=True)
    if completed.returncode not in (0, 1):
        raise RuntimeError(f"pgrep failed for {pattern}")
    return [int(value) for value in completed.stdout.split()]


def counts():
    return {
        "gzserver": len(pids("gzserver", exact=True)),
        "px4": len(pids("px4", exact=True)),
        "controllers": len(pids("ladrc_position_controller_node")),
        "agent": len(pids("MicroXRCEAgent")),
        "location_allocator": len(pids("location_allocate")),
    }


def wait_for_spawn(n: int, timeout: float):
    started = time.monotonic()
    last = counts()
    while time.monotonic() - started < timeout:
        last = counts()
        if last["gzserver"] >= 1 and last["px4"] == n:
            return True, time.monotonic() - started, last
        time.sleep(1.0)
    return False, time.monotonic() - started, last


def host_diagnostics():
    memory = {}
    for line in Path("/proc/meminfo").read_text(encoding="utf-8").splitlines():
        if line.startswith(("MemTotal:", "MemAvailable:")):
            key, value, *_ = line.split()
            memory[key.rstrip(":")] = int(value)
    load = [float(value) for value in Path("/proc/loadavg").read_text().split()[:3]]
    return {"memory_kib": memory, "load_average": load, "cpu_count": os.cpu_count()}


def gazebo_stats(environment):
    try:
        completed = subprocess.run(
            ["timeout", "4", "gz", "stats", "-p"],
            env=environment,
            capture_output=True,
            text=True,
            timeout=6,
        )
        values = [
            float(match.group(1))
            for match in re.finditer(
                r"real[_ ]time[_ ]factor\s*[:=]\s*([0-9.eE+-]+)",
                completed.stdout,
                flags=re.IGNORECASE,
            )
        ]
        return {
            "available": bool(values),
            "real_time_factor_samples": values,
            "stdout_sha256": hashlib.sha256(
                completed.stdout.encode("utf-8")
            ).hexdigest(),
            "returncode": completed.returncode,
        }
    except Exception as exc:
        return {"available": False, "error": f"{type(exc).__name__}: {exc}"}


def stop_process(process: subprocess.Popen, grace: float = 12.0):
    if process.poll() is not None:
        return process.returncode
    try:
        os.killpg(process.pid, signal.SIGINT)
        return process.wait(timeout=grace)
    except subprocess.TimeoutExpired:
        os.killpg(process.pid, signal.SIGTERM)
        try:
            return process.wait(timeout=grace)
        except subprocess.TimeoutExpired:
            os.killpg(process.pid, signal.SIGKILL)
            return process.wait(timeout=grace)


def scoped_residual_cleanup():
    targets = (
        ("px4", True),
        ("gzserver", True),
        ("gzclient", True),
        ("MicroXRCEAgent", False),
        ("ladrc_position_controller_node", False),
    )
    before = {name: pids(name, exact) for name, exact in targets}
    for name, exact in targets:
        if before[name]:
            subprocess.run(
                ["pkill", "-TERM", "-x" if exact else "-f", name],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
    time.sleep(2.0)
    after = {name: pids(name, exact) for name, exact in targets}
    return before, after


def run_smoke(n: int, install: Path, px4_root: Path, output_root: Path):
    protocol = load_yaml(PROTOCOL)
    entry = next(item for item in protocol["smokes"] if int(item["N"]) == n)
    ids = uav_ids(n)
    if entry["uav_ids"] != ids:
        raise ValueError("protocol ID enumeration mismatch")
    output = output_root / f"N{n}_seed{entry['engineering_seed']}"
    if output.exists():
        raise RuntimeError(f"refusing to overwrite retained smoke evidence: {output}")
    output.mkdir(parents=True)
    (output / "ros_home").mkdir()
    environment = sourced_environment(install, 70 + n, output)
    runtime = protocol["fixed_runtime"]
    processes = []
    handles = []
    started = time.monotonic()
    result = {
        "smoke_id": entry["smoke_id"],
        "N": n,
        "uav_ids": ids,
        "engineering_seed": int(entry["engineering_seed"]),
        "dataset_class": "engineering_validation",
        "accepted_formal_result": False,
        "scientific_mission": False,
        "formal_trial_id": None,
        "formal_journal_entry": False,
        "candidate_payload_submitted": False,
        "command_publications": 0,
        "baseline_commit": protocol["baseline_commit"],
        "configuration_id": protocol["configuration_id"],
        "protocol_sha256": sha256_file(PROTOCOL),
        "success": False,
        "failure": None,
    }
    initial_residual = counts()
    result["initial_process_counts"] = initial_residual
    if any(initial_residual[key] for key in ("gzserver", "px4", "controllers", "agent")):
        result["failure"] = "pre-existing scoped simulator/controller process"
        (output / "smoke_result.json").write_text(
            json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        return result, output
    try:
        agent, handle = start(
            ["MicroXRCEAgent", "udp4", "-p", "8888"],
            output / "agent.log", cwd=None, environment=environment,
        )
        processes.append(agent)
        handles.append(handle)
        sitl, handle = start(
            [
                "bash",
                str(px4_root / "Tools/simulation/gazebo-classic/sitl_multiple_run.sh"),
                "-n", str(n), "-m", "iris", "-w", "empty",
            ],
            output / "sitl.log", cwd=px4_root, environment=environment,
        )
        processes.append(sitl)
        handles.append(handle)
        spawn_ok, spawn_elapsed, spawn_counts = wait_for_spawn(
            n, float(runtime["simulator_spawn_timeout_s"])
        )
        result.update({
            "spawn_ready": spawn_ok,
            "spawn_elapsed_s": spawn_elapsed,
            "process_counts_after_spawn": spawn_counts,
        })
        if not spawn_ok:
            raise RuntimeError("spawn process-count gate failed")

        ids_launch = "[" + ",".join(str(value) for value in ids) + "]"
        controllers, handle = start(
            [
                "ros2", "launch", "ladrc_controller", "swarm_launch.py",
                f"uav_ids:={ids_launch}",
                "control_mode:=ladrc_acceleration",
                "avoidance_mode:=iapf_dual",
                "iapf_escape_mode:=id_order",
                f"lfs_policy_file:={REPO_ROOT / 'lfs_policy/config/lfs_policy.paper_current.yaml'}",
            ],
            output / "controllers.log", cwd=REPO_ROOT, environment=environment,
        )
        processes.append(controllers)
        handles.append(handle)

        ready_started = time.monotonic()
        ready = subprocess.run(
            [
                "python3", str(READY),
                "--uav-ids", ",".join(str(value) for value in ids),
                "--timeout", str(runtime["readiness_timeout_s"]),
                "--hold", str(runtime["readiness_hold_s"]),
                "--freshness", str(runtime["freshness_timeout_s"]),
                "--minimum-altitude", str(runtime["minimum_altitude_m"]),
                "--speed-tolerance", str(runtime["speed_tolerance_mps"]),
            ],
            cwd=REPO_ROOT,
            env=environment,
            capture_output=True,
            text=True,
            timeout=float(runtime["readiness_timeout_s"]) + 20.0,
        )
        (output / "readiness.stdout.json").write_text(
            ready.stdout, encoding="utf-8"
        )
        (output / "readiness.stderr.log").write_text(
            ready.stderr, encoding="utf-8"
        )
        readiness = json.loads(ready.stdout) if ready.stdout.strip() else {}
        process_counts = counts()
        result.update({
            "readiness_returncode": ready.returncode,
            "readiness_elapsed_wall_s": time.monotonic() - ready_started,
            "readiness": readiness,
            "process_counts_at_readiness": process_counts,
            "host_diagnostics_at_readiness": host_diagnostics(),
            "gazebo_stats": gazebo_stats(environment),
        })
        if ready.returncode != 0 or not readiness.get("ready"):
            raise RuntimeError("continuous readiness gate failed")
        if process_counts["px4"] != n or process_counts["controllers"] != n:
            raise RuntimeError("exact PX4/controller count gate failed")
        if process_counts["gzserver"] < 1 or process_counts["agent"] < 1:
            raise RuntimeError("gzserver/agent liveness gate failed")
        if process_counts["location_allocator"] != 0:
            raise RuntimeError("scientific allocator process unexpectedly present")
        if not readiness.get("all_states_finite"):
            raise RuntimeError("non-finite readiness state")
        time.sleep(float(runtime["post_readiness_observation_s"]))
        result["success"] = True
    except Exception as exc:
        result["failure"] = f"{type(exc).__name__}: {exc}"
    finally:
        result["process_exit_status"] = [
            stop_process(process) for process in reversed(processes)
        ]
        for handle in handles:
            handle.close()
        before_cleanup, after_cleanup = scoped_residual_cleanup()
        result["cleanup"] = {
            "residual_before_scoped_cleanup": before_cleanup,
            "residual_after_scoped_cleanup": after_cleanup,
            "success": not any(after_cleanup.values()),
        }
        result["elapsed_total_s"] = time.monotonic() - started
        if not result["cleanup"]["success"]:
            result["success"] = False
            result["failure"] = result["failure"] or "residual process cleanup failed"
        result["log_sha256"] = {
            path.name: sha256_file(path)
            for path in output.iterdir()
            if path.is_file() and path.name != "smoke_result.json"
        }
        (output / "smoke_result.json").write_text(
            json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
    return result, output


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--n", type=int, required=True, choices=(8, 12, 16))
    parser.add_argument("--install", type=Path, required=True)
    parser.add_argument("--px4-root", type=Path, default=Path("/home/yihuang/PX4-Autopilot"))
    parser.add_argument("--output-root", type=Path, required=True)
    args = parser.parse_args()
    result, output = run_smoke(
        args.n, args.install.resolve(), args.px4_root.resolve(), args.output_root.resolve()
    )
    print(json.dumps({
        "success": result["success"],
        "N": result["N"],
        "failure": result["failure"],
        "output": str(output),
    }, sort_keys=True))
    return 0 if result["success"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
