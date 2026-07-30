#!/usr/bin/env python3
"""Run one reproducible experiment 09 safety-ablation trial."""

from __future__ import annotations

import argparse
import csv
import json
import math
import os
import platform
import signal
import subprocess
import time
from pathlib import Path
from typing import Any, Dict, List, Mapping

import rclpy
from geometry_msgs.msg import Point
from px4_msgs.msg import VehicleStatus
from rcl_interfaces.srv import SetParameters
from rclpy.node import Node
from rclpy.parameter import Parameter
from rclpy.qos import qos_profile_sensor_data
from rosgraph_msgs.msg import Clock
from uav_swarm_interfaces.msg import IAPFDebug, UAVStatus, UAVSwarmCommand

from analysis_core import analyze_trial, write_dict_rows
from experiment_common import (
    RESULTS_ROOT,
    allocate_targets,
    assignment_mode,
    experiment_id,
    lfs_metadata,
    load_configuration,
    paired_input_digest,
    perturb_groups,
    scenario_groups,
)


ODOM_FIELDS = ["timestamp", "uav_id", "x", "y", "z"]
DEBUG_FIELDS = [
    "timestamp", "experiment_id", "scenario", "method", "trial", "seed",
    "phase", "family",
    "mission_id", "uav_id", "avoidance_mode", "has_nearest_neighbor",
    "nearest_neighbor_id", "nearest_neighbor_distance",
    "nearest_neighbor_closing_speed", "iapf_active", "hysteresis_active",
    "active_neighbor_count",
    "raw_repulsion_x", "raw_repulsion_y", "raw_repulsion_z",
    "position_offset_x", "position_offset_y", "position_offset_z",
    "acceleration_offset_x", "acceleration_offset_y", "acceleration_offset_z",
    "position_saturated", "acceleration_saturated", "valid_neighbor_count",
    "stale_neighbor_count", "nominal_ref_x", "nominal_ref_y", "nominal_ref_z",
    "modulated_ref_x", "modulated_ref_y", "modulated_ref_z",
    "nominal_acceleration_x", "nominal_acceleration_y",
    "nominal_acceleration_z", "modulated_acceleration_x",
    "modulated_acceleration_y", "modulated_acceleration_z",
]


def command_output(command: List[str], cwd: Path | None = None) -> str:
    result = subprocess.run(
        command, cwd=cwd, text=True, stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT, check=False)
    return result.stdout.strip()


def git_metadata(repository: Path) -> Dict[str, Any]:
    status = ["git", "status", "--porcelain"]
    if (repository / "experiments" / "results" / "experiments_09").is_dir():
        status.extend([
            "--", ".",
            ":(exclude)experiments/results/experiments_09",
        ])
    return {
        "commit": command_output(["git", "rev-parse", "HEAD"], repository),
        "dirty": bool(command_output(status, repository)),
    }


