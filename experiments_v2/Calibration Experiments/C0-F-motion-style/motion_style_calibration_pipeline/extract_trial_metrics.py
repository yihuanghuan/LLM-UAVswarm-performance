#!/usr/bin/env python3
"""Extract the preregistered C0-F metrics from one trial rosbag."""
from __future__ import annotations

import argparse
import itertools
import json
import math
from pathlib import Path

import numpy as np
import rosbag2_py
from rclpy.serialization import deserialize_message
from rosidl_runtime_py.utilities import get_message

from common import load_yaml, write_json


TOL = 2e-5


def vector(value) -> np.ndarray:
    return np.asarray([value.x, value.y, value.z], dtype=float)


def read_bag(path: Path):
    reader = rosbag2_py.SequentialReader()
    reader.open(
        rosbag2_py.StorageOptions(uri=str(path), storage_id="sqlite3"),
        rosbag2_py.ConverterOptions("cdr", "cdr"),
    )
    types = {item.name: item.type for item in reader.get_all_topics_and_types()}
    messages = []
    while reader.has_next():
        topic, data, timestamp = reader.read_next()
        messages.append((timestamp / 1e9, topic, deserialize_message(data, get_message(types[topic]))))
    return messages


def uid_from_topic(topic: str) -> int | None:
    head = topic.split("/")[1] if topic.startswith("/") and len(topic.split("/")) > 1 else ""
    if head.startswith("uav") and head[3:].isdigit():
        return int(head[3:])
    if head.startswith("px4_") and head[4:].isdigit():
        return int(head[4:])
    return None


def interpolate_states(records, ids, start, end):
    source = {uid: [] for uid in ids}
    for timestamp, topic, message in records:
        uid = uid_from_topic(topic)
        if uid in source and topic.endswith("/swarm_state") and start - 0.2 <= timestamp <= end + 0.5:
            source[uid].append((timestamp, vector(message.pose.pose.position)))
    if any(len(source[uid]) < 2 for uid in ids):
        raise RuntimeError("insufficient scored swarm_state samples")
    grid = np.arange(start, end + 1e-9, 0.02)
    positions = {}
    for uid, samples in source.items():
        times = np.asarray([item[0] for item in samples])
        positions[uid] = np.column_stack([
            np.interp(grid, times, [item[1][axis] for item in samples])
            for axis in range(3)
        ])
    return grid, positions


def minimum_jerk_t_min(distance: float) -> float:
    return max(0.5, 1.875 * distance / 5.0,
               math.sqrt((10.0 / math.sqrt(3.0)) * distance / 5.0),
               (60.0 * distance / 10.0) ** (1.0 / 3.0))


