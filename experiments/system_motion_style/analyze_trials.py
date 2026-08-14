#!/usr/bin/env python3
"""Extract per-command semantic motion-style metrics from validation bags."""

import argparse
from collections import Counter, defaultdict
import json
import math
from pathlib import Path
from statistics import mean

import rosbag2_py
from rclpy.serialization import deserialize_message
from rosidl_runtime_py.utilities import get_message


def norm(vector):
    return math.sqrt(vector.x ** 2 + vector.y ** 2 + vector.z ** 2)


def point_tuple(point):
    return (float(point.x), float(point.y), float(point.z))


def vector_tuple(vector):
    return (float(vector.x), float(vector.y), float(vector.z))


def percentile(values, fraction):
    ordered = sorted(values)
    return ordered[int(fraction * (len(ordered) - 1))]


def read_bag(path):
    reader = rosbag2_py.SequentialReader()
    reader.open(
        rosbag2_py.StorageOptions(uri=str(path), storage_id="sqlite3"),
        rosbag2_py.ConverterOptions("cdr", "cdr"),
    )
    types = {
        item.name: get_message(item.type)
        for item in reader.get_all_topics_and_types()
    }
    records = []
    while reader.has_next():
        topic, data, timestamp_ns = reader.read_next()
        records.append((
            timestamp_ns * 1e-9,
            topic,
            deserialize_message(data, types[topic]),
        ))
    return records


def matching(records, suffix, uav_id, start, end):
    topic = f"/uav{uav_id}/{suffix}"
    return [
        (timestamp, message)
        for timestamp, item_topic, message in records
        if item_topic == topic and start <= timestamp < end
    ]


def finite_difference_peaks(debug):
    accelerations = []
    acceleration_samples = []
    previous = None
    for timestamp, message in debug:
        velocity = vector_tuple(message.actual_velocity)
        if previous is not None:
            dt = timestamp - previous[0]
            if 0.005 <= dt <= 0.1:
                acceleration = tuple(
                    (velocity[axis] - previous[1][axis]) / dt
                    for axis in range(3)
                )
                acceleration_samples.append((timestamp, acceleration))
                accelerations.append(math.dist((0.0, 0.0, 0.0), acceleration))
        previous = (timestamp, velocity)
    jerks = []
    previous = None
    for timestamp, acceleration in acceleration_samples:
        if previous is not None:
            dt = timestamp - previous[0]
            if 0.005 <= dt <= 0.1:
                jerk = tuple(
                    (acceleration[axis] - previous[1][axis]) / dt
                    for axis in range(3)
                )
                jerks.append(math.dist((0.0, 0.0, 0.0), jerk))
        previous = (timestamp, acceleration)
    return (
        percentile(accelerations, 0.99) if accelerations else None,
        percentile(jerks, 0.99) if jerks else None,
    )


