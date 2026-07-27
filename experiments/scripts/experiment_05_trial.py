#!/usr/bin/env python3
"""Publish one fixed experiment-05 mission and monitor its completion."""

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
from uav_swarm_interfaces.msg import TrajectoryMetrics, UAVSwarmCommand


TARGETS = {
    1: (11.23606798, 5.19577393, 5.0),
    2: (6.76393202, 6.64885899, 5.0),
    3: (14.0, 9.0, 5.0),
    4: (6.76393202, 11.35114101, 5.0),
    5: (11.23606798, 12.80422607, 5.0),
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--profile", required=True)
    parser.add_argument("--trial-id", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--duration", type=float, default=8.0)
    parser.add_argument("--timeout-after-duration", type=float, default=20.0)
    parser.add_argument("--discovery-timeout", type=float, default=90.0)
    return parser.parse_args()


class TrialNode(Node):
    def __init__(self, args: argparse.Namespace) -> None:
        super().__init__("experiment_05_trial")
        self.args = args
        self.command_publishers = {
            uav_id: self.create_publisher(
                UAVSwarmCommand, f"/uav{uav_id}/swarm_command", 10
            )
            for uav_id in TARGETS
        }
        self.latest: Dict[int, TrajectoryMetrics] = {}
        self.ready_odom = set()
        self.metric_subscriptions = [
            self.create_subscription(
                TrajectoryMetrics,
                f"/uav{uav_id}/trajectory_metrics",
                lambda msg, uid=uav_id: self.latest.__setitem__(uid, msg),
                10,
            )
            for uav_id in TARGETS
        ]
        self.odom_subscriptions = [
            self.create_subscription(
                Point,
                f"/uav{uav_id}/odom",
                lambda _msg, uid=uav_id: self.ready_odom.add(uid),
                10,
            )
            for uav_id in TARGETS
        ]

    def wait_for_command_subscribers(self) -> None:
        deadline = time.monotonic() + self.args.discovery_timeout
        while rclpy.ok() and time.monotonic() < deadline:
            rclpy.spin_once(self, timeout_sec=0.2)
            counts = {
                uid: self.count_subscribers(f"/uav{uid}/swarm_command")
                for uid in TARGETS
            }
            if (
                all(count > 0 for count in counts.values())
                and len(self.ready_odom) == len(TARGETS)
            ):
                return
        raise TimeoutError("controllers did not publish ready odometry")

    def publish_mission(self) -> float:
        start_delay_s = 2.0
        stamp = (self.get_clock().now() + Duration(seconds=start_delay_s)).to_msg()
        digits = "".join(
            character for character in self.args.trial_id if character.isdigit()
        )
        mission_id = int(digits[-8:] or "5")
        messages = {}
        for uav_id, target in TARGETS.items():
            message = UAVSwarmCommand()
            message.header.stamp = stamp
            message.header.frame_id = "world"
            message.mission_id = mission_id
            message.uav_id = uav_id
            message.target_pos.x, message.target_pos.y, message.target_pos.z = target
            message.duration = self.args.duration
            message.motion_style = "normal"
            message.safety_factor = 0.0
            messages[uav_id] = message

        command_time = time.monotonic() + start_delay_s
        for _ in range(10):
            for uav_id, message in messages.items():
                self.command_publishers[uav_id].publish(message)
            rclpy.spin_once(self, timeout_sec=0.1)
        return command_time

    def monitor(self, command_time: float) -> Dict[str, object]:
        deadline = command_time + self.args.duration + self.args.timeout_after_duration
        while rclpy.ok() and time.monotonic() < deadline:
            rclpy.spin_once(self, timeout_sec=0.1)
            if len(self.latest) == len(TARGETS) and all(
                message.is_hover_stable for message in self.latest.values()
            ):
                break
        for _ in range(10):
            rclpy.spin_once(self, timeout_sec=0.1)

        uavs = {}
        for uav_id in TARGETS:
            message = self.latest.get(uav_id)
            arrival_error = (
                float(message.arrival_time_error) if message is not None else math.nan
            )
            arrived = (
                message is not None
                and message.is_hover_stable
                and math.isfinite(arrival_error)
            )
            uavs[str(uav_id)] = {
                "arrived": arrived,
                "arrival_time_s": self.args.duration + arrival_error if arrived else None,
                "arrival_time_error_s": arrival_error if arrived else None,
                "final_position_error_m": (
                    float(message.final_position_error) if message is not None else None
                ),
                "last_elapsed_time_s": (
                    float(message.elapsed_time) if message is not None else None
                ),
            }
        arrivals = [
            item["arrival_time_s"]
            for item in uavs.values()
            if item["arrival_time_s"] is not None
        ]
        return {
            "trial_id": self.args.trial_id,
            "profile": self.args.profile,
            "duration_s": self.args.duration,
            "completed_at_utc": datetime.now(timezone.utc).isoformat(),
            "all_arrived": len(arrivals) == len(TARGETS),
            "timeout": len(arrivals) != len(TARGETS),
            "synchronization_error_s": (
                max(arrivals) - min(arrivals) if len(arrivals) == len(TARGETS) else None
            ),
            "uavs": uavs,
        }


def main() -> int:
    args = parse_args()
    rclpy.init()
    node = TrialNode(args)
    try:
        node.wait_for_command_subscribers()
        command_time = node.publish_mission()
        result = node.monitor(command_time)
        output = Path(args.output)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(result, indent=2), encoding="utf-8")
        print(json.dumps(result, indent=2))
        return 0
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == "__main__":
    raise SystemExit(main())
