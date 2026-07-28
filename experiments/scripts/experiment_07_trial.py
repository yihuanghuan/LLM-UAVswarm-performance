#!/usr/bin/env python3
"""Run one natural-language-to-Gazebo trial for experiment 07."""

from __future__ import annotations

import argparse
import json
import math
import time
import zlib
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List

import rclpy
from geometry_msgs.msg import Point
from px4_msgs.msg import VehicleStatus
from rclpy.node import Node
from rclpy.qos import qos_profile_sensor_data
from uav_swarm_interfaces.msg import (
    ControlAdaptationLog,
    TrajectoryMetrics,
    UAVStatus,
    UAVSwarmCommand,
)

from experiment_07_config import (
    COMMANDS,
    DURATION_S,
    FORMATION,
    FORMATION_RADIUS,
    OBSERVATION_S,
    ROS_AUX_INFO,
    TARGET,
    UAV_ID,
    validate,
)
from location_allocate.location_allocate import FormationGenerator, TopologyAllocator
from location_allocate.no_location import parse_uav_command


class ParseGateError(RuntimeError):
    """Raised when the LLM output differs from the preregistered mission."""


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--method", required=True)
    parser.add_argument("--style", choices=COMMANDS, required=True)
    parser.add_argument("--repeat", type=int, required=True)
    parser.add_argument("--trial-id", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--parse-output", type=Path, required=True)
    parser.add_argument("--discovery-timeout", type=float, default=35.0)
    return parser.parse_args()


def validate_compiled_result(result: Dict[str, object], expected_style: str) -> Dict[str, object]:
    tasks = result.get("task_sequences")
    if not isinstance(tasks, list) or len(tasks) != 1:
        raise ParseGateError("expected exactly one compiled task")
    task = tasks[0]
    if not isinstance(task, dict):
        raise ParseGateError("compiled task is not an object")
    checks = {
        "uav_id": task.get("uav_id") == [UAV_ID],
        "uav_count": task.get("uav_count") == 1,
        "duration": math.isclose(float(task.get("duration_seconds", math.nan)), DURATION_S),
        "style": task.get("motion_profile") == expected_style,
        "center": all(
            math.isclose(float(actual), expected, abs_tol=1e-6)
            for actual, expected in zip(task.get("global_center", []), TARGET)
        ) and len(task.get("global_center", [])) == 3,
        "formation": (
            isinstance(task.get("parametric_data"), dict)
            and task["parametric_data"].get("formation_type") == FORMATION
        ),
        "radius": (
            isinstance(task.get("parametric_data"), dict)
            and math.isclose(
                float(task["parametric_data"].get("formation_radius", math.nan)),
                FORMATION_RADIUS,
            )
        ),
    }
    failed = [name for name, passed in checks.items() if not passed]
    if failed:
        raise ParseGateError("preregistration mismatch: " + ", ".join(failed))
    return task


class TrialNode(Node):
    def __init__(self, args: argparse.Namespace) -> None:
        super().__init__("experiment_07_trial")
        self.args = args
        self.position: List[float] | None = None
        self.vehicle_status: VehicleStatus | None = None
        self.uav_status: UAVStatus | None = None
        self.metrics: TrajectoryMetrics | None = None
        self.adaptation: ControlAdaptationLog | None = None
        self.command_pub = self.create_publisher(
            UAVSwarmCommand, f"/uav{UAV_ID}/swarm_command", 10
        )
        self.subscription_handles = [
            self.create_subscription(
                Point, f"/uav{UAV_ID}/odom", self._odom_callback, 10
            ),
            self.create_subscription(
                UAVStatus, f"/uav{UAV_ID}/status", self._status_callback, 10
            ),
            self.create_subscription(
                TrajectoryMetrics,
                f"/uav{UAV_ID}/trajectory_metrics",
                self._metrics_callback,
                10,
            ),
            self.create_subscription(
                ControlAdaptationLog,
                f"/uav{UAV_ID}/control_adaptation",
                self._adaptation_callback,
                10,
            ),
            self.create_subscription(
                VehicleStatus,
                f"/px4_{UAV_ID}/fmu/out/vehicle_status",
                self._vehicle_status_callback,
                qos_profile_sensor_data,
            ),
        ]

    def _odom_callback(self, message: Point) -> None:
        self.position = [message.x, message.y, message.z]

    def _status_callback(self, message: UAVStatus) -> None:
        self.uav_status = message

    def _metrics_callback(self, message: TrajectoryMetrics) -> None:
        self.metrics = message

    def _adaptation_callback(self, message: ControlAdaptationLog) -> None:
        self.adaptation = message

    def _vehicle_status_callback(self, message: VehicleStatus) -> None:
        self.vehicle_status = message

    def wait_ready(self) -> None:
        deadline = time.monotonic() + self.args.discovery_timeout
        while rclpy.ok() and time.monotonic() < deadline:
            rclpy.spin_once(self, timeout_sec=0.2)
            status = self.vehicle_status
            if (
                self.position is not None
                and self.count_subscribers(f"/uav{UAV_ID}/swarm_command") > 0
                and status is not None
                and status.arming_state == VehicleStatus.ARMING_STATE_ARMED
                and status.nav_state == VehicleStatus.NAVIGATION_STATE_OFFBOARD
                and not status.failsafe
            ):
                return
        raise TimeoutError("PX4/controller did not reach armed OFFBOARD readiness")

    def publish_task(self, task: Dict[str, object]) -> float:
        if self.position is None:
            raise RuntimeError("current odometry is unavailable")
        generator = FormationGenerator(
            list(task["global_center"]),
            float(task["parametric_data"]["formation_radius"]),
        )
        targets = generator.generate(
            str(task["parametric_data"]["formation_type"]), 1
        )
        allocator = TopologyAllocator()
        allocated = allocator.allocate(
            [self.position],
            targets,
            duration=float(task["duration_seconds"]),
        )
        target = [float(value) for value in allocated[0]]
        if any(not math.isclose(value, expected, abs_tol=1e-6)
               for value, expected in zip(target, TARGET)):
            raise RuntimeError(f"allocated target differs from preregistration: {target}")

        message = UAVSwarmCommand()
        message.header.stamp = self.get_clock().now().to_msg()
        message.header.frame_id = "world"
        message.mission_id = zlib.crc32(self.args.trial_id.encode()) & 0xFFFFFFFF
        message.uav_id = UAV_ID
        message.target_pos.x, message.target_pos.y, message.target_pos.z = target
        message.duration = float(task["duration_seconds"])
        message.motion_style = str(task["motion_profile"])
        safety = task.get("iapf_safety_margin_factor")
        message.safety_factor = float(safety) if safety is not None else 1.0

        scheduled = time.monotonic()
        for _ in range(10):
            self.command_pub.publish(message)
            cycle_end = time.monotonic() + 0.1
            while rclpy.ok() and time.monotonic() < cycle_end:
                rclpy.spin_once(self, timeout_sec=0.02)
        return scheduled

    def monitor(self, command_time: float) -> Dict[str, object]:
        deadline = command_time + OBSERVATION_S
        while rclpy.ok() and time.monotonic() < deadline:
            rclpy.spin_once(self, timeout_sec=0.1)

        adaptation = self.adaptation
        complete = (
            adaptation is not None
            and adaptation.motion_style == self.args.style
            and math.isfinite(float(adaptation.gain_multiplier))
            and self.metrics is not None
            and float(self.metrics.elapsed_time) >= DURATION_S
        )
        return {
            "trial_id": self.args.trial_id,
            "method": self.args.method,
            "motion_style": self.args.style,
            "repeat": self.args.repeat,
            "completed_at_utc": datetime.now(timezone.utc).isoformat(),
            "complete_telemetry": complete,
            "hover_stable": bool(self.uav_status and self.uav_status.is_hover_stable),
            "gain_multiplier": (
                float(adaptation.gain_multiplier) if adaptation is not None else None
            ),
            "target_distance": (
                float(adaptation.target_distance) if adaptation is not None else None
            ),
            "duration_s": (
                float(adaptation.duration) if adaptation is not None else None
            ),
        }


def main() -> int:
    validate()
    args = parse_args()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.parse_output.parent.mkdir(parents=True, exist_ok=True)
    rclpy.init()
    node = TrialNode(args)
    try:
        node.wait_ready()
        parse_started = time.monotonic()
        result = parse_uav_command(COMMANDS[args.style], ROS_AUX_INFO)
        parse_elapsed_ms = round((time.monotonic() - parse_started) * 1000.0, 3)
        parse_record = {
            "trial_id": args.trial_id,
            "method": args.method,
            "motion_style": args.style,
            "repeat": args.repeat,
            "command": COMMANDS[args.style],
            "parse_elapsed_ms": parse_elapsed_ms,
            "compiled_result": result,
        }
        try:
            task = validate_compiled_result(result, args.style)
        except ParseGateError as exc:
            parse_record["gate_passed"] = False
            parse_record["gate_error"] = str(exc)
            args.parse_output.write_text(
                json.dumps(parse_record, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            return 3
        parse_record["gate_passed"] = True
        args.parse_output.write_text(
            json.dumps(parse_record, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        command_time = node.publish_task(task)
        status = node.monitor(command_time)
        args.output.write_text(
            json.dumps(status, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        print(json.dumps(status, ensure_ascii=False, indent=2))
        return 0 if status["complete_telemetry"] else 2
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == "__main__":
    raise SystemExit(main())
