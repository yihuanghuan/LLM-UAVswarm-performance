#!/usr/bin/env python3
"""Audit C0-A prereg-v2 stability/jerk metrics from immutable raw evidence.

This script is diagnostic only.  It never writes into a formal trial directory
and it does not reclassify, select, or rank C0-A candidates.
"""

from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import csv
from datetime import datetime, timezone
import json
import math
from pathlib import Path
import statistics
import sys

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import rosbag2_py
from rclpy.serialization import deserialize_message
from rosidl_runtime_py.utilities import get_message
from scipy.stats import pearsonr, spearmanr


AXES = ("x", "y", "z")
ZERO_CROSSING_LIMIT = 6
POST_RMS_LIMIT_M = 0.25
P2P_LIMIT_M = 0.60
LAST_FIRST_LIMIT = 1.0
TRACKING_RMSE_LIMIT_M = 0.50
MAX_ERROR_LIMIT_M = 1.00
FINAL_ERROR_LIMIT_M = 0.40
DT_MIN_S = 0.005
DT_MAX_S = 0.1


def vector(item):
    return np.array((float(item.x), float(item.y), float(item.z)), dtype=float)


def json_number(value):
    value = float(value)
    return value if math.isfinite(value) else None


def stats(values):
    data = np.asarray([value for value in values if value is not None and math.isfinite(value)], dtype=float)
    if not data.size:
        return {"count": 0, "min": None, "p01": None, "median": None, "p90": None, "p95": None, "p99": None, "max": None}
    return {
        "count": int(data.size),
        "min": float(np.min(data)),
        "p01": float(np.percentile(data, 1)),
        "median": float(np.median(data)),
        "p90": float(np.percentile(data, 90)),
        "p95": float(np.percentile(data, 95)),
        "p99": float(np.percentile(data, 99)),
        "max": float(np.max(data)),
    }


def correlation(left, right):
    x = np.asarray(left, dtype=float)
    y = np.asarray(right, dtype=float)
    if x.size < 3 or np.all(x == x[0]) or np.all(y == y[0]):
        return {"n": int(x.size), "pearson": None, "pearson_p": None, "spearman": None, "spearman_p": None}
    pearson = pearsonr(x, y)
    spearman = spearmanr(x, y)
    return {
        "n": int(x.size),
        "pearson": json_number(pearson.statistic),
        "pearson_p": json_number(pearson.pvalue),
        "spearman": json_number(spearman.statistic),
        "spearman_p": json_number(spearman.pvalue),
    }


def nearest_rank_percentile(values, probability):
    if not values:
        return None
    ordered = sorted(values)
    index = max(0, math.ceil(probability * len(ordered)) - 1)
    return ordered[index]


def header_time(message):
    return float(message.header.stamp.sec) + float(message.header.stamp.nanosec) * 1e-9


def read_selected_topics(bag_path, topics):
    reader = rosbag2_py.SequentialReader()
    reader.open(
        rosbag2_py.StorageOptions(uri=str(bag_path), storage_id="sqlite3"),
        rosbag2_py.ConverterOptions("cdr", "cdr"),
    )
    type_names = {item.name: item.type for item in reader.get_all_topics_and_types()}
    message_types = {topic: get_message(type_names[topic]) for topic in topics if topic in type_names}
    output = defaultdict(list)
    while reader.has_next():
        topic, payload, timestamp_ns = reader.read_next()
        if topic in message_types:
            output[topic].append((timestamp_ns * 1e-9, deserialize_message(payload, message_types[topic])))
    return output


def zero_crossing_events(times, values):
    center = float(np.mean(values))
    centered = np.asarray(values, dtype=float) - center
    signed = np.sign(centered).astype(int)
    kept = [(index, int(sign)) for index, sign in enumerate(signed) if sign]
    events = []
    for (left_index, left_sign), (right_index, right_sign) in zip(kept, kept[1:]):
        if left_sign == right_sign:
            continue
        left = float(centered[left_index])
        right = float(centered[right_index])
        fraction = -left / (right - left) if right != left else 0.5
        event_time = float(times[left_index] + fraction * (times[right_index] - times[left_index]))
        events.append({
            "left_index": left_index,
            "right_index": right_index,
            "time_s": event_time,
            "bracket_dt_s": float(times[right_index] - times[left_index]),
            "target_relative_interpolated_abs_m": abs(center),
            "target_relative_bracket_near_abs_m": min(abs(float(values[left_index])), abs(float(values[right_index]))),
            "target_relative_bracket_max_abs_m": max(abs(float(values[left_index])), abs(float(values[right_index]))),
            "centered_bracket_near_abs_m": min(abs(left), abs(right)),
            "centered_bracket_max_abs_m": max(abs(left), abs(right)),
        })
    return center, centered, signed, events


def filtered_differences(times, values):
    samples = []
    for index in range(1, len(times)):
        dt = float(times[index] - times[index - 1])
        if DT_MIN_S <= dt <= DT_MAX_S:
            derivative = (values[index] - values[index - 1]) / dt
            samples.append({
                "index": index,
                "time_s": float(times[index]),
                "dt_s": dt,
                "vector": derivative,
                "norm": float(np.linalg.norm(derivative)),
            })
    return samples