def write_csv(path: Path, fields: List[str], rows: List[Mapping[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


class TrialNode(Node):
    def __init__(self, context: Mapping[str, Any], uav_ids: List[int]):
        super().__init__("experiment_09_runner")
        self.trial_context = context
        self.uav_ids = uav_ids
        self.odom_rows: List[Dict[str, Any]] = []
        self.debug_rows: List[Dict[str, Any]] = []
        self.events: List[Dict[str, Any]] = []
        self.positions: Dict[int, List[float]] = {}
        self.position_speeds = {uav_id: math.inf for uav_id in uav_ids}
        self.position_update_times: Dict[int, float] = {}
        self.stable = {uav_id: False for uav_id in uav_ids}
        self.formal_recording = False
        self.px4_failsafe = False
        self.sim_clock: float | None = None
        self.sim_clock_start: float | None = None
        self.wall_clock_start: float | None = None
        self.command_publishers = {
            uav_id: self.create_publisher(
                UAVSwarmCommand, f"/uav{uav_id}/swarm_command", 10)
            for uav_id in uav_ids
        }
        self.trial_subscriptions = []
        for uav_id in uav_ids:
            self.trial_subscriptions.append(self.create_subscription(
                Point, f"/uav{uav_id}/odom",
                lambda msg, uid=uav_id: self.odom_callback(msg, uid), 20))
            self.trial_subscriptions.append(self.create_subscription(
                UAVStatus, f"/uav{uav_id}/status",
                lambda msg, uid=uav_id: self.status_callback(msg, uid), 20))
            self.trial_subscriptions.append(self.create_subscription(
                IAPFDebug, f"/uav{uav_id}/iapf_debug",
                lambda msg, uid=uav_id: self.debug_callback(msg, uid), 50))
            self.trial_subscriptions.append(self.create_subscription(
                VehicleStatus, f"/px4_{uav_id}/fmu/out/vehicle_status",
                lambda msg, uid=uav_id: self.vehicle_status_callback(msg, uid),
                qos_profile_sensor_data))
        self.trial_subscriptions.append(self.create_subscription(
            Clock, "/clock", self.clock_callback, qos_profile_sensor_data))

    def timestamp(self) -> float:
        return self.get_clock().now().nanoseconds / 1e9

    def event(self, name: str, uav_id: int = 0, detail: str = "") -> None:
        self.events.append({
            "timestamp": self.timestamp(), "event": name,
            "uav_id": uav_id, "detail": detail})

    def odom_callback(self, msg: Point, uav_id: int) -> None:
        timestamp = self.timestamp()
        update_time = time.monotonic()
        if uav_id in self.positions:
            elapsed = update_time - self.position_update_times[uav_id]
            if elapsed > 1e-6:
                self.position_speeds[uav_id] = (
                    math.dist(self.positions[uav_id], [msg.x, msg.y, msg.z])
                    / elapsed)
        self.positions[uav_id] = [msg.x, msg.y, msg.z]
        self.position_update_times[uav_id] = update_time
        self.odom_rows.append({
            "timestamp": timestamp, "uav_id": uav_id,
            "x": msg.x, "y": msg.y, "z": msg.z})

    def status_callback(self, msg: UAVStatus, uav_id: int) -> None:
        value = bool(msg.is_hover_stable)
        if value != self.stable[uav_id]:
            self.event("hover_stable" if value else "hover_unstable", uav_id)
        self.stable[uav_id] = value

    def debug_callback(self, msg: IAPFDebug, uav_id: int) -> None:
        def vector(prefix: str, value: Any) -> Dict[str, float]:
            return {
                f"{prefix}_x": value.x,
                f"{prefix}_y": value.y,
                f"{prefix}_z": value.z,
            }
        row: Dict[str, Any] = {
            "timestamp": self.timestamp(),
            **self.trial_context,
            "mission_id": msg.mission_id,
            "uav_id": uav_id,
            "avoidance_mode": msg.avoidance_mode,
            "has_nearest_neighbor": msg.has_nearest_neighbor,
            "nearest_neighbor_id": msg.nearest_neighbor_id,
            "nearest_neighbor_distance": msg.nearest_neighbor_distance,
            "nearest_neighbor_closing_speed":
                msg.nearest_neighbor_closing_speed,
            "iapf_active": msg.iapf_active,
            "hysteresis_active": msg.hysteresis_active,
            "active_neighbor_count": msg.active_neighbor_count,
            "position_saturated": msg.position_saturated,
            "acceleration_saturated": msg.acceleration_saturated,
            "valid_neighbor_count": msg.valid_neighbor_count,
            "stale_neighbor_count": msg.stale_neighbor_count,
        }
        row.update(vector("raw_repulsion", msg.raw_repulsion))
        row.update(vector("position_offset", msg.position_offset))
        row.update(vector("acceleration_offset", msg.acceleration_offset))
        row.update(vector("nominal_ref", msg.nominal_reference))
        row.update(vector("modulated_ref", msg.modulated_reference))
        row.update(vector("nominal_acceleration", msg.nominal_acceleration))
        row.update(vector("modulated_acceleration", msg.modulated_acceleration))
        self.debug_rows.append(row)

    def vehicle_status_callback(
        self, msg: VehicleStatus, uav_id: int
    ) -> None:
        if self.formal_recording and (
                msg.failsafe or msg.failure_detector_status != msg.FAILURE_NONE):
            if not self.px4_failsafe:
                self.event(
                    "px4_failsafe", uav_id,
                    f"failsafe={msg.failsafe},failure={msg.failure_detector_status}")
            self.px4_failsafe = True

    def clock_callback(self, msg: Clock) -> None:
        self.sim_clock = msg.clock.sec + msg.clock.nanosec / 1e9

    def begin_formal_recording(self) -> None:
        self.formal_recording = True
        self.px4_failsafe = False
        self.sim_clock_start = self.sim_clock
        self.wall_clock_start = time.monotonic()

    def rtf_summary(self) -> Dict[str, float | None]:
        if (
            self.sim_clock_start is None or self.sim_clock is None
            or self.wall_clock_start is None
        ):
            return {"sim_seconds": None, "wall_seconds": None, "rtf": None}
        wall = time.monotonic() - self.wall_clock_start
        sim = self.sim_clock - self.sim_clock_start
        return {
            "sim_seconds": sim, "wall_seconds": wall,
            "rtf": sim / wall if wall > 0.0 else None,
        }

    def spin_for(self, duration: float) -> None:
        end = time.monotonic() + duration
        while time.monotonic() < end:
            rclpy.spin_once(self, timeout_sec=min(0.1, end - time.monotonic()))

    def wait_for_odom(self, timeout: float) -> bool:
        end = time.monotonic() + timeout
        while time.monotonic() < end:
            rclpy.spin_once(self, timeout_sec=0.1)
            if all(uav_id in self.positions for uav_id in self.uav_ids):
                return True
        return False

    def send_goals(
        self, groups: List[Dict[str, Any]], mission_id: int, duration: float,
        motion_style: str, safety_factor: float
    ) -> None:
        commanded_ids = {
            uav_id for group in groups for uav_id in group["uav_ids"]}
        for uav_id in commanded_ids:
            self.stable[uav_id] = False
        for group in groups:
            for uav_id, target in zip(group["uav_ids"], group["targets"]):
                message = UAVSwarmCommand()
                message.header.stamp = self.get_clock().now().to_msg()
                message.header.frame_id = "world"
                message.mission_id = mission_id
                message.uav_id = uav_id
                message.target_pos.x = float(target[0])
                message.target_pos.y = float(target[1])
                message.target_pos.z = float(target[2])
                message.duration = float(duration)
                message.motion_style = motion_style
                message.safety_factor = float(safety_factor)
                self.command_publishers[uav_id].publish(message)
        self.event(
            "command_sent",
            detail=f"mission={mission_id},uavs={sorted(commanded_ids)}")

    def wait_for_stable(
        self, timeout: float, hold_time: float,
        disturbance: Mapping[str, Any] | None = None,
    ) -> bool:
        end = time.monotonic() + timeout
        start = time.monotonic()
        stable_start = None
        disturbance_started = False
        disturbance_finished = False
        while time.monotonic() < end:
            rclpy.spin_once(self, timeout_sec=0.1)
            elapsed = time.monotonic() - start
            if disturbance and disturbance.get("type") in (
                    "temporary_hold", "reference_bias"):
                trigger = float(disturbance.get(
                    "trigger_time", disturbance.get("start_time", 0.0)))
                finish = trigger + float(disturbance["duration"])
                uav_id = int(disturbance["uav_id"])
                if elapsed >= trigger and not disturbance_started:
                    values: Dict[str, Any]
                    if disturbance["type"] == "temporary_hold":
                        values = {"experiment_reference_hold": True}
                    else:
                        offset = disturbance["offset"]
                        values = {
                            "experiment_reference_bias_x": float(offset[0]),
                            "experiment_reference_bias_y": float(offset[1]),
                            "experiment_reference_bias_z": float(offset[2]),
                        }
                    set_controller_parameters(self, [uav_id], values)
                    self.event(
                        "disturbance_started", uav_id,
                        json.dumps(dict(disturbance), sort_keys=True))
                    disturbance_started = True
                if elapsed >= finish and disturbance_started and not disturbance_finished:
                    reset = (
                        {"experiment_reference_hold": False}
                        if disturbance["type"] == "temporary_hold"
                        else {
                            "experiment_reference_bias_x": 0.0,
                            "experiment_reference_bias_y": 0.0,
                            "experiment_reference_bias_z": 0.0,
                        })
                    set_controller_parameters(self, [uav_id], reset)
                    self.event("disturbance_finished", uav_id)
                    disturbance_finished = True
            if all(self.stable.values()):
                stable_start = stable_start or time.monotonic()
                if time.monotonic() - stable_start >= hold_time:
                    return True
            else:
                stable_start = None
        if disturbance_started and not disturbance_finished:
            reset = (
                {"experiment_reference_hold": False}
                if disturbance["type"] == "temporary_hold"
                else {
                    "experiment_reference_bias_x": 0.0,
                    "experiment_reference_bias_y": 0.0,
                    "experiment_reference_bias_z": 0.0,
                })
            set_controller_parameters(self, [int(disturbance["uav_id"])], reset)
        return False

    def wait_for_positions(
        self, targets: Mapping[int, List[float]], timeout: float,
        hold_time: float, tolerance: float = 0.3,
        speed_tolerance: float = 0.3,
    ) -> bool:
        end = time.monotonic() + timeout
        stable_start = None
        while time.monotonic() < end:
            rclpy.spin_once(self, timeout_sec=0.1)
            now = time.monotonic()
            settled = all(
                uav_id in self.positions
                and now - self.position_update_times[uav_id] <= 0.5
                and math.dist(self.positions[uav_id], target) < tolerance
                and self.position_speeds[uav_id] < speed_tolerance
                for uav_id, target in targets.items())
            if settled:
                stable_start = stable_start or now
                if now - stable_start >= hold_time:
                    return True
            else:
                stable_start = None
        return False


def preposition_uavs(
    node: TrialNode, groups: List[Dict[str, Any]], trial: int,
    hold_time: float
) -> bool:
    """Move to initial states through vertically separated transit lanes."""
    desired = {
        uav_id: list(target)
        for group in groups
        for uav_id, target in zip(group["uav_ids"], group["initial"])
    }
    uav_ids = sorted(desired)
    maximum_initial_z = max(target[2] for target in desired.values())
    transit = {
        uav_id: maximum_initial_z + 1.5 * (index + 1)
        for index, uav_id in enumerate(uav_ids)
    }
    current = {uav_id: list(node.positions[uav_id]) for uav_id in uav_ids}

    phases = [
        (
            "vertical_separation",
            {
                uav_id: [current[uav_id][0], current[uav_id][1], transit[uav_id]]
                for uav_id in uav_ids
            },
            1.0,
        ),
        (
            "horizontal_transit",
            {
                uav_id: [
                    desired[uav_id][0], desired[uav_id][1], transit[uav_id]]
                for uav_id in uav_ids
            },
            1.5,
        ),
        ("final_descent", desired, 1.0),
    ]
    for phase_index, (name, targets, nominal_speed) in enumerate(phases):
        start = {
            uav_id: list(node.positions.get(uav_id, current[uav_id]))
            for uav_id in uav_ids
        }
        maximum_distance = max(
            math.dist(start[uav_id], targets[uav_id]) for uav_id in uav_ids)
        duration = max(5.0, maximum_distance / nominal_speed)
        node.event("preposition_phase", detail=name)
        node.send_goals(
            [{"uav_ids": uav_ids,
              "targets": [targets[uav_id] for uav_id in uav_ids]}],
            900000 + trial * 10 + phase_index, duration, "normal", 0.0)
        if node.wait_for_positions(
                targets, duration + 10.0, hold_time):
            continue
        node.event("preposition_correction", detail=name)
        correction_targets = {
            uav_id: [
                target[axis] + target[axis] - node.positions[uav_id][axis]
                for axis in range(3)]
            for uav_id, target in targets.items()
        }
        node.send_goals(
            [{"uav_ids": uav_ids,
              "targets": [
                  correction_targets[uav_id] for uav_id in uav_ids]}],
            910000 + trial * 10 + phase_index, 8.0, "normal", 0.0)
        if not node.wait_for_positions(targets, 28.0, hold_time):
            node.event("preposition_failed", detail=name)
            return False
    return True


def set_controller_parameters(
    node: Node, uav_ids: List[int], values: Mapping[str, Any]
) -> None:
    for uav_id in uav_ids:
        remote_node = f"/uav{uav_id}/ladrc_position_controller"
        client = node.create_client(
            SetParameters, f"{remote_node}/set_parameters")
        try:
            if not client.wait_for_service(timeout_sec=5.0):
                raise RuntimeError(
                    f"parameter service unavailable for {remote_node}")
            parameters = [
                Parameter(name=name, value=value) for name, value in values.items()]
            request = SetParameters.Request()
            request.parameters = [
                parameter.to_parameter_msg() for parameter in parameters]
            future = client.call_async(request)
            rclpy.spin_until_future_complete(node, future, timeout_sec=5.0)
            if not future.done():
                raise RuntimeError(
                    f"timed out setting parameters on {remote_node}")
            failures = [
                f"{parameter.name}: {result.reason}"
                for parameter, result in zip(
                    parameters, future.result().results)
                if not result.successful]
            if failures:
                raise RuntimeError(
                    f"failed to set {remote_node}: {'; '.join(failures)}")
        finally:
            node.destroy_client(client)


def select_group_uavs(
    groups: List[Dict[str, Any]], selected_ids: set[int]
) -> List[Dict[str, Any]]:
    selected: List[Dict[str, Any]] = []
    for group in groups:
        rows = [
            (uav_id, target)
            for uav_id, target in zip(group["uav_ids"], group["targets"])
            if uav_id in selected_ids
        ]
        if rows:
            selected.append({
                "uav_ids": [row[0] for row in rows],
                "targets": [row[1] for row in rows],
            })
    return selected


def start_rosbag(trial_dir: Path, uav_ids: List[int]) -> subprocess.Popen:
    topics = []
    for uav_id in uav_ids:
        topics.extend([
            f"/uav{uav_id}/odom",
            f"/uav{uav_id}/status",
            f"/uav{uav_id}/iapf_debug",
            f"/uav{uav_id}/trajectory_metrics",
            f"/uav{uav_id}/swarm_command",
            f"/px4_{uav_id}/fmu/out/vehicle_odometry",
            f"/px4_{uav_id}/fmu/out/vehicle_status",
        ])
    log_handle = (trial_dir / "rosbag_record.log").open("w", encoding="utf-8")
    process = subprocess.Popen(
        ["ros2", "bag", "record", "-o", str(trial_dir / "rosbag2"), *topics],
        stdout=log_handle, stderr=subprocess.STDOUT, start_new_session=True)
    process._experiment_log_handle = log_handle  # type: ignore[attr-defined]
    time.sleep(1.0)
    if process.poll() is not None:
        raise RuntimeError("rosbag recorder exited during startup")
    return process


def stop_rosbag(process: subprocess.Popen | None) -> None:
    if process is None:
        return
    if process.poll() is None:
        os.killpg(process.pid, signal.SIGINT)
        try:
            process.wait(timeout=15)
        except subprocess.TimeoutExpired:
            os.killpg(process.pid, signal.SIGTERM)
            process.wait(timeout=5)
    handle = getattr(process, "_experiment_log_handle", None)
    if handle:
        handle.close()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--scenario", required=True)
    parser.add_argument("--method", required=True)
    parser.add_argument("--trial", type=int, required=True)
    parser.add_argument("--seed", type=int, required=True)
    parser.add_argument("--batch-id", required=True)
    parser.add_argument("--results-root", type=Path)
    parser.add_argument("--phase", default="unspecified")
    parser.add_argument("--family", default="unspecified")
    parser.add_argument("--parameter-override", action="append", default=[])
    parser.add_argument("--escape-mode")
    parser.add_argument("--condition-label")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--no-rosbag", action="store_true")
    return parser.parse_args()


def parse_overrides(values: List[str]) -> Dict[str, float]:
    result = {}
    for value in values:
        name, separator, raw = value.partition("=")
        if not separator:
            raise ValueError(f"invalid parameter override: {value}")
        result[name] = float(raw)
    return result


def main() -> int:
    args = parse_args()
    defaults, method, scenario = load_configuration(args.scenario, args.method)
    result_method = args.condition_label or args.method
    overrides = parse_overrides(args.parameter_override)
    iapf_parameters = dict(defaults["iapf"])
    iapf_parameters.update(overrides)
    if args.escape_mode:
        iapf_parameters["iapf_escape_mode"] = args.escape_mode
    mode = assignment_mode(scenario, method)
    base_groups = scenario_groups(scenario)
    paired_groups = perturb_groups(
        base_groups, args.seed, float(scenario.get("randomization_range", 0.0)))
    input_digest = paired_input_digest(scenario, paired_groups, args.seed)
    allocation_started = time.perf_counter()
    groups, allocation_metrics = allocate_targets(
        paired_groups, float(scenario["duration"]), mode,
        float(defaults["safety"]["d_assignment"]))
    assignment_compute_time_ms = (
        time.perf_counter() - allocation_started) * 1000.0
    uav_ids = [uav_id for group in groups for uav_id in group["uav_ids"]]
    identifier = experiment_id(
        args.batch_id, args.scenario, result_method, args.trial, args.seed)
    results_root = args.results_root or RESULTS_ROOT
    trial_dir = (
        results_root / args.batch_id / "raw" / args.scenario / result_method
        / f"trial_{args.trial:02d}_seed_{args.seed}")
    if trial_dir.exists() and any(trial_dir.iterdir()):
        raise FileExistsError(f"refusing to overwrite {trial_dir}")
    trial_dir.mkdir(parents=True, exist_ok=True)
    context = {
        "experiment_id": identifier, "scenario": args.scenario,
        "method": result_method, "trial": args.trial, "seed": args.seed,
        "phase": args.phase, "family": args.family,
    }
    assignment_rows = []
    for group_index, group in enumerate(groups):
        for uav_id, initial, target in zip(
                group["uav_ids"], group["initial"], group["targets"]):
            assignment_rows.append({
                **context, "group": group_index, "uav_id": uav_id,
                "assignment_mode": mode,
                "initial_x": initial[0], "initial_y": initial[1],
                "initial_z": initial[2], "target_x": target[0],
                "target_y": target[1], "target_z": target[2],
            })
    write_dict_rows(trial_dir / "assignment.csv", assignment_rows)

    repo_root = Path(__file__).resolve().parents[3]
    px4_root = Path(os.environ.get("PX4_AUTOPILOT_DIR", "/home/yihuang/PX4-Autopilot"))
    metadata: Dict[str, Any] = {
        **context,
        "batch_id": args.batch_id,
        "phase": args.phase,
        "git": git_metadata(repo_root),
        "px4": git_metadata(px4_root) if px4_root.is_dir() else {"missing": True},
        "date_time": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "uav_ids": uav_ids,
        "duration": float(scenario["duration"]),
        "motion_style": scenario["motion_style"],
        "assignment_mode": mode,
        "avoidance_mode": method["avoidance_mode"],
        "base_method": args.method,
        "iapf_parameters": iapf_parameters,
        "safety_thresholds": defaults["safety"],
        "analysis": {
            "sample_hz": defaults["experiment"]["sample_hz"],
            "max_odom_gap": defaults["experiment"]["max_odom_gap"],
            "final_position_tolerance": defaults["experiment"][
                "final_position_tolerance"],
            "stall_distance": defaults["experiment"]["stall_distance"],
            "stall_speed": defaults["experiment"]["stall_speed"],
            "stall_duration": defaults["experiment"]["stall_duration"],
        },
        "control_frequency": defaults["experiment"]["control_frequency"],
        "simulator_version": command_output(["gzserver", "--version"]).splitlines()[:1],
        "ros_distribution": os.environ.get("ROS_DISTRO", "unknown"),
        "platform": platform.platform(),
        "assignment_metrics": allocation_metrics,
        "assignment_compute_time_ms": assignment_compute_time_ms,
        "paired_input_digest": input_digest,
        "lfs": lfs_metadata(args.scenario),
        "disturbance": scenario.get("disturbance"),
        "outcome": {},
    }
    (trial_dir / "run_metadata.json").write_text(
        json.dumps(metadata, indent=2, ensure_ascii=False), encoding="utf-8")
    if args.dry_run:
        print(trial_dir)
        return 0

    rclpy.init()
    node = TrialNode(context, uav_ids)
    bag_process = None
    formal_odom_start = 0
    formal_debug_start = 0
    outcome = {
        "hover_stable": False, "timed_out": False, "px4_failsafe": False,
        "node_crash": False, "failure_reason": "unknown",
    }
    try:
        if not node.wait_for_odom(20.0):
            outcome["failure_reason"] = "stale_odometry"
            raise RuntimeError("did not receive odometry from all UAVs")
        set_controller_parameters(node, uav_ids, {"avoidance_mode": "off"})
        if not preposition_uavs(
                node, groups, args.trial,
                float(scenario["pre_hold_time"])):
            outcome["failure_reason"] = "invalid_initialization"
            raise RuntimeError("UAVs did not stabilize at initial positions")

        formal_parameters = dict(iapf_parameters)
        formal_parameters["avoidance_mode"] = method["avoidance_mode"]
        formal_parameters.update({
            "experiment_reference_hold": False,
            "experiment_reference_bias_x": 0.0,
            "experiment_reference_bias_y": 0.0,
            "experiment_reference_bias_z": 0.0,
        })
        set_controller_parameters(node, uav_ids, formal_parameters)
        formal_odom_start = len(node.odom_rows)
        formal_debug_start = len(node.debug_rows)
        node.events.clear()
        if not args.no_rosbag:
            bag_process = start_rosbag(trial_dir, uav_ids)
        node.begin_formal_recording()
        mission_id = int(identifier[-8:], 16) & 0xFFFFFFFF
        disturbance = scenario.get("disturbance")
        if disturbance and disturbance.get("type") in (
                "command_delay", "group_command_delay"):
            delayed_ids = {
                int(value) for value in disturbance.get(
                    "uav_ids", [disturbance.get("uav_id")])
            }
            immediate = select_group_uavs(groups, set(uav_ids) - delayed_ids)
            delayed = select_group_uavs(groups, delayed_ids)
            node.send_goals(
                immediate, mission_id, float(scenario["duration"]),
                scenario["motion_style"], 1.0)
            node.event(
                "disturbance_started", min(delayed_ids),
                json.dumps(dict(disturbance), sort_keys=True))
            node.spin_for(float(disturbance["delay_sec"]))
            node.send_goals(
                delayed, mission_id, float(scenario["duration"]),
                scenario["motion_style"], 1.0)
            node.event(
                "disturbance_finished", min(delayed_ids),
                detail=f"uavs={sorted(delayed_ids)}")
        else:
            node.send_goals(
                groups, mission_id, float(scenario["duration"]),
                scenario["motion_style"], 1.0)
        stable = node.wait_for_stable(
            float(scenario["timeout"]),
            float(defaults["experiment"]["stable_hold_time"]),
            disturbance)
        outcome["hover_stable"] = stable
        outcome["timed_out"] = not stable
        outcome["px4_failsafe"] = node.px4_failsafe
        outcome["failure_reason"] = (
            "px4_failsafe" if node.px4_failsafe
            else ("none" if stable else "timeout"))
        node.spin_for(float(scenario["post_hold_time"]))
    except Exception:
        if outcome["failure_reason"] == "unknown":
            outcome["failure_reason"] = "node_crash"
            outcome["node_crash"] = True
        raise
    finally:
        stop_rosbag(bag_process)
        write_csv(
            trial_dir / "odom.csv", ODOM_FIELDS,
            node.odom_rows[formal_odom_start:])
        write_csv(
            trial_dir / "iapf_debug.csv", DEBUG_FIELDS,
            node.debug_rows[formal_debug_start:])
        write_dict_rows(
            trial_dir / "mission_events.csv",
            node.events or [{
                "timestamp": node.timestamp(), "event": "no_events",
                "uav_id": 0, "detail": "",
            }])
        metadata["outcome"] = outcome
        metadata["rtf_summary"] = node.rtf_summary()
        (trial_dir / "run_metadata.json").write_text(
            json.dumps(metadata, indent=2, ensure_ascii=False), encoding="utf-8")
        node.destroy_node()
        rclpy.shutdown()

    pairs, summary = analyze_trial(trial_dir)
    write_dict_rows(
        trial_dir / "pair_summary.csv",
        [pair.__dict__ for pair in pairs])
    write_dict_rows(trial_dir / "trial_summary.csv", [summary])
    print(trial_dir)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
