#!/usr/bin/env python3
"""Run one conditional, non-scientific large-swarm infrastructure diagnostic."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import re
import signal
import subprocess
import threading
import time
from pathlib import Path

import yaml


HERE = Path(__file__).resolve()
V2 = HERE.parents[1]
STUDY = HERE.parents[2]
V1_TOOLING = STUDY / "tooling"
PROFILE = V2 / "infrastructure_profile_v2.yaml"
RESULTS = V2 / "results"
POLICY = HERE.parents[4] / "lfs_policy/config/lfs_policy.paper_current.yaml"
POLICY_SHA = "6b47d27f4253d7311e79ea51f6dd1cf0d0182e6df24374a94abae0aa6a135858"
E5_READY = HERE.parents[3] / "Formal Evaluation Experiments/E5_v2/tooling/e5_v2_wait_ready.py"
LAUNCHER = HERE.with_name("large_swarm_controller_batch_launch.py")

import sys
sys.path.insert(0, str(V1_TOOLING))
from large_swarm_common import layout_audit, parking_layout  # noqa: E402


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def sourced_environment(install: Path, px4_root: Path, output: Path, domain: int) -> dict[str, str]:
    command = (
        "source /opt/ros/humble/setup.bash && "
        f"source '{install}/setup.bash' && "
        f"source '{px4_root}/Tools/simulation/gazebo-classic/setup_gazebo.bash' "
        f"'{px4_root}' '{px4_root}/build/px4_sitl_default' && env -0"
    )
    raw = subprocess.check_output(["bash", "-lc", command])
    env = {}
    for entry in raw.split(b"\0"):
        if b"=" in entry:
            key, value = entry.split(b"=", 1)
            env[key.decode()] = value.decode()
    env.update({
        "ROS_DOMAIN_ID": str(domain),
        "RMW_IMPLEMENTATION": "rmw_fastrtps_cpp",
        "ROS_HOME": str(output / "ros_home"),
        "PX4_SIM_MODEL": "gazebo-classic_iris",
    })
    return env


def start(command: list[str], log: Path, env: dict[str, str], cwd: Path | None = None):
    handle = log.open("w", encoding="utf-8")
    process = subprocess.Popen(command, cwd=str(cwd) if cwd else None, env=env,
                               stdout=handle, stderr=subprocess.STDOUT,
                               start_new_session=True, text=True)
    return process, handle


def pids(pattern: str, exact: bool = False) -> list[int]:
    result = subprocess.run(["pgrep", "-x" if exact else "-f", pattern], capture_output=True, text=True)
    if result.returncode not in (0, 1):
        raise RuntimeError(f"pgrep failed for {pattern}")
    return [int(value) for value in result.stdout.split()]


def scoped_pids() -> dict[str, list[int]]:
    return {
        "gzserver": pids("gzserver", True),
        "px4": pids("px4", True),
        "controllers": pids("[l]adrc_position_controller_node"),
        "agent": pids("[M]icroXRCEAgent"),
        "allocator": pids("[l]ocation_allocate"),
    }


def counts() -> dict[str, int]:
    return {name: len(values) for name, values in scoped_pids().items()}


def host_diagnostics() -> dict:
    memory = {}
    for line in Path("/proc/meminfo").read_text().splitlines():
        if line.startswith(("MemTotal:", "MemAvailable:")):
            key, value, *_ = line.split()
            memory[key.rstrip(":")] = int(value)
    scoped = scoped_pids()
    all_pids = sorted({pid for values in scoped.values() for pid in values})
    rss = 0
    if all_pids:
        result = subprocess.run(["ps", "-o", "rss=", "-p", ",".join(map(str, all_pids))], capture_output=True, text=True)
        if result.returncode == 0:
            rss = sum(int(value) for value in result.stdout.split())
    return {
        "cpu_count": os.cpu_count(),
        "load_average": [float(value) for value in Path("/proc/loadavg").read_text().split()[:3]],
        "memory_kib": memory,
        "scoped_process_rss_kib": rss,
        "scoped_process_counts": {name: len(values) for name, values in scoped.items()},
    }


def stop(process: subprocess.Popen, grace: float = 15.0) -> int | None:
    if process.poll() is not None:
        return process.returncode
    for sig in (signal.SIGINT, signal.SIGTERM, signal.SIGKILL):
        try:
            os.killpg(process.pid, sig)
        except ProcessLookupError:
            return process.poll()
        try:
            return process.wait(timeout=grace)
        except subprocess.TimeoutExpired:
            continue
    return process.poll()


def cleanup_residuals() -> dict:
    before = scoped_pids()
    for pattern, exact in (("px4", True), ("gzserver", True), ("[M]icroXRCEAgent", False), ("[l]adrc_position_controller_node", False)):
        if pids(pattern, exact):
            subprocess.run(["pkill", "-TERM", "-x" if exact else "-f", pattern], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    time.sleep(3)
    after = scoped_pids()
    return {"before": before, "after": after, "success": not any(after.values())}


def generate_sdf(uid: int, px4_root: Path, output: Path, env: dict[str, str]) -> Path:
    source = px4_root / "Tools/simulation/gazebo-classic/sitl_gazebo-classic"
    generator = source / "scripts/jinja_gen.py"
    template = source / "models/iris/iris.sdf.jinja"
    sdf = output / f"iris_{uid}.sdf"
    command = ["python3", str(generator), str(template), str(source),
               "--mavlink_tcp_port", str(4560 + uid), "--mavlink_udp_port", str(14560 + uid),
               "--mavlink_id", str(uid + 1), "--gst_udp_port", str(5600 + uid),
               "--video_uri", str(5600 + uid), "--mavlink_cam_udp_port", str(14530 + uid),
               "--output-file", str(sdf)]
    result = subprocess.run(command, env=env, capture_output=True, text=True)
    if result.returncode or not sdf.exists():
        raise RuntimeError(f"SDF generation failed for UAV {uid}: {result.stderr}")
    return sdf


def writer_gate(log: Path, timeout: float) -> tuple[bool, float, dict]:
    started = time.monotonic()
    last = ""
    while time.monotonic() - started < timeout:
        if log.exists():
            last = log.read_text(encoding="utf-8", errors="replace")
            flags = {
                "sim_connected": "Simulator connected" in last,
                "dds_synchronized": "synchronized with time offset" in last,
                "vehicle_odometry_writer": "vehicle_odometry data writer" in last,
                "vehicle_status_writer": "vehicle_status data writer" in last,
            }
            if all(flags.values()):
                return True, time.monotonic() - started, flags
        time.sleep(0.2)
    flags = {
        "sim_connected": "Simulator connected" in last,
        "dds_synchronized": "synchronized with time offset" in last,
        "vehicle_odometry_writer": "vehicle_odometry data writer" in last,
        "vehicle_status_writer": "vehicle_status data writer" in last,
    }
    return False, time.monotonic() - started, flags


def time_series_sampler(output: Path, stage_ref: dict, stop_event: threading.Event, started: float) -> None:
    path = output / "diagnostic_time_series.jsonl"
    while not stop_event.is_set():
        px4_progress = {}
        for log in sorted(output.glob("px4_*.log")):
            uid = int(log.stem.split("_")[1])
            text = log.read_text(encoding="utf-8", errors="replace")
            px4_progress[str(uid)] = {
                "sim_connected": "Simulator connected" in text,
                "dds_synchronized": "synchronized with time offset" in text,
                "odometry_writer": "vehicle_odometry data writer" in text,
                "status_writer": "vehicle_status data writer" in text,
                "height_unstable": "height estimate not stable" in text,
                "failsafe_logged": "Failsafe activated" in text,
            }
        record = {
            "elapsed_wall_s": time.monotonic() - started,
            "stage": stage_ref["value"],
            "host": host_diagnostics(),
            "px4_progress": px4_progress,
        }
        with path.open("a", encoding="utf-8") as stream:
            stream.write(json.dumps(record, sort_keys=True) + "\n")
        stop_event.wait(1.0)


def run(n: int, install: Path, px4_root: Path) -> tuple[dict, Path]:
    profile = yaml.safe_load(PROFILE.read_text(encoding="utf-8"))
    if profile["status"] != "FROZEN_BEFORE_PROFILE_V2_EXECUTION" or profile["test_order"] != [24, 28, 32]:
        raise RuntimeError("profile v2 is not prospectively frozen")
    if sha256_file(POLICY) != POLICY_SHA or layout_audit()["status"] != "PASS":
        raise RuntimeError("frozen policy/layout identity mismatch")
    output = RESULTS / f"N{n}"
    if output.exists():
        raise RuntimeError(f"refusing to overwrite retained profile-v2 evidence: {output}")
    output.mkdir(parents=True)
    (output / "ros_home").mkdir()
    layout = parking_layout(n)
    layout_path = output / "layout.json"
    layout_path.write_text(json.dumps({"N": n, "positions": layout}, indent=2, sort_keys=True) + "\n")
    runtime = profile["fixed_runtime"]
    change = profile["profile_differences_from_v1"]
    env = sourced_environment(install, px4_root, output, int(runtime["ros_domain_id"]))
    result = {
        "schema": "large_swarm_infrastructure_diagnostic_result_v2",
        "N_requested": n,
        "dataset_class": "supplementary_infrastructure_diagnostic",
        "accepted_formal_result": False,
        "scientific_mission": False,
        "llm_calls": 0,
        "candidate_commands": 0,
        "formation_commands": 0,
        "profile_sha256": sha256_file(PROFILE),
        "policy_sha256": POLICY_SHA,
        "layout_sha256": sha256_file(layout_path),
        "success": False,
        "startup_failure_stage": None,
        "host_diagnostics_before": host_diagnostics(),
    }
    initial = counts()
    result["initial_process_counts"] = initial
    if any(initial.values()):
        raise RuntimeError(f"pre-existing scoped processes: {initial}")
    processes = []
    handles = []
    stage_ref = {"value": "preflight"}
    started = time.monotonic()
    sampler_stop = threading.Event()
    sampler = threading.Thread(target=time_series_sampler, args=(output, stage_ref, sampler_stop, started), daemon=True)
    sampler.start()
    try:
        stage_ref["value"] = "micro_xrce_agent"
        process, handle = start(["MicroXRCEAgent", "udp4", "-p", "8888"], output / "agent.log", env)
        processes.append(process); handles.append(handle)
        stage_ref["value"] = "gzserver"
        world = px4_root / "Tools/simulation/gazebo-classic/sitl_gazebo-classic/worlds/empty.world"
        process, handle = start(["gzserver", str(world), "--verbose", "-s", "libgazebo_ros_init.so", "-s", "libgazebo_ros_factory.so"], output / "gzserver.log", env)
        processes.append(process); handles.append(handle)
        time.sleep(6)
        stage_ref["value"] = "staged_px4_and_model_spawn"
        build = px4_root / "build/px4_sitl_default"
        spawn_records = []
        writer_records = []
        gate_timeout = float(change["px4_startup"]["per_instance_writer_gate_timeout_s"])
        settle = float(change["px4_startup"]["inter_instance_settle_s"])
        for position in layout:
            uid = int(position["uav_id"])
            sdf = generate_sdf(uid, px4_root, output, env)
            work = build / "rootfs" / str(uid - 1)
            work.mkdir(parents=True, exist_ok=True)
            px4_log = output / f"px4_{uid}.log"
            process, handle = start([str(build / "bin/px4"), "-i", str(uid), "-d", str(build / "etc")], px4_log, env, work)
            processes.append(process); handles.append(handle)
            spawned = subprocess.run(["gz", "model", f"--spawn-file={sdf}", f"--model-name=iris_{uid}",
                                      "-x", str(position["x"]), "-y", str(position["y"]), "-z", str(position["z"])],
                                     env=env, capture_output=True, text=True, timeout=30)
            spawn_records.append({"uav_id": uid, "returncode": spawned.returncode,
                                  "stdout_sha256": hashlib.sha256(spawned.stdout.encode()).hexdigest(),
                                  "stderr": spawned.stderr[-1000:]})
            if spawned.returncode:
                raise RuntimeError(f"Gazebo model spawn failed for UAV {uid}")
            ok, elapsed, flags = writer_gate(px4_log, gate_timeout)
            writer_records.append({"uav_id": uid, "success": ok, "elapsed_s": elapsed, **flags})
            if not ok:
                raise RuntimeError(f"per-instance PX4/XRCE writer gate failed for UAV {uid}")
            time.sleep(settle)
        result["spawn_records"] = spawn_records
        result["px4_writer_gate_records"] = writer_records
        result["models_spawned"] = len(spawn_records)
        result["stage_A_success"] = len(writer_records) == n and all(record["success"] for record in writer_records)
        result["process_counts_after_spawn"] = counts()
        if result["process_counts_after_spawn"]["px4"] != n:
            raise RuntimeError("exact PX4 process-count gate failed after staged spawn")
        stage_ref["value"] = "batched_controller_startup"
        swarm_ids = list(range(1, n + 1))
        all_ids_text = "[" + ",".join(map(str, swarm_ids)) + "]"
        batch_size = int(change["controller_startup"]["batch_size"])
        interval = float(change["controller_startup"]["inter_batch_interval_s"])
        batches = [swarm_ids[index:index + batch_size] for index in range(0, n, batch_size)]
        batch_records = []
        for index, batch in enumerate(batches, start=1):
            batch_text = "[" + ",".join(map(str, batch)) + "]"
            command = ["ros2", "launch", str(LAUNCHER), f"layout_json:={layout_path}",
                       f"launch_uav_ids:={batch_text}", f"swarm_uav_ids:={all_ids_text}",
                       f"lfs_policy_file:={POLICY}", "control_mode:=ladrc_acceleration",
                       "avoidance_mode:=iapf_dual", "iapf_escape_mode:=id_order"]
            process, handle = start(command, output / f"controllers_batch_{index:02d}.log", env)
            processes.append(process); handles.append(handle)
            batch_records.append({"batch_index": index, "uav_ids": batch,
                                  "launch_elapsed_wall_s": time.monotonic() - started})
            if index != len(batches):
                time.sleep(interval)
        result["controller_batches"] = batch_records
        controller_wait_started = time.monotonic()
        while time.monotonic() - controller_wait_started < 30 and counts()["controllers"] != n:
            time.sleep(0.5)
        result["process_counts_after_controller_startup"] = counts()
        if result["process_counts_after_controller_startup"]["controllers"] != n:
            raise RuntimeError("exact controller process-count gate failed")
        stage_ref["value"] = "frozen_readiness"
        readiness_started = time.monotonic()
        ready = subprocess.run(["/usr/bin/python3", str(E5_READY), "--uav-ids", ",".join(map(str, swarm_ids)),
                                "--timeout", str(runtime["readiness_timeout_s"]), "--hold", str(runtime["readiness_hold_s"]),
                                "--freshness", str(runtime["freshness_timeout_s"]),
                                "--minimum-altitude", str(runtime["minimum_altitude_m"]),
                                "--speed-tolerance", str(runtime["speed_tolerance_mps"])],
                               env=env, capture_output=True, text=True,
                               timeout=float(runtime["readiness_timeout_s"]) + 30)
        (output / "readiness.stdout.json").write_text(ready.stdout)
        (output / "readiness.stderr.log").write_text(ready.stderr)
        readiness = json.loads(ready.stdout) if ready.stdout.strip() else {}
        diagnostics = readiness.get("diagnostics", {})
        states = readiness.get("state_diagnostics", {})
        current = counts()
        result.update({
            "readiness_success": ready.returncode == 0 and bool(readiness.get("ready")),
            "readiness_elapsed_s": readiness.get("elapsed_s", time.monotonic() - readiness_started),
            "stable_hover_duration_s": float(runtime["readiness_hold_s"]),
            "fresh_state_count": sum(bool(value.get("present")) and float(value.get("age_s", math.inf)) <= float(runtime["freshness_timeout_s"]) for value in states.values()),
            "armed_offboard_count": sum(bool(value.get("armed")) and bool(value.get("offboard")) for value in diagnostics.values()),
            "failsafe_count": sum(bool(value.get("failsafe")) for value in diagnostics.values()),
            "all_states_finite": bool(readiness.get("all_states_finite")),
            "process_counts_at_readiness": current,
            "micro_xrce_agent_alive": current["agent"] == 1,
            "gzserver_alive": current["gzserver"] == 1,
            "host_diagnostics_at_readiness": host_diagnostics(),
            "gazebo_real_time_factor": {"available": False, "reason": "no reliable low-intrusion parseable source"},
        })
        gates = [result["models_spawned"] == n, current["px4"] == n, current["controllers"] == n,
                 result["micro_xrce_agent_alive"], result["gzserver_alive"],
                 result["armed_offboard_count"] == n, result["fresh_state_count"] == n,
                 result["readiness_success"], result["all_states_finite"], result["failsafe_count"] == 0]
        if not all(gates):
            raise RuntimeError("one or more unchanged infrastructure PASS gates failed")
        result["success"] = True
    except Exception as exc:
        result["startup_failure_stage"] = stage_ref["value"]
        result["failure"] = f"{type(exc).__name__}: {exc}"
    finally:
        stage_ref["value"] = "cleanup"
        result["process_exit_status"] = [stop(process, float(runtime["cleanup_grace_s"])) for process in reversed(processes)]
        for handle in handles:
            handle.close()
        result["cleanup"] = cleanup_residuals()
        if not result["cleanup"]["success"]:
            result["success"] = False
            result["failure"] = result.get("failure") or "cleanup residual gate failed"
        sampler_stop.set()
        sampler.join(timeout=3)
        result["host_diagnostics_after"] = host_diagnostics()
        result["elapsed_total_s"] = time.monotonic() - started
        result["evidence_file_hashes"] = {path.name: sha256_file(path) for path in sorted(output.iterdir()) if path.is_file() and path.name != "result.json"}
        (output / "result.json").write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    return result, output


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--n", type=int, required=True, choices=(24, 28, 32))
    parser.add_argument("--install", type=Path, default=Path("/home/yihuang/learning/LLM_swarm_ws/e5_v2_build/install"))
    parser.add_argument("--px4-root", type=Path, default=Path("/home/yihuang/PX4-Autopilot"))
    args = parser.parse_args()
    result, output = run(args.n, args.install.resolve(), args.px4_root.resolve())
    print(json.dumps({"N": args.n, "success": result["success"], "failure": result.get("failure"), "output": str(output)}, sort_keys=True))
    return 0 if result["success"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