def extract_trial_series(trial_dir, spec, manifest, stored_metrics):
    uid = int(spec["uav_ids"][0])
    topics = {
        f"/uav{uid}/control_tracking_debug",
        f"/px4_{uid}/fmu/out/vehicle_odometry",
    }
    records = read_selected_topics(trial_dir / "rosbag", topics)
    mission_id = int(manifest.get("driver_result", {}).get("mission_id", 0))
    debug = [
        (timestamp, message)
        for timestamp, message in records[f"/uav{uid}/control_tracking_debug"]
        if message.has_command and int(message.mission_id) == mission_id
    ]
    if not debug:
        raise RuntimeError("active control_tracking_debug is missing")
    start = debug[0][0]
    duration = float(spec["explicit_duration_s"])
    active_end = start + duration
    active = [(timestamp, message) for timestamp, message in debug if timestamp <= active_end]
    post = [(timestamp, message) for timestamp, message in debug if active_end <= timestamp <= active_end + 5.0]
    if len(post) < 2:
        raise RuntimeError("post window is missing")

    offset = np.array((
        0.0 if spec["layout"] == "single_origin" else -4.0,
        0.0 if spec["layout"] == "single_origin" else 3.0 * uid,
        1.5,
    ))
    target_local = np.asarray(spec["world_targets"][0], dtype=float) - offset
    post_times = np.asarray([timestamp - active_end for timestamp, _ in post], dtype=float)
    post_errors = np.asarray([vector(message.actual_position) - target_local for _, message in post])

    axis_data = []
    for axis in range(3):
        center, centered, signs, events = zero_crossing_events(post_times, post_errors[:, axis])
        axis_data.append({
            "center": center,
            "centered": centered,
            "events": events,
            "signs": signs,
            "values": post_errors[:, axis],
        })
    recomputed_crossings = [len(item["events"]) for item in axis_data]
    stored_crossings = stored_metrics["post_trajectory_zero_crossings_per_axis"]
    if recomputed_crossings != stored_crossings:
        raise RuntimeError(f"zero-crossing mismatch: {recomputed_crossings} != {stored_crossings}")

    active_times = np.asarray([timestamp - start for timestamp, _ in active], dtype=float)
    command = np.asarray([vector(message.ladrc_output) for _, message in active])
    jerk_samples = filtered_differences(active_times, command)
    jerk_norms = [item["norm"] for item in jerk_samples]
    recomputed_jerk = nearest_rank_percentile(jerk_norms, 0.995)
    stored_jerk = float(stored_metrics["command_jerk_p99_5_mps3"])
    if not math.isclose(recomputed_jerk, stored_jerk, rel_tol=1e-9, abs_tol=1e-9):
        raise RuntimeError(f"command-jerk mismatch: {recomputed_jerk} != {stored_jerk}")

    debug_bag_times = np.asarray([timestamp for timestamp, _ in debug], dtype=float)
    debug_header_times = np.asarray([header_time(message) for _, message in debug], dtype=float)
    odometry_bag_times = np.asarray([timestamp for timestamp, _ in records[f"/px4_{uid}/fmu/out/vehicle_odometry"]], dtype=float)
    post_steps = np.abs(np.diff(post_errors, axis=0)).ravel()
    nonzero_steps = post_steps[post_steps > 0]
    return {
        "active_command": command,
        "active_times": active_times,
        "axis": axis_data,
        "debug_bag_dt": np.diff(debug_bag_times),
        "debug_header_dt": np.diff(debug_header_times),
        "jerk_samples": jerk_samples,
        "odometry_bag_dt": np.diff(odometry_bag_times),
        "post_errors": post_errors,
        "post_nonzero_steps": nonzero_steps,
        "post_repeat_fraction": float(np.mean(post_steps == 0)) if post_steps.size else None,
        "post_times": post_times,
        "recomputed_jerk_p99_5": recomputed_jerk,
        "target_local": target_local,
    }


def bool_int(value):
    return 1 if value else 0


def write_csv(path, rows, fieldnames=None):
    rows = list(rows)
    if fieldnames is None:
        fieldnames = list(rows[0]) if rows else []
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(
            stream,
            fieldnames=fieldnames,
            extrasaction="ignore",
            lineterminator="\n",
        )
        writer.writeheader()
        writer.writerows(rows)


def select_quantiles(rows, key, count):
    ordered = sorted(rows, key=lambda row: (key(row), row["trial_id"]))
    if len(ordered) <= count:
        return ordered
    indices = np.linspace(0, len(ordered) - 1, count).round().astype(int)
    return [ordered[index] for index in dict.fromkeys(indices)]


def plot_terminal_trace(row, series, groups, output):
    fig, axes = plt.subplots(3, 2, figsize=(15, 11), sharex="col", constrained_layout=True)
    colors = ("tab:red", "tab:green", "tab:blue")
    crossing_counts = []
    for axis, axis_name in enumerate(AXES):
        data = series["axis"][axis]
        times = series["post_times"]
        values = data["values"]
        centered = data["centered"]
        events = data["events"]
        crossing_counts.append(len(events))
        left = axes[axis, 0]
        left.plot(times, values, color=colors[axis], linewidth=1.0, label="target-relative error")
        left.plot(times, centered, color="black", linewidth=0.8, alpha=0.7, label="mean-centered error")
        left.axhline(0.0, color="gray", linewidth=0.6)
        for event in events:
            left.axvline(event["time_s"], color="tab:orange", alpha=0.25, linewidth=0.7)
        left.set_ylabel(f"{axis_name} error (m)")
        left.grid(alpha=0.2)
        left.set_title(
            f"{axis_name}: RMS={row[f'post_rms_{axis_name}_m']:.4f} m, "
            f"P2P={row[f'post_p2p_{axis_name}_m']:.4f} m, crossings={len(events)}"
        )
        right = axes[axis, 1]
        right.step(times, data["signs"], where="post", color=colors[axis], linewidth=0.9)
        for event in events:
            right.axvline(event["time_s"], color="tab:orange", alpha=0.35, linewidth=0.8)
        right.set_ylim(-1.4, 1.4)
        right.set_yticks((-1, 0, 1))
        right.set_ylabel(f"sign({axis_name} - mean)")
        right.grid(alpha=0.2)
    axes[-1, 0].set_xlabel("time from nominal trajectory end (s)")
    axes[-1, 1].set_xlabel("time from nominal trajectory end (s)")
    axes[0, 0].legend(loc="upper right", fontsize=8)
    fig.suptitle(
        f"{row['trial_id']}\n"
        f"groups={','.join(groups)} | post RMS={row['post_rms_m']:.4f} m | "
        f"max P2P={row['post_p2p_max_m']:.4f} m | last/first={row['last_first_ratio']:.4f} | "
        f"crossings={crossing_counts}",
        fontsize=10,
    )
    fig.savefig(output, dpi=160)
    plt.close(fig)


