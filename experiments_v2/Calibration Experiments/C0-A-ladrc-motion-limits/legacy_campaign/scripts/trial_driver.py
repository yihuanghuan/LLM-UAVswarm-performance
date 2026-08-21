#!/usr/bin/env python3
"""Publish one frozen-compiler command batch and enforce C0-A deadlines."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace
import sys
import time

import rclpy
from rclpy.node import Node
from rclpy.qos import qos_profile_sensor_data

ROOT = Path(__file__).resolve().parents[1]
REPOSITORY = ROOT.parents[3]
sys.path.insert(0, str(REPOSITORY / "location_allocate"))

from location_allocate.execution_command_builder import (
    build_task_command_batch,
)
from location_allocate.lfs_types import ExecutableLFS, ExecutionProfile
from uav_swarm_interfaces.msg import (
    ControlTrackingDebug,
    StartupEvent,
    UAVExecutionCommand,
    UAVStatus,
)


def utc_now():
    return datetime.now(timezone.utc).isoformat()


def mission_id(trial_id):
    value = int(hashlib.sha256(trial_id.encode("utf-8")).hexdigest()[:8], 16)
    return value or 1


class TrialDriver(Node):
    def __init__(self, spec):
        super().__init__("c0a_trial_driver")
        self.spec = spec
        self.ids = [int(value) for value in spec["uav_ids"]]
        self.mission_id = mission_id(spec["entry"]["trial_id"])
        self.status = {}
        self.events = {uid: [] for uid in self.ids}
        self.accepted = set()
        self.tracking_seen = set()
        self.control_modes = set()
        self.command_publishers = {}
        self.command_subscriptions = []
        for uid in self.ids:
            self.command_publishers[uid] = self.create_publisher(
                UAVExecutionCommand, f"/uav{uid}/execution_command", 10
            )
            self.command_subscriptions.append(self.create_subscription(
                UAVStatus,
                f"/uav{uid}/status",
                lambda message, uav_id=uid: self.on_status(uav_id, message),
                20,
            ))
            self.command_subscriptions.append(self.create_subscription(
                StartupEvent,
                f"/uav{uid}/startup_event",
                lambda message, uav_id=uid: self.on_event(uav_id, message),
                20,
            ))
            self.command_subscriptions.append(self.create_subscription(
                ControlTrackingDebug,
                f"/uav{uid}/control_tracking_debug",
                lambda message, uav_id=uid: self.on_debug(uav_id, message),
                qos_profile_sensor_data,
            ))

    def on_status(self, uid, message):
        self.status[uid] = message

    def on_event(self, uid, message):
        if int(message.mission_id) != self.mission_id:
            return
        self.events[uid].append({
            "event": message.event,
            "received_monotonic": time.monotonic(),
        })
        if message.event == "command_accepted":
            self.accepted.add(uid)

    def on_debug(self, uid, message):
        if int(message.mission_id) == self.mission_id and message.has_command:
            self.tracking_seen.add(uid)
            self.control_modes.add(message.control_mode)

    def build_commands(self):
        executable = ExecutableLFS(
            uav_ids=tuple(self.ids),
            formation={"type": "c0a_registered_direct_targets"},
            center=(0.0, 0.0, 0.0),
            radius=0.0,
            duration=float(self.spec["explicit_duration_s"]),
            motion_style="normal",
            safety_factor=1.0,
            trigger_semantics={"mode": "immediate"},
        )
        profiles = tuple(ExecutionProfile(
            duration=float(item["duration"]),
            style=item["style"],
            omega_c=tuple(item["omega_c"]),
            omega_o=tuple(item["omega_o"]),
            velocity_limit=float(item["velocity_limit"]),
            acceleration_limit=float(item["acceleration_limit"]),
            jerk_limit=float(item["jerk_limit"]),
            iapf_enter_distance=float(item["iapf_enter_distance"]),
            iapf_exit_distance=float(item["iapf_exit_distance"]),
            iapf_repulsion_scale=float(item["iapf_repulsion_scale"]),
            configuration_id=item["configuration_id"],
            style_gain=float(item["style_gain"]),
            task_gain=float(item["task_gain"]),
        ) for item in self.spec["profiles"])
        resolved = SimpleNamespace(
            executable_lfs=executable,
            assigned_targets=tuple(tuple(item) for item in self.spec["world_targets"]),
            profiles=profiles,
        )
        return build_task_command_batch(
            resolved,
            mission_id=self.mission_id,
            task_id=1,
            group_id=1,
            stamp=self.get_clock().now().to_msg(),
        )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--spec", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--wall-deadline-monotonic", type=float, required=True)
    args = parser.parse_args()
    spec = json.loads(args.spec.read_text(encoding="utf-8"))
    result = {
        "trial_id": spec["entry"]["trial_id"],
        "started_utc": utc_now(),
        "mission_id": mission_id(spec["entry"]["trial_id"]),
        "success": False,
        "termination_reason": "UNKNOWN",
    }
    rclpy.init()
    node = TrialDriver(spec)
    try:
        discovery_deadline = min(time.monotonic() + 5.0, args.wall_deadline_monotonic)
        while time.monotonic() < discovery_deadline:
            rclpy.spin_once(node, timeout_sec=0.05)
            if all(pub.get_subscription_count() >= 1 for pub in node.command_publishers.values()):
                break
        if not all(pub.get_subscription_count() >= 1 for pub in node.command_publishers.values()):
            result["termination_reason"] = "COMMAND_SUBSCRIBER_MISSING"
            return_code = 2
        else:
            commands = node.build_commands()
            for command in commands:
                node.command_publishers[int(command.uav_id)].publish(command)
            published = time.monotonic()
            result["command_published_utc"] = utc_now()
            result["command_count"] = len(commands)
            wall_deadline = args.wall_deadline_monotonic
            duration = float(spec["explicit_duration_s"])
            hover_deadline = published + max(duration + 20.0, 3.0 * duration)
            deadline = min(wall_deadline, hover_deadline)
            post_window_complete = published + duration + 5.0
            failure = None
            while time.monotonic() < deadline:
                rclpy.spin_once(node, timeout_sec=0.05)
                if node.accepted:
                    for uid in node.ids:
                        status = node.status.get(uid)
                        if status is None:
                            continue
                        if status.failsafe:
                            failure = "PX4_FAILSAFE"
                        elif not status.armed:
                            failure = "UNINTENDED_DISARM"
                        elif not status.offboard:
                            failure = "OFFBOARD_LOSS"
                if failure:
                    break
                stable = all(
                    uid in node.status
                    and int(node.status[uid].mission_id) == node.mission_id
                    and node.status[uid].is_hover_stable
                    for uid in node.ids
                )
                if stable and time.monotonic() >= post_window_complete:
                    break
            stable = all(
                uid in node.status
                and int(node.status[uid].mission_id) == node.mission_id
                and node.status[uid].is_hover_stable
                for uid in node.ids
            )
            if failure:
                result["termination_reason"] = failure
                return_code = 2
            elif node.accepted != set(node.ids):
                result["termination_reason"] = "COMMAND_REJECTED"
                return_code = 2
            elif node.tracking_seen != set(node.ids):
                result["termination_reason"] = "MANDATORY_TOPIC_MISSING"
                return_code = 2
            elif node.control_modes != {"ladrc_acceleration"}:
                result["termination_reason"] = "INVALID_CONTROL_MODE"
                return_code = 2
            elif not stable:
                result["termination_reason"] = "TIMEOUT"
                return_code = 2
            elif time.monotonic() < post_window_complete:
                result["termination_reason"] = "POST_WINDOW_INCOMPLETE"
                return_code = 2
            else:
                result["success"] = True
                result["termination_reason"] = "SUCCESS"
                return_code = 0
            result["accepted_uav_ids"] = sorted(node.accepted)
            result["tracking_uav_ids"] = sorted(node.tracking_seen)
            result["control_modes"] = sorted(node.control_modes)
            result["stable_uav_ids"] = sorted(
                uid for uid in node.ids
                if uid in node.status and node.status[uid].is_hover_stable
            )
            result["events"] = node.events
    except Exception as error:
        result["termination_reason"] = "DRIVER_EXCEPTION"
        result["error"] = f"{type(error).__name__}: {error}"
        return_code = 2
    finally:
        result["finished_utc"] = utc_now()
        args.output.write_text(
            json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        node.destroy_node()
        rclpy.shutdown()
    return return_code


if __name__ == "__main__":
    raise SystemExit(main())