def summarize_segment(records, timestamp, end, command):
    uav_id = int(command.uav_id)
    debug = matching(records, "control_tracking_debug", uav_id, timestamp, end)
    debug = [item for item in debug if item[1].has_command]
    adaptations = matching(records, "control_adaptation", uav_id, timestamp, end)
    trajectories = matching(records, "trajectory_metrics", uav_id, timestamp, end)
    iapf = matching(records, "iapf_debug", uav_id, timestamp, end)
    status = matching(records, "status", uav_id, timestamp, end)
    if not debug or not trajectories or not adaptations:
        raise RuntimeError(
            f"incomplete metrics for UAV {uav_id} task {command.task_id}"
        )

    errors = [norm(message.tracking_error) for _, message in debug]
    speeds = [message.position_derived_speed for _, message in debug]
    z2 = [norm(message.leso_z2) for _, message in debug]
    z3 = [norm(message.leso_z3) for _, message in debug]
    saturation = [
        max(
            abs(message.ladrc_output.x),
            abs(message.ladrc_output.y),
            abs(message.ladrc_output.z),
        ) >= command.profile.acceleration_limit * 0.999
        for _, message in debug
    ]
    px4_link_errors = []
    for _, message in debug:
        expected = (
            message.ladrc_output.y,
            message.ladrc_output.x,
            -message.ladrc_output.z,
        )
        px4 = vector_tuple(message.px4_acceleration_setpoint)
        px4_link_errors.append(math.dist(expected, px4))

    target_local = (
        command.target_pos.x,
        command.target_pos.y - 3.0 * uav_id,
        command.target_pos.z,
    )
    start_local = point_tuple(debug[0][1].actual_position)
    distance = math.dist(start_local, target_local)
    if distance > 1e-9:
        direction = tuple(
            (target_local[axis] - start_local[axis]) / distance
            for axis in range(3)
        )
        overshoot = max(
            0.0,
            max(
                sum(
                    (point_tuple(message.actual_position)[axis]
                     - target_local[axis]) * direction[axis]
                    for axis in range(3)
                )
                for _, message in debug
            ),
        )
    else:
        overshoot = 0.0

    final_trajectory = trajectories[-1][1]
    final_adaptation = adaptations[-1][1]
    first_half_second = [
        message
        for sample_time, message in debug
        if sample_time - debug[0][0] <= 0.5
    ]
    acceleration_p99, jerk_p99 = finite_difference_peaks(debug)
    nearest = [
        message.nearest_neighbor_distance
        for _, message in iapf
        if message.has_nearest_neighbor
        and math.isfinite(message.nearest_neighbor_distance)
    ]
    stable_samples = [
        timestamp_value - timestamp
        for timestamp_value, message in status
        if message.is_hover_stable
    ]
    return {
        "task_id": int(command.task_id),
        "uav_id": uav_id,
        "motion_style": command.profile.style,
        "configuration_id": command.profile.configuration_id,
        "style_gain": float(command.profile.style_gain),
        "task_gain": float(command.profile.task_gain),
        "omega_c": [float(value) for value in command.profile.omega_c],
        "omega_o": [float(value) for value in command.profile.omega_o],
        "applied_gain_multiplier": float(final_adaptation.gain_multiplier),
        "applied_omega_c": [
            float(final_adaptation.omega_c_x),
            float(final_adaptation.omega_c_y),
            float(final_adaptation.omega_c_z),
        ],
        "applied_omega_o": [
            float(final_adaptation.omega_o_x),
            float(final_adaptation.omega_o_y),
            float(final_adaptation.omega_o_z),
        ],
        "t_exec_s": float(command.profile.duration),
        "target_world": point_tuple(command.target_pos),
        "start_world": point_tuple(final_trajectory.start_pos),
        "path_length_m": float(final_trajectory.path_length),
        "predicted_peak_velocity_mps": float(final_trajectory.max_velocity),
        "predicted_peak_acceleration_mps2": float(
            final_trajectory.max_acceleration
        ),
        "predicted_peak_jerk_mps3": float(final_trajectory.max_jerk),
        "tracking_rmse_m": math.sqrt(mean(value * value for value in errors)),
        "peak_tracking_error_m": max(errors),
        "switch_first_0_5s_peak_error_m": max(
            norm(message.tracking_error) for message in first_half_second
        ),
        "switch_first_0_5s_saturation_fraction": mean(
            max(
                abs(message.ladrc_output.x),
                abs(message.ladrc_output.y),
                abs(message.ladrc_output.z),
            ) >= command.profile.acceleration_limit * 0.999
            for message in first_half_second
        ),
        "settling_time_s": (
            float(final_adaptation.settling_time)
            if math.isfinite(final_adaptation.settling_time)
            else (stable_samples[0] if stable_samples else None)
        ),
        "overshoot_m": overshoot,
        "ladrc_saturation_fraction": mean(saturation),
        "leso_z2_peak": max(z2),
        "leso_z3_peak": max(z3),
        "final_position_error_m": float(final_trajectory.final_position_error),
        "position_derived_speed_peak_mps": max(speeds),
        "actual_velocity_peak_mps": max(
            norm(message.actual_velocity) for _, message in debug
        ),
        "actual_acceleration_p99_mps2": acceleration_p99,
        "actual_jerk_p99_mps3": jerk_p99,
        "px4_acceleration_link_max_error": max(px4_link_errors),
        "iapf_active_fraction": (
            mean(message.iapf_active for _, message in iapf) if iapf else 0.0
        ),
        "minimum_neighbor_distance_m": min(nearest) if nearest else None,
        "hard_safety_violation": bool(any(value < 1.0 for value in nearest)),
        "finished": bool(final_trajectory.is_finished),
        "hover_stable": bool(final_trajectory.is_hover_stable),
        "debug_samples": len(debug),
    }


