#!/usr/bin/env python3
"""Extract C0-E safety, IAPF, tracking, and scene-semantic metrics."""
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
import yaml


def vector(value):
    return np.asarray([value.x, value.y, value.z], dtype=float)


def read_bag(path):
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


def integrate(times, values):
    if len(times) < 2:
        return 0.0
    return float(np.trapz(np.asarray(values, dtype=float), np.asarray(times, dtype=float)))


def interpolate_states(records, ids, start, end):
    source = {uid: [] for uid in ids}
    for timestamp, topic, message in records:
        if start - 0.2 <= timestamp <= end + 0.2 and topic.endswith("/swarm_state"):
            uid = int(topic.split("/")[1][3:])
            if uid in source:
                source[uid].append((timestamp, vector(message.pose.pose.position),
                                    vector(message.twist.twist.linear)))
    if any(len(source[uid]) < 2 for uid in ids):
        raise RuntimeError("insufficient scored swarm_state samples")
    grid = np.arange(start, end + 1e-9, 0.02)
    positions, velocities = {}, {}
    for uid, samples in source.items():
        times = np.asarray([item[0] for item in samples])
        positions[uid] = np.column_stack([
            np.interp(grid, times, [item[1][axis] for item in samples])
            for axis in range(3)
        ])
        velocities[uid] = np.column_stack([
            np.interp(grid, times, [item[2][axis] for item in samples])
            for axis in range(3)
        ])
    return grid, positions, velocities


