#!/usr/bin/env python3
"""Cold E3-v4 qualification execution for post-planning deviations only."""

from __future__ import annotations

import argparse
import copy
from datetime import datetime, timezone
import hashlib
import json
import math
import os
from pathlib import Path
import signal
import subprocess
import sys
import time
from types import SimpleNamespace

from e3_physical_trial import (
    FORMAL_INSTALL, POLICY, PX4, READY, REPO, VENV_PYTHON, WORKSPACE,
    clean_residuals, ros_environment, start, stop,
)
from e3_runtime_diagnostics import (
    collect_runtime_provenance, endpoint_snapshot, runtime_provenance_gate,
    validate_command, write_json,
)

EVENT_TOPIC = "/e3_v4/manipulation_event"


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def bag_topics(ids: list[int]) -> list[str]:
    topics = ["/clock", EVENT_TOPIC]
    for uid in ids:
        topics.extend([
            f"/uav{uid}/status",
            f"/uav{uid}/startup_event",
            f"/uav{uid}/execution_command",
            f"/uav{uid}/trajectory_metrics",
            f"/uav{uid}/control_tracking_debug",
            f"/uav{uid}/iapf_debug",
            f"/uav{uid}/swarm_state",
            f"/px4_{uid}/fmu/out/vehicle_odometry",
            f"/px4_{uid}/fmu/out/vehicle_status",
        ])
    return topics


def minimum_jerk(progress: float) -> float:
    value = min(max(float(progress), 0.0), 1.0)
    return 10.0 * value**3 - 15.0 * value**4 + 6.0 * value**5