def summarize_trial(trial_dir):
    manifest = json.loads((trial_dir / "manifest.json").read_text())
    records = read_bag(trial_dir / "rosbag")
    commands = []
    for timestamp, topic, message in records:
        if topic.endswith("/execution_command"):
            commands.append((timestamp, message))
    commands.sort(key=lambda item: item[0])
    bag_end = records[-1][0] + 1e-9
    segments = []
    for timestamp, command in commands:
        later = [
            other_timestamp
            for other_timestamp, other in commands
            if other.uav_id == command.uav_id and other_timestamp > timestamp
        ]
        end = min(later) if later else bag_end
        segments.append(summarize_segment(
            records, timestamp, end, command
        ))
    return {"manifest": manifest, "segments": segments}


def minimum_jerk_duration(distance):
    return max(
        0.5,
        1.875 * distance / 5.0,
        math.sqrt((10.0 / math.sqrt(3.0)) * distance / 5.0),
        (60.0 * distance / 10.0) ** (1.0 / 3.0),
    )


def aggregate(summaries):
    by_style_task = defaultdict(list)
    by_trial_task = defaultdict(list)
    for summary in summaries:
        style = summary["manifest"]["style"]
        trial = int(summary["manifest"]["trial"])
        for segment in summary["segments"]:
            by_style_task[(style, segment["task_id"])].append(segment)
            by_trial_task[(style, trial, segment["task_id"])].append(segment)

    metrics = {}
    for (style, task_id), segments in sorted(by_style_task.items()):
        settling = [
            item["settling_time_s"] for item in segments
            if item["settling_time_s"] is not None
        ]
        measured_acceleration = [
            item["actual_acceleration_p99_mps2"] for item in segments
            if item["actual_acceleration_p99_mps2"] is not None
        ]
        measured_jerk = [
            item["actual_jerk_p99_mps3"] for item in segments
            if item["actual_jerk_p99_mps3"] is not None
        ]
        metrics[f"{style}:task{task_id}"] = {
            "uav_segments": len(segments),
            "t_exec_mean_s": mean(item["t_exec_s"] for item in segments),
            "tracking_rmse_mean_m": mean(
                item["tracking_rmse_m"] for item in segments
            ),
            "tracking_rmse_max_m": max(
                item["tracking_rmse_m"] for item in segments
            ),
            "peak_tracking_error_max_m": max(
                item["peak_tracking_error_m"] for item in segments
            ),
            "final_position_error_max_m": max(
                item["final_position_error_m"] for item in segments
            ),
            "speed_peak_max_mps": max(
                item["position_derived_speed_peak_mps"] for item in segments
            ),
            "saturation_fraction_mean": mean(
                item["ladrc_saturation_fraction"] for item in segments
            ),
            "saturation_fraction_max": max(
                item["ladrc_saturation_fraction"] for item in segments
            ),
            "leso_z2_peak_max": max(item["leso_z2_peak"] for item in segments),
            "leso_z3_peak_max": max(item["leso_z3_peak"] for item in segments),
            "overshoot_max_m": max(item["overshoot_m"] for item in segments),
            "settling_time_mean_s": mean(settling) if settling else None,
            "settling_time_max_s": max(settling) if settling else None,
            "switch_first_0_5s_peak_error_max_m": max(
                item["switch_first_0_5s_peak_error_m"] for item in segments
            ),
            "switch_first_0_5s_saturation_fraction_max": max(
                item["switch_first_0_5s_saturation_fraction"]
                for item in segments
            ),
            "measured_acceleration_p99_max_mps2": (
                max(measured_acceleration) if measured_acceleration else None
            ),
            "measured_jerk_p99_max_mps3": (
                max(measured_jerk) if measured_jerk else None
            ),
            "predicted_peak_velocity_max_mps": max(
                item["predicted_peak_velocity_mps"] for item in segments
            ),
            "predicted_peak_acceleration_max_mps2": max(
                item["predicted_peak_acceleration_mps2"] for item in segments
            ),
            "predicted_peak_jerk_max_mps3": max(
                item["predicted_peak_jerk_mps3"] for item in segments
            ),
        }

    trial_durations = {}
    feasibility = []
    for key, segments in sorted(by_trial_task.items()):
        style, trial, task_id = key
        duration = mean(item["t_exec_s"] for item in segments)
        trial_durations[f"{style}:{trial}:task{task_id}"] = duration
        if task_id in (2, 3):
            minimum = max(
                minimum_jerk_duration(item["path_length_m"])
                for item in segments
            )
            feasibility.append({
                "style": style,
                "trial": trial,
                "task_id": task_id,
                "t_exec_s": duration,
                "t_min_s": minimum,
                "ratio": duration / minimum,
            })

    expected_styles = ("smooth", "normal", "aggressive")
    counts = Counter(item["manifest"]["style"] for item in summaries)
    profile = {}
    for style in expected_styles:
        segments = [
            segment
            for summary in summaries
            for segment in summary["segments"]
            if segment["motion_style"] == style
        ]
        if segments:
            profile[style] = {
                "style_gain": segments[0]["style_gain"],
                "task_gain": segments[0]["task_gain"],
                "omega_c": segments[0]["omega_c"],
                "omega_o": segments[0]["omega_o"],
            }

    auto_duration_order = []
    for trial in (1, 2, 3):
        for task_id in (2, 3):
            values = {
                style: trial_durations.get(f"{style}:{trial}:task{task_id}")
                for style in expected_styles
            }
            if all(value is not None for value in values.values()):
                auto_duration_order.append({
                    "trial": trial,
                    "task_id": task_id,
                    "durations": values,
                    "ordered": (
                        values["smooth"] > values["normal"]
                        > values["aggressive"]
                    ),
                })

    all_segments = [
        segment for summary in summaries for segment in summary["segments"]
    ]
    explicit_by_uav = defaultdict(list)
    for item in all_segments:
        if item["task_id"] == 1:
            explicit_by_uav[item["uav_id"]].append(item)
    explicit_reference = {
        "target_equal_by_uav": all(
            len({tuple(item["target_world"]) for item in items}) == 1
            for items in explicit_by_uav.values()
        ),
        "start_max_pairwise_spread_m": max(
            (
                max(
                    math.dist(left["start_world"], right["start_world"])
                    for left in items for right in items
                )
                for items in explicit_by_uav.values()
            ),
            default=0.0,
        ),
        "path_length_max_spread_m": max(
            (
                max(item["path_length_m"] for item in items)
                - min(item["path_length_m"] for item in items)
                for items in explicit_by_uav.values()
            ),
            default=0.0,
        ),
    }
    link_error = max(
        (item["px4_acceleration_link_max_error"] for item in all_segments),
        default=None,
    )
    profile_apply_error = max(
        (
            max(
                abs(expected - applied)
                for expected, applied in zip(
                    item["omega_c"] + item["omega_o"],
                    item["applied_omega_c"] + item["applied_omega_o"],
                )
            )
            for item in all_segments
        ),
        default=None,
    )
    return {
        "trial_count_by_style": dict(sorted(counts.items())),
        "candidate_completed_all": all(
            item["manifest"].get("candidate_completed", False)
            for item in summaries
        ),
        "readiness_4_of_4_all": all(
            item["manifest"].get("readiness", False) for item in summaries
        ),
        "segment_count": len(all_segments),
        "motion_style_matches_manifest_all": all(
            segment["motion_style"] == summary["manifest"]["style"]
            for summary in summaries
            for segment in summary["segments"]
        ),
        "task3_received_4_of_4_all": (
            all(
                sum(
                    segment["task_id"] == 3
                    for segment in summary["segments"]
                ) == 4
                for summary in summaries
            )
            if any(
                segment["task_id"] == 3
                for summary in summaries for segment in summary["segments"]
            )
            else None
        ),
        "profile": profile,
        "style_profile_strict_order_all_axes": (
            set(profile) == set(expected_styles)
            and all(
                profile["smooth"][family][axis]
                < profile["normal"][family][axis]
                < profile["aggressive"][family][axis]
                for family in ("omega_c", "omega_o")
                for axis in range(3)
            )
        ),
        "configuration_ids": sorted({
            item["configuration_id"] for item in all_segments
        }),
        "profile_application_max_abs_error": profile_apply_error,
        "explicit_t_all_8_s": all(
            abs(item["t_exec_s"] - 8.0) <= 1e-6
            for item in all_segments if item["task_id"] == 1
        ),
        "explicit_reference": explicit_reference,
        "auto_duration_order": auto_duration_order,
        "auto_duration_strict_order_all": (
            all(item["ordered"] for item in auto_duration_order)
            if auto_duration_order else None
        ),
        "auto_feasibility": feasibility,
        "auto_t_at_or_above_t_min_all": (
            all(
                item["t_exec_s"] + 1e-6 >= item["t_min_s"]
                for item in feasibility
            )
            if feasibility else None
        ),
        "predicted_motion_limits_respected_all": all(
            item["predicted_peak_velocity_mps"] <= 5.0 + 1e-6
            and item["predicted_peak_acceleration_mps2"] <= 5.0 + 1e-6
            and item["predicted_peak_jerk_mps3"] <= 10.0 + 1e-6
            for item in all_segments
        ),
        "finished_all": all(item["finished"] for item in all_segments),
        "hard_safety_violation_count": sum(
            item["hard_safety_violation"] for item in all_segments
        ),
        "minimum_neighbor_distance_m": min(
            (
                item["minimum_neighbor_distance_m"] for item in all_segments
                if item["minimum_neighbor_distance_m"] is not None
            ),
            default=None,
        ),
        "iapf_active_fraction_max": max(
            (item["iapf_active_fraction"] for item in all_segments), default=0.0
        ),
        "px4_acceleration_link_max_error": link_error,
        "metrics_by_style_task": metrics,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("results", type=Path)
    args = parser.parse_args()
    trial_dirs = sorted(
        path.parent
        for path in args.results.glob("*_trial_*/manifest.json")
        if (path.parent / "rosbag" / "metadata.yaml").is_file()
    )
    summaries = [summarize_trial(path) for path in trial_dirs]
    output = args.results / "trial_metrics.json"
    output.write_text(json.dumps(summaries, indent=2), encoding="utf-8")
    aggregate_output = args.results / "acceptance_summary.json"
    aggregate_output.write_text(
        json.dumps(aggregate(summaries), indent=2), encoding="utf-8"
    )
    print(json.dumps({
        "trial_count": len(summaries),
        "segment_count": sum(len(item["segments"]) for item in summaries),
        "output": str(output),
        "aggregate_output": str(aggregate_output),
    }, indent=2))


if __name__ == "__main__":
    main()