def plot_jerk_trace(row, series, output):
    command = series["active_command"]
    times = series["active_times"]
    jerk = series["jerk_samples"]
    jerk_times = np.asarray([item["time_s"] for item in jerk])
    jerk_norms = np.asarray([item["norm"] for item in jerk])
    dts = np.asarray([item["dt_s"] for item in jerk])
    threshold = row["command_jerk_threshold_mps3"]
    fig, axes = plt.subplots(3, 1, figsize=(13, 10), constrained_layout=True)
    for axis, axis_name in enumerate(AXES):
        axes[0].plot(times, command[:, axis], label=f"a_cmd {axis_name}", linewidth=1.0)
    axes[0].set_ylabel("LADRC acceleration command (m/s²)")
    axes[0].legend(ncol=3)
    axes[0].grid(alpha=0.2)
    axes[1].plot(jerk_times, jerk_norms, color="tab:red", linewidth=1.0, label="derived jerk norm")
    axes[1].axhline(threshold, color="black", linestyle="--", label=f"hard threshold={threshold:g}")
    axes[1].axhline(row["command_jerk_p99_5_mps3"], color="tab:purple", linestyle=":", label="stored p99.5")
    axes[1].set_ylabel("derived command jerk (m/s³)")
    axes[1].legend()
    axes[1].grid(alpha=0.2)
    axes[2].plot(jerk_times, dts * 1000.0, color="tab:blue", linewidth=0.9)
    axes[2].axhline(float(np.median(dts)) * 1000.0, color="black", linestyle="--", label="median dt")
    axes[2].set_ylabel("sample dt (ms)")
    axes[2].set_xlabel("time from command start (s)")
    axes[2].legend()
    axes[2].grid(alpha=0.2)
    fig.suptitle(
        f"{row['trial_id']}\n"
        f"p99.5={row['command_jerk_p99_5_mps3']:.3f} m/s³ | "
        f"samples>{threshold:g}={row['jerk_samples_above_threshold']} | "
        f"peak dt={row['jerk_peak_dt_s'] * 1000.0:.3f} ms",
        fontsize=10,
    )
    fig.savefig(output, dpi=160)
    plt.close(fig)


