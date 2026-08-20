#!/usr/bin/env python3
"""Extract all preregistered C0-A metrics and hard criteria from one bag."""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path

import rosbag2_py
from rclpy.serialization import deserialize_message
from rosidl_runtime_py.utilities import get_message


def vec(item):
    return (float(item.x), float(item.y), float(item.z))


def norm(values):
    return math.sqrt(sum(value * value for value in values))


def finite_vector(values):
    return all(math.isfinite(value) for value in values)


def percentile(values, probability):
    if not values:
        return None
    ordered = sorted(values)
    index = max(0, math.ceil(probability * len(ordered)) - 1)
    return ordered[index]


def rms(values):
    return math.sqrt(sum(value * value for value in values) / len(values)) if values else None


def zero_crossings(values):
    if not values:
        return None
    center = sum(values) / len(values)
    signs = []
    for value in values:
        delta = value - center
        if delta > 0.0:
            signs.append(1)
        elif delta < 0.0:
            signs.append(-1)
    return sum(left != right for left, right in zip(signs, signs[1:]))


def differences(samples):
    output = []
    previous = None
    for timestamp, values in samples:
        if previous is not None:
            dt = timestamp - previous[0]
            if 0.005 <= dt <= 0.1:
                output.append((timestamp, tuple(
                    (values[axis] - previous[1][axis]) / dt for axis in range(3)
                )))
        previous = (timestamp, values)
    return output


def read_bag(path):
    reader = rosbag2_py.SequentialReader()
    reader.open(
        rosbag2_py.StorageOptions(uri=str(path), storage_id="sqlite3"),
        rosbag2_py.ConverterOptions("cdr", "cdr"),
    )
    types = {item.name: get_message(item.type) for item in reader.get_all_topics_and_types()}
    records = []
    while reader.has_next():
        topic, payload, timestamp_ns = reader.read_next()
        records.append((timestamp_ns * 1e-9, topic, deserialize_message(payload, types[topic])))
    return records, types


def matching(records, topic, start=None, end=None):
    return [
        (timestamp, message)
        for timestamp, item_topic, message in records
        if item_topic == topic
        and (start is None or timestamp >= start)
        and (end is None or timestamp < end)
    ]


def attitude_roll_pitch(message):
    w, x, y, z = (float(value) for value in message.q)
    roll = math.atan2(2.0 * (w * x + y * z), 1.0 - 2.0 * (x * x + y * y))
    sin_pitch = max(-1.0, min(1.0, 2.0 * (w * y - z * x)))
    pitch = math.asin(sin_pitch)
    return math.degrees(roll), math.degrees(pitch)


def axis_peaks(vectors):
    return [max((abs(item[axis]) for item in vectors), default=None) for axis in range(3)]


