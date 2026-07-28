#!/usr/bin/env python3
"""Run one reproducible experiment 08 trial against a running simulator."""

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
from rclpy.node import Node
from rclpy.qos import qos_profile_sensor_data
from rosgraph_msgs.msg import Clock
from uav_swarm_interfaces.msg import IAPFDebug, UAVStatus, UAVSwarmCommand

from analysis_core import analyze_trial, write_dict_rows
from experiment_common import (
    RESULTS_ROOT,
    allocate_targets,
    assignment_mode,
    experiment_id,
    load_configuration,
    perturb_groups,
    scenario_groups,
)


ODOM_FIELDS = ["timestamp", "uav_id", "x", "y", "z"]
DEBUG_FIELDS = [
    "timestamp", "experiment_id", "scenario", "method", "trial", "seed", "phase",
    "mission_id", "uav_id", "avoidance_mode", "has_nearest_neighbor",
    "nearest_neighbor_id", "nearest_neighbor_distance", "iapf_active",
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
    return {
        "commit": command_output(["git", "rev-parse", "HEAD"], repository),
        "dirty": bool(command_output(["git", "status", "--porcelain"], repository)),
    }


def write_csv(path: Path, fields: List[str], rows: List[Mapping[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


class TrialNode(Node):
    def __init__(self, context: Mapping[str, Any], uav_ids: List[int]):
        super().__init__("experiment_08_runner")
        self.context = context
        self.uav_ids = uav_ids
        self.odom_rows: List[Dict[str, Any]] = []
        self.debug_rows: List[Dict[str, Any]] = []
        self.events: List[Dict[str, Any]] = []
        self.positions: Dict[int, List[float]] = {}
        self.stable = {uav_id: False for uav_id in uav_ids}
        self.formal_recording = False
        self.px4_failsafe = False
        self.sim_clock: float | None = None
        self.sim_clock_start: float | None = None
        self.wall_clock_start: float | None = None
        self.publishers = {
            uav_id: self.create_publisher(
                UAVSwarmCommand, f"/uav{uav_id}/swarm_command", 10)
            for uav_id in uav_ids
        }
        self.subscriptions = []
        for uav_id in uav_ids:
            self.subscriptions.append(self.create_subscription(
                Point, f"/uav{uav_id}/odom",
                lambda msg, uid=uav_id: self.odom_callback(msg, uid), 20))
            self.subscriptions.append(self.create_subscription(
                UAVStatus, f"/uav{uav_id}/status",
                lambda msg, uid=uav_id: self.status_callback(msg, uid), 20))
            self.subscriptions.append(self.create_subscription(
                IAPFDebug, f"/uav{uav_id}/iapf_debug",
                lambda msg, uid=uav_id: self.debug_callback(msg, uid), 50))
            self.subscriptions.append(self.create_subscription(
                VehicleStatus, f"/px4_{uav_id}/fmu/out/vehicle_status",
                lambda msg, uid=uav_id: self.vehicle_status_callback(msg, uid),
                qos_profile_sensor_data))
        self.subscriptions.append(self.create_subscription(
            Clock, "/clock", self.clock_callback, qos_profile_sensor_data))

    def timestamp(self) -> float:
        return self.get_clock().now().nanoseconds / 1e9

    def event(self, name: str, uav_id: int = 0, detail: str = "") -> None:
        self.events.append({
            "timestamp": self.timestamp(), "event": name,
            "uav_id": uav_id, "detail": detail})

    def odom_callback(self, msg: Point, uav_id: int) -> None:
        timestamp = self.timestamp()
        self.positions[uav_id] = [msg.x, msg.y, msg.z]
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
            **self.context,
            "mission_id": msg.mission_id,
            "uav_id": uav_id,
            "avoidance_mode": msg.avoidance_mode,
            "has_nearest_neighbor": msg.has_nearest_neighbor,
            "nearest_neighbor_id": msg.nearest_neighbor_id,
            "nearest_neighbor_distance": msg.nearest_neighbor_distance,
            "iapf_active": msg.iapf_active,
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
        for uav_id in self.uav_ids:
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
                self.publishers[uav_id].publish(message)
        self.event("command_sent", detail=f"mission={mission_id}")

    def wait_for_stable(self, timeout: float, hold_time: float) -> bool:
        end = time.monotonic() + timeout
        stable_start = None
        while time.monotonic() < end:
            rclpy.spin_once(self, timeout_sec=0.1)
            if all(self.stable.values()):
                stable_start = stable_start or time.monotonic()
                if time.monotonic() - stable_start >= hold_time:
                    return True
            else:
                stable_start = None
        return False


def set_controller_parameters(
    uav_ids: List[int], values: Mapping[str, Any]
) -> None:
    for uav_id in uav_ids:
        node = f"/uav{uav_id}/ladrc_position_controller"
        for name, value in values.items():
            rendered = str(value).lower() if isinstance(value, bool) else str(value)
            result = subprocess.run(
                ["ros2", "param", "set", node, name, rendered],
                text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                check=False)
            if result.returncode != 0 or "Successful" not in result.stdout:
                raise RuntimeError(
                    f"failed to set {node} {name}: {result.stdout.strip()}")


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
    parser.add_argument("--phase", default="unspecified")
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
    groups = perturb_groups(
        base_groups, args.seed, float(scenario.get("randomization_range", 0.0)))
    groups, allocation_metrics = allocate_targets(
        groups, float(scenario["duration"]), mode,
        float(defaults["safety"]["d_assignment"]))
    uav_ids = [uav_id for group in groups for uav_id in group["uav_ids"]]
    identifier = experiment_id(
        args.batch_id, args.scenario, result_method, args.trial, args.seed)
    trial_dir = (
        RESULTS_ROOT / args.batch_id / "raw" / args.scenario / result_method
        / f"trial_{args.trial:02d}_seed_{args.seed}")
    if trial_dir.exists() and any(trial_dir.iterdir()):
        raise FileExistsError(f"refusing to overwrite {trial_dir}")
    trial_dir.mkdir(parents=True, exist_ok=True)
    context = {
        "experiment_id": identifier, "scenario": args.scenario,
        "method": result_method, "trial": args.trial, "seed": args.seed,
        "phase": args.phase,
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
        set_controller_parameters(uav_ids, {"avoidance_mode": "off"})
        preposition_groups = [
            {**group, "targets": group["initial"]} for group in groups]
        node.send_goals(
            preposition_groups, 900000 + args.trial, 5.0,
            scenario["motion_style"], 0.0)
        if not node.wait_for_stable(
                30.0, float(scenario["pre_hold_time"])):
            outcome["failure_reason"] = "invalid_initialization"
            raise RuntimeError("UAVs did not stabilize at initial positions")

        formal_parameters = dict(iapf_parameters)
        formal_parameters["avoidance_mode"] = method["avoidance_mode"]
        set_controller_parameters(uav_ids, formal_parameters)
        formal_odom_start = len(node.odom_rows)
        formal_debug_start = len(node.debug_rows)
        node.events.clear()
        if not args.no_rosbag:
            bag_process = start_rosbag(trial_dir, uav_ids)
        node.begin_formal_recording()
        mission_id = int(identifier[-8:], 16) & 0xFFFFFFFF
        node.send_goals(
            groups, mission_id, float(scenario["duration"]),
            scenario["motion_style"], 1.0)
        stable = node.wait_for_stable(
            float(scenario["timeout"]),
            float(defaults["experiment"]["stable_hold_time"]))
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
