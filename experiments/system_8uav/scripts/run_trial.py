#!/usr/bin/env python3
"""Run one end-to-end experiment 10 trial against an eight-UAV ROS stack."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import signal
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Sequence

from system_common import (
    CONFIG_PATH,
    EXPERIMENT_ROOT,
    REPO_ROOT,
    TaskDefinition,
    config_checksum,
    git_revision,
    load_task,
    load_yaml,
    stage_groups,
    utc_now,
    verify_llm_intent,
    write_csv,
    write_json,
)


ODOM_FIELDS = [
    "timestamp", "uav_id", "x", "y", "z", "speed", "raw_ekf_speed",
]
STATUS_FIELDS = [
    "timestamp", "uav_id", "mission_id", "system_ready", "is_hover_stable",
    "stability_state", "position_error", "speed", "raw_ekf_speed",
]
TRAJECTORY_FIELDS = [
    "timestamp", "uav_id", "mission_id", "start_x", "start_y", "start_z",
    "target_x", "target_y", "target_z", "requested_duration",
    "trajectory_duration", "motion_style", "safety_factor", "path_length",
    "max_velocity", "max_acceleration", "max_jerk",
    "integrated_squared_jerk", "elapsed_time", "arrival_time_error",
    "final_position_error", "is_finished", "is_hover_stable",
]
CONTROL_FIELDS = [
    "timestamp", "mission_id", "uav_id", "motion_style",
    "target_distance", "duration", "average_speed", "gain_multiplier",
    "omega_o_x", "omega_o_y", "omega_o_z", "omega_c_x", "omega_c_y",
    "omega_c_z", "peak_velocity", "peak_acceleration", "settling_time",
    "reported_tracking_rmse",
]
IAPF_FIELDS = [
    "timestamp", "mission_id", "uav_id", "avoidance_mode",
    "has_nearest_neighbor", "nearest_neighbor_id",
    "nearest_neighbor_distance", "nearest_neighbor_closing_speed",
    "iapf_active", "hysteresis_active", "active_neighbor_count",
    "raw_repulsion_x", "raw_repulsion_y", "raw_repulsion_z",
    "position_offset_x", "position_offset_y", "position_offset_z",
    "acceleration_offset_x", "acceleration_offset_y", "acceleration_offset_z",
    "position_saturated", "acceleration_saturated", "valid_neighbor_count",
    "stale_neighbor_count", "nominal_ref_x", "nominal_ref_y",
    "nominal_ref_z", "modulated_ref_x", "modulated_ref_y",
    "modulated_ref_z", "nominal_accel_x", "nominal_accel_y",
    "nominal_accel_z", "modulated_accel_x", "modulated_accel_y",
    "modulated_accel_z",
]
COMMAND_FIELDS = [
    "timestamp", "mission_id", "uav_id", "target_x", "target_y", "target_z",
    "duration", "motion_style", "safety_factor",
]
RESOURCE_FIELDS = [
    "timestamp", "cpu_percent", "memory_used_bytes", "memory_percent",
    "real_time_factor",
]
EVENT_FIELDS = [
    "timestamp", "event", "stage_id", "mission_ids", "uav_ids", "success",
    "failure_reason", "duration_s", "assignment_compute_time_ms",
    "planned_xy_crossings", "planned_proximity_crossings",
    "planned_min_distance", "local_swap_iterations", "dispatch_skew_ms",
    "mission_id", "uav_id", "position_error", "speed",
]

FROZEN_LFS_ROOT = EXPERIMENT_ROOT / "frozen_lfs"


class SystemSampler:
    """Sample host CPU and memory without an optional Python dependency."""

    def __init__(self):
        self.previous_cpu = self._cpu_totals()

    @staticmethod
    def _cpu_totals() -> tuple[int, int]:
        values = [
            int(value) for value in Path("/proc/stat").read_text(
                encoding="utf-8").splitlines()[0].split()[1:]
        ]
        idle = values[3] + (values[4] if len(values) > 4 else 0)
        return sum(values), idle

    @staticmethod
    def _memory() -> tuple[int, float]:
        entries = {}
        content = Path("/proc/meminfo").read_text(encoding="utf-8")
        for line in content.splitlines():
            key, value = line.split(":", 1)
            entries[key] = int(value.strip().split()[0]) * 1024
        total = entries["MemTotal"]
        available = entries["MemAvailable"]
        used = total - available
        return used, used * 100.0 / total

    def sample(self) -> tuple[float, int, float]:
        total, idle = self._cpu_totals()
        previous_total, previous_idle = self.previous_cpu
        self.previous_cpu = total, idle
        delta_total = total - previous_total
        cpu = (
            100.0 * (delta_total - (idle - previous_idle)) / delta_total
            if delta_total > 0 else 0.0)
        used, percent = self._memory()
        return cpu, used, percent


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--task", required=True, choices=[
        "task_a_simple", "task_b_sequential", "task_c_grouped",
        "task_d_dense", "task_e_mixed"])
    parser.add_argument("--trial", type=int, required=True)
    parser.add_argument("--attempt-id", required=True)
    parser.add_argument("--target-execution-index", type=int, required=True)
    parser.add_argument("--replacement-for", default="")
    parser.add_argument("--batch-id", required=True)
    parser.add_argument(
        "--phase", choices=["pilot", "formal", "diagnostic"], default="formal")
    parser.add_argument("--config", default=str(CONFIG_PATH))
    parser.add_argument("--results-root")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--no-rosbag", action="store_true")
    parser.add_argument("--readiness-only", action="store_true")
    parser.add_argument("--input-mode", choices=["llm", "replay"], default="llm")
    parser.add_argument("--replay-lfs-root", default=str(FROZEN_LFS_ROOT))
    revision = git_revision(REPO_ROOT)
    parser.add_argument(
        "--execution-commit",
        default=revision["commit"],
        help="git commit of the code that runs this attempt (auto-detected)")
    parser.add_argument(
        "--execution-commit-dirty",
        action="store_true", default=False,
        help="mark the executing working tree as dirty")
    return parser.parse_args()


def load_frozen_lfs(task_type: str, root: Path) -> tuple[Dict[str, Any], str, Path]:
    path = root / f"{task_type}.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    canonical = json.dumps(
        payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    checksum = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    return payload, checksum, path


def topic_list() -> set[str]:
    result = subprocess.run(
        ["ros2", "topic", "list"], text=True, stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT, check=False)
    if result.returncode:
        raise RuntimeError(f"ros2 topic list failed: {result.stdout.strip()}")
    return set(result.stdout.splitlines())


def required_topics(uav_ids: Sequence[int]) -> List[str]:
    topics = ["/clock", "/gazebo/performance_metrics"]
    for uid in uav_ids:
        topics.extend([
            f"/uav{uid}/odom",
            f"/uav{uid}/status",
            f"/uav{uid}/trajectory_metrics",
            f"/uav{uid}/control_adaptation",
            f"/uav{uid}/iapf_debug",
            f"/uav{uid}/swarm_command",
            f"/px4_{uid}/fmu/out/vehicle_odometry",
            f"/px4_{uid}/fmu/out/vehicle_status",
        ])
    return topics


def wait_for_topics(uav_ids: Sequence[int], timeout: float) -> None:
    expected = set(required_topics(uav_ids))
    deadline = time.monotonic() + timeout
    missing = expected
    while time.monotonic() < deadline:
        missing = expected - topic_list()
        if not missing:
            return
        time.sleep(1.0)
    raise RuntimeError("missing_required_topics:" + ",".join(sorted(missing)))


def start_rosbag(trial_dir: Path, uav_ids: Sequence[int]) -> subprocess.Popen:
    topics = required_topics(uav_ids)
    if "/fmu/out/vehicle_odometry" in topic_list():
        topics.append("/fmu/out/vehicle_odometry")
    log_handle = (trial_dir / "rosbag_record.log").open("w", encoding="utf-8")
    process = subprocess.Popen(
        ["ros2", "bag", "record", "-o", str(trial_dir / "rosbag2"), *topics],
        stdout=log_handle, stderr=subprocess.STDOUT, start_new_session=True)
    process._experiment_log_handle = log_handle  # type: ignore[attr-defined]
    time.sleep(2.0)
    if process.poll() is not None:
        log_handle.close()
        raise RuntimeError("rosbag recorder exited during startup")
    return process


def stop_process(process: subprocess.Popen | None) -> None:
    if process is None:
        return
    if process.poll() is None:
        try:
            os.killpg(process.pid, signal.SIGINT)
            process.wait(timeout=15)
        except subprocess.TimeoutExpired:
            os.killpg(process.pid, signal.SIGTERM)
            process.wait(timeout=5)
        except ProcessLookupError:
            pass
    handle = getattr(process, "_experiment_log_handle", None)
    if handle:
        handle.close()


def import_ros():
    import rclpy
    from gazebo_msgs.msg import PerformanceMetrics
    from geometry_msgs.msg import Point
    from px4_msgs.msg import VehicleOdometry, VehicleStatus
    from rclpy.node import Node
    from rclpy.qos import qos_profile_sensor_data
    from rosgraph_msgs.msg import Clock
    from uav_swarm_interfaces.msg import (
        ControlAdaptationLog,
        IAPFDebug,
        TrajectoryMetrics,
        UAVStatus,
        UAVSwarmCommand,
    )
    return {
        "rclpy": rclpy, "Node": Node, "Point": Point,
        "VehicleOdometry": VehicleOdometry, "VehicleStatus": VehicleStatus,
        "PerformanceMetrics": PerformanceMetrics,
        "ControlAdaptationLog": ControlAdaptationLog,
        "IAPFDebug": IAPFDebug, "TrajectoryMetrics": TrajectoryMetrics,
        "UAVStatus": UAVStatus, "UAVSwarmCommand": UAVSwarmCommand,
        "sensor_qos": qos_profile_sensor_data,
        "Clock": Clock,
    }


def build_trial_node(
    ros: Dict[str, Any], uav_ids: Sequence[int], velocity_filter_tau: float = 0.5,
):
    Node = ros["Node"]

    class TrialNode(Node):
        def __init__(self):
            super().__init__("experiment_10_trial")
            self.started = time.monotonic()
            self.odom_rows: List[Dict[str, Any]] = []
            self.status_rows: List[Dict[str, Any]] = []
            self.trajectory_rows: List[Dict[str, Any]] = []
            self.control_rows: List[Dict[str, Any]] = []
            self.iapf_rows: List[Dict[str, Any]] = []
            self.command_rows: List[Dict[str, Any]] = []
            self.resource_rows: List[Dict[str, Any]] = []
            self.events: List[Dict[str, Any]] = []
            self.positions: Dict[int, List[float]] = {}
            self.velocities: Dict[int, float] = {}
            self.raw_ekf_velocities: Dict[int, float] = {}
            self.velocity_vectors = {
                uid: [0.0, 0.0, 0.0] for uid in uav_ids}
            self.velocity_filter_state: Dict[int, tuple[float, List[float]]] = {}
            self.velocity_filter_valid: set[int] = set()
            self.last_odom_time: Dict[int, float] = {}
            self.vehicle_status: Dict[int, Any] = {}
            self.hover_status = {uid: False for uid in uav_ids}
            self.current_mission = {uid: 0 for uid in uav_ids}
            self.command_ack: set[tuple[int, int]] = set()
            self.command_ack_times: Dict[tuple[int, int], float] = {}
            self.arrival_times: Dict[tuple[int, int], float] = {}
            self.last_stability: Dict[tuple[int, int], int] = {}
            self.reference_started: set[tuple[int, int]] = set()
            self.reference_finished: set[tuple[int, int]] = set()
            self.reference_finish_times: Dict[tuple[int, int], float] = {}
            self.last_status_time: Dict[int, float] = {}
            self.latest_status: Dict[int, Dict[str, Any]] = {}
            self.latest_iapf: Dict[int, Dict[str, Any]] = {}
            self.last_candidate_time: Dict[tuple[int, int], float] = {}
            self.last_confirmed_time: Dict[tuple[int, int], float] = {}
            self.stage_failure_diagnostics: List[Dict[str, Any]] = []
            self.entered_execution = False
            self.active_stage_id = 0
            self.latest_rtf = math.nan
            self.latest_sim_time = math.nan
            self.clock_origin: tuple[float, float] | None = None
            self.saw_performance_metrics = False
            self.system_sampler = SystemSampler()
            self.command_publishers = {
                uid: self.create_publisher(
                    ros["UAVSwarmCommand"], f"/uav{uid}/swarm_command", 10)
                for uid in uav_ids
            }
            self.trial_subscriptions = []
            for uid in uav_ids:
                self.trial_subscriptions.extend([
                    self.create_subscription(
                        ros["Point"], f"/uav{uid}/odom",
                        lambda msg, value=uid: self.odom_callback(msg, value), 20),
                    self.create_subscription(
                        ros["UAVStatus"], f"/uav{uid}/status",
                        lambda msg, value=uid: self.status_callback(msg, value), 20),
                    self.create_subscription(
                        ros["TrajectoryMetrics"], f"/uav{uid}/trajectory_metrics",
                        lambda msg, value=uid: self.trajectory_callback(msg, value), 20),
                    self.create_subscription(
                        ros["ControlAdaptationLog"], f"/uav{uid}/control_adaptation",
                        lambda msg: self.control_callback(msg), 20),
                    self.create_subscription(
                        ros["IAPFDebug"], f"/uav{uid}/iapf_debug",
                        lambda msg: self.iapf_callback(msg), 50),
                    self.create_subscription(
                        ros["UAVSwarmCommand"], f"/uav{uid}/swarm_command",
                        lambda msg: self.command_callback(msg), 20),
                    self.create_subscription(
                        ros["VehicleOdometry"],
                        f"/px4_{uid}/fmu/out/vehicle_odometry",
                        lambda msg, value=uid: self.px4_odom_callback(msg, value),
                        ros["sensor_qos"]),
                    self.create_subscription(
                        ros["VehicleStatus"],
                        f"/px4_{uid}/fmu/out/vehicle_status",
                        lambda msg, value=uid: self.vehicle_status_callback(msg, value),
                        ros["sensor_qos"]),
                ])
            self.trial_subscriptions.append(self.create_subscription(
                ros["PerformanceMetrics"], "/gazebo/performance_metrics",
                self.performance_callback, 20))
            self.trial_subscriptions.append(self.create_subscription(
                ros["Clock"], "/clock", self.clock_callback,
                ros["sensor_qos"]))
            self.resource_timer = self.create_timer(0.2, self.resource_callback)

        def stamp(self) -> float:
            return time.monotonic() - self.started

        def odom_callback(self, msg, uid: int) -> None:
            now = self.stamp()
            position = [float(msg.x), float(msg.y), float(msg.z)]
            previous = self.velocity_filter_state.get(uid)
            if previous is not None:
                previous_time, previous_position = previous
                dt = now - previous_time
                if 1e-4 < dt <= 0.5:
                    raw = [
                        (value - old) / dt
                        for value, old in zip(position, previous_position)
                    ]
                    alpha = 1.0 - math.exp(
                        -dt / max(float(velocity_filter_tau), 1e-3))
                    filtered = self.velocity_vectors[uid]
                    self.velocity_vectors[uid] = [
                        value + alpha * (sample - value)
                        for value, sample in zip(filtered, raw)
                    ]
                    self.velocities[uid] = math.sqrt(sum(
                        value * value for value in self.velocity_vectors[uid]))
                    self.velocity_filter_valid.add(uid)
                else:
                    self.velocity_vectors[uid] = [0.0, 0.0, 0.0]
                    self.velocity_filter_valid.discard(uid)
            self.velocity_filter_state[uid] = now, position
            self.positions[uid] = position
            self.last_odom_time[uid] = time.monotonic()
            self.odom_rows.append({
                "timestamp": now, "uav_id": uid, "x": msg.x, "y": msg.y,
                "z": msg.z, "speed": self.velocities.get(uid, math.nan),
                "raw_ekf_speed": self.raw_ekf_velocities.get(uid, math.nan),
            })

        def px4_odom_callback(self, msg, uid: int) -> None:
            self.raw_ekf_velocities[uid] = math.sqrt(
                sum(float(v) ** 2 for v in msg.velocity))

        def vehicle_status_callback(self, msg, uid: int) -> None:
            self.vehicle_status[uid] = msg

        def status_callback(self, msg, uid: int) -> None:
            now = self.stamp()
            mission_id = int(msg.mission_id)
            stable = bool(msg.is_hover_stable)
            state = int(msg.stability_state)
            key = (mission_id, uid)
            self.last_status_time[uid] = time.monotonic()
            if mission_id == self.current_mission.get(uid, 0):
                self.hover_status[uid] = stable
                self.latest_status[uid] = {
                    "mission_id": mission_id,
                    "system_ready": bool(msg.system_ready),
                    "stability_state": state,
                    "position_error": float(msg.position_error),
                    "speed": float(msg.speed),
                    "raw_ekf_speed": float(msg.raw_ekf_speed),
                }
            previous = self.last_stability.get(key)
            if previous != state and mission_id == self.current_mission.get(uid, 0):
                if state == 0 and previous == 1:
                    event = "stable_candidate_exit"
                elif state == 0 and previous == 2:
                    event = "stable_confirmed_exit"
                else:
                    event = {
                        0: "stable_unstable", 1: "stable_candidate_enter",
                        2: "stable_confirmed",
                    }.get(state, "stable_unknown")
                self.add_event(
                    event,
                    mission_id=mission_id, uav_id=uid,
                    uav_ids=[uid], mission_ids=[mission_id],
                    position_error=float(msg.position_error),
                    speed=float(msg.speed))
                if state == 1:
                    self.last_candidate_time[key] = now
                elif state == 2:
                    self.last_confirmed_time[key] = now
                    self.arrival_times[key] = now
                elif state == 0:
                    self.arrival_times.pop(key, None)
                self.last_stability[key] = state
            self.status_rows.append({
                "timestamp": now, "uav_id": uid,
                "mission_id": mission_id, "system_ready": msg.system_ready,
                "is_hover_stable": stable,
                "stability_state": state,
                "position_error": msg.position_error, "speed": msg.speed,
                "raw_ekf_speed": msg.raw_ekf_speed,
            })

        def trajectory_callback(self, msg, uid: int) -> None:
            mission_id = int(msg.mission_id)
            key = (mission_id, uid)
            if key not in self.reference_started:
                self.reference_started.add(key)
                self.add_event(
                    "reference_start", mission_id=mission_id, uav_id=uid,
                    mission_ids=[mission_id], uav_ids=[uid])
            if bool(msg.is_finished) and key not in self.reference_finished:
                self.reference_finished.add(key)
                self.reference_finish_times[key] = self.stamp()
                self.add_event(
                    "reference_finish", mission_id=mission_id, uav_id=uid,
                    mission_ids=[mission_id], uav_ids=[uid])
            self.trajectory_rows.append({
                "timestamp": self.stamp(), "uav_id": uid,
                "mission_id": mission_id,
                "start_x": msg.start_pos.x, "start_y": msg.start_pos.y,
                "start_z": msg.start_pos.z, "target_x": msg.target_pos.x,
                "target_y": msg.target_pos.y, "target_z": msg.target_pos.z,
                "requested_duration": msg.requested_duration,
                "trajectory_duration": msg.trajectory_duration,
                "motion_style": msg.motion_style,
                "safety_factor": msg.safety_factor, "path_length": msg.path_length,
                "max_velocity": msg.max_velocity,
                "max_acceleration": msg.max_acceleration,
                "max_jerk": msg.max_jerk,
                "integrated_squared_jerk": msg.integrated_squared_jerk,
                "elapsed_time": msg.elapsed_time,
                "arrival_time_error": msg.arrival_time_error,
                "final_position_error": msg.final_position_error,
                "is_finished": msg.is_finished,
                "is_hover_stable": msg.is_hover_stable,
            })

        def control_callback(self, msg) -> None:
            key = (int(msg.mission_id), int(msg.uav_id))
            if key not in self.command_ack:
                self.command_ack.add(key)
                self.command_ack_times[key] = self.stamp()
                self.add_event(
                    "command_acknowledged", mission_id=key[0], uav_id=key[1],
                    mission_ids=[key[0]], uav_ids=[key[1]])
            self.control_rows.append({
                "timestamp": self.stamp(), "mission_id": msg.mission_id,
                "uav_id": msg.uav_id, "motion_style": msg.motion_style,
                "target_distance": msg.target_distance, "duration": msg.duration,
                "average_speed": msg.average_speed,
                "gain_multiplier": msg.gain_multiplier,
                "omega_o_x": msg.omega_o_x, "omega_o_y": msg.omega_o_y,
                "omega_o_z": msg.omega_o_z, "omega_c_x": msg.omega_c_x,
                "omega_c_y": msg.omega_c_y, "omega_c_z": msg.omega_c_z,
                "peak_velocity": msg.peak_velocity,
                "peak_acceleration": msg.peak_acceleration,
                "settling_time": msg.settling_time,
                "reported_tracking_rmse": msg.tracking_rmse,
            })

        def iapf_callback(self, msg) -> None:
            self.latest_iapf[int(msg.uav_id)] = {
                "mission_id": int(msg.mission_id),
                "iapf_active": bool(msg.iapf_active),
                "nearest_neighbor_distance": float(msg.nearest_neighbor_distance),
            }
            self.iapf_rows.append({
                "timestamp": self.stamp(), "mission_id": msg.mission_id,
                "uav_id": msg.uav_id, "avoidance_mode": msg.avoidance_mode,
                "has_nearest_neighbor": msg.has_nearest_neighbor,
                "nearest_neighbor_id": msg.nearest_neighbor_id,
                "nearest_neighbor_distance": msg.nearest_neighbor_distance,
                "nearest_neighbor_closing_speed": msg.nearest_neighbor_closing_speed,
                "iapf_active": msg.iapf_active,
                "hysteresis_active": msg.hysteresis_active,
                "active_neighbor_count": msg.active_neighbor_count,
                "raw_repulsion_x": msg.raw_repulsion.x,
                "raw_repulsion_y": msg.raw_repulsion.y,
                "raw_repulsion_z": msg.raw_repulsion.z,
                "position_offset_x": msg.position_offset.x,
                "position_offset_y": msg.position_offset.y,
                "position_offset_z": msg.position_offset.z,
                "acceleration_offset_x": msg.acceleration_offset.x,
                "acceleration_offset_y": msg.acceleration_offset.y,
                "acceleration_offset_z": msg.acceleration_offset.z,
                "position_saturated": msg.position_saturated,
                "acceleration_saturated": msg.acceleration_saturated,
                "valid_neighbor_count": msg.valid_neighbor_count,
                "stale_neighbor_count": msg.stale_neighbor_count,
                "nominal_ref_x": msg.nominal_reference.x,
                "nominal_ref_y": msg.nominal_reference.y,
                "nominal_ref_z": msg.nominal_reference.z,
                "modulated_ref_x": msg.modulated_reference.x,
                "modulated_ref_y": msg.modulated_reference.y,
                "modulated_ref_z": msg.modulated_reference.z,
                "nominal_accel_x": msg.nominal_acceleration.x,
                "nominal_accel_y": msg.nominal_acceleration.y,
                "nominal_accel_z": msg.nominal_acceleration.z,
                "modulated_accel_x": msg.modulated_acceleration.x,
                "modulated_accel_y": msg.modulated_acceleration.y,
                "modulated_accel_z": msg.modulated_acceleration.z,
            })

        def command_callback(self, msg) -> None:
            uid = int(msg.uav_id)
            self.current_mission[uid] = int(msg.mission_id)
            self.command_rows.append({
                "timestamp": self.stamp(), "mission_id": msg.mission_id,
                "uav_id": uid, "target_x": msg.target_pos.x,
                "target_y": msg.target_pos.y, "target_z": msg.target_pos.z,
                "duration": msg.duration, "motion_style": msg.motion_style,
                "safety_factor": msg.safety_factor,
            })

        def performance_callback(self, msg) -> None:
            self.latest_rtf = float(msg.real_time_factor)
            self.saw_performance_metrics = True

        def clock_callback(self, msg) -> None:
            self.latest_sim_time = (
                float(msg.clock.sec) + float(msg.clock.nanosec) * 1e-9)

        def resource_callback(self) -> None:
            cpu, memory_used, memory_percent = self.system_sampler.sample()
            wall_time = time.monotonic()
            if (
                not self.saw_performance_metrics
                and math.isfinite(self.latest_sim_time)
            ):
                if self.clock_origin is None:
                    self.clock_origin = wall_time, self.latest_sim_time
                else:
                    origin_wall, origin_sim = self.clock_origin
                    wall_delta = wall_time - origin_wall
                    sim_delta = self.latest_sim_time - origin_sim
                    if wall_delta > 0.0 and sim_delta >= 0.0:
                        self.latest_rtf = sim_delta / wall_delta
            self.resource_rows.append({
                "timestamp": self.stamp(),
                "cpu_percent": cpu,
                "memory_used_bytes": memory_used,
                "memory_percent": memory_percent,
                "real_time_factor": self.latest_rtf,
            })

        def add_event(self, event: str, **kwargs: Any) -> None:
            row = {field: "" for field in EVENT_FIELDS}
            row.update({
                "timestamp": self.stamp(), "event": event,
                "stage_id": self.active_stage_id,
            })
            row.update(kwargs)
            for field in ("mission_ids", "uav_ids"):
                if isinstance(row.get(field), (list, tuple, set)):
                    row[field] = json.dumps(list(row[field]))
            self.events.append(row)

        def spin_for(self, seconds: float) -> None:
            deadline = time.monotonic() + seconds
            while time.monotonic() < deadline:
                ros["rclpy"].spin_once(self, timeout_sec=min(0.1, seconds))

        def ready(self, ids: Sequence[int]) -> bool:
            now = time.monotonic()
            return all(
                uid in self.positions
                and now - self.last_odom_time.get(uid, 0.0) < 0.5
                and uid in self.vehicle_status
                and int(self.vehicle_status[uid].arming_state) == 2
                and int(self.vehicle_status[uid].nav_state) == 14
                and not bool(self.vehicle_status[uid].failsafe)
                and bool(self.latest_status.get(uid, {}).get("system_ready"))
                for uid in ids
            )

        def readiness_diagnostics(self, ids: Sequence[int]) -> List[Dict[str, Any]]:
            now = time.monotonic()
            rows = []
            for uid in ids:
                vehicle = self.vehicle_status.get(uid)
                rows.append({
                    "uav_id": uid,
                    "has_odom": uid in self.positions,
                    "odom_fresh": (
                        uid in self.positions
                        and now - self.last_odom_time.get(uid, 0.0) < 0.5),
                    "has_vehicle_status": vehicle is not None,
                    "armed": bool(
                        vehicle is not None and int(vehicle.arming_state) == 2),
                    "offboard": bool(
                        vehicle is not None and int(vehicle.nav_state) == 14),
                    "failsafe": bool(
                        vehicle is not None and bool(vehicle.failsafe)),
                    "system_ready": bool(
                        self.latest_status.get(uid, {}).get("system_ready")),
                    "speed": self.velocities.get(uid, math.nan),
                    "raw_ekf_speed": self.raw_ekf_velocities.get(uid, math.nan),
                    "altitude": self.positions.get(
                        uid, [math.nan, math.nan, math.nan])[2],
                })
            return rows

        def wait_ready(
            self, ids: Sequence[int], timeout: float, hold: float,
            speed_tolerance: float, minimum_altitude: float,
        ) -> bool:
            deadline = time.monotonic() + timeout
            stable_since = None
            while time.monotonic() < deadline:
                ros["rclpy"].spin_once(self, timeout_sec=0.1)
                speeds_ok = all(
                    uid in self.velocity_filter_valid
                    and self.velocities.get(uid, math.inf) < speed_tolerance
                    for uid in ids)
                altitude_ok = all(
                    self.positions.get(uid, [0.0, 0.0, -math.inf])[2]
                    >= minimum_altitude for uid in ids)
                if self.ready(ids) and speeds_ok and altitude_ok:
                    stable_since = stable_since or time.monotonic()
                    if time.monotonic() - stable_since >= hold:
                        return True
                else:
                    stable_since = None
            return False

        def publish_command(
            self, mission_id: int, uid: int, target: Sequence[float],
            duration: float, style: str, safety_factor: float,
        ) -> float:
            msg = ros["UAVSwarmCommand"]()
            msg.header.stamp = self.get_clock().now().to_msg()
            msg.header.frame_id = "world"
            msg.mission_id = mission_id
            msg.uav_id = uid
            msg.target_pos.x, msg.target_pos.y, msg.target_pos.z = map(float, target)
            msg.duration = float(duration)
            msg.motion_style = style
            msg.safety_factor = float(safety_factor)
            self.hover_status[uid] = False
            self.current_mission[uid] = mission_id
            key = (mission_id, uid)
            self.arrival_times.pop(key, None)
            self.last_stability.pop(key, None)
            self.command_publishers[uid].publish(msg)
            self.entered_execution = True
            self.add_event(
                "command_dispatch", mission_id=mission_id, uav_id=uid,
                mission_ids=[mission_id], uav_ids=[uid])
            return time.monotonic()

        def wait_stage(
            self, mission_by_uid: Dict[int, int], targets: Dict[int, Sequence[float]],
            requested_duration: float, config: Dict[str, Any],
        ) -> tuple[bool, str]:
            experiment = config["experiment"]
            expected = {
                (mission, uid) for uid, mission in mission_by_uid.items()}

            def wait_for(predicate, seconds: float) -> bool:
                deadline = time.monotonic() + seconds
                while time.monotonic() < deadline:
                    ros["rclpy"].spin_once(self, timeout_sec=0.1)
                    if predicate():
                        return True
                return predicate()

            def stale_uavs() -> List[int]:
                now = time.monotonic()
                max_age = float(experiment["stage_data_max_age"])
                return [
                    uid for uid in mission_by_uid
                    if now - self.last_odom_time.get(uid, 0.0) > max_age
                    or now - self.last_status_time.get(uid, 0.0) > max_age
                ]

            def fail(default_reason: str) -> tuple[bool, str]:
                reason = "stage_data_stale" if stale_uavs() else default_reason
                self.stage_failure_diagnostics.append(
                    self.stage_diagnostics(
                        mission_by_uid, targets, reason,
                        float(experiment["stage_data_max_age"])))
                return False, reason

            if not wait_for(
                lambda: expected.issubset(self.command_ack),
                float(experiment["dispatch_timeout"]),
            ):
                return fail("dispatch_timeout")
            self.add_event(
                "all_commands_acknowledged",
                mission_ids=sorted(set(mission_by_uid.values())),
                uav_ids=sorted(mission_by_uid), success=True)

            reference_timeout = requested_duration + float(
                experiment["reference_finish_timeout_margin"])
            if not wait_for(
                lambda: expected.issubset(self.reference_finished),
                reference_timeout,
            ):
                return fail("reference_finish_timeout")
            self.add_event(
                "all_references_finished",
                mission_ids=sorted(set(mission_by_uid.values())),
                uav_ids=sorted(mission_by_uid), success=True)

            if not wait_for(
                lambda: all(
                    self.current_mission.get(uid) == mission
                    and self.hover_status.get(uid, False)
                    for uid, mission in mission_by_uid.items()),
                float(experiment["stabilization_timeout"]),
            ):
                return fail("stabilization_timeout")
            self.add_event(
                "all_uavs_stable",
                mission_ids=sorted(set(mission_by_uid.values())),
                uav_ids=sorted(mission_by_uid), success=True)
            return True, ""

        def stage_diagnostics(
            self, mission_by_uid: Dict[int, int],
            targets: Dict[int, Sequence[float]], reason: str,
            max_data_age: float,
        ) -> Dict[str, Any]:
            now = time.monotonic()
            rows = []
            for uid, mission in sorted(mission_by_uid.items()):
                key = (mission, uid)
                status = self.latest_status.get(uid, {})
                iapf = self.latest_iapf.get(uid, {})
                odom_age = now - self.last_odom_time.get(uid, 0.0)
                status_age = now - self.last_status_time.get(uid, 0.0)
                if key not in self.command_ack:
                    condition = "missing_command_ack"
                elif key not in self.reference_finished:
                    condition = "reference_not_finished"
                elif not self.hover_status.get(uid, False):
                    condition = "not_confirmed"
                else:
                    condition = "stage_peer_failure"
                if odom_age > max_data_age or status_age > max_data_age:
                    condition = "data_stale"
                rows.append({
                    "uav_id": uid, "mission_id": mission,
                    "command_ack": key in self.command_ack,
                    "reference_finished": key in self.reference_finished,
                    "stability_state": status.get("stability_state"),
                    "position_error": status.get("position_error"),
                    "speed": status.get("speed"),
                    "raw_ekf_speed": status.get("raw_ekf_speed"),
                    "odom_age": odom_age, "status_age": status_age,
                    "iapf_active": iapf.get("iapf_active"),
                    "nearest_neighbor_distance": iapf.get(
                        "nearest_neighbor_distance"),
                    "last_candidate_time": self.last_candidate_time.get(key),
                    "last_confirmed_time": self.last_confirmed_time.get(key),
                    "target": [float(value) for value in targets[uid]],
                    "failure_condition": condition,
                })
            return {
                "stage_id": self.active_stage_id,
                "failure_reason": reason,
                "timestamp": self.stamp(),
                "uavs": rows,
            }

    return TrialNode()


def execute_mission(
    node, task: TaskDefinition, lfs: Dict[str, Any], config: Dict[str, Any],
) -> tuple[bool, str]:
    from location_allocate.location_allocate import FormationGenerator, TopologyAllocator

    lfs_tasks = list(lfs["task_sequences"])
    cursor = 0
    for logical_group in stage_groups(task):
        group_tasks = lfs_tasks[cursor:cursor + len(logical_group)]
        cursor += len(logical_group)
        stage_id = logical_group[0].stage_id
        node.active_stage_id = stage_id
        started = time.monotonic()
        node.add_event(
            "stage_start", stage_id=stage_id,
            mission_ids=[row["task_sequence_id"] for row in group_tasks],
            uav_ids=sorted({uid for row in group_tasks for uid in row["uav_id"]}))
        grouped_inputs = []
        for row in group_tasks:
            ids = [int(uid) for uid in row["uav_id"]]
            generator = FormationGenerator(
                row["global_center"],
                row["parametric_data"]["formation_radius"])
            targets = generator.generate(
                row["parametric_data"]["formation_type"], len(ids))
            grouped_inputs.append({
                "uav_ids": ids,
                "initial": [node.positions[uid][:] for uid in ids],
                "targets": targets,
            })
        allocator = TopologyAllocator()
        allocation_started = time.perf_counter()
        if len(grouped_inputs) == 1:
            allocated, metrics = allocator.allocate_mode_with_metrics(
                grouped_inputs[0]["initial"], grouped_inputs[0]["targets"],
                duration=float(group_tasks[0]["duration_seconds"]),
                mode=config["experiment"]["assignment_mode"])
            allocated_groups = [allocated]
        else:
            allocated_groups, metrics = allocator.allocate_grouped(
                grouped_inputs,
                duration=float(group_tasks[0]["duration_seconds"]),
                mode=config["experiment"]["assignment_mode"])
        assignment_ms = (time.perf_counter() - allocation_started) * 1000.0
        node.add_event(
            "assignment_complete", stage_id=stage_id,
            mission_ids=[row["task_sequence_id"] for row in group_tasks],
            uav_ids=sorted({uid for row in group_tasks for uid in row["uav_id"]}),
            success=True, assignment_compute_time_ms=assignment_ms,
            planned_xy_crossings=metrics.xy_crossings,
            planned_proximity_crossings=metrics.proximity_crossings,
            planned_min_distance=metrics.min_distance,
            local_swap_iterations=allocator.last_iterations)

        dispatch_times: List[float] = []
        mission_by_uid: Dict[int, int] = {}
        targets_by_uid: Dict[int, Sequence[float]] = {}
        for row, group_input, allocated in zip(
            group_tasks, grouped_inputs, allocated_groups
        ):
            mission_id = int(row["task_sequence_id"])
            for uid, target in zip(group_input["uav_ids"], allocated):
                dispatch_times.append(node.publish_command(
                    mission_id, uid, target,
                    float(row["duration_seconds"]), row["motion_profile"],
                    float(row.get("iapf_safety_margin_factor") or 1.0)))
                mission_by_uid[uid] = mission_id
                targets_by_uid[uid] = target
        skew_ms = (
            (max(dispatch_times) - min(dispatch_times)) * 1000.0
            if dispatch_times else math.nan)
        node.add_event(
            "commands_dispatched", stage_id=stage_id,
            mission_ids=sorted(set(mission_by_uid.values())),
            uav_ids=sorted(mission_by_uid), success=True,
            dispatch_skew_ms=skew_ms)
        requested_duration = max(
            float(row["duration_seconds"]) for row in group_tasks)
        success, reason = node.wait_stage(
            mission_by_uid, targets_by_uid, requested_duration, config)
        node.add_event(
            "stage_end", stage_id=stage_id,
            mission_ids=sorted(set(mission_by_uid.values())),
            uav_ids=sorted(mission_by_uid), success=success,
            failure_reason=reason,
            duration_s=time.monotonic() - started)
        if not success:
            return False, reason
    return True, ""


def write_raw_csvs(node, trial_dir: Path) -> None:
    write_csv(trial_dir / "odom.csv", node.odom_rows, ODOM_FIELDS)
    write_csv(trial_dir / "status.csv", node.status_rows, STATUS_FIELDS)
    write_csv(
        trial_dir / "trajectory_metrics.csv", node.trajectory_rows,
        TRAJECTORY_FIELDS)
    write_csv(
        trial_dir / "control_adaptation.csv", node.control_rows, CONTROL_FIELDS)
    write_csv(trial_dir / "iapf_debug.csv", node.iapf_rows, IAPF_FIELDS)
    write_csv(trial_dir / "swarm_commands.csv", node.command_rows, COMMAND_FIELDS)
    write_csv(trial_dir / "system_resources.csv", node.resource_rows, RESOURCE_FIELDS)
    write_csv(trial_dir / "mission_events.csv", node.events, EVENT_FIELDS)


def main() -> int:
    args = parse_args()
    if args.trial <= 0:
        raise ValueError("--trial must be positive")
    config_path = Path(args.config).resolve()
    config = load_yaml(config_path)
    task = load_task(args.task)
    experiment = config["experiment"]
    uav_ids = [int(value) for value in experiment["uav_ids"]]
    plan = {
        "task_type": task.task_type,
        "trial_id": args.trial,
        "attempt_id": args.attempt_id,
        "target_execution_index": args.target_execution_index,
        "replacement_for": args.replacement_for,
        "phase": args.phase,
        "command_text": task.command_text,
        "stage_groups": [
            [stage.__dict__ for stage in group] for group in stage_groups(task)
        ],
        "config_checksum": config_checksum(),
        "input_mode": args.input_mode,
    }
    if args.input_mode == "replay":
        replay_lfs, replay_checksum, replay_path = load_frozen_lfs(
            args.task, Path(args.replay_lfs_root).resolve())
        semantic_ok, semantic_error = verify_llm_intent(task, replay_lfs)
        if not semantic_ok:
            raise ValueError(semantic_error)
        plan.update({
            "frozen_lfs_path": str(replay_path),
            "frozen_lfs_checksum": replay_checksum,
        })
    if args.dry_run:
        print(json.dumps(plan, indent=2, ensure_ascii=False, default=list))
        return 0

    results_root = Path(args.results_root).resolve() if args.results_root else (
        REPO_ROOT / config["paths"]["results_root"])
    phase_root = results_root / args.batch_id
    if args.phase == "pilot":
        phase_root = phase_root / "pilot"
    trial_dir = phase_root / "raw" / args.task / args.attempt_id
    if trial_dir.exists() and any(trial_dir.iterdir()):
        raise FileExistsError(f"refusing to overwrite existing trial: {trial_dir}")
    trial_dir.mkdir(parents=True, exist_ok=True)
    write_json(trial_dir / "trial_plan.json", plan)

    manifest: Dict[str, Any] = {
        "experiment_id": experiment["experiment_id"],
        "batch_id": args.batch_id,
        "task_type": args.task,
        "trial_id": args.trial,
        "attempt_id": args.attempt_id,
        "target_execution_index": args.target_execution_index,
        "replacement_for": args.replacement_for,
        "entered_execution": False,
        "phase": args.phase,
        "command_text": task.command_text,
        "llm_model": experiment["llm_model"],
        "input_mode": args.input_mode,
        "assignment_mode": experiment["assignment_mode"],
        "avoidance_mode": experiment["avoidance_mode"],
        "iapf_escape_mode": experiment["iapf_escape_mode"],
        "iapf_parameters": config["iapf"],
        "motion_styles": [stage.motion_style for stage in task.stages],
        "start_time": utc_now(),
        "end_time": "",
        "timeout": sum(
            max(stage.duration for stage in group)
            + float(experiment["dispatch_timeout"])
            + float(experiment["reference_finish_timeout_margin"])
            + float(experiment["stabilization_timeout"])
            for group in stage_groups(task)),
        "semantic_success": False,
        "execution_success": False,
        "failure_reason": "unknown",
        "rosbag_path": "" if args.no_rosbag else str(trial_dir / "rosbag2"),
        "config_checksum": config_checksum(),
        "collision_source": "distance_proxy",
        "rtf_source": "performance_metrics_or_clock",
        "manifest_stage": "runtime",
        "verdicts_pending": True,
        "execution_commit": args.execution_commit,
        "execution_commit_dirty": bool(args.execution_commit_dirty),
    }
    write_json(trial_dir / "runtime_manifest.json", manifest)

    ros = import_ros()
    ros["rclpy"].init()
    node = build_trial_node(
        ros, uav_ids, float(experiment["hover_velocity_filter_tau"]))
    bag_process = None
    failure_reason = "unknown"
    try:
        try:
            wait_for_topics(uav_ids, float(experiment["readiness_timeout"]))
        except Exception:
            failure_reason = "readiness_timeout"
            write_json(trial_dir / "readiness_failure.json", {
                "condition": "required_topics",
                "uavs": node.readiness_diagnostics(uav_ids),
                "timestamp": utc_now(),
            })
            raise
        if not node.wait_ready(
            uav_ids, float(experiment["readiness_timeout"]),
            float(experiment["stable_hold_time"]),
            float(experiment["readiness_speed_tolerance"]),
            float(experiment["readiness_min_altitude"]),
        ):
            failure_reason = "readiness_timeout"
            write_json(trial_dir / "readiness_failure.json", {
                "condition": "armed_offboard_odom_speed_hold",
                "uavs": node.readiness_diagnostics(uav_ids),
                "timestamp": utc_now(),
            })
            raise RuntimeError("UAVs did not reach armed Offboard stable readiness")
        manifest["readiness_success"] = True
        if args.readiness_only:
            failure_reason = ""
            return 0
        if not args.no_rosbag:
            bag_process = start_rosbag(trial_dir, uav_ids)

        if args.input_mode == "replay":
            lfs, replay_checksum, replay_path = load_frozen_lfs(
                args.task, Path(args.replay_lfs_root).resolve())
            manifest["frozen_lfs_path"] = str(replay_path)
            manifest["frozen_lfs_checksum"] = replay_checksum
            parse_metrics = {
                "input_mode": "replay", "llm_called": False,
                "parsing_success": True, "attempts": [],
                "frozen_lfs_path": str(replay_path),
                "frozen_lfs_checksum": replay_checksum,
            }
        else:
            from location_allocate.no_location import parse_uav_command_with_metrics
            parse_started = time.monotonic()
            lfs, parse_metrics = parse_uav_command_with_metrics(
                task.command_text,
                "当前可用无人机编号: [1,2,3,4,5,6,7,8]，总数: 8",
                config.get("llm", {}))
            parse_metrics["end_to_end_parse_elapsed_ms"] = (
                time.monotonic() - parse_started) * 1000.0
            if not parse_metrics["parsing_success"]:
                write_json(trial_dir / "llm_metrics.json", parse_metrics)
                write_json(trial_dir / "compiled_lfs.json", lfs)
                manifest["semantic_success"] = False
                failure_reason = "llm_parse_failure"
                raise RuntimeError(
                    parse_metrics.get("error_message")
                    or lfs.get("error_msg")
                    or "LLM parsing failed")
        write_json(trial_dir / "llm_metrics.json", parse_metrics)
        write_json(trial_dir / "compiled_lfs.json", lfs)
        semantic_ok, semantic_error = verify_llm_intent(task, lfs)
        if parse_metrics.get("attempts"):
            parse_metrics["attempts"][-1]["semantic_valid"] = semantic_ok
            write_json(trial_dir / "llm_metrics.json", parse_metrics)
        manifest["semantic_success"] = bool(semantic_ok)
        if not manifest["semantic_success"]:
            failure_reason = "schema_failure"
            raise RuntimeError(semantic_error)

        execution_ok, execution_reason = execute_mission(node, task, lfs, config)
        manifest["entered_execution"] = node.entered_execution
        manifest["execution_success"] = execution_ok
        if not execution_ok:
            failure_reason = execution_reason
            raise RuntimeError(execution_reason)
        node.spin_for(float(experiment["post_roll_seconds"]))
        failure_reason = ""
    except Exception as exc:
        manifest["exception"] = f"{type(exc).__name__}: {exc}"
        print(manifest["exception"], file=sys.stderr)
    finally:
        stop_process(bag_process)
        node.spin_for(0.2)
        write_raw_csvs(node, trial_dir)
        if node.stage_failure_diagnostics:
            write_json(
                trial_dir / "stage_failure_diagnostics.json",
                {"stages": node.stage_failure_diagnostics})
        manifest["rtf_source"] = (
            "gazebo_performance_metrics"
            if node.saw_performance_metrics else "clock_wall_ratio")
        manifest["end_time"] = utc_now()
        manifest["entered_execution"] = node.entered_execution
        manifest["failure_reason"] = failure_reason
        write_json(trial_dir / "runtime_manifest.json", manifest)
        node.destroy_node()
        ros["rclpy"].shutdown()

    print(trial_dir)
    return 0 if not failure_reason else 2


if __name__ == "__main__":
    raise SystemExit(main())