def tilt_degrees(message) -> float:
    q = [float(value) for value in message.q]
    if len(q) != 4 or not all(math.isfinite(value) for value in q):
        return float("nan")
    w, x, y, z = q
    norm = math.sqrt(sum(value * value for value in q))
    if norm <= 0.0:
        return float("nan")
    w, x, y, z = (value / norm for value in (w, x, y, z))
    vertical_alignment = max(-1.0, min(1.0, 1.0 - 2.0 * (x * x + y * y)))
    return math.degrees(math.acos(vertical_alignment))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("trial_dir", type=Path)
    args = parser.parse_args()
    manifest = json.loads((args.trial_dir / "manifest.json").read_text(encoding="utf-8"))
    result = {"trial_id": manifest["trial_id"], "metric_extraction_success": False}
    try:
        records = read_bag(args.trial_dir / "rosbag")
        score_ids = set(int(value) for value in manifest["score_task_ids"])
        commands = [
            (timestamp, uid_from_topic(topic), message)
            for timestamp, topic, message in records
            if topic.endswith("/execution_command") and int(message.task_id) in score_ids
        ]
        if not commands:
            raise RuntimeError("scored execution commands missing")
        starts = {int(message.task_id): timestamp for timestamp, _, message in commands}
        start = min(starts.values())
        end = max(timestamp + float(message.profile.duration) for timestamp, _, message in commands) + 1.0
        ids = [int(value) for value in manifest["participants"]]
        grid, positions = interpolate_states(records, ids, start, end)
        pair_values = {
            pair: np.linalg.norm(positions[pair[0]] - positions[pair[1]], axis=1)
            for pair in itertools.combinations(ids, 2)
        }
        minimum_pairwise = min(float(values.min()) for values in pair_values.values())
        below = np.any(np.column_stack([values < 1.50 for values in pair_values.values()]), axis=1)
        hard_violations = int(np.count_nonzero(below & ~np.r_[False, below[:-1]]))

        scored_trajectory = []
        debug = []
        iapf = []
        adaptation = []
        attitudes = []
        for timestamp, topic, message in records:
            if not start <= timestamp <= end + 2.0:
                continue
            if topic.endswith("/trajectory_metrics") and bool(message.is_finished):
                scored_trajectory.append((timestamp, uid_from_topic(topic), message))
            elif topic.endswith("/control_tracking_debug") and bool(message.has_command):
                debug.append((timestamp, uid_from_topic(topic), message))
            elif topic.endswith("/iapf_debug"):
                iapf.append((timestamp, uid_from_topic(topic), message))
            elif topic.endswith("/control_adaptation"):
                adaptation.append((timestamp, uid_from_topic(topic), message))
            elif topic.endswith("/vehicle_attitude"):
                attitudes.append((timestamp, uid_from_topic(topic), message))
        if not debug or not scored_trajectory:
            raise RuntimeError("scored controller or trajectory diagnostics missing")

        # For ordinary trials, discard the staging completion message that may race with the score start.
        allowed_styles = ({manifest["style"]} if manifest["style"] != "style_switch"
                          else {"smooth", "normal", "aggressive"})
        scored_trajectory = [item for item in scored_trajectory if item[2].motion_style in allowed_styles]
        adaptation = [item for item in adaptation if item[2].motion_style in allowed_styles]
        if not scored_trajectory:
            raise RuntimeError("finished scored trajectory metrics missing")

        durations = [float(message.profile.duration) for _, _, message in commands]
        compiled_c = [tuple(float(v) for v in message.profile.omega_c) for _, _, message in commands]
        compiled_o = [tuple(float(v) for v in message.profile.omega_o) for _, _, message in commands]
        style_gains = [float(message.profile.style_gain) for _, _, message in commands]
        task_gains = [float(message.profile.task_gain) for _, _, message in commands]
        applied_profiles = {}
        for _, uid, message in adaptation:
            applied_profiles[(uid, message.motion_style)] = {
                "omega_c": tuple(float(getattr(message, f"omega_c_{axis}")) for axis in "xyz"),
                "omega_o": tuple(float(getattr(message, f"omega_o_{axis}")) for axis in "xyz"),
                "gain": float(message.gain_multiplier),
            }
        applied_c = [item["omega_c"] for item in applied_profiles.values()]
        applied_o = [item["omega_o"] for item in applied_profiles.values()]
        applied_gain = [item["gain"] for item in applied_profiles.values()]
        profile_mismatches = 0
        for _, uid, command in commands:
            applied = applied_profiles.get((uid, command.profile.style))
            if applied is None:
                profile_mismatches += 1
                continue
            profile_mismatches += sum(
                abs(float(requested) - actual) > TOL
                for requested, actual in zip(command.profile.omega_c, applied["omega_c"])
            )
            profile_mismatches += sum(
                abs(float(requested) - actual) > TOL
                for requested, actual in zip(command.profile.omega_o, applied["omega_o"])
            )
            expected_gain = float(command.profile.style_gain) * float(command.profile.task_gain)
            profile_mismatches += int(abs(expected_gain - applied["gain"]) > TOL)

        tracking = [float(np.linalg.norm(vector(message.tracking_error))) for _, _, message in debug]
        accel = [float(np.max(np.abs(vector(message.px4_acceleration_setpoint)))) for _, _, message in debug]
        controller_saturated = sum(value >= 4.999 for value in accel)
        finite = all(math.isfinite(value) for value in tracking + accel)
        # `is_finished` becomes true at the nominal duration and remains true
        # while the production runtime performs its hover-stability gate.  The
        # final error is therefore the last recorded completion sample per UAV,
        # not the largest lag at the first duration-boundary sample.
        final_by_uav = {}
        for timestamp, uid, message in scored_trajectory:
            if uid is not None and (uid not in final_by_uav or timestamp > final_by_uav[uid][0]):
                final_by_uav[uid] = (timestamp, float(message.final_position_error))
        final_errors = [item[1] for item in final_by_uav.values()]
        if not final_errors:
            raise RuntimeError("final completion samples missing")
        analytic_v = max(float(message.max_velocity) for _, _, message in scored_trajectory)
        analytic_a = max(float(message.max_acceleration) for _, _, message in scored_trajectory)
        analytic_j = max(float(message.max_jerk) for _, _, message in scored_trajectory)
        path_lengths = [float(message.path_length) for _, _, message in scored_trajectory]
        t_min = max(minimum_jerk_t_min(value) for value in path_lengths)

        # Absolute along-track overshoot beyond the target plane.
        command_target = {uid: vector(message.target_pos) for _, uid, message in commands}
        per_uav_debug = {uid: [] for uid in ids}
        for timestamp, uid, message in debug:
            if uid in per_uav_debug:
                per_uav_debug[uid].append((timestamp, message))
        overshoots = []
        persistent = False
        for uid, samples in per_uav_debug.items():
            if not samples or uid not in command_target:
                continue
            initial = vector(samples[0][1].nominal_position)
            target = command_target[uid]
            direction = target - initial
            norm = float(np.linalg.norm(direction))
            if norm > 1e-9:
                unit = direction / norm
                overshoots.extend(max(0.0, float(np.dot(vector(msg.actual_position) - target, unit)))
                                  for _, msg in samples)
            tail = samples[int(0.6 * len(samples)):]
            if len(tail) >= 10:
                errors = np.asarray([vector(msg.tracking_error) for _, msg in tail])
                centered = errors - errors.mean(axis=0)
                crossings = np.count_nonzero(centered[:-1] * centered[1:] < 0.0, axis=0)
                amplitude = np.ptp(errors, axis=0)
                persistent |= bool(np.any((crossings >= 8) & (amplitude > 0.15)))

        active_count = sum(bool(message.iapf_active) for _, _, message in iapf)
        iapf_clamps = sum(bool(message.position_saturated or message.acceleration_saturated)
                          for _, _, message in iapf)
        tilts = [tilt_degrees(message) for _, _, message in attitudes]
        tilts = [value for value in tilts if math.isfinite(value)]
        settling = [float(message.settling_time) for _, _, message in adaptation
                    if math.isfinite(float(message.settling_time))]
        rmse = math.sqrt(float(np.mean(np.square(tracking))))
        max_final = max(final_errors)
        instability = (not finite or max(tracking) > 2.0 or max_final > 0.50)
        feasibility_violation = analytic_v > 5.0 + TOL or analytic_a > 5.0 + TOL or analytic_j > 10.0 + TOL
        result.update({
            "mission_success": bool(manifest["mission_success"]),
            "candidate_completed": bool(manifest["candidate_completed"]),
            "T_min_s": t_min,
            "T_exec_s": max(durations),
            "motion_style": manifest["style"],
            "style_gain": max(style_gains),
            "task_gain": max(task_gains),
            "compiled_omega_c": compiled_c,
            "compiled_omega_o": compiled_o,
            "applied_omega_c": applied_c,
            "applied_omega_o": applied_o,
            "analytic_mj_velocity_peak_mps": analytic_v,
            "analytic_mj_acceleration_peak_mps2": analytic_a,
            "analytic_mj_jerk_peak_mps3": analytic_j,
            "tracking_rmse_m": rmse,
            "final_error_m": max_final,
            "settling_time_s": max(settling) if settling else None,
            "overshoot_m": max(overshoots, default=0.0),
            "controller_acceleration_saturation_ratio": controller_saturated / len(accel),
            "controller_acceleration_saturation_samples": controller_saturated,
            "profile_clamp_activity": profile_mismatches,
            "iapf_clamp_activity": iapf_clamps,
            "peak_tilt_deg": max(tilts) if tilts else None,
            "hard_safety_violation_count": hard_violations,
            "minimum_pairwise_distance_m": minimum_pairwise,
            "iapf_activation_fraction": active_count / len(iapf) if iapf else None,
            "dynamic_feasibility_violation": feasibility_violation,
            "compiled_applied_profile_consistent": profile_mismatches == 0,
            "instability_or_divergence": instability,
            "persistent_oscillation": persistent,
            "metric_extraction_success": True,
        })
    except Exception as error:
        result["error"] = f"{type(error).__name__}: {error}"
    write_json(args.trial_dir / "metrics.json", result)
    print(json.dumps(result, sort_keys=True))
    return 0 if result["metric_extraction_success"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
