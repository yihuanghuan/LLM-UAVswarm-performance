#!/usr/bin/env python3
"""Publish one experiment-06 mission and monitor complete tracking telemetry."""

from __future__ import annotations

import argparse
import json
import math
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict

import rclpy
from rclpy.duration import Duration
from rclpy.node import Node

from geometry_msgs.msg import Point
from px4_msgs.msg import VehicleStatus
from rclpy.qos import qos_profile_sensor_data
from uav_swarm_interfaces.msg import TrajectoryMetrics, UAVSwarmCommand

from experiment_06_config import METHODS, SCENARIOS, validate


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--scenario", choices=SCENARIOS, required=True)
    parser.add_argument("--method", choices=METHODS, required=True)
    parser.add_argument("--trial-id", required=True)
    parser.add_argument("--repeat", type=int, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--timeout-after-duration", type=float, default=20.0)
    parser.add_argument("--discovery-timeout", type=float, default=30.0)
    return parser.parse_args()


class TrialNode(Node):
    def __init__(self, args: argparse.Namespace) -> None:
        super().__init__("experiment_06_trial")
        self.args = args
        self.config = SCENARIOS[args.scenario]
        self.ids = list(self.config["uav_ids"])
        self.latest: Dict[int, TrajectoryMetrics] = {}
        self.vehicle_status: Dict[int, VehicleStatus] = {}
        self.ready_odom = set()
        self.command_publishers = {
            uid: self.create_publisher(UAVSwarmCommand, f"/uav{uid}/swarm_command", 10)
            for uid in self.ids
        }
        self.metric_subscriptions = [
            self.create_subscription(
                TrajectoryMetrics,
                f"/uav{uid}/trajectory_metrics",
                lambda msg, uid=uid: self.latest.__setitem__(uid, msg),
                10,
            )
            for uid in self.ids
        ]
        self.odom_subscriptions = [
            self.create_subscription(
                Point,
                f"/uav{uid}/odom",
                lambda _msg, uid=uid: self.ready_odom.add(uid),
                10,
            )
            for uid in self.ids
        ]
        self.vehicle_status_subscriptions = [
            self.create_subscription(
                VehicleStatus,
                (
                    "/fmu/out/vehicle_status"
                    if uid == 0 else f"/px4_{uid}/fmu/out/vehicle_status"
                ),
                lambda msg, uid=uid: self.vehicle_status.__setitem__(uid, msg),
                qos_profile_sensor_data,
            )
            for uid in self.ids
        ]

    def wait_ready(self) -> None:
        deadline = time.monotonic() + self.args.discovery_timeout
        while rclpy.ok() and time.monotonic() < deadline:
            rclpy.spin_once(self, timeout_sec=0.2)
            connected = all(
                self.count_subscribers(f"/uav{uid}/swarm_command") > 0
                for uid in self.ids
            )
            flight_ready = all(
                uid in self.vehicle_status
                and self.vehicle_status[uid].arming_state
                    == VehicleStatus.ARMING_STATE_ARMED
                and self.vehicle_status[uid].nav_state
                    == VehicleStatus.NAVIGATION_STATE_OFFBOARD
                and not self.vehicle_status[uid].failsafe
                for uid in self.ids
            )
            if connected and self.ready_odom == set(self.ids) and flight_ready:
                return
        states = {
            uid: {
                "arming_state": self.vehicle_status[uid].arming_state,
                "nav_state": self.vehicle_status[uid].nav_state,
                "failsafe": self.vehicle_status[uid].failsafe,
            }
            for uid in self.ids if uid in self.vehicle_status
        }
        raise TimeoutError(
            f"controllers/PX4 did not reach armed OFFBOARD readiness: {states}"
        )

    def publish_mission(self) -> float:
        start_delay_s = 2.0
        stamp = (self.get_clock().now() + Duration(seconds=start_delay_s)).to_msg()
        digits = "".join(character for character in self.args.trial_id if character.isdigit())
        mission_id = int((digits or "6")[-8:])
        messages = {}
        for uid in self.ids:
            message = UAVSwarmCommand()
            message.header.stamp = stamp
            message.header.frame_id = "world"
            message.mission_id = mission_id
            message.uav_id = uid
            target = self.config["targets"][uid]
            message.target_pos.x, message.target_pos.y, message.target_pos.z = target
            message.duration = float(self.config["duration_s"])
            message.motion_style = "normal"
            message.safety_factor = 0.0
            messages[uid] = message
        scheduled = time.monotonic() + start_delay_s
        for _ in range(10):
            cycle_deadline = time.monotonic() + 0.1
            for uid, message in messages.items():
                self.command_publishers[uid].publish(message)
            while rclpy.ok() and time.monotonic() < cycle_deadline:
                remaining = cycle_deadline - time.monotonic()
                rclpy.spin_once(self, timeout_sec=min(0.02, max(0.0, remaining)))
        return scheduled

    def monitor(self, scheduled: float) -> Dict[str, object]:
        duration = float(self.config["duration_s"])
        deadline = scheduled + duration + self.args.timeout_after_duration
        all_stable_at = None
        while rclpy.ok() and time.monotonic() < deadline:
            rclpy.spin_once(self, timeout_sec=0.1)
            complete = len(self.latest) == len(self.ids)
            stable = complete and all(
                math.sqrt(
                    (message.target_pos.x - message.actual_pos.x) ** 2
                    + (message.target_pos.y - message.actual_pos.y) ** 2
                    + (message.target_pos.z - message.actual_pos.z) ** 2
                ) < 0.3
                and math.sqrt(
                    message.actual_velocity.x ** 2
                    + message.actual_velocity.y ** 2
                    + message.actual_velocity.z ** 2
                ) < 0.3
                for message in self.latest.values()
            )
            if stable and all_stable_at is None:
                all_stable_at = time.monotonic()
            elif not stable:
                all_stable_at = None
            if (
                all_stable_at is not None
                and time.monotonic() >= scheduled + duration
                and time.monotonic() - all_stable_at >= 1.5
            ):
                break

        uavs = {}
        for uid in self.ids:
            message = self.latest.get(uid)
            elapsed = float(message.elapsed_time) if message is not None else math.nan
            uavs[str(uid)] = {
                "samples_received": message is not None,
                "last_elapsed_time_s": elapsed if math.isfinite(elapsed) else None,
                "node_hover_stable": bool(message.is_hover_stable) if message is not None else False,
                "final_position_error_m": (
                    float(message.final_position_error) if message is not None else None
                ),
            }
        complete_telemetry = all(
            data["samples_received"]
            and data["last_elapsed_time_s"] is not None
            and data["last_elapsed_time_s"] >= duration
            for data in uavs.values()
        )
        return {
            "trial_id": self.args.trial_id,
            "scenario": self.args.scenario,
            "method": self.args.method,
            "repeat": self.args.repeat,
            "duration_s": duration,
            "completed_at_utc": datetime.now(timezone.utc).isoformat(),
            "complete_telemetry": complete_telemetry,
            "all_node_hover_stable": all(data["node_hover_stable"] for data in uavs.values()),
            "uavs": uavs,
        }


def main() -> int:
    validate()
    args = parse_args()
    rclpy.init()
    node = TrialNode(args)
    try:
        node.wait_ready()
        scheduled = node.publish_mission()
        result = node.monitor(scheduled)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(result, indent=2), encoding="utf-8")
        print(json.dumps(result, indent=2))
        return 0 if result["complete_telemetry"] else 2
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == "__main__":
    raise SystemExit(main())