def heatmap(axis, matrix, title, row_labels, column_labels, fmt="d"):
    image = axis.imshow(matrix, cmap="viridis", aspect="auto")
    axis.set_title(title)
    axis.set_xticks(range(len(column_labels)), column_labels)
    axis.set_yticks(range(len(row_labels)), row_labels)
    axis.set_xlabel("omega_o multiplier")
    axis.set_ylabel("omega_c multiplier")
    for row in range(matrix.shape[0]):
        for column in range(matrix.shape[1]):
            value = matrix[row, column]
            text = format(value, fmt)
            axis.text(column, row, text, ha="center", va="center", color="white" if value > np.nanmax(matrix) / 2 else "black", fontsize=8)
    return image


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--artifact-root", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    artifact = args.artifact_root.resolve()
    output = args.output_dir.resolve()
    metrics_dir = output / "metrics"
    figures_dir = output / "figures"
    representative_dir = output / "representative_trials"
    logs_dir = output / "logs"
    for directory in (metrics_dir, figures_dir, representative_dir, logs_dir):
        directory.mkdir(parents=True, exist_ok=True)

    rows = []
    series_by_id = {}
    crossing_event_rows = []
    jerk_sample_rows = []
    extraction_errors = []
    raw_dirs = sorted((artifact / "raw").iterdir())
    for ordinal, trial_dir in enumerate(raw_dirs, 1):
        if not trial_dir.is_dir() or not (trial_dir / "manifest.json").is_file():
            continue
        manifest = json.loads((trial_dir / "manifest.json").read_text(encoding="utf-8"))
        formal_metrics = json.loads((trial_dir / "metrics.json").read_text(encoding="utf-8"))
        spec = json.loads((trial_dir / "trial_spec.json").read_text(encoding="utf-8"))
        failures = set(formal_metrics.get("hard_failures", []))
        parameters = spec["resolved_candidate_parameters"]
        row = {
            "trial_id": formal_metrics["trial_id"],
            "candidate_id": formal_metrics["candidate_id"],
            "scenario_id": formal_metrics["scenario_id"],
            "signed_displacement_id": spec["entry"]["signed_displacement_id"],
            "seed": formal_metrics["seed"],
            "omega_c_multiplier": parameters["omega_c_multiplier"],
            "omega_o_multiplier": parameters["omega_o_multiplier"],
            "formal_hard_pass": bool_int(formal_metrics["hard_pass"]),
            "hard_failures": ";".join(sorted(failures)),
            "termination_reason": manifest["termination_reason"],
            "metric_extraction_success": bool_int(formal_metrics["metric_extraction_success"]),
        }
        if formal_metrics.get("per_uav"):
            item = formal_metrics["per_uav"][0]
            p2p = item["post_trajectory_peak_to_peak_per_axis_m"]
            post_rms_axis = item["post_trajectory_rms_per_axis_m"]
            crossings = item["post_trajectory_zero_crossings_per_axis"]
            jerk_threshold = 1.5 * float(parameters["j_limit"])
            row.update({
                "zero_crossings_x": crossings[0],
                "zero_crossings_y": crossings[1],
                "zero_crossings_z": crossings[2],
                "zero_crossings_max": max(crossings),
                "zero_crossings_fail": bool_int("ZERO_CROSSINGS" in failures),
                "post_rms_m": item["post_trajectory_rms_m"],
                "post_rms_x_m": post_rms_axis[0],
                "post_rms_y_m": post_rms_axis[1],
                "post_rms_z_m": post_rms_axis[2],
                "post_rms_pass": bool_int(item["post_trajectory_rms_m"] <= POST_RMS_LIMIT_M),
                "post_p2p_x_m": p2p[0],
                "post_p2p_y_m": p2p[1],
                "post_p2p_z_m": p2p[2],
                "post_p2p_max_m": max(p2p),
                "post_p2p_pass": bool_int(max(p2p) <= P2P_LIMIT_M),
                "last_first_ratio": item["post_trajectory_last_first_rms_ratio"],
                "last_first_pass": bool_int(item["post_trajectory_last_first_rms_ratio"] <= LAST_FIRST_LIMIT),
                "tracking_rmse_m": item["tracking_rmse_m"],
                "tracking_rmse_pass": bool_int(item["tracking_rmse_m"] <= TRACKING_RMSE_LIMIT_M),
                "maximum_tracking_error_m": item["maximum_tracking_error_m"],
                "maximum_tracking_error_pass": bool_int(item["maximum_tracking_error_m"] <= MAX_ERROR_LIMIT_M),
                "final_error_m": item["final_error_m"],
                "final_error_pass": bool_int(item["final_error_m"] <= FINAL_ERROR_LIMIT_M),
                "command_jerk_p99_5_mps3": item["command_jerk_p99_5_mps3"],
                "command_jerk_threshold_mps3": jerk_threshold,
                "command_jerk_fail": bool_int("COMMAND_JERK_P99_5" in failures),
                "acceleration_saturation_ratio": max(item["acceleration_saturation_ratio_per_axis"]),
                "mission_success": bool_int(item["mission_success"]),
                "growing_oscillation_fail": bool_int("GROWING_OSCILLATION" in failures),
                "roll_pitch_peak_deg": max(item["roll_peak_deg"], item["pitch_peak_deg"]),
            })
            specified_clean = (
                row["zero_crossings_fail"]
                and row["post_rms_pass"]
                and row["post_p2p_pass"]
                and row["last_first_pass"]
                and row["tracking_rmse_pass"]
                and row["maximum_tracking_error_pass"]
                and row["final_error_pass"]
                and row["mission_success"]
            )
            row["zero_crossings_cross_metric_only"] = bool_int(specified_clean)
            row["zero_crossings_formal_only"] = bool_int(failures == {"ZERO_CROSSINGS"})
            row["counterfactual_pass_excluding_zero_crossings"] = bool_int(not (failures - {"ZERO_CROSSINGS"}))
            row["other_hard_failure_excluding_zc_jerk"] = bool_int(bool(failures - {"ZERO_CROSSINGS", "COMMAND_JERK_P99_5"}))
            try:
                series = extract_trial_series(trial_dir, spec, manifest, item)
                series_by_id[row["trial_id"]] = series
                jerk_norms = [sample["norm"] for sample in series["jerk_samples"]]
                peak_index = int(np.argmax(jerk_norms)) if jerk_norms else None
                row["jerk_sample_count"] = len(jerk_norms)
                row["jerk_samples_above_threshold"] = sum(value > jerk_threshold for value in jerk_norms)
                row["jerk_fraction_above_threshold"] = row["jerk_samples_above_threshold"] / len(jerk_norms) if jerk_norms else None
                row["jerk_peak_dt_s"] = series["jerk_samples"][peak_index]["dt_s"] if peak_index is not None else None
                row["jerk_p99_5_equals_max"] = bool_int(bool(jerk_norms) and math.isclose(max(jerk_norms), row["command_jerk_p99_5_mps3"], rel_tol=1e-12))
                row["debug_dt_median_s"] = float(np.median(series["debug_bag_dt"]))
                row["debug_dt_p95_s"] = float(np.percentile(series["debug_bag_dt"], 95))
                row["debug_header_dt_median_s"] = float(np.median(series["debug_header_dt"]))
                row["odometry_dt_median_s"] = float(np.median(series["odometry_bag_dt"]))
                row["terminal_position_step_min_nonzero_m"] = float(np.min(series["post_nonzero_steps"])) if series["post_nonzero_steps"].size else None
                row["terminal_position_repeat_fraction"] = series["post_repeat_fraction"]
                for axis, axis_name in enumerate(AXES):
                    for event_index, event in enumerate(series["axis"][axis]["events"], 1):
                        crossing_event_rows.append({
                            "trial_id": row["trial_id"],
                            "candidate_id": row["candidate_id"],
                            "scenario_id": row["scenario_id"],
                            "seed": row["seed"],
                            "axis": axis_name,
                            "event_index": event_index,
                            "zero_crossings_cross_metric_only": row["zero_crossings_cross_metric_only"],
                            **event,
                        })
                for sample in series["jerk_samples"]:
                    jerk_sample_rows.append({
                        "trial_id": row["trial_id"],
                        "candidate_id": row["candidate_id"],
                        "omega_c_multiplier": row["omega_c_multiplier"],
                        "omega_o_multiplier": row["omega_o_multiplier"],
                        "command_jerk_fail": row["command_jerk_fail"],
                        "time_s": sample["time_s"],
                        "dt_s": sample["dt_s"],
                        "jerk_norm_mps3": sample["norm"],
                        "above_threshold": bool_int(sample["norm"] > jerk_threshold),
                    })
            except Exception as error:
                extraction_errors.append({"trial_id": row["trial_id"], "error": f"{type(error).__name__}: {error}"})
        else:
            for field in (
                "zero_crossings_x", "zero_crossings_y", "zero_crossings_z", "zero_crossings_max",
                "zero_crossings_fail", "post_rms_m", "post_rms_x_m", "post_rms_y_m", "post_rms_z_m",
                "post_rms_pass", "post_p2p_x_m", "post_p2p_y_m", "post_p2p_z_m", "post_p2p_max_m",
                "post_p2p_pass", "last_first_ratio", "last_first_pass", "tracking_rmse_m",
                "tracking_rmse_pass", "maximum_tracking_error_m", "maximum_tracking_error_pass",
                "final_error_m", "final_error_pass", "command_jerk_p99_5_mps3",
                "command_jerk_threshold_mps3", "command_jerk_fail", "acceleration_saturation_ratio",
                "mission_success", "growing_oscillation_fail", "roll_pitch_peak_deg",
                "zero_crossings_cross_metric_only", "zero_crossings_formal_only",
                "counterfactual_pass_excluding_zero_crossings", "other_hard_failure_excluding_zc_jerk",
            ):
                row[field] = None
        rows.append(row)
        if ordinal % 25 == 0:
            print(f"processed {ordinal}/{len(raw_dirs)} trial directories", file=sys.stderr)

    rows.sort(key=lambda row: row["trial_id"])
    valid_rows = [row for row in rows if row["metric_extraction_success"] and row["trial_id"] in series_by_id]
    if len(rows) != 300 or len(valid_rows) != 295 or extraction_errors:
        raise RuntimeError(f"unexpected audit extraction counts: rows={len(rows)}, valid={len(valid_rows)}, errors={extraction_errors}")

    cross_metric_path = metrics_dir / "trial_cross_metrics.csv"
    write_csv(cross_metric_path, rows)
    (metrics_dir / "trial_cross_metrics.json").write_text(json.dumps(rows, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    write_csv(metrics_dir / "aggregate_v2.csv", rows)
    (metrics_dir / "aggregate_v2.json").write_text(json.dumps(rows, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    write_csv(metrics_dir / "crossing_events.csv", crossing_event_rows)
    write_csv(metrics_dir / "command_jerk_samples.csv", jerk_sample_rows)

    correlation_data = {
        "zero_crossings_max_vs_post_rms": correlation([row["zero_crossings_max"] for row in valid_rows], [row["post_rms_m"] for row in valid_rows]),
        "zero_crossings_max_vs_post_p2p": correlation([row["zero_crossings_max"] for row in valid_rows], [row["post_p2p_max_m"] for row in valid_rows]),
        "zero_crossings_max_vs_last_first_ratio": correlation([row["zero_crossings_max"] for row in valid_rows], [row["last_first_ratio"] for row in valid_rows]),
        "command_jerk_vs_tracking_rmse": correlation([row["command_jerk_p99_5_mps3"] for row in valid_rows], [row["tracking_rmse_m"] for row in valid_rows]),
        "command_jerk_vs_maximum_tracking_error": correlation([row["command_jerk_p99_5_mps3"] for row in valid_rows], [row["maximum_tracking_error_m"] for row in valid_rows]),
        "command_jerk_vs_roll_pitch_peak": correlation([row["command_jerk_p99_5_mps3"] for row in valid_rows], [row["roll_pitch_peak_deg"] for row in valid_rows]),
        "command_jerk_vs_sample_dt": correlation([row["jerk_norm_mps3"] for row in jerk_sample_rows], [row["dt_s"] for row in jerk_sample_rows]),
    }
    (metrics_dir / "correlations.json").write_text(json.dumps(correlation_data, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    candidates = defaultdict(list)
    for row in rows:
        candidates[row["candidate_id"]].append(row)
    candidate_rows = []
    for candidate_id, items in sorted(candidates.items()):
        candidate_rows.append({
            "candidate_id": candidate_id,
            "omega_c_multiplier": items[0]["omega_c_multiplier"],
            "omega_o_multiplier": items[0]["omega_o_multiplier"],
            "trial_count": len(items),
            "formal_pass_count": sum(row["formal_hard_pass"] for row in items),
            "zero_crossings_fail_count": sum(row["zero_crossings_fail"] or 0 for row in items),
            "command_jerk_fail_count": sum(row["command_jerk_fail"] or 0 for row in items),
            "other_hard_failure_count": sum(row["other_hard_failure_excluding_zc_jerk"] or 0 for row in items),
            "counterfactual_pass_count_excluding_zero_crossings": sum(row["counterfactual_pass_excluding_zero_crossings"] or 0 for row in items),
            "metric_extraction_success_count": sum(row["metric_extraction_success"] for row in items),
        })
    write_csv(metrics_dir / "candidate_failure_map.csv", candidate_rows)
    (metrics_dir / "candidate_failure_map.json").write_text(json.dumps(candidate_rows, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    contingency = {
        "zero_crossings_pass_growing_pass": sum(not row["zero_crossings_fail"] and not row["growing_oscillation_fail"] for row in valid_rows),
        "zero_crossings_pass_growing_fail": sum(not row["zero_crossings_fail"] and row["growing_oscillation_fail"] for row in valid_rows),
        "zero_crossings_fail_growing_pass": sum(row["zero_crossings_fail"] and not row["growing_oscillation_fail"] for row in valid_rows),
        "zero_crossings_fail_growing_fail": sum(row["zero_crossings_fail"] and row["growing_oscillation_fail"] for row in valid_rows),
    }

    critical_ids = {row["trial_id"] for row in valid_rows if row["zero_crossings_cross_metric_only"]}
    critical_events = [event for event in crossing_event_rows if event["trial_id"] in critical_ids]
    all_centered_abs = []
    critical_centered_abs = []
    all_target_abs = []
    all_position_steps = []
    debug_dt = []
    debug_header_dt = []
    odometry_dt = []
    repeat_fractions = []
    for row in valid_rows:
        series = series_by_id[row["trial_id"]]
        centered = np.column_stack([item["centered"] for item in series["axis"]])
        all_centered_abs.extend(np.abs(centered).ravel())
        all_target_abs.extend(np.abs(series["post_errors"]).ravel())
        all_position_steps.extend(series["post_nonzero_steps"])
        debug_dt.extend(series["debug_bag_dt"])
        debug_header_dt.extend(series["debug_header_dt"])
        odometry_dt.extend(series["odometry_bag_dt"])
        repeat_fractions.append(series["post_repeat_fraction"])
        if row["trial_id"] in critical_ids:
            critical_centered_abs.extend(np.abs(centered).ravel())

    jerk_fail_rows = [row for row in valid_rows if row["command_jerk_fail"]]
    jerk_pass_rows = [row for row in valid_rows if not row["command_jerk_fail"]]
    jerk_summary = {
        "failure_count": len(jerk_fail_rows),
        "p99_5_equals_sample_max_count": sum(row["jerk_p99_5_equals_max"] for row in valid_rows),
        "jerk_sample_count_per_trial": stats([row["jerk_sample_count"] for row in valid_rows]),
        "failure_sample_count_above_threshold": stats([row["jerk_samples_above_threshold"] for row in jerk_fail_rows]),
        "failure_fraction_above_threshold": stats([row["jerk_fraction_above_threshold"] for row in jerk_fail_rows]),
        "failure_peak_dt_s": stats([row["jerk_peak_dt_s"] for row in jerk_fail_rows]),
        "pass_peak_dt_s": stats([row["jerk_peak_dt_s"] for row in jerk_pass_rows]),
        "candidate_failure_counts": {
            row["candidate_id"]: row["command_jerk_fail_count"] for row in candidate_rows
        },
        "omega_o_failure_counts": dict(sorted(Counter(
            str(row["omega_o_multiplier"]) for row in jerk_fail_rows
        ).items())),
        "acceleration_saturation_nonzero_trials": sum(row["acceleration_saturation_ratio"] > 0 for row in valid_rows),
        "correlations": {key: value for key, value in correlation_data.items() if key.startswith("command_jerk")},
    }
    (metrics_dir / "command_jerk_audit.json").write_text(json.dumps(jerk_summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    infrastructure_rows = []
    for row in rows:
        termination = row["termination_reason"]
        if termination == "SUCCESS":
            continue
        if termination in {"INFRASTRUCTURE_ERROR", "MANDATORY_TOPIC_MISSING", "COMMAND_REJECTED"}:
            category = "infrastructure_failure"
        elif termination == "CAMPAIGN_INTERRUPTED":
            category = "diagnostic_only_interruption_record"
        else:
            category = "scientific_failure"
        infrastructure_rows.append({
            "trial_id": row["trial_id"],
            "candidate_id": row["candidate_id"],
            "termination_reason": termination,
            "hard_failures": row["hard_failures"],
            "classification": category,
            "included_in_formal_denominator": "YES",
            "replacement_rerun": "NO",
        })
    write_csv(metrics_dir / "infrastructure_failures.csv", infrastructure_rows)
    (metrics_dir / "infrastructure_failures.json").write_text(json.dumps(infrastructure_rows, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    noise_summary = {
        "cross_metric_clean_crossing_events": len(critical_events),
        "crossing_target_relative_interpolated_abs_m": stats([event["target_relative_interpolated_abs_m"] for event in critical_events]),
        "crossing_target_relative_bracket_near_abs_m": stats([event["target_relative_bracket_near_abs_m"] for event in critical_events]),
        "crossing_centered_bracket_near_abs_m": stats([event["centered_bracket_near_abs_m"] for event in critical_events]),
        "crossing_centered_bracket_max_abs_m": stats([event["centered_bracket_max_abs_m"] for event in critical_events]),
        "terminal_centered_abs_m_all_valid": stats(all_centered_abs),
        "terminal_centered_abs_m_cross_metric_clean": stats(critical_centered_abs),
        "terminal_target_relative_abs_m_all_valid": stats(all_target_abs),
        "terminal_position_nonzero_step_m": stats(all_position_steps),
        "terminal_position_repeat_fraction_per_trial": stats(repeat_fractions),
        "control_debug_bag_dt_s": stats(debug_dt),
        "control_debug_header_dt_s": stats(debug_header_dt),
        "control_debug_bag_dt_jitter_abs_from_median_s": stats(np.abs(np.asarray(debug_dt) - np.median(debug_dt))),
        "odometry_bag_dt_s": stats(odometry_dt),
    }
    (metrics_dir / "noise_characterization.json").write_text(json.dumps(noise_summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    group1_pool = [row for row in valid_rows if row["zero_crossings_cross_metric_only"]]
    group2_pool = [row for row in valid_rows if not row["zero_crossings_fail"]]
    group3_pool = [row for row in valid_rows if row["growing_oscillation_fail"]]
    group4_pool = jerk_fail_rows
    selected_groups = {
        "group1_zero_crossings_fail_other_stability_pass": select_quantiles(group1_pool, lambda row: (row["zero_crossings_max"], row["post_rms_m"]), 10),
        "group2_zero_crossings_pass": select_quantiles(group2_pool, lambda row: (row["zero_crossings_max"], row["post_rms_m"]), 5),
        "group3_growing_oscillation_fail": group3_pool,
        "group4_command_jerk_fail": select_quantiles(group4_pool, lambda row: row["command_jerk_p99_5_mps3"], 5),
    }
    membership = defaultdict(list)
    representative_rows = []
    for group, selected in selected_groups.items():
        for row in selected:
            membership[row["trial_id"]].append(group)
            representative_rows.append({"group": group, "trial_id": row["trial_id"], "candidate_id": row["candidate_id"], "scenario_id": row["scenario_id"], "seed": row["seed"]})
    write_csv(representative_dir / "selection.csv", representative_rows)
    (representative_dir / "selection.json").write_text(json.dumps(representative_rows, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    row_by_id = {row["trial_id"]: row for row in valid_rows}
    for trial_id, groups in sorted(membership.items()):
        plot_terminal_trace(
            row_by_id[trial_id], series_by_id[trial_id], groups,
            representative_dir / f"v2_terminal__{trial_id}.png",
        )
    for row in selected_groups["group4_command_jerk_fail"]:
        plot_jerk_trace(row, series_by_id[row["trial_id"]], representative_dir / f"v2_jerk__{row['trial_id']}.png")

    fig, axes = plt.subplots(1, 3, figsize=(16, 5), constrained_layout=True)
    for axis, (field, label, limit) in zip(axes, (
        ("post_rms_m", "post RMS (m)", POST_RMS_LIMIT_M),
        ("post_p2p_max_m", "post P2P max axis (m)", P2P_LIMIT_M),
        ("last_first_ratio", "last/first RMS ratio", LAST_FIRST_LIMIT),
    )):
        axis.scatter([row["zero_crossings_max"] for row in valid_rows], [row[field] for row in valid_rows], s=14, alpha=0.55)
        axis.axvline(ZERO_CROSSING_LIMIT, color="tab:red", linestyle="--")
        axis.axhline(limit, color="black", linestyle=":")
        corr = correlation_data[f"zero_crossings_max_vs_{'post_p2p' if field == 'post_p2p_max_m' else field.replace('_m','')}"]
        axis.set_title(f"Pearson={corr['pearson']:.3f}; Spearman={corr['spearman']:.3f}")
        axis.set_xlabel("max zero crossings across axes")
        axis.set_ylabel(label)
        axis.grid(alpha=0.2)
    fig.savefig(figures_dir / "v2_zero_crossing_correlations.png", dpi=180)
    plt.close(fig)

    fig, axes = plt.subplots(1, 2, figsize=(13, 5), constrained_layout=True)
    target_amplitudes = np.asarray([event["target_relative_interpolated_abs_m"] for event in critical_events])
    centered_amplitudes = np.asarray([event["centered_bracket_near_abs_m"] for event in critical_events])
    axes[0].hist(target_amplitudes * 1000.0, bins=50, alpha=0.75, label="|target-relative error| at interpolated mean crossing")
    axes[0].set_xlabel("amplitude (mm)")
    axes[0].set_ylabel("event count")
    axes[0].legend(fontsize=8)
    ordered = np.sort(centered_amplitudes * 1000.0)
    axes[1].plot(ordered, np.arange(1, len(ordered) + 1) / len(ordered))
    axes[1].set_xscale("log")
    axes[1].set_xlabel("nearest centered bracket amplitude (mm, log scale)")
    axes[1].set_ylabel("empirical CDF")
    axes[1].grid(alpha=0.2)
    fig.savefig(figures_dir / "v2_crossing_amplitude_distribution.png", dpi=180)
    plt.close(fig)

    omega_values = [0.67, 0.83, 1.0, 1.17, 1.33]
    candidate_lookup = {(row["omega_c_multiplier"], row["omega_o_multiplier"]): row for row in candidate_rows}
    matrices = []
    fields = (
        ("formal_pass_count", "Formal PASS count / 12"),
        ("zero_crossings_fail_count", "ZERO_CROSSINGS fail count"),
        ("command_jerk_fail_count", "COMMAND_JERK fail count"),
        ("counterfactual_pass_count_excluding_zero_crossings", "Diagnostic pass count excluding ZC"),
    )
    fig, axes = plt.subplots(2, 2, figsize=(13, 11), constrained_layout=True)
    for axis, (field, title) in zip(axes.ravel(), fields):
        matrix = np.asarray([[candidate_lookup[(oc, oo)][field] for oo in omega_values] for oc in omega_values])
        heatmap(axis, matrix, title, omega_values, omega_values)
        matrices.append(matrix)
    fig.savefig(figures_dir / "v2_candidate_failure_heatmap.png", dpi=180)
    plt.close(fig)

    fig, axes = plt.subplots(1, 2, figsize=(14, 5), constrained_layout=True)
    oo_groups = {value: [row["command_jerk_p99_5_mps3"] for row in valid_rows if row["omega_o_multiplier"] == value] for value in omega_values}
    axes[0].boxplot([oo_groups[value] for value in omega_values], tick_labels=[str(value) for value in omega_values])
    axes[0].axhline(15.0, color="tab:red", linestyle="--")
    axes[0].set_xlabel("omega_o multiplier")
    axes[0].set_ylabel("command jerk p99.5 (m/s³)")
    axes[0].grid(alpha=0.2)
    fail_matrix = np.asarray([[candidate_lookup[(oc, oo)]["command_jerk_fail_count"] for oo in omega_values] for oc in omega_values])
    heatmap(axes[1], fail_matrix, "COMMAND_JERK failures / 12", omega_values, omega_values)
    fig.savefig(figures_dir / "v2_command_jerk_candidate_discrimination.png", dpi=180)
    plt.close(fig)

    zc_fail_rows = [row for row in valid_rows if row["zero_crossings_fail"]]
    z_solo_trigger_rows = [
        row for row in zc_fail_rows
        if row["zero_crossings_z"] > max(row["zero_crossings_x"], row["zero_crossings_y"])
    ]
    trigger_axis_counts = Counter()
    for row in zc_fail_rows:
        maximum = row["zero_crossings_max"]
        for axis_name in AXES:
            if row[f"zero_crossings_{axis_name}"] == maximum:
                trigger_axis_counts[axis_name] += 1
    summary = {
        "dataset_class": "calibration_diagnostic",
        "protocol_result_preserved": "C0-A-prereg-v2 NO_ACCEPTABLE_CONFIGURATION",
        "formal_trial_count": len(rows),
        "valid_time_series_count": len(valid_rows),
        "formal_pass_count": sum(row["formal_hard_pass"] for row in rows),
        "formal_fail_count": sum(not row["formal_hard_pass"] for row in rows),
        "zero_crossings_failure_count": sum(row["zero_crossings_fail"] or 0 for row in rows),
        "zero_crossings_cross_metric_only_count": len(critical_ids),
        "zero_crossings_cross_metric_only_percentage_of_all_formal_trials": 100.0 * len(critical_ids) / len(rows),
        "zero_crossings_cross_metric_only_percentage_of_zero_crossing_failures": 100.0 * len(critical_ids) / sum(row["zero_crossings_fail"] or 0 for row in rows),
        "zero_crossings_formal_only_count": sum(row["zero_crossings_formal_only"] or 0 for row in rows),
        "zero_crossings_trigger_axis_maximum_counts": dict(sorted(trigger_axis_counts.items())),
        "zero_crossings_z_solo_trigger_count": len(z_solo_trigger_rows),
        "zero_crossings_z_solo_trigger_post_rms_z_m": stats([row["post_rms_z_m"] for row in z_solo_trigger_rows]),
        "zero_crossings_z_solo_trigger_post_p2p_z_m": stats([row["post_p2p_z_m"] for row in z_solo_trigger_rows]),
        "correlations": correlation_data,
        "growing_oscillation_contingency": contingency,
        "noise_characterization": noise_summary,
        "command_jerk": jerk_summary,
        "infrastructure_affected_trial_count": len(infrastructure_rows),
        "metric_definition": {
            "signal": "per-axis target-relative post-trajectory position error",
            "centering": "subtract arithmetic mean of the same 5 s post window",
            "deadband": None,
            "hysteresis": None,
            "low_pass_filter": None,
            "zero_samples": "discarded before adjacent non-zero sign comparison",
            "threshold": "maximum per-axis count <= 6",
        },
        "generated_utc": datetime.now(timezone.utc).isoformat(),
    }
    (metrics_dir / "audit_summary.json").write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    log_lines = [
        "C0-A prereg-v2 metric validity audit",
        "dataset_class=calibration_diagnostic",
        f"artifact_root={artifact}",
        f"formal_trials={len(rows)}",
        f"valid_time_series={len(valid_rows)}",
        f"zero_crossings_failures={summary['zero_crossings_failure_count']}",
        f"zero_crossings_cross_metric_only={len(critical_ids)}",
        f"command_jerk_failures={len(jerk_fail_rows)}",
        f"infrastructure_affected_trials={len(infrastructure_rows)}",
        "formal_trial_files_modified=0",
        "diagnostic_reruns_started=0",
    ]
    (logs_dir / "v2_metric_validity_audit.log").write_text("\n".join(log_lines) + "\n", encoding="utf-8")
    print(json.dumps({
        "audit_summary": str(metrics_dir / "audit_summary.json"),
        "formal_trials": len(rows),
        "valid_time_series": len(valid_rows),
        "zero_crossings_cross_metric_only": len(critical_ids),
    }, sort_keys=True))


if __name__ == "__main__":
    main()