def first_motion_diagnostic(grid, positions, velocities, pairs, family):
    """Select a representative early-interaction relative-motion sample.

    Minimum-jerk commands start at zero velocity, while the first measured
    nonzero sample can contain residual hover noise.  Closing scenes therefore
    use the strongest closing sample in the first 2.5 s; the separating scene
    uses the first clearly separating sample for the initially closest pair.
    """
    candidates = []
    for pair in pairs:
        first, second = map(int, pair)
        relative_p = positions[first] - positions[second]
        relative_v = velocities[first] - velocities[second]
        speed = np.linalg.norm(relative_v, axis=1)
        moving = np.flatnonzero((speed > 0.10) & ((grid - grid[0]) <= 2.5))
        if family == "already_separating":
            separating = [index for index in moving
                          if float(np.dot(relative_p[index], relative_v[index])) > 0.0]
            index = int(separating[0]) if separating else (int(moving[0]) if len(moving) else 0)
        else:
            index = int(min(
                moving, key=lambda value: float(np.dot(relative_p[value], relative_v[value]))
            )) if len(moving) else 0
        dot = float(np.dot(relative_p[index], relative_v[index]))
        lateral = float(np.linalg.norm(np.cross(relative_p[index], relative_v[index])) /
                        max(speed[index], 1e-12))
        distance = float(np.linalg.norm(relative_p[index]))
        candidates.append((distance, first, second, index, dot, lateral,
                           float(relative_v[index, 2])))
    if family == "already_separating":
        return min(candidates, key=lambda item: item[0])
    return min(candidates, key=lambda item: item[4])


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("trial_dir", type=Path)
    parser.add_argument("--scene-definitions", type=Path, required=True)
    args = parser.parse_args()
    manifest = json.loads((args.trial_dir / "manifest.json").read_text())
    definitions = yaml.safe_load(args.scene_definitions.read_text())
    scene = definitions["scenes"][manifest["scene"]]
    result = {"trial_id": manifest["trial_id"], "metric_extraction_success": False}
    try:
        records = read_bag(args.trial_dir / "rosbag")
        score_ids = set(int(value) for value in manifest["score_task_ids"])
        commands = [
            (timestamp, message) for timestamp, topic, message in records
            if topic.endswith("/execution_command") and int(message.task_id) in score_ids
        ]
        if not commands:
            raise RuntimeError("interaction execution commands missing")
        start = min(item[0] for item in commands)
        end = max(item[0] + float(item[1].profile.duration) for item in commands)
        ids = [int(value) for value in manifest["participants"]]
        grid, positions, velocities = interpolate_states(records, ids, start, end)
        pairs = list(itertools.combinations(ids, 2))
        pair_distances = {
            pair: np.linalg.norm(positions[pair[0]] - positions[pair[1]], axis=1)
            for pair in pairs
        }
        min_pair, min_values = min(pair_distances.items(), key=lambda item: float(item[1].min()))
        below = np.any(np.column_stack([values < 1.50 for values in pair_distances.values()]), axis=1)
        hard_entries = int(np.count_nonzero(below & ~np.r_[False, below[:-1]]))
        hard_duration = float(np.count_nonzero(below) * 0.02)
        initial_min = min(float(values[0]) for values in pair_distances.values())

        critical = first_motion_diagnostic(
            grid, positions, velocities, scene["critical_pair_candidates"],
            scene["family"],
        )
        _, first, second, motion_index, closing_dot, lateral, vertical_speed = critical
        critical_distance = float(np.linalg.norm(positions[first][motion_index] - positions[second][motion_index]))
        v_first, v_second = velocities[first][motion_index], velocities[second][motion_index]
        velocity_cosine = float(np.dot(v_first, v_second) /
                                max(np.linalg.norm(v_first) * np.linalg.norm(v_second), 1e-12))

        policy = yaml.safe_load(Path(manifest["policy"]).read_text())
        hard = float(policy["safety"]["d_hard"])
        enter = hard + float(manifest["s"]) * (float(policy["safety"]["iapf_enter_base"]) - hard)
        exit_distance = hard + float(manifest["s"]) * (float(policy["safety"]["iapf_exit_base"]) - hard)
        soft_neighbor_count = max(
            sum(float(values[index]) <= exit_distance + 0.03 for values in pair_distances.values())
            for index in range(len(grid))
        )
        family = scene["family"]
        semantics = initial_min > hard
        if family == "head_on_closing":
            semantics &= closing_dot < 0.0 and lateral <= 1.75 and velocity_cosine < -0.70
        elif family == "offset_crossing":
            semantics &= closing_dot < 0.0 and lateral > 0.20 and abs(velocity_cosine) < 0.80
        elif family == "vertical_crossing":
            semantics &= closing_dot < 0.0 and abs(vertical_speed) > 0.20
        elif family == "dense_interaction":
            semantics &= soft_neighbor_count >= 2
        elif family == "already_separating":
            semantics &= closing_dot > 0.0 and critical_distance <= 1.90

        iapf_by_uav = {uid: [] for uid in ids}
        tracking_errors, final_errors = [], []
        acceleration_saturated = 0
        acceleration_samples = 0
        for timestamp, topic, message in records:
            if not start <= timestamp <= end + 0.5:
                continue
            uid = int(topic.split("/")[1][3:]) if topic.startswith("/uav") else None
            if topic.endswith("/iapf_debug") and uid in iapf_by_uav:
                iapf_by_uav[uid].append((timestamp, message))
            elif topic.endswith("/control_tracking_debug"):
                tracking_errors.append(float(np.linalg.norm(vector(message.tracking_error))))
                if message.has_command:
                    acceleration_samples += 1
                    if np.max(np.abs(vector(message.px4_acceleration_setpoint))) >= 4.999:
                        acceleration_saturated += 1
            elif topic.endswith("/trajectory_metrics") and message.is_finished:
                final_errors.append(float(message.final_position_error))

        active_duration = position_integral = acceleration_integral = 0.0
        activation_count = deactivation_count = clamp_activity = 0
        position_peaks, acceleration_peaks = [], []
        for samples in iapf_by_uav.values():
            times = [item[0] for item in samples]
            active = [bool(item[1].iapf_active) for item in samples]
            position_norm = [float(np.linalg.norm(vector(item[1].position_offset))) for item in samples]
            acceleration_norm = [float(np.linalg.norm(vector(item[1].acceleration_offset))) for item in samples]
            if len(times) > 1:
                active_duration += integrate(times, [float(value) for value in active])
                position_integral += integrate(times, position_norm)
                acceleration_integral += integrate(times, acceleration_norm)
            activation_count += sum(not a and b for a, b in zip(active, active[1:]))
            deactivation_count += sum(a and not b for a, b in zip(active, active[1:]))
            clamp_activity += sum(
                bool(item[1].position_saturated or item[1].acceleration_saturated)
                for item in samples
            )
            position_peaks.extend(position_norm)
            acceleration_peaks.extend(acceleration_norm)
        toggles = activation_count + deactivation_count
        chatter = max(0, toggles - 2 * len(ids))
        result.update({
            "score_start_bag_s": start, "score_end_bag_s": end,
            "min_pair_distance_m": float(min_values.min()),
            "min_pair": list(min_pair), "hard_violation_count": hard_entries,
            "hard_violation_duration_s": hard_duration,
            "candidate_completed": bool(manifest["candidate_completed"]),
            "mission_failure": not bool(manifest["candidate_completed"]),
            "stall": False, "timeout": "Timeout" in manifest["failure_reason"],
            "iapf_active_duration_s": active_duration,
            "activation_count": activation_count,
            "deactivation_count": deactivation_count,
            "chatter_toggle_count": chatter,
            "integrated_position_modulation": position_integral,
            "peak_position_modulation": max(position_peaks, default=0.0),
            "integrated_acceleration_modulation": acceleration_integral,
            "peak_acceleration_modulation": max(acceleration_peaks, default=0.0),
            "clamp_activity": clamp_activity,
            "tracking_rmse_m": math.sqrt(np.mean(np.square(tracking_errors))) if tracking_errors else None,
            "final_error_m": max(final_errors) if final_errors else None,
            "acceleration_saturation_ratio": (
                acceleration_saturated / acceleration_samples if acceleration_samples else None
            ),
            "scene_semantics_valid": bool(semantics),
            "critical_pair": [first, second],
            "initial_pair_distance_m": initial_min,
            "initial_critical_distance_m": critical_distance,
            "relative_closing_metric": closing_dot,
            "lateral_offset_m": lateral,
            "relative_vertical_speed_mps": vertical_speed,
            "critical_velocity_cosine": velocity_cosine,
            "neighbor_count": int(soft_neighbor_count),
            "scene_initially_safe": bool(initial_min > hard),
            "metric_extraction_success": True,
        })
    except Exception as error:
        result["error"] = f"{type(error).__name__}: {error}"
    (args.trial_dir / "metrics.json").write_text(
        json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(json.dumps({
        "trial_id": result["trial_id"],
        "metric_extraction_success": result["metric_extraction_success"],
        "scene_semantics_valid": result.get("scene_semantics_valid"),
        "error": result.get("error"),
    }, sort_keys=True))
    return 0 if result["metric_extraction_success"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
