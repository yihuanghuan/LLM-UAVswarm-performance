#!/usr/bin/env python3
"""Run one retained, non-scientific supplementary infrastructure smoke."""

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

import yaml

from large_swarm_common import POLICY, POLICY_SHA, PROTOCOL, RESULTS, SIZES, layout_audit, parking_layout, sha256_file

LAUNCHER = Path(__file__).with_name("large_swarm_controller_launch.py")
E5_READY = Path(__file__).resolve().parents[2] / "Formal Evaluation Experiments/E5_v2/tooling/e5_v2_wait_ready.py"


def sourced_environment(install: Path, px4_root: Path, output: Path, domain: int) -> dict[str, str]:
    command = (
        "source /opt/ros/humble/setup.bash && "
        f"source '{install}/setup.bash' && "
        f"source '{px4_root}/Tools/simulation/gazebo-classic/setup_gazebo.bash' "
        f"'{px4_root}' '{px4_root}/build/px4_sitl_default' && env -0"
    )
    raw = subprocess.check_output(["bash", "-lc", command])
    env: dict[str, str] = {}
    for entry in raw.split(b"\0"):
        if b"=" in entry:
            key, value = entry.split(b"=", 1)
            env[key.decode()] = value.decode()
    env.update({
        "ROS_DOMAIN_ID": str(domain), "RMW_IMPLEMENTATION": "rmw_fastrtps_cpp",
        "ROS_HOME": str(output / "ros_home"), "PX4_SIM_MODEL": "gazebo-classic_iris",
    })
    return env


def start(command: list[str], log: Path, env: dict[str, str], cwd: Path | None = None):
    handle = log.open("w", encoding="utf-8")
    process = subprocess.Popen(command, cwd=str(cwd) if cwd else None, env=env, stdout=handle, stderr=subprocess.STDOUT, start_new_session=True, text=True)
    return process, handle


def pids(pattern: str, exact: bool = False) -> list[int]:
    command = ["pgrep", "-x" if exact else "-f", pattern]
    result = subprocess.run(command, capture_output=True, text=True)
    if result.returncode not in (0, 1):
        raise RuntimeError(f"pgrep failed for {pattern}")
    return [int(value) for value in result.stdout.split()]


def scoped_pids() -> dict[str, list[int]]:
    return {
        "gzserver": pids("gzserver", True), "px4": pids("px4", True),
        "controllers": pids("[l]adrc_position_controller_node"),
        "agent": pids("[M]icroXRCEAgent"), "allocator": pids("[l]ocation_allocate"),
    }


def counts() -> dict[str, int]:
    return {key: len(value) for key, value in scoped_pids().items()}


def host_diagnostics() -> dict:
    memory = {}
    for line in Path("/proc/meminfo").read_text().splitlines():
        if line.startswith(("MemTotal:", "MemAvailable:")):
            key, value, *_ = line.split(); memory[key.rstrip(":")] = int(value)
    scoped = scoped_pids()
    all_pids = sorted({pid for values in scoped.values() for pid in values})
    rss = 0
    if all_pids:
        result = subprocess.run(["ps", "-o", "rss=", "-p", ",".join(map(str, all_pids))], capture_output=True, text=True)
        if result.returncode == 0:
            rss = sum(int(value) for value in result.stdout.split())
    return {
        "cpu_count": os.cpu_count(), "load_average": [float(x) for x in Path("/proc/loadavg").read_text().split()[:3]],
        "memory_kib": memory, "scoped_process_rss_kib": rss, "scoped_process_counts": {k: len(v) for k, v in scoped.items()},
    }


