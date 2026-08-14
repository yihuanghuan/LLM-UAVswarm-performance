#!/usr/bin/env python3
"""Summarize LADRC steady-state behavior from one or more ROS 2 bags."""

import argparse
import json
import math
from pathlib import Path
from statistics import mean

import rosbag2_py
from rclpy.serialization import deserialize_message
from rosidl_runtime_py.utilities import get_message


def norm3(vector):
    return math.sqrt(vector.x ** 2 + vector.y ** 2 + vector.z ** 2)


def summarize(bag_dir: Path, tail_seconds: float):
    reader = rosbag2_py.SequentialReader()
    reader.open(
        rosbag2_py.StorageOptions(uri=str(bag_dir), storage_id="sqlite3"),
        rosbag2_py.ConverterOptions("cdr", "cdr"),
    )
    topic_types = {
        item.name: get_message(item.type) for item in reader.get_all_topics_and_types()
    }
    debug_by_uav = {}
    status_by_uav = {}
    while reader.has_next():
        topic, data, timestamp_ns = reader.read_next()
        if topic.endswith("/control_tracking_debug"):
            message = deserialize_message(data, topic_types[topic])
            if message.has_command:
                debug_by_uav.setdefault(message.uav_id, []).append(
                    (timestamp_ns * 1e-9, message)
                )
        elif topic.endswith("/status"):
            message = deserialize_message(data, topic_types[topic])
            status_by_uav.setdefault(message.uav_id, []).append(
                (timestamp_ns * 1e-9, message)
            )

    if not debug_by_uav:
        raise RuntimeError(f"no commanded control_tracking_debug samples in {bag_dir}")

    return [
        summarize_uav(
            bag_dir, uav_id, debug, status_by_uav.get(uav_id, []), tail_seconds
        )
        for uav_id, debug in sorted(debug_by_uav.items())
    ]


def summarize_uav(bag_dir, uav_id, debug, status, tail_seconds):

    mission_id = debug[-1][1].mission_id
    debug = [sample for sample in debug if sample[1].mission_id == mission_id]
    mission_start = debug[0][0]
    mission_end = debug[-1][0]
    tail_start = mission_end - tail_seconds
    tail = [sample for sample in debug if sample[0] >= tail_start]

    stable_times = [
        timestamp
        for timestamp, message in status
        if message.is_hover_stable and timestamp >= mission_start
    ]
    stable_transitions = 0
    previous = False
    stable_samples = 0
    status_samples = 0
    for timestamp, message in status:
        if timestamp < mission_start:
            continue
        current = bool(message.is_hover_stable)
        stable_transitions += int(current != previous)
        previous = current
        stable_samples += int(current)
        status_samples += 1

    def axis_error(message, axis):
        return getattr(message.actual_position, axis) - getattr(message.nominal_position, axis)

    def rms(values):
        return math.sqrt(mean(value * value for value in values))

    axes = ("x", "y", "z")
    errors = {axis: [axis_error(msg, axis) for _, msg in tail] for axis in axes}
    positions = {
        axis: [getattr(msg.actual_position, axis) for _, msg in tail] for axis in axes
    }
    horizontal_saturation = mean(
        max(abs(msg.ladrc_output.x) / 5.0, abs(msg.ladrc_output.y) / 5.0) >= 0.999
        for _, msg in tail
    )
    vertical_saturation = mean(
        abs(msg.ladrc_output.z) / 8.0 >= 0.999 for _, msg in tail
    )
    any_saturation = mean(
        max(
            abs(msg.ladrc_output.x) / 5.0,
            abs(msg.ladrc_output.y) / 5.0,
            abs(msg.ladrc_output.z) / 8.0,
        )
        >= 0.999
        for _, msg in tail
    )

    return {
        "bag": str(bag_dir),
        "uav_id": uav_id,
        "mission_id": mission_id,
        "mission_duration_s": mission_end - mission_start,
        "tail_duration_s": min(tail_seconds, mission_end - mission_start),
        "tail_samples": len(tail),
        "tail_mean_position_error_m": mean(
            norm3(msg.tracking_error) for _, msg in tail
        ),
        "tail_position_error_rms_m": {axis: rms(errors[axis]) for axis in axes},
        "tail_position_peak_to_peak_m": {
            axis: max(positions[axis]) - min(positions[axis]) for axis in axes
        },
        "tail_mean_raw_ekf_speed_mps": mean(msg.raw_ekf_speed for _, msg in tail),
        "tail_mean_position_derived_speed_mps": mean(
            msg.position_derived_speed for _, msg in tail
        ),
        "tail_p95_position_derived_speed_mps": sorted(
            msg.position_derived_speed for _, msg in tail
        )[int(0.95 * (len(tail) - 1))],
        "tail_mean_leso_z2_speed_mps": mean(msg.leso_z2_speed for _, msg in tail),
        "tail_saturation_fraction": any_saturation,
        "tail_horizontal_saturation_fraction": horizontal_saturation,
        "tail_vertical_saturation_fraction": vertical_saturation,
        "stable_confirmed": bool(stable_times),
        "first_settling_time_s": stable_times[0] - mission_start if stable_times else None,
        "stable_status_fraction": stable_samples / status_samples if status_samples else None,
        "stable_state_transitions": stable_transitions,
        "final_position_error_m": norm3(debug[-1][1].tracking_error),
        "final_raw_ekf_speed_mps": debug[-1][1].raw_ekf_speed,
        "final_position_derived_speed_mps": debug[-1][1].position_derived_speed,
        "final_leso_z2_speed_mps": debug[-1][1].leso_z2_speed,
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("bags", nargs="+", type=Path)
    parser.add_argument("--tail-seconds", type=float, default=30.0)
    args = parser.parse_args()
    summaries = [
        summary
        for path in args.bags
        for summary in summarize(path.resolve(), args.tail_seconds)
    ]
    print(json.dumps(summaries, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