def direct_driver(spec: dict, phase: str, result_path: Path) -> int:
    sys.path[:0] = [str(REPO / "location_allocate"), str(REPO / "lfs_policy")]
    import rclpy
    from rclpy.node import Node
    from rclpy.parameter import Parameter
    from std_msgs.msg import String
    from uav_swarm_interfaces.msg import (
        ControlTrackingDebug, StartupEvent, UAVExecutionCommand, UAVStatus,
    )
    from location_allocate.execution_command_builder import build_task_command_batch
    from location_allocate.lfs_types import ExecutableLFS, ExecutionProfile

    ids = [int(value) for value in spec["uav_ids"]]
    targets = (
        spec["initial_positions_m"] if phase == "stage"
        else spec["assigned_targets_m"]
    )
    duration = (
        max(6.0, float(spec["duration_s"]))
        if phase == "stage" else float(spec["duration_s"])
    )
    nominal_mission = (
        int(hashlib.sha256((spec["trial_id"] + phase).encode()).hexdigest()[:8], 16)
        or 1
    )
    bias_mission = (nominal_mission + 1) & 0xFFFFFFFF or 1
    reset_mission = (nominal_mission + 2) & 0xFFFFFFFF or 2
    profiles = []
    for item in spec["profiles"]:
        value = dict(item)
        value["duration"] = duration
        profiles.append(ExecutionProfile(**{
            **value,
            "omega_c": tuple(value["omega_c"]),
            "omega_o": tuple(value["omega_o"]),
        }))

    class Driver(Node):
        def __init__(self):
            super().__init__(
                "e3_v4_execution_deviation_driver",
                parameter_overrides=[Parameter("use_sim_time", value=True)],
            )
            self.status: dict[int, object] = {}
            self.events: list[dict] = []
            self.debug_seen: dict[int, set[int]] = {uid: set() for uid in ids}
            self.command_publishers = {
                uid: self.create_publisher(
                    UAVExecutionCommand, f"/uav{uid}/execution_command", 10
                ) for uid in ids
            }
            self.event_publisher = self.create_publisher(String, EVENT_TOPIC, 20)
            self._e3_subscriptions = []
            for uid in ids:
                self._e3_subscriptions.append(self.create_subscription(
                    UAVStatus, f"/uav{uid}/status",
                    lambda msg, value=uid: self._status(value, msg), 20,
                ))
                self._e3_subscriptions.append(self.create_subscription(
                    StartupEvent, f"/uav{uid}/startup_event",
                    lambda msg, value=uid: self._event(value, msg), 40,
                ))
                self._e3_subscriptions.append(self.create_subscription(
                    ControlTrackingDebug, f"/uav{uid}/control_tracking_debug",
                    lambda msg, value=uid: self.debug_seen[value].add(
                        int(msg.mission_id)
                    ), 20,
                ))

        def ros_seconds(self) -> float:
            return self.get_clock().now().nanoseconds * 1.0e-9

        def _status(self, uid, msg) -> None:
            self.status[uid] = msg

        def _event(self, uid, msg) -> None:
            stamp = float(msg.header.stamp.sec) + float(msg.header.stamp.nanosec) * 1e-9
            self.events.append({
                "uav_id": uid,
                "mission_id": int(msg.mission_id),
                "event": str(msg.event),
                "stamp_s": stamp,
                "failsafe": bool(msg.failsafe),
            })

        def ledger(self, name: str, **detail) -> dict:
            entry = {"event": name, "ros_time_s": self.ros_seconds(), **detail}
            message = String()
            message.data = json.dumps(entry, sort_keys=True, separators=(",", ":"))
            self.event_publisher.publish(message)
            return entry

        def commands(self, mission: int, task: int = 1):
            executable = ExecutableLFS(
                uav_ids=tuple(ids), formation={"type": "E3_exact_targets"},
                center=(0.0, 0.0, 0.0), radius=0.0, duration=duration,
                motion_style="normal", safety_factor=1.0,
                trigger_semantics={"mode": "immediate"},
            )
            resolved = SimpleNamespace(
                executable_lfs=executable,
                assigned_targets=tuple(tuple(value) for value in targets),
                profiles=tuple(profiles),
            )
            return list(build_task_command_batch(
                resolved, mission_id=mission, task_id=task, group_id=1,
                stamp=self.get_clock().now().to_msg(),
            ))

    def wait_until_ros(node: Driver, target: float, watchdog_s: float) -> None:
        wall_deadline = time.monotonic() + watchdog_s
        while node.ros_seconds() + 1.0e-9 < target:
            if time.monotonic() >= wall_deadline:
                raise RuntimeError("ROS/simulation clock did not reach scheduled event")
            rclpy.spin_once(node, timeout_sec=0.01)

    def accepted(node: Driver, uid: int, mission: int) -> bool:
        return any(
            item["uav_id"] == uid and item["mission_id"] == mission
            and item["event"] == "command_accepted"
            for item in node.events
        )

    def wait_for_acceptance(
        node: Driver, required: list[tuple[int, int]], timeout_ros_s: float = 1.0
    ) -> bool:
        start_ros = node.ros_seconds()
        wall_deadline = time.monotonic() + 5.0
        while node.ros_seconds() - start_ros <= timeout_ros_s:
            if all(accepted(node, uid, mission) for uid, mission in required):
                return True
            if time.monotonic() >= wall_deadline:
                return False
            rclpy.spin_once(node, timeout_sec=0.01)
        return all(accepted(node, uid, mission) for uid, mission in required)

    def stamp_command(command, node: Driver) -> float:
        stamp = node.get_clock().now().to_msg()
        command.header.stamp = stamp
        return float(stamp.sec) + float(stamp.nanosec) * 1e-9

    rclpy.init()
    node = Driver()
    result = {
        "phase": phase,
        "success": False,
        "started_utc": utc_now(),
        "mission_id": nominal_mission,
        "bias_mission_id": bias_mission if phase == "interaction" else None,
        "reset_mission_id": reset_mission if phase == "interaction" else None,
        "execution_command_t0_ros_s": None,
        "command_publish_count_by_uav": {str(uid): 0 for uid in ids},
        "command_publications": [],
        "manipulation_ledger": [],
    }
    try:
        # Fail closed unless the node is actually using a live simulation clock.
        wall_deadline = time.monotonic() + 10.0
        while node.ros_seconds() <= 0.0 and time.monotonic() < wall_deadline:
            rclpy.spin_once(node, timeout_sec=0.05)
        if node.ros_seconds() <= 0.0:
            raise RuntimeError("authoritative ROS/simulation clock unavailable")

        snapshots = {}
        wall_deadline = time.monotonic() + 20.0
        while time.monotonic() < wall_deadline:
            rclpy.spin_once(node, timeout_sec=0.05)
            snapshots = {
                str(uid): endpoint_snapshot(
                    node, node.command_publishers[uid],
                    f"/uav{uid}/execution_command", uid,
                ) for uid in ids
            }
            if (
                all(item["controller_endpoint_present"]
                    and item["recorder_endpoint_present"]
                    for item in snapshots.values())
                and node.event_publisher.get_subscription_count() > 0
            ):
                break
        write_json(result_path.parent / f"{phase}_endpoint_snapshot.json", {
            "phase": phase,
            "captured_immediately_before_publish": True,
            "manipulation_event_recorder_endpoint_present":
                node.event_publisher.get_subscription_count() > 0,
            "endpoints": snapshots,
        })
        if not all(item["controller_endpoint_present"] for item in snapshots.values()):
            raise RuntimeError("expected controller command endpoint missing")
        if not all(item["recorder_endpoint_present"] for item in snapshots.values()):
            raise RuntimeError("required command recorder endpoint missing")
        if node.event_publisher.get_subscription_count() <= 0:
            raise RuntimeError("required manipulation-event recorder endpoint missing")

        commands = node.commands(nominal_mission)
        validations = {
            str(command.uav_id): validate_command(command, int(command.uav_id))
            for command in commands
        }
        validation_path = result_path.parent / "command_validation.json"
        combined = (
            json.loads(validation_path.read_text())
            if validation_path.exists() else {"phases": {}}
        )
        combined["phases"][phase] = {
            "mission_id": nominal_mission,
            "commands": validations,
            "all_frozen_controller_metadata_guards_pass": all(
                value["frozen_controller_metadata_guard_pass"]
                for value in validations.values()
            ),
        }
        write_json(validation_path, combined)
        if len(commands) != len(ids) or set(validations) != {str(uid) for uid in ids}:
            raise RuntimeError("exactly one nominal command per UAV was not constructed")
        if not combined["phases"][phase]["all_frozen_controller_metadata_guards_pass"]:
            raise RuntimeError("nominal command failed frozen metadata guard")

        plan_entry = node.ledger(
            "planning_committed",
            phase=phase,
            runtime_spec_sha256=spec["runtime_spec_sha256"],
            assignment=list(spec["allocator_diagnostics"]["final_assignment"]),
            assignment_mode=spec["assignment_mode"],
        )
        result["manipulation_ledger"].append(plan_entry)
        # Let the recorder receive the commitment before the first command.
        rclpy.spin_once(node, timeout_sec=0.05)

        manipulation = spec.get("manipulation", {"type": "none"})
        if phase == "stage" or manipulation["type"] == "none":
            common_stamp = node.get_clock().now().to_msg()
            t0 = float(common_stamp.sec) + float(common_stamp.nanosec) * 1e-9
            for command in commands:
                command.header.stamp = common_stamp
                node.command_publishers[int(command.uav_id)].publish(command)
                result["command_publish_count_by_uav"][str(command.uav_id)] += 1
                result["command_publications"].append({
                    "role": "nominal", "uav_id": int(command.uav_id),
                    "mission_id": nominal_mission, "ros_time_s": t0,
                })
            required = [(uid, nominal_mission) for uid in ids]
        elif manipulation["type"] == "command_delay":
            delayed = [int(value) for value in manipulation["affected_uavs"]]
            immediate = [uid for uid in ids if uid not in delayed]
            common_stamp = node.get_clock().now().to_msg()
            t0 = float(common_stamp.sec) + float(common_stamp.nanosec) * 1e-9
            result["manipulation_ledger"].append(node.ledger(
                "delay_started", affected_uavs=delayed,
                registered_delay_s=float(manipulation["delay_s"]),
            ))
            for command in commands:
                if int(command.uav_id) not in immediate:
                    continue
                command.header.stamp = common_stamp
                node.command_publishers[int(command.uav_id)].publish(command)
                result["command_publish_count_by_uav"][str(command.uav_id)] += 1
                result["command_publications"].append({
                    "role": "reference_nominal", "uav_id": int(command.uav_id),
                    "mission_id": nominal_mission, "ros_time_s": t0,
                })
            wait_until_ros(node, t0 + float(manipulation["delay_s"]), 10.0)
            delayed_stamp = node.get_clock().now().to_msg()
            delayed_time = (
                float(delayed_stamp.sec) + float(delayed_stamp.nanosec) * 1e-9
            )
            for command in commands:
                if int(command.uav_id) not in delayed:
                    continue
                command.header.stamp = delayed_stamp
                node.command_publishers[int(command.uav_id)].publish(command)
                result["command_publish_count_by_uav"][str(command.uav_id)] += 1
                result["command_publications"].append({
                    "role": "delayed_nominal", "uav_id": int(command.uav_id),
                    "mission_id": nominal_mission, "ros_time_s": delayed_time,
                })
            result["manipulation_ledger"].append(node.ledger(
                "delayed_command_published", affected_uavs=delayed,
                actual_delay_s=delayed_time - t0,
            ))
            required = [(uid, nominal_mission) for uid in ids]
        elif manipulation["type"] == "reference_deviation":
            affected = int(manipulation["affected_uav"])
            common_stamp = node.get_clock().now().to_msg()
            t0 = float(common_stamp.sec) + float(common_stamp.nanosec) * 1e-9
            for command in commands:
                command.header.stamp = common_stamp
                node.command_publishers[int(command.uav_id)].publish(command)
                result["command_publish_count_by_uav"][str(command.uav_id)] += 1
                result["command_publications"].append({
                    "role": "nominal", "uav_id": int(command.uav_id),
                    "mission_id": nominal_mission, "ros_time_s": t0,
                })
            if not wait_for_acceptance(
                node, [(uid, nominal_mission) for uid in ids], 1.0
            ):
                raise RuntimeError("nominal command acceptance missing before bias")
            start_s = float(manipulation["start_s"])
            interval_s = float(manipulation["duration_s"])
            wait_until_ros(node, t0 + start_s, start_s + 5.0)
            original = commands[ids.index(affected)]
            bias_command = copy.deepcopy(original)
            bias_command.mission_id = bias_mission
            bias_command.task_id = 2
            bias_command.profile.duration = interval_s
            initial = spec["initial_positions_m"][ids.index(affected)]
            target = spec["assigned_targets_m"][ids.index(affected)]
            progress = minimum_jerk((start_s + interval_s) / duration)
            counterfactual = [
                float(initial[axis])
                + progress * (float(target[axis]) - float(initial[axis]))
                for axis in range(3)
            ]
            offset = [float(value) for value in manipulation["offset_m"]]
            biased_target = [counterfactual[axis] + offset[axis] for axis in range(3)]
            bias_command.target_pos.x = biased_target[0]
            bias_command.target_pos.y = biased_target[1]
            bias_command.target_pos.z = biased_target[2]
            bias_time = stamp_command(bias_command, node)
            bias_validation = validate_command(bias_command, affected)
            if not bias_validation["frozen_controller_metadata_guard_pass"]:
                raise RuntimeError("bias command failed frozen metadata guard")
            node.command_publishers[affected].publish(bias_command)
            result["command_publish_count_by_uav"][str(affected)] += 1
            result["command_publications"].append({
                "role": "reference_deviation", "uav_id": affected,
                "mission_id": bias_mission, "ros_time_s": bias_time,
                "target_m": biased_target,
                "counterfactual_nominal_endpoint_m": counterfactual,
                "offset_m": offset,
                "duration_s": interval_s,
            })
            result["manipulation_ledger"].append(node.ledger(
                "reference_deviation_published", affected_uav=affected,
                mission_id=bias_mission, target_m=biased_target,
                offset_m=offset,
            ))
            if not wait_for_acceptance(node, [(affected, bias_mission)], 1.0):
                raise RuntimeError("reference-deviation activation not acknowledged")
            wait_until_ros(node, bias_time + interval_s, interval_s + 5.0)
            reset_command = copy.deepcopy(original)
            reset_command.mission_id = reset_mission
            reset_command.task_id = 3
            reset_command.profile.duration = max(
                0.5, duration - (start_s + interval_s)
            )
            reset_time = stamp_command(reset_command, node)
            reset_validation = validate_command(reset_command, affected)
            if not reset_validation["frozen_controller_metadata_guard_pass"]:
                raise RuntimeError("reset command failed frozen metadata guard")
            node.command_publishers[affected].publish(reset_command)
            result["command_publish_count_by_uav"][str(affected)] += 1
            result["command_publications"].append({
                "role": "reference_reset", "uav_id": affected,
                "mission_id": reset_mission, "ros_time_s": reset_time,
                "target_m": [float(value) for value in target],
                "duration_s": float(reset_command.profile.duration),
            })
            result["manipulation_ledger"].append(node.ledger(
                "reference_reset_published", affected_uav=affected,
                mission_id=reset_mission,
                actual_duration_s=reset_time - bias_time,
            ))
            if not wait_for_acceptance(node, [(affected, reset_mission)], 1.0):
                raise RuntimeError("reference-deviation reset not acknowledged")
            required = [(uid, nominal_mission) for uid in ids]
        else:
            raise RuntimeError(f"unsupported manipulation: {manipulation['type']}")

        result["execution_command_t0_ros_s"] = t0
        if not wait_for_acceptance(node, required, 1.5):
            raise RuntimeError("one or more nominal commands were not acknowledged")

        end_ros = t0 + duration + 2.0
        wait_until_ros(node, end_ros, duration + 20.0)
        result["success"] = True
        result["termination_reason"] = "SUCCESS"
        result["controller_events"] = node.events
        result["debug_mission_ids_seen"] = {
            str(uid): sorted(value) for uid, value in node.debug_seen.items()
        }
        result["final_status"] = {
            str(uid): {
                "mission_id": int(node.status[uid].mission_id),
                "is_hover_stable": bool(node.status[uid].is_hover_stable),
                "position_error": float(node.status[uid].position_error),
                "speed": float(node.status[uid].speed),
                "failsafe": bool(node.status[uid].failsafe),
            } if uid in node.status else None
            for uid in ids
        }
    except Exception as exc:
        result["termination_reason"] = "DRIVER_FAILURE"
        result["error"] = f"{type(exc).__name__}: {exc}"
    finally:
        result["finished_utc"] = utc_now()
        write_json(result_path, result)
        node.destroy_node()
        rclpy.shutdown()
    return 0 if result["success"] else 2