def gazebo_stats(env: dict[str, str]) -> dict:
    try:
        result = subprocess.run(["timeout", "5", "gz", "stats", "-p"], env=env, capture_output=True, text=True, timeout=7)
        values = [float(x) for x in re.findall(r"real[_ ]time[_ ]factor\s*[:=]\s*([0-9.eE+-]+)", result.stdout, re.I)]
        return {"available": bool(values), "real_time_factor_samples": values, "returncode": result.returncode, "stdout_sha256": hashlib.sha256(result.stdout.encode()).hexdigest()}
    except Exception as exc:
        return {"available": False, "error": f"{type(exc).__name__}: {exc}"}


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
    targets = [("px4", True), ("gzserver", True), ("[M]icroXRCEAgent", False), ("[l]adrc_position_controller_node", False)]
    for pattern, exact in targets:
        if pids(pattern, exact):
            subprocess.run(["pkill", "-TERM", "-x" if exact else "-f", pattern], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    time.sleep(3)
    after = scoped_pids()
    return {"before": before, "after": after, "success": not any(after.values())}


def wait_counts(n: int, timeout: float) -> tuple[bool, float, dict[str, int]]:
    start_time = time.monotonic(); last = counts()
    while time.monotonic() - start_time < timeout:
        last = counts()
        if last["gzserver"] == 1 and last["px4"] == n:
            return True, time.monotonic() - start_time, last
        time.sleep(1)
    return False, time.monotonic() - start_time, last


def generate_sdf(uid: int, px4_root: Path, output: Path, env: dict[str, str]) -> Path:
    generator = px4_root / "Tools/simulation/gazebo-classic/sitl_gazebo-classic/scripts/jinja_gen.py"
    template = px4_root / "Tools/simulation/gazebo-classic/sitl_gazebo-classic/models/iris/iris.sdf.jinja"
    source = px4_root / "Tools/simulation/gazebo-classic/sitl_gazebo-classic"
    sdf = output / f"iris_{uid}.sdf"
    command = ["python3", str(generator), str(template), str(source), "--mavlink_tcp_port", str(4560 + uid), "--mavlink_udp_port", str(14560 + uid), "--mavlink_id", str(uid + 1), "--gst_udp_port", str(5600 + uid), "--video_uri", str(5600 + uid), "--mavlink_cam_udp_port", str(14530 + uid), "--output-file", str(sdf)]
    result = subprocess.run(command, env=env, capture_output=True, text=True)
    if result.returncode != 0 or not sdf.exists():
        raise RuntimeError(f"SDF generation failed for UAV {uid}: {result.stderr}")
    return sdf


def run(n: int, install: Path, px4_root: Path) -> tuple[dict, Path]:
    protocol = yaml.safe_load(PROTOCOL.read_text())
    assert protocol["status"] == "FROZEN_BEFORE_FIRST_N20_SWEEP"
    assert protocol["swarm_sizes"] == list(SIZES) and sha256_file(POLICY) == POLICY_SHA
    assert layout_audit()["status"] == "PASS"
    output = RESULTS / f"N{n}"
    if output.exists():
        raise RuntimeError(f"refusing to overwrite retained sweep evidence: {output}")
    output.mkdir(parents=True); (output / "ros_home").mkdir()
    layout = parking_layout(n)
    layout_path = output / "layout.json"
    layout_path.write_text(json.dumps({"N": n, "positions": layout}, indent=2, sort_keys=True) + "\n")
    env = sourced_environment(install, px4_root, output, int(protocol["fixed_runtime"]["ros_domain_id"]))
    runtime = protocol["fixed_runtime"]
    processes: list[subprocess.Popen] = []; handles = []; stage = "preflight"
    result = {
        "schema": "large_swarm_infrastructure_result_v1", "N_requested": n,
        "dataset_class": "supplementary_infrastructure_validation", "accepted_formal_result": False,
        "scientific_mission": False, "candidate_command_submitted": False, "llm_calls": 0,
        "formation_commands": 0, "protocol_sha256": sha256_file(PROTOCOL), "policy_sha256": POLICY_SHA,
        "layout_sha256": sha256_file(layout_path), "success": False, "startup_failure_stage": None,
        "host_diagnostics_before": host_diagnostics(),
    }
    initial = counts(); result["initial_process_counts"] = initial
    if any(initial.values()):
        raise RuntimeError(f"pre-existing scoped processes: {initial}")
    started = time.monotonic()
    try:
        stage = "micro_xrce_agent"
        process, handle = start(["MicroXRCEAgent", "udp4", "-p", "8888"], output / "agent.log", env)
        processes.append(process); handles.append(handle)
        stage = "gzserver"
        world = px4_root / "Tools/simulation/gazebo-classic/sitl_gazebo-classic/worlds/empty.world"
        process, handle = start(["gzserver", str(world), "--verbose", "-s", "libgazebo_ros_init.so", "-s", "libgazebo_ros_factory.so"], output / "gzserver.log", env)
        processes.append(process); handles.append(handle)
        time.sleep(6)
        stage = "px4_and_model_spawn"
        spawn_records = []
        build = px4_root / "build/px4_sitl_default"
        for position in layout:
            uid = int(position["uav_id"])
            sdf = generate_sdf(uid, px4_root, output, env)
            work = build / "rootfs" / str(uid - 1); work.mkdir(parents=True, exist_ok=True)
            process, handle = start([str(build / "bin/px4"), "-i", str(uid), "-d", str(build / "etc")], output / f"px4_{uid}.log", env, work)
            processes.append(process); handles.append(handle)
            spawned = subprocess.run(["gz", "model", f"--spawn-file={sdf}", f"--model-name=iris_{uid}", "-x", str(position["x"]), "-y", str(position["y"]), "-z", str(position["z"])], env=env, capture_output=True, text=True, timeout=30)
            spawn_records.append({"uav_id": uid, "returncode": spawned.returncode, "stdout_sha256": hashlib.sha256(spawned.stdout.encode()).hexdigest(), "stderr": spawned.stderr[-1000:]})
            if spawned.returncode != 0:
                raise RuntimeError(f"Gazebo model spawn failed for UAV {uid}")
        result["spawn_records"] = spawn_records
        ok, elapsed, spawn_counts = wait_counts(n, float(runtime["simulator_spawn_timeout_s"]))
        result.update({"models_spawned": len(spawn_records), "spawn_gate_success": ok, "spawn_elapsed_s": elapsed, "process_counts_after_spawn": spawn_counts})
        if not ok:
            raise RuntimeError("exact spawn process-count gate failed")
        stage = "controller_startup"
        ids = "[" + ",".join(str(i) for i in range(1, n + 1)) + "]"
        command = ["ros2", "launch", str(LAUNCHER), f"layout_json:={layout_path}", f"uav_ids:={ids}", f"lfs_policy_file:={POLICY}", "control_mode:=ladrc_acceleration", "avoidance_mode:=iapf_dual", "iapf_escape_mode:=id_order"]
        process, handle = start(command, output / "controllers.log", env)
        processes.append(process); handles.append(handle)
        stage = "readiness"
        readiness_started = time.monotonic()
        ready = subprocess.run(["/usr/bin/python3", str(E5_READY), "--uav-ids", ",".join(str(i) for i in range(1, n + 1)), "--timeout", str(runtime["readiness_timeout_s"]), "--hold", str(runtime["readiness_hold_s"]), "--freshness", str(runtime["freshness_timeout_s"]), "--minimum-altitude", str(runtime["minimum_altitude_m"]), "--speed-tolerance", str(runtime["speed_tolerance_mps"])], env=env, capture_output=True, text=True, timeout=float(runtime["readiness_timeout_s"]) + 30)
        (output / "readiness.stdout.json").write_text(ready.stdout); (output / "readiness.stderr.log").write_text(ready.stderr)
        readiness = json.loads(ready.stdout) if ready.stdout.strip() else {}
        current_counts = counts()
        diagnostics = readiness.get("diagnostics", {})
        result.update({
            "readiness_success": ready.returncode == 0 and bool(readiness.get("ready")),
            "readiness_elapsed_s": readiness.get("elapsed_s", time.monotonic() - readiness_started),
            "stable_hover_duration_s": float(runtime["readiness_hold_s"]),
            "fresh_state_count": sum(1 for value in readiness.get("state_diagnostics", {}).values() if value.get("present") and value.get("age_s", math.inf) <= float(runtime["freshness_timeout_s"])),
            "armed_offboard_count": sum(1 for value in diagnostics.values() if value.get("armed") and value.get("offboard")),
            "failsafe_count": sum(1 for value in diagnostics.values() if value.get("failsafe")),
            "all_states_finite": bool(readiness.get("all_states_finite")),
            "process_counts_at_readiness": current_counts,
            "micro_xrce_agent_alive": current_counts["agent"] == 1, "gzserver_alive": current_counts["gzserver"] == 1,
            "host_diagnostics_at_readiness": host_diagnostics(), "gazebo_stats": gazebo_stats(env),
        })
        topics = subprocess.run(["ros2", "topic", "list"], env=env, capture_output=True, text=True, timeout=20)
        topic_names = set(topics.stdout.splitlines())
        result["topic_connectivity"] = {
            "command_returncode": topics.returncode,
            "status_topics_present": sum(f"/uav{i}/status" in topic_names for i in range(1, n + 1)),
            "state_topics_present": sum(f"/uav{i}/swarm_state" in topic_names for i in range(1, n + 1)),
            "total_topic_count": len(topic_names),
        }
        gates = [result["models_spawned"] == n, current_counts["px4"] == n, current_counts["controllers"] == n, result["micro_xrce_agent_alive"], result["gzserver_alive"], result["armed_offboard_count"] == n, result["fresh_state_count"] == n, result["readiness_success"], result["all_states_finite"], result["failsafe_count"] == 0, result["topic_connectivity"]["status_topics_present"] == n, result["topic_connectivity"]["state_topics_present"] == n]
        if not all(gates):
            raise RuntimeError("one or more frozen infrastructure PASS gates failed")
        result["success"] = True
    except Exception as exc:
        result["startup_failure_stage"] = stage
        result["failure"] = f"{type(exc).__name__}: {exc}"
    finally:
        result["process_exit_status"] = [stop(p, float(runtime["cleanup_grace_s"])) for p in reversed(processes)]
        for handle in handles: handle.close()
        result["cleanup"] = cleanup_residuals()
        if not result["cleanup"]["success"]:
            result["success"] = False; result["failure"] = result.get("failure") or "cleanup residual gate failed"
        result["host_diagnostics_after"] = host_diagnostics()
        result["elapsed_total_s"] = time.monotonic() - started
        result["evidence_file_hashes"] = {p.name: sha256_file(p) for p in sorted(output.iterdir()) if p.is_file() and p.name != "result.json"}
        (output / "result.json").write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    return result, output


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--n", type=int, required=True, choices=SIZES)
    parser.add_argument("--install", type=Path, default=Path("/home/yihuang/learning/LLM_swarm_ws/e5_v2_build/install"))
    parser.add_argument("--px4-root", type=Path, default=Path("/home/yihuang/PX4-Autopilot"))
    args = parser.parse_args()
    result, output = run(args.n, args.install.resolve(), args.px4_root.resolve())
    print(json.dumps({"N": args.n, "success": result["success"], "failure": result.get("failure"), "output": str(output)}, sort_keys=True))
    return 0 if result["success"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
