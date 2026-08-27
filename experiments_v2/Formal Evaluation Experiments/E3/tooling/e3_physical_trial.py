#!/usr/bin/env python3
"""One cold E3 ROS/Gazebo/PX4 execution; no campaign or retry authority."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import time
from types import SimpleNamespace

from e3_runtime_diagnostics import (
    collect_runtime_provenance, endpoint_snapshot, expected_wrench_topic,
    runtime_provenance_gate, validate_command, write_json,
)

WORKSPACE = Path("/home/yihuang/learning/LLM_swarm_ws")
PX4 = Path("/home/yihuang/PX4-Autopilot-formal-v1")
FORMAL_INSTALL = WORKSPACE / "formal_install_v1/setup.bash"
VENV_PYTHON = WORKSPACE / "llm_env/bin/python"
POLICY = WORKSPACE / "formal_install_v1/lfs_policy/share/lfs_policy/config/lfs_policy.paper_current.yaml"
REPO = Path(__file__).resolve().parents[4]
READY = REPO / "experiments-legacy/system_8uav/scripts/wait_swarm_ready.py"
WRENCH = Path(__file__).with_name("e3_wrench_compat.py")


def utc_now():
    return datetime.now(timezone.utc).isoformat()


def ros_environment(seed):
    shell = f"source /opt/ros/humble/setup.bash && source {FORMAL_INSTALL} && env -0"
    raw = subprocess.check_output(["bash", "-lc", shell])
    env = {a.decode(): b.decode() for item in raw.split(b"\0") if b"=" in item
           for a, b in [item.split(b"=", 1)]}
    env.update({"ROS_DOMAIN_ID": "42", "RMW_IMPLEMENTATION": "rmw_fastrtps_cpp",
                "FORMAL_GAZEBO_SEED": str(seed)})
    env["GAZEBO_PLUGIN_PATH"] = "/opt/ros/humble/lib:" + env.get("GAZEBO_PLUGIN_PATH", "")
    return env


def start(command, path, *, cwd=None, env=None):
    stream = path.open("w", encoding="utf-8")
    process = subprocess.Popen(command, cwd=cwd, env=env, stdout=stream,
                               stderr=subprocess.STDOUT, start_new_session=True)
    return process, stream


def stop(process):
    if process is None or process.poll() is not None:
        return
    os.killpg(process.pid, signal.SIGINT)
    try:
        process.wait(20)
    except subprocess.TimeoutExpired:
        os.killpg(process.pid, signal.SIGTERM)
        try:
            process.wait(8)
        except subprocess.TimeoutExpired:
            os.killpg(process.pid, signal.SIGKILL)
            process.wait(5)


def clean_residuals():
    patterns = ("(^|/)px4( |$)", "(^|/)gzserver( |$)", "(^|/)gzclient( |$)",
                "(^|/)MicroXRCEAgent( |$)", "ladrc_position_controller_node")
    for sig in ("INT", "TERM"):
        for pattern in patterns:
            subprocess.run(["pkill", f"-{sig}", "-f", pattern], check=False,
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        time.sleep(2)


def bag_topics(ids):
    topics = ["/clock", "/e3/disturbance_arm"]
    for uid in ids:
        topics += [f"/uav{uid}/status", f"/uav{uid}/startup_event",
                   f"/uav{uid}/execution_command", f"/uav{uid}/trajectory_metrics",
                   f"/uav{uid}/control_tracking_debug", f"/uav{uid}/iapf_debug",
                   f"/uav{uid}/swarm_state", f"/px4_{uid}/fmu/out/vehicle_odometry",
                   f"/px4_{uid}/fmu/out/vehicle_status",
                   expected_wrench_topic(uid)]
    return topics


def direct_driver(spec, phase, result_path):
    repo = Path(__file__).resolve().parents[4]
    sys.path[:0] = [str(repo / "location_allocate"), str(repo / "lfs_policy")]
    import rclpy
    from rclpy.node import Node
    from std_msgs.msg import Empty
    from uav_swarm_interfaces.msg import UAVExecutionCommand, UAVStatus, StartupEvent
    from location_allocate.execution_command_builder import build_task_command_batch
    from location_allocate.lfs_types import ExecutableLFS, ExecutionProfile

    ids = [int(v) for v in spec["uav_ids"]]
    targets = spec["initial_positions_m"] if phase == "stage" else spec["assigned_targets_m"]
    duration = max(6.0, float(spec["duration_s"])) if phase == "stage" else float(spec["duration_s"])
    mission = int(hashlib.sha256((spec["trial_id"] + phase).encode()).hexdigest()[:8], 16) or 1
    profiles = []
    for item in spec["profiles"]:
        value = dict(item); value["duration"] = duration
        profiles.append(ExecutionProfile(**{
            **value,
            "omega_c": tuple(value["omega_c"]), "omega_o": tuple(value["omega_o"]),
        }))

    class Driver(Node):
        def __init__(self):
            super().__init__("e3_exact_command_driver", parameter_overrides=[])
            self.status = {}; self.events = {uid: [] for uid in ids}
            self.mission_status_seen = {uid: False for uid in ids}
            self.command_publishers = {uid: self.create_publisher(UAVExecutionCommand,
                              f"/uav{uid}/execution_command", 10) for uid in ids}
            self.arm = self.create_publisher(Empty, "/e3/disturbance_arm", 10)
            self.status_subscriptions = []
            for uid in ids:
                self.status_subscriptions.append(self.create_subscription(
                    UAVStatus, f"/uav{uid}/status",
                    lambda msg, value=uid: self._status(value, msg), 20))
                self.status_subscriptions.append(self.create_subscription(
                    StartupEvent, f"/uav{uid}/startup_event",
                    lambda msg, value=uid: self.events[value].append(msg.event)
                    if int(msg.mission_id) == mission else None, 20))

        def _status(self, uid, msg):
            self.status[uid] = msg
            if int(msg.mission_id) == mission:
                self.mission_status_seen[uid] = True

        def commands(self):
            executable = ExecutableLFS(
                uav_ids=tuple(ids), formation={"type": "E3_exact_targets"},
                center=(0.0, 0.0, 0.0), radius=0.0, duration=duration,
                motion_style="normal", safety_factor=1.0,
                trigger_semantics={"mode": "immediate"})
            resolved = SimpleNamespace(executable_lfs=executable,
                assigned_targets=tuple(tuple(v) for v in targets), profiles=tuple(profiles))
            return build_task_command_batch(resolved, mission_id=mission, task_id=1,
                                            group_id=1, stamp=self.get_clock().now().to_msg())

    rclpy.init()
    node = Driver(); started = time.monotonic(); published = None; stable_since = None
    timeout = (duration + 30.0) if phase == "stage" else float(spec["timeout_after_t0_s"])
    result = {"phase": phase, "success": False, "started_utc": utc_now(),
              "mission_id": mission, "execution_command_t0_monotonic": None,
              "command_publish_count_by_uav": {str(uid): 0 for uid in ids}}
    try:
        deadline = time.monotonic() + 20
        snapshots = {}
        while time.monotonic() < deadline:
            rclpy.spin_once(node, timeout_sec=0.05)
            snapshots = {
                str(uid): endpoint_snapshot(
                    node, node.command_publishers[uid],
                    f"/uav{uid}/execution_command", uid,
                ) for uid in ids
            }
            if all(
                item["controller_endpoint_present"] and item["recorder_endpoint_present"]
                for item in snapshots.values()
            ):
                break
        write_json(result_path.parent / f"{phase}_endpoint_snapshot.json", {
            "phase": phase, "captured_immediately_before_single_publish": True,
            "endpoints": snapshots,
        })
        if not all(item["controller_endpoint_present"] for item in snapshots.values()):
            raise RuntimeError("expected LADRC controller execution-command endpoint missing")
        if not all(item["recorder_endpoint_present"] for item in snapshots.values()):
            raise RuntimeError("required execution-command recorder endpoint missing")

        commands = node.commands()
        validations = {
            str(command.uav_id): validate_command(command, int(command.uav_id))
            for command in commands
        }
        validation_path = result_path.parent / "command_validation.json"
        combined = (json.loads(validation_path.read_text())
                    if validation_path.exists() else {"phases": {}})
        combined["phases"][phase] = {
            "mission_id": mission, "commands": validations,
            "all_frozen_controller_metadata_guards_pass": all(
                item["frozen_controller_metadata_guard_pass"]
                for item in validations.values()
            ),
        }
        write_json(validation_path, combined)
        if len(commands) != len(ids) or set(validations) != {str(uid) for uid in ids}:
            raise RuntimeError("exactly one command per participating UAV was not constructed")
        if not combined["phases"][phase]["all_frozen_controller_metadata_guards_pass"]:
            raise RuntimeError("command payload failed frozen controller metadata guard")
        if phase == "interaction":
            node.arm.publish(Empty())
        published = time.monotonic()
        result["execution_command_t0_monotonic"] = published
        for command in commands:
            node.command_publishers[int(command.uav_id)].publish(command)
            result["command_publish_count_by_uav"][str(command.uav_id)] += 1
        deadline = published + timeout
        required_stable = 2.0
        while time.monotonic() < deadline:
            rclpy.spin_once(node, timeout_sec=0.02)
            stable = all(uid in node.status and int(node.status[uid].mission_id) == mission
                         and node.status[uid].is_hover_stable for uid in ids)
            stable_since = (stable_since or time.monotonic()) if stable else None
            if phase == "stage" and stable_since and time.monotonic() - stable_since >= required_stable:
                result["success"] = True; break
            if phase == "interaction" and time.monotonic() >= published + duration + 2.0:
                result["success"] = True; break
        if not result["success"]:
            result["termination_reason"] = "TIMEOUT"
        else:
            result["termination_reason"] = "SUCCESS"
        result["events"] = node.events
        result["controller_acceptance_event"] = {
            str(uid): "command_accepted" in node.events[uid] for uid in ids
        }
        result["mission_trajectory_started_event"] = {
            str(uid): "mission_trajectory_started" in node.events[uid] for uid in ids
        }
        result["controller_mission_status_seen"] = {
            str(uid): node.mission_status_seen[uid] for uid in ids
        }
        result["final_mission_status"] = {
            str(uid): {
                "mission_id": int(node.status[uid].mission_id),
                "is_hover_stable": bool(node.status[uid].is_hover_stable),
                "stability_state": int(node.status[uid].stability_state),
                "position_error": float(node.status[uid].position_error),
                "speed": float(node.status[uid].speed),
            } if uid in node.status else None for uid in ids
        }
        result["stable_continuous_observed_s"] = (
            time.monotonic() - stable_since if stable_since is not None else 0.0
        )
    except Exception as exc:
        result["termination_reason"] = "DRIVER_FAILURE"
        result["error"] = f"{type(exc).__name__}: {exc}"
    finally:
        result["finished_utc"] = utc_now()
        result_path.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
        node.destroy_node(); rclpy.shutdown()
    return 0 if result["success"] else 2


def orchestrate(spec, output, result_path):
    output = Path(output).resolve()
    result_path = Path(result_path).resolve()
    output.mkdir(parents=True, exist_ok=True)
    env = ros_environment(spec["seed"]); ids = [int(v) for v in spec["uav_ids"]]
    ids_arg = "[" + ",".join(map(str, ids)) + "]"
    processes = []; streams = []; result = {
        "attempt_status": "infrastructure_failure", "started_utc": utc_now(),
        "cold_start": True,
        "fixture_class": spec.get("fixture_class", "registered_formal_spec"),
        "dataset_class": spec.get("dataset_class", "formal_evaluation"),
        "retry_performed": False,
    }
    try:
        clean_residuals()
        commands = [
            ("agent", ["MicroXRCEAgent", "udp4", "-p", "8888"], None),
            ("sitl", ["bash", str(PX4 / "Tools/simulation/gazebo-classic/sitl_multiple_run.sh"),
                      "-n", str(len(ids)), "-m", "iris", "-w", "empty"], PX4),
        ]
        for name, command, cwd in commands:
            process, stream = start(command, output / f"{name}.log", cwd=cwd, env=env)
            processes.append(process); streams.append(stream)
        time.sleep(20)
        if processes[-1].poll() is not None: raise RuntimeError("PX4/Gazebo startup failed")
        controller = ["ros2", "launch", "ladrc_controller", "swarm_launch.py",
            f"uav_ids:={ids_arg}", "control_mode:=ladrc_acceleration",
            f"avoidance_mode:={spec['avoidance_mode']}", "iapf_escape_mode:=id_order",
            "iapf_filter_alpha:=0.20", f"lfs_policy_file:={POLICY}"]
        process, stream = start(controller, output / "controllers.log", cwd=WORKSPACE, env=env)
        processes.append(process); streams.append(stream)
        ready = subprocess.run([str(VENV_PYTHON), str(READY), "--uav-ids", ",".join(map(str, ids)),
                                "--timeout", "150"], cwd=WORKSPACE, env=env,
                               text=True, capture_output=True, timeout=165)
        (output / "readiness.log").write_text(ready.stdout + ready.stderr)
        if ready.returncode: raise RuntimeError("all-UAV readiness failed")
        vectors = spec["disturbance"]["vectors_N"]
        wrench_json = json.dumps({str(uid): vectors.get(str(uid), vectors.get(uid))
                                  for uid in spec["disturbance"]["affected_uavs"]})
        wrench = [str(VENV_PYTHON), str(WRENCH), "--ros-args", "-p",
                  f"wrenches_json:='{wrench_json}'", "-p", f"onset_s:={spec['disturbance']['onset_s']}",
                  "-p", f"duration_s:={spec['disturbance']['duration_s']}"]
        process, stream = start(wrench, output / "wrench.log", cwd=WORKSPACE, env=env)
        processes.append(process); streams.append(stream)
        bag = ["ros2", "bag", "record", "-o", str(output / "rosbag"), *bag_topics(ids)]
        process, stream = start(bag, output / "rosbag.log", cwd=WORKSPACE, env=env)
        processes.append(process); streams.append(stream); time.sleep(2)
        runtime_provenance = collect_runtime_provenance(REPO, env, ids)
        write_json(output / "runtime_provenance.json", runtime_provenance)
        if not runtime_provenance_gate(runtime_provenance):
            raise RuntimeError("installed runtime provenance gate failed")
        for phase in ("stage", "interaction"):
            phase_result = output / f"{phase}_result.json"
            command = [str(VENV_PYTHON), str(Path(__file__).resolve()), "--direct-driver",
                       "--runtime-spec", str(output / "runtime_spec.json"),
                       "--phase", phase, "--result", str(phase_result)]
            run = subprocess.run(command, cwd=WORKSPACE, env=env, text=True,
                                 capture_output=True, timeout=float(spec["duration_s"]) + 90)
            (output / f"{phase}.stdout.log").write_text(run.stdout + run.stderr)
            if run.returncode: raise RuntimeError(f"{phase} driver failed")
        result["attempt_status"] = "success"
        result["raw_evidence"] = {"rosbag": "rosbag", "staging": "stage_result.json",
                                  "interaction": "interaction_result.json",
                                  "wrench_log": "wrench.log",
                                  "runtime_provenance": "runtime_provenance.json",
                                  "command_validation": "command_validation.json"}
    except subprocess.TimeoutExpired as exc:
        result["attempt_status"] = "timeout"; result["error"] = str(exc)
    except Exception as exc:
        result["error"] = f"{type(exc).__name__}: {exc}"
    finally:
        for process in reversed(processes): stop(process)
        for stream in streams: stream.close()
        result["finished_utc"] = utc_now()
        result_path.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    return 0 if result["attempt_status"] == "success" else 2


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--runtime-spec", type=Path, required=True)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--result", type=Path, required=True)
    parser.add_argument("--direct-driver", action="store_true")
    parser.add_argument("--phase", choices=("stage", "interaction"))
    args = parser.parse_args(); spec = json.loads(args.runtime_spec.read_text())
    if args.direct_driver:
        return direct_driver(spec, args.phase, args.result)
    (args.output / "runtime_spec.json").write_text(args.runtime_spec.read_text())
    return orchestrate(spec, args.output, args.result)


if __name__ == "__main__":
    raise SystemExit(main())