def orchestrate(spec: dict, output: Path, result_path: Path) -> int:
    output = Path(output).resolve()
    result_path = Path(result_path).resolve()
    output.mkdir(parents=True, exist_ok=True)
    env = ros_environment(spec["seed"])
    ids = [int(value) for value in spec["uav_ids"]]
    ids_arg = "[" + ",".join(map(str, ids)) + "]"
    processes = []
    streams = []
    result = {
        "attempt_status": "infrastructure_failure",
        "started_utc": utc_now(),
        "cold_start": True,
        "fixture_class": spec.get("fixture_class"),
        "dataset_class": spec.get("dataset_class"),
        "retry_performed": False,
    }
    try:
        clean_residuals()
        commands = [
            ("agent", ["MicroXRCEAgent", "udp4", "-p", "8888"], None),
            ("sitl", [
                "bash", str(PX4 / "Tools/simulation/gazebo-classic/sitl_multiple_run.sh"),
                "-n", str(len(ids)), "-m", "iris", "-w", "empty",
            ], PX4),
        ]
        for name, command, cwd in commands:
            process, stream = start(command, output / f"{name}.log", cwd=cwd, env=env)
            processes.append(process)
            streams.append(stream)
        time.sleep(20)
        if processes[-1].poll() is not None:
            raise RuntimeError("PX4/Gazebo startup failed")
        controller = [
            "ros2", "launch", "ladrc_controller", "swarm_launch.py",
            f"uav_ids:={ids_arg}", "control_mode:=ladrc_acceleration",
            f"avoidance_mode:={spec['avoidance_mode']}",
            "iapf_escape_mode:=id_order", "iapf_filter_alpha:=0.20",
            f"lfs_policy_file:={POLICY}",
        ]
        process, stream = start(
            controller, output / "controllers.log", cwd=WORKSPACE, env=env
        )
        processes.append(process)
        streams.append(stream)
        ready = subprocess.run(
            [str(VENV_PYTHON), str(READY), "--uav-ids", ",".join(map(str, ids)),
             "--timeout", "150"],
            cwd=WORKSPACE, env=env, text=True, capture_output=True, timeout=165,
        )
        (output / "readiness.log").write_text(ready.stdout + ready.stderr)
        if ready.returncode:
            raise RuntimeError("all-UAV readiness failed")
        bag = ["ros2", "bag", "record", "-o", str(output / "rosbag"), *bag_topics(ids)]
        process, stream = start(bag, output / "rosbag.log", cwd=WORKSPACE, env=env)
        processes.append(process)
        streams.append(stream)
        time.sleep(2)
        runtime_provenance = collect_runtime_provenance(REPO, env, ids)
        write_json(output / "runtime_provenance.json", runtime_provenance)
        if not runtime_provenance_gate(runtime_provenance):
            raise RuntimeError("installed runtime provenance gate failed")
        for phase in ("stage", "interaction"):
            phase_result = output / f"{phase}_result.json"
            command = [
                str(VENV_PYTHON), str(Path(__file__).resolve()), "--direct-driver",
                "--runtime-spec", str(output / "runtime_spec.json"),
                "--phase", phase, "--result", str(phase_result),
            ]
            run = subprocess.run(
                command, cwd=WORKSPACE, env=env, text=True, capture_output=True,
                timeout=float(spec["duration_s"]) + 100.0,
            )
            (output / f"{phase}.stdout.log").write_text(run.stdout + run.stderr)
            if run.returncode:
                raise RuntimeError(f"{phase} deviation driver failed")
        result["attempt_status"] = "success"
        result["raw_evidence"] = {
            "rosbag": "rosbag",
            "staging": "stage_result.json",
            "interaction": "interaction_result.json",
            "runtime_provenance": "runtime_provenance.json",
            "command_validation": "command_validation.json",
        }
    except subprocess.TimeoutExpired as exc:
        result["attempt_status"] = "timeout"
        result["error"] = str(exc)
    except Exception as exc:
        result["error"] = f"{type(exc).__name__}: {exc}"
    finally:
        for process in reversed(processes):
            stop(process)
        for stream in streams:
            stream.close()
        result["finished_utc"] = utc_now()
        write_json(result_path, result)
    return 0 if result["attempt_status"] == "success" else 2


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runtime-spec", type=Path, required=True)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--result", type=Path, required=True)
    parser.add_argument("--direct-driver", action="store_true")
    parser.add_argument("--phase", choices=("stage", "interaction"))
    args = parser.parse_args()
    spec = json.loads(args.runtime_spec.read_text())
    if args.direct_driver:
        return direct_driver(spec, args.phase, args.result)
    (args.output / "runtime_spec.json").write_text(args.runtime_spec.read_text())
    return orchestrate(spec, args.output, args.result)


if __name__ == "__main__":
    raise SystemExit(main())