def summarize_uav(records, types, spec, manifest, uid, index):
    mission_id = int(manifest.get("driver_result", {}).get("mission_id", 0))
    duration = float(spec["explicit_duration_s"])
    debug_all = matching(records, f"/uav{uid}/control_tracking_debug")
    debug = [
        (timestamp, message) for timestamp, message in debug_all
        if message.has_command and int(message.mission_id) == mission_id
    ]
    if not debug:
        raise RuntimeError(f"missing active control_tracking_debug for UAV {uid}")
    start = debug[0][0]
    active_end = start + duration
    active = [(timestamp, message) for timestamp, message in debug if timestamp <= active_end]
    post = [
        (timestamp, message) for timestamp, message in debug
        if active_end <= timestamp <= active_end + 5.0
    ]
    if len(post) < 2 or post[-1][0] - post[0][0] < 4.8:
        raise RuntimeError(f"incomplete 5 s post-trajectory window for UAV {uid}")

    errors = []
    for _, message in active:
        nominal = vec(message.nominal_position)
        actual = vec(message.actual_position)
        errors.append(tuple(nominal[axis] - actual[axis] for axis in range(3)))
    error_norms = [norm(item) for item in errors]
    per_axis_rmse = [rms([item[axis] for item in errors]) for axis in range(3)]

    offset = (
        0.0 if spec["layout"] == "single_origin" else -4.0,
        0.0 if spec["layout"] == "single_origin" else 3.0 * uid,
        1.5,
    )
    target_world = spec["world_targets"][index]
    target_local = tuple(target_world[axis] - offset[axis] for axis in range(3))
    post_errors = [tuple(
        vec(message.actual_position)[axis] - target_local[axis] for axis in range(3)
    ) for _, message in post]
    post_norms = [norm(item) for item in post_errors]
    post_axis = [[item[axis] for item in post_errors] for axis in range(3)]
    first = [
        (timestamp, item) for (timestamp, _), item in zip(post, post_errors)
        if timestamp < active_end + 2.0
    ]
    last = [
        (timestamp, item) for (timestamp, _), item in zip(post, post_errors)
        if timestamp >= active_end + 3.0
    ]
    first_rms = rms([norm(item) for _, item in first])
    last_rms = rms([norm(item) for _, item in last])
    last_first_ratio = (
        last_rms / first_rms if first_rms is not None and first_rms > 1e-12
        else (0.0 if (last_rms or 0.0) <= 1e-12 else math.inf)
    )

    command_acceleration = [vec(message.ladrc_output) for _, message in active]
    actual_velocity = [
        (timestamp, vec(message.actual_velocity)) for timestamp, message in active
    ]
    measured_acceleration_samples = differences(actual_velocity)
    measured_acceleration = [item for _, item in measured_acceleration_samples]
    command_jerk_samples = differences([
        (timestamp, vec(message.ladrc_output)) for timestamp, message in active
    ])
    command_jerk = [item for _, item in command_jerk_samples]
    acceleration_limit = float(spec["profiles"][index]["acceleration_limit"])
    saturation_axis = [
        sum(abs(item[axis]) >= 0.99 * acceleration_limit for item in command_acceleration)
        / len(command_acceleration)
        for axis in range(3)
    ]
    saturation_any = sum(
        any(abs(item[axis]) >= 0.99 * acceleration_limit for axis in range(3))
        for item in command_acceleration
    ) / len(command_acceleration)

    times = [timestamp for timestamp, _ in active]
    achieved_rate = (len(times) - 1) / (times[-1] - times[0]) if len(times) > 1 else 0.0
    expected_samples = round(duration * 50.0) + 1
    missed_samples = max(0, expected_samples - len(times))
    attitudes = matching(
        records, f"/px4_{uid}/fmu/out/vehicle_attitude", start, start + duration + 2.0
    )
    if not attitudes:
        raise RuntimeError(f"missing vehicle_attitude for UAV {uid}")
    roll_pitch = [attitude_roll_pitch(message) for _, message in attitudes]

    statuses = matching(records, f"/uav{uid}/status", start)
    failsafe = any(message.failsafe for _, message in statuses)
    offboard_loss = any(not message.offboard for _, message in statuses)
    unintended_disarm = any(not message.armed for _, message in statuses)
    startup_failure = any(message.startup_state == message.STARTUP_FAILED for _, message in statuses)
    nonfinite_setpoint = any(
        not finite_vector(vec(message.px4_acceleration_setpoint)) for _, message in active
    )
    iapf = matching(records, f"/uav{uid}/iapf_debug", start, active_end + 5.0)
    iapf_active = any(message.iapf_active for _, message in iapf)
    neighbor_distances = [
        float(message.nearest_neighbor_distance) for _, message in iapf
        if message.has_nearest_neighbor and math.isfinite(message.nearest_neighbor_distance)
    ]
    adaptations = matching(records, f"/uav{uid}/control_adaptation", start)
    requested = spec["profiles"][index]
    omega_applied = None
    omega_apply_error = math.inf
    if adaptations:
        last_adaptation = adaptations[-1][1]
        omega_applied = {
            "omega_c": [last_adaptation.omega_c_x, last_adaptation.omega_c_y, last_adaptation.omega_c_z],
            "omega_o": [last_adaptation.omega_o_x, last_adaptation.omega_o_y, last_adaptation.omega_o_z],
        }
        omega_apply_error = max(
            abs(float(actual) - float(expected))
            for family in ("omega_c", "omega_o")
            for actual, expected in zip(omega_applied[family], requested[family])
        )
    clamps = spec["resolved_hard_clamps"]
    mathematical_clamp = any(
        value < low or value > high
        for family in ("omega_c", "omega_o")
        for value, low, high in zip(
            requested[family], clamps[f"{family}_min"], clamps[f"{family}_max"]
        )
    ) or any((
        requested["velocity_limit"] > clamps["velocity_max"],
        requested["acceleration_limit"] > clamps["acceleration_max"],
        requested["jerk_limit"] > clamps["jerk_max"],
    ))
    profile_clamped = mathematical_clamp or omega_apply_error > 1e-5
    observer_vectors = [
        vec(getattr(message, family))
        for _, message in active
        for family in ("leso_z1", "leso_z2", "leso_z3")
    ]
    observer_finite = all(finite_vector(item) for item in observer_vectors)
    trajectories = matching(records, f"/uav{uid}/trajectory_metrics", start)
    if not trajectories:
        raise RuntimeError(f"missing trajectory_metrics for UAV {uid}")
    final_trajectory = trajectories[-1][1]

    distance = float(spec["distance_m"])
    analytic = {
        "velocity": 1.875 * distance / duration,
        "acceleration": (10.0 / math.sqrt(3.0)) * distance / (duration ** 2),
        "jerk": 60.0 * distance / (duration ** 3),
    }
    jerk_norms = [norm(item) for item in command_jerk]
    result = {
        "uav_id": uid,
        "tracking_rmse_m": rms(error_norms),
        "tracking_rmse_per_axis_m": per_axis_rmse,
        "maximum_tracking_error_m": max(error_norms),
        "final_error_m": float(final_trajectory.final_position_error),
        "measured_peak_velocity_mps": max(norm(vec(message.actual_velocity)) for _, message in active),
        "analytic_reference_peaks": analytic,
        "ladrc_command_peak_acceleration_mps2": max(norm(item) for item in command_acceleration),
        "ladrc_command_peak_acceleration_per_axis_mps2": axis_peaks(command_acceleration),
        "measured_peak_acceleration_mps2": max((norm(item) for item in measured_acceleration), default=None),
        "measured_peak_acceleration_per_axis_mps2": axis_peaks(measured_acceleration),
        "command_jerk_peak_mps3": max(jerk_norms, default=None),
        "command_jerk_peak_per_axis_mps3": axis_peaks(command_jerk),
        "command_jerk_p99_5_mps3": percentile(jerk_norms, 0.995),
        "acceleration_saturation_ratio_per_axis": saturation_axis,
        "acceleration_saturation_ratio_any_axis": saturation_any,
        "roll_peak_deg": max(abs(item[0]) for item in roll_pitch),
        "pitch_peak_deg": max(abs(item[1]) for item in roll_pitch),
        "post_trajectory_rms_m": rms(post_norms),
        "post_trajectory_rms_per_axis_m": [rms(values) for values in post_axis],
        "post_trajectory_peak_to_peak_per_axis_m": [max(values) - min(values) for values in post_axis],
        "post_trajectory_zero_crossings_per_axis": [zero_crossings(values) for values in post_axis],
        "post_trajectory_last_first_rms_ratio": last_first_ratio,
        "mission_success": bool(manifest.get("success")),
        "px4_failsafe": failsafe,
        "offboard_loss": offboard_loss,
        "unintended_disarm": unintended_disarm,
        "startup_failure": startup_failure,
        "nonfinite_setpoint": nonfinite_setpoint,
        "control_loop_achieved_hz": achieved_rate,
        "missed_samples": missed_samples,
        "iapf_activation": iapf_active,
        "minimum_neighbor_distance_m": min(neighbor_distances) if neighbor_distances else None,
        "profile_clamped": profile_clamped,
        "omega_application_max_abs_error": omega_apply_error,
        "observer_states_finite": observer_finite,
        "observer_state_peak": max((norm(item) for item in observer_vectors), default=None),
        "actual_duration_s": float(final_trajectory.trajectory_duration),
        "arrival_time_error_s": float(final_trajectory.arrival_time_error),
        "active_samples": len(active),
        "post_samples": len(post),
    }
    limits = spec["resolved_candidate_parameters"]
    hard_failures = []
    checks = (
        (result["mission_success"], "MISSION_FAILED"),
        (not failsafe, "PX4_FAILSAFE"),
        (not offboard_loss, "OFFBOARD_LOSS"),
        (not unintended_disarm, "UNINTENDED_DISARM"),
        (not startup_failure, "STARTUP_FAILED"),
        (not nonfinite_setpoint, "NONFINITE_SETPOINT"),
        (result["post_trajectory_rms_m"] <= 0.25, "POST_RMS"),
        (max(result["post_trajectory_peak_to_peak_per_axis_m"]) <= 0.60, "PEAK_TO_PEAK"),
        (result["post_trajectory_last_first_rms_ratio"] <= 1.0, "GROWING_OSCILLATION"),
        (analytic["velocity"] <= limits["v_limit"] + 1e-9, "REFERENCE_V_LIMIT"),
        (analytic["acceleration"] <= limits["a_limit"] + 1e-9, "REFERENCE_A_LIMIT"),
        (analytic["jerk"] <= limits["j_limit"] + 1e-9, "REFERENCE_J_LIMIT"),
        (not profile_clamped, "PROFILE_CLAMP"),
        (max(saturation_axis) <= 0.02, "ACCELERATION_SATURATION"),
        (47.5 <= achieved_rate <= 52.5, "CONTROL_LOOP_RATE"),
        (result["roll_peak_deg"] <= 30.0, "ROLL_LIMIT"),
        (result["pitch_peak_deg"] <= 30.0, "PITCH_LIMIT"),
        (result["tracking_rmse_m"] <= 0.50, "TRACKING_RMSE"),
        (result["maximum_tracking_error_m"] <= 1.00, "MAX_TRACKING_ERROR"),
        (result["final_error_m"] <= 0.40, "FINAL_ERROR"),
        (
            result["command_jerk_p99_5_mps3"] is not None
            and math.isfinite(result["command_jerk_p99_5_mps3"])
            and result["command_jerk_p99_5_mps3"] <= 1.5 * limits["j_limit"],
            "COMMAND_JERK_P99_5",
        ),
        (observer_finite, "NONFINITE_OBSERVER_STATE"),
    )
    hard_failures.extend(code for passed, code in checks if not passed)
    result["hard_failures"] = hard_failures
    result["hard_pass"] = not hard_failures
    result["raw_zero_crossings_diagnostic_only"] = True
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("trial_dir", type=Path)
    args = parser.parse_args()
    output = args.trial_dir / "metrics.json"
    manifest = json.loads((args.trial_dir / "manifest.json").read_text(encoding="utf-8"))
    spec = json.loads((args.trial_dir / "trial_spec.json").read_text(encoding="utf-8"))
    try:
        if not (args.trial_dir / "rosbag" / "metadata.yaml").is_file():
            raise RuntimeError("rosbag metadata missing")
        records, types = read_bag(args.trial_dir / "rosbag")
        per_uav = [
            summarize_uav(records, types, spec, manifest, uid, index)
            for index, uid in enumerate(spec["uav_ids"])
        ]
        min_separation = min(
            (item["minimum_neighbor_distance_m"] for item in per_uav
             if item["minimum_neighbor_distance_m"] is not None),
            default=None,
        )
        multi_failures = []
        if len(per_uav) > 1:
            if min_separation is None or min_separation < 1.0:
                multi_failures.append("MINIMUM_SEPARATION")
            if any(item["iapf_activation"] for item in per_uav):
                multi_failures.append("IAPF_UNEXPECTED_ACTIVE")
            if not all(item["mission_success"] for item in per_uav):
                multi_failures.append("MULTI_UAV_MISSION_FAILURE")
        result = {
            "trial_id": manifest["trial_id"],
            "stage": manifest["stage"],
            "candidate_id": manifest["candidate_id"],
            "scenario_id": manifest["scenario_id"],
            "seed": manifest["seed"],
            "per_uav": per_uav,
            "minimum_inter_uav_distance_m": min_separation,
            "multi_uav_failures": multi_failures,
            "hard_pass": all(item["hard_pass"] for item in per_uav) and not multi_failures,
            "hard_failures": sorted({
                failure for item in per_uav for failure in item["hard_failures"]
            } | set(multi_failures)),
            "metric_extraction_success": True,
        }
    except Exception as error:
        result = {
            "trial_id": manifest["trial_id"],
            "stage": manifest["stage"],
            "candidate_id": manifest["candidate_id"],
            "scenario_id": manifest["scenario_id"],
            "seed": manifest["seed"],
            "per_uav": [],
            "hard_pass": False,
            "hard_failures": ["METRIC_EXTRACTION_FAILED"],
            "metric_extraction_success": False,
            "error": f"{type(error).__name__}: {error}",
        }
    output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({
        "trial_id": result["trial_id"],
        "hard_pass": result["hard_pass"],
        "hard_failures": result["hard_failures"],
    }, sort_keys=True))
    return 0 if result["metric_extraction_success"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
