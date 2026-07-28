#!/usr/bin/env python3
"""Analyze semantic-conditioned LADRC Gazebo trials."""

from __future__ import annotations

import argparse
import csv
import json
import math
from collections import defaultdict
from pathlib import Path
from statistics import fmean, stdev
from typing import Dict, Iterable, List, Sequence, Tuple

import numpy as np
from scipy.signal import savgol_filter

from experiment_07_config import DURATION_S, METHODS, TARGET


SAMPLE_DT = 0.02
POSITION_THRESHOLD_M = 0.3
VELOCITY_THRESHOLD_MPS = 0.3
SETTLING_DWELL_S = 1.0

TRIAL_FIELDS = [
    "trial_id", "method", "motion_style", "repeat", "samples",
    "gain_multiplier", "target_distance_m", "duration_s",
    "peak_velocity_mps", "peak_acceleration_mps2", "peak_jerk_mps3",
    "settling_time_s", "tracking_rmse_m", "overshoot_m",
    "peak_abs_roll_deg", "peak_abs_pitch_deg", "final_position_error_m",
]
SUMMARY_METRICS = [
    "gain_multiplier", "peak_velocity_mps", "peak_acceleration_mps2",
    "peak_jerk_mps3", "settling_time_s", "tracking_rmse_m", "overshoot_m",
    "peak_abs_roll_deg", "peak_abs_pitch_deg", "final_position_error_m",
]
TIMESERIES_FIELDS = [
    "trial_id", "method", "motion_style", "repeat", "elapsed_time_s",
    "reference_x", "reference_y", "reference_z",
    "actual_x", "actual_y", "actual_z", "speed_mps",
    "acceleration_mps2", "jerk_mps3", "roll_deg", "pitch_deg",
    "tracking_error_m",
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("experiment_dir", type=Path)
    parser.add_argument("--output-dir", type=Path)
    return parser.parse_args()


def read_csv(path: Path) -> List[Dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def parse_float(value: object, default: float = math.nan) -> float:
    try:
        result = float(str(value).strip())
    except (TypeError, ValueError):
        return default
    return result if math.isfinite(result) else default


def minimum_jerk_progress(t: np.ndarray, duration: float) -> np.ndarray:
    tau = np.clip(t / duration, 0.0, 1.0)
    return 10.0 * tau**3 - 15.0 * tau**4 + 6.0 * tau**5


def expected_task_gain(style: str, distance: float, duration: float) -> float:
    profiles = {
        "smooth": (0.75, 1.0),
        "normal": (1.0, 1.8),
        "aggressive": (1.3, 2.6),
    }
    base_gain, reference_speed = profiles[style]
    average_speed = distance / max(duration, 1e-3)
    gain = base_gain * (0.75 + 0.25 * average_speed / reference_speed)
    return min(2.0, max(0.5, gain))


def quaternion_to_roll_pitch(
    w: np.ndarray, x: np.ndarray, y: np.ndarray, z: np.ndarray
) -> Tuple[np.ndarray, np.ndarray]:
    roll = np.arctan2(
        2.0 * (w * x + y * z),
        1.0 - 2.0 * (x * x + y * y),
    )
    sin_pitch = np.clip(2.0 * (w * y - z * x), -1.0, 1.0)
    pitch = np.arcsin(sin_pitch)
    return np.degrees(np.unwrap(roll)), np.degrees(np.unwrap(pitch))


def first_sustained_time(
    times: Sequence[float], conditions: Sequence[bool], dwell_s: float
) -> float:
    start: float | None = None
    previous: float | None = None
    for current, condition in zip(times, conditions):
        if previous is not None and current - previous > 1.5 * SAMPLE_DT:
            start = None
        if condition:
            start = current if start is None else start
            if current - start >= dwell_s:
                return start
        else:
            start = None
        previous = current
    return math.nan


def command_time_ns(trial_dir: Path) -> int:
    rows = read_csv(trial_dir / "bag_csv/uav1_swarm_command.csv")
    if not rows:
        raise ValueError("swarm_command CSV is empty")
    return min(int(row["bag_time_ns"]) for row in rows)


def adaptation_values(trial_dir: Path) -> Tuple[float, float, float]:
    rows = read_csv(trial_dir / "bag_csv/uav1_control_adaptation.csv")
    if not rows:
        raise ValueError("control_adaptation CSV is empty")
    row = rows[-1]
    return (
        parse_float(row.get("gain_multiplier")),
        parse_float(row.get("target_distance")),
        parse_float(row.get("duration")),
    )


def load_resampled_odom(
    trial_dir: Path, start_ns: int
) -> Dict[str, np.ndarray]:
    rows = read_csv(trial_dir / "bag_csv/px4_1_fmu_out_vehicle_odometry.csv")
    if len(rows) < 20:
        raise ValueError("vehicle_odometry has too few samples")
    raw_t = np.array(
        [(int(row["bag_time_ns"]) - start_ns) / 1e9 for row in rows],
        dtype=float,
    )
    keep = raw_t >= -0.25
    raw_t = raw_t[keep]
    selected = [row for row, include in zip(rows, keep) if include]
    order = np.argsort(raw_t)
    raw_t = raw_t[order]
    selected = [selected[index] for index in order]
    unique_t, unique_indices = np.unique(raw_t, return_index=True)
    raw_t = unique_t
    selected = [selected[index] for index in unique_indices]
    if raw_t[-1] < DURATION_S:
        raise ValueError("vehicle_odometry does not cover commanded duration")
    grid = np.arange(0.0, raw_t[-1] + SAMPLE_DT / 2.0, SAMPLE_DT)

    def values(name: str) -> np.ndarray:
        raw = np.array([parse_float(row.get(name)) for row in selected])
        if not np.all(np.isfinite(raw)):
            raise ValueError(f"non-finite odometry field: {name}")
        return np.interp(grid, raw_t, raw)

    position = np.column_stack((
        values("position_1"),
        values("position_0") + 3.0,
        -values("position_2"),
    ))
    velocity = np.column_stack((
        values("velocity_1"),
        values("velocity_0"),
        -values("velocity_2"),
    ))
    q = [values(f"q_{index}") for index in range(4)]
    roll, pitch = quaternion_to_roll_pitch(*q)
    window = min(11, len(grid) if len(grid) % 2 else len(grid) - 1)
    if window < 5:
        raise ValueError("resampled odometry has too few points")
    velocity_smooth = savgol_filter(
        velocity, window_length=window, polyorder=3, axis=0, mode="interp"
    )
    acceleration = savgol_filter(
        velocity, window_length=window, polyorder=3,
        deriv=1, delta=SAMPLE_DT, axis=0, mode="interp",
    )
    jerk = savgol_filter(
        velocity, window_length=window, polyorder=3,
        deriv=2, delta=SAMPLE_DT, axis=0, mode="interp",
    )
    return {
        "time": grid,
        "position": position,
        "velocity": velocity_smooth,
        "acceleration": acceleration,
        "jerk": jerk,
        "roll": roll,
        "pitch": pitch,
    }


def analyze_trial(trial_dir: Path) -> Tuple[Dict[str, object], List[Dict[str, object]]]:
    config = json.loads((trial_dir / "trial_config.json").read_text(encoding="utf-8"))
    start_ns = command_time_ns(trial_dir)
    data = load_resampled_odom(trial_dir, start_ns)
    gain, target_distance, duration = adaptation_values(trial_dir)
    if not math.isclose(duration, DURATION_S, abs_tol=1e-4):
        raise ValueError(f"unexpected duration: {duration}")
    if config["method"] == "fixed_gain" and not math.isclose(gain, 1.0, abs_tol=1e-5):
        raise ValueError(f"fixed_gain trial used kappa={gain}")
    if config["method"] == "task_conditioned":
        expected_gain = expected_task_gain(
            str(config["motion_style"]), target_distance, duration
        )
        if not math.isclose(gain, expected_gain, rel_tol=1e-5, abs_tol=1e-5):
            raise ValueError(
                f"task_conditioned trial used kappa={gain}, expected {expected_gain}"
            )

    time_values = data["time"]
    position = data["position"]
    velocity = data["velocity"]
    acceleration = data["acceleration"]
    jerk = data["jerk"]
    start = position[0]
    target = np.array(TARGET)
    displacement = target - start
    distance = float(np.linalg.norm(displacement))
    direction = displacement / distance
    progress = minimum_jerk_progress(time_values, duration)
    reference = start + progress[:, None] * displacement
    tracking_error = np.linalg.norm(reference - position, axis=1)
    target_error = np.linalg.norm(target - position, axis=1)
    speed = np.linalg.norm(velocity, axis=1)
    acceleration_norm = np.linalg.norm(acceleration, axis=1)
    jerk_norm = np.linalg.norm(jerk, axis=1)
    stable = (target_error < POSITION_THRESHOLD_M) & (speed < VELOCITY_THRESHOLD_MPS)
    settling = first_sustained_time(time_values, stable, SETTLING_DWELL_S)
    command_window = time_values <= duration + 1e-9
    along_track = (position - start) @ direction
    overshoot = float(max(0.0, np.max(along_track - distance)))

    summary: Dict[str, object] = {
        "trial_id": config["trial_id"],
        "method": config["method"],
        "motion_style": config["motion_style"],
        "repeat": config["repeat"],
        "samples": len(time_values),
        "gain_multiplier": gain,
        "target_distance_m": target_distance,
        "duration_s": duration,
        "peak_velocity_mps": float(np.max(speed)),
        "peak_acceleration_mps2": float(np.max(acceleration_norm)),
        "peak_jerk_mps3": float(np.max(jerk_norm)),
        "settling_time_s": settling,
        "tracking_rmse_m": float(np.sqrt(np.mean(tracking_error[command_window] ** 2))),
        "overshoot_m": overshoot,
        "peak_abs_roll_deg": float(np.max(np.abs(data["roll"]))),
        "peak_abs_pitch_deg": float(np.max(np.abs(data["pitch"]))),
        "final_position_error_m": float(target_error[-1]),
    }
    timeseries = []
    for index, elapsed in enumerate(time_values):
        timeseries.append({
            "trial_id": config["trial_id"],
            "method": config["method"],
            "motion_style": config["motion_style"],
            "repeat": config["repeat"],
            "elapsed_time_s": elapsed,
            "reference_x": reference[index, 0],
            "reference_y": reference[index, 1],
            "reference_z": reference[index, 2],
            "actual_x": position[index, 0],
            "actual_y": position[index, 1],
            "actual_z": position[index, 2],
            "speed_mps": speed[index],
            "acceleration_mps2": acceleration_norm[index],
            "jerk_mps3": jerk_norm[index],
            "roll_deg": data["roll"][index],
            "pitch_deg": data["pitch"][index],
            "tracking_error_m": tracking_error[index],
        })
    return summary, timeseries


def finite(values: Iterable[object]) -> List[float]:
    parsed = [parse_float(value) for value in values]
    return [value for value in parsed if math.isfinite(value)]


def summarize(trials: Sequence[Dict[str, object]]) -> List[Dict[str, object]]:
    grouped: Dict[Tuple[str, str], List[Dict[str, object]]] = defaultdict(list)
    for row in trials:
        grouped[(str(row["method"]), str(row["motion_style"]))].append(row)
    output = []
    for (method, style), rows in sorted(grouped.items()):
        result: Dict[str, object] = {
            "method": method,
            "motion_style": style,
            "trials": len(rows),
        }
        for metric in SUMMARY_METRICS:
            values = finite(row[metric] for row in rows)
            result[f"mean_{metric}"] = fmean(values) if values else math.nan
            result[f"std_{metric}"] = stdev(values) if len(values) > 1 else 0.0
            result[f"valid_{metric}"] = len(values)
        output.append(result)
    return output


def write_csv(path: Path, fields: Sequence[str], rows: Sequence[Dict[str, object]]) -> None:
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def plot_results(
    output_dir: Path,
    trials: Sequence[Dict[str, object]],
    timeseries: Sequence[Dict[str, object]],
) -> None:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    colors = {"smooth": "#1f77b4", "normal": "#555555", "aggressive": "#d62728"}
    grouped: Dict[Tuple[str, str], List[Dict[str, object]]] = defaultdict(list)
    for row in timeseries:
        grouped[(str(row["method"]), str(row["motion_style"]))].append(row)

    def draw_lines(axes, metrics, ylabels, filename):
        for row_index, method in enumerate(METHODS):
            for style, color in colors.items():
                rows = grouped[(method, style)]
                by_trial: Dict[str, List[Dict[str, object]]] = defaultdict(list)
                for row in rows:
                    by_trial[str(row["trial_id"])].append(row)
                for column, metric in enumerate(metrics):
                    axis = axes[row_index, column]
                    for trial_rows in by_trial.values():
                        trial_rows.sort(key=lambda item: float(item["elapsed_time_s"]))
                        axis.plot(
                            [float(row["elapsed_time_s"]) for row in trial_rows],
                            [float(row[metric]) for row in trial_rows],
                            color=color, alpha=0.16, linewidth=0.7,
                        )
                    if by_trial:
                        common_end = min(
                            max(float(row["elapsed_time_s"]) for row in trial_rows)
                            for trial_rows in by_trial.values()
                        )
                        grid = np.arange(0.0, common_end + SAMPLE_DT / 2.0, SAMPLE_DT)
                        series = []
                        for trial_rows in by_trial.values():
                            trial_rows.sort(key=lambda item: float(item["elapsed_time_s"]))
                            series.append(np.interp(
                                grid,
                                [float(row["elapsed_time_s"]) for row in trial_rows],
                                [float(row[metric]) for row in trial_rows],
                            ))
                        axis.plot(
                            grid, np.mean(series, axis=0), color=color,
                            linewidth=1.8, label=style,
                        )
                    axis.axvline(DURATION_S, color="#999999", linestyle=":", linewidth=0.8)
                    axis.grid(alpha=0.25)
                    axis.set_ylabel(ylabels[column])
                    if row_index == 0:
                        axis.set_title(ylabels[column])
                    if row_index == len(METHODS) - 1:
                        axis.set_xlabel("Time (s)")
                axes[row_index, 0].text(
                    0.02, 0.92, method.replace("_", " "),
                    transform=axes[row_index, 0].transAxes,
                )
        axes[0, -1].legend(fontsize="small")
        axes[0, 0].figure.tight_layout()
        for suffix in ("png", "pdf"):
            axes[0, 0].figure.savefig(output_dir / f"{filename}.{suffix}", dpi=220)
        plt.close(axes[0, 0].figure)

    fig, axes = plt.subplots(2, 3, figsize=(13, 7), squeeze=False)
    draw_lines(
        axes,
        ["actual_x", "actual_y", "actual_z"],
        ["X position (m)", "Y position (m)", "Z position (m)"],
        "fig_position_response",
    )
    fig, axes = plt.subplots(2, 3, figsize=(13, 7), squeeze=False)
    draw_lines(
        axes,
        ["speed_mps", "acceleration_mps2", "jerk_mps3"],
        ["Speed (m/s)", "Acceleration (m/s²)", "Jerk (m/s³)"],
        "fig_velocity_acceleration_jerk",
    )
    fig, axes = plt.subplots(2, 2, figsize=(10, 7), squeeze=False)
    draw_lines(
        axes,
        ["roll_deg", "pitch_deg"],
        ["Roll (deg)", "Pitch (deg)"],
        "fig_pitch_roll",
    )

    labels = [
        f"{method.replace('_gain', '')}\n{style}"
        for method in METHODS for style in colors
    ]
    fig, axes = plt.subplots(1, 2, figsize=(14, 5))
    for axis, metric, ylabel in (
        (axes[0], "peak_velocity_mps", "Peak velocity (m/s)"),
        (axes[1], "settling_time_s", "Settling time (s)"),
    ):
        data = [
            finite(
                row[metric] for row in trials
                if row["method"] == method and row["motion_style"] == style
            )
            for method in METHODS for style in colors
        ]
        axis.boxplot(data, tick_labels=labels, showmeans=True)
        axis.set_ylabel(ylabel)
        axis.tick_params(axis="x", labelrotation=30)
        axis.grid(alpha=0.25)
    fig.tight_layout()
    for suffix in ("png", "pdf"):
        fig.savefig(output_dir / f"fig_peak_velocity_settling_boxplot.{suffix}", dpi=220)
    plt.close(fig)


def write_markdown_table(path: Path, summary: Sequence[Dict[str, object]]) -> None:
    lines = [
        "# Experiment 07 mean ± std",
        "",
        "| Method | Style | Trials | Gain | Peak velocity | Peak acceleration | Peak jerk | Settling | RMSE | Overshoot |",
        "| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for row in summary:
        def cell(metric: str) -> str:
            mean_value = parse_float(row[f"mean_{metric}"])
            std_value = parse_float(row[f"std_{metric}"])
            return (
                f"{mean_value:.3f} ± {std_value:.3f}"
                if math.isfinite(mean_value) else "N/A"
            )
        lines.append(
            f"| {row['method']} | {row['motion_style']} | {row['trials']} | "
            f"{cell('gain_multiplier')} | {cell('peak_velocity_mps')} | "
            f"{cell('peak_acceleration_mps2')} | {cell('peak_jerk_mps3')} | "
            f"{cell('settling_time_s')} | {cell('tracking_rmse_m')} | "
            f"{cell('overshoot_m')} |"
        )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def llm_reliability(experiment_dir: Path) -> Dict[str, object]:
    formal = list((experiment_dir / "trials").glob("*/llm_parse_result.json"))
    rejected = list((experiment_dir / "rejected").glob("*/llm_parse_result.json"))
    passed = 0
    for path in formal + rejected:
        record = json.loads(path.read_text(encoding="utf-8"))
        passed += bool(record.get("gate_passed"))
    attempts = len(formal) + len(rejected)
    return {
        "parse_attempts_with_result": attempts,
        "gate_passed": passed,
        "gate_failed": attempts - passed,
        "formal_trials": len(formal),
        "rejected_attempt_directories": len(list((experiment_dir / "rejected").iterdir())),
        "gate_pass_rate": passed / attempts if attempts else math.nan,
    }


def main() -> int:
    args = parse_args()
    experiment_dir = args.experiment_dir.resolve()
    output_dir = (args.output_dir or experiment_dir).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    trial_dirs = sorted(
        path for path in (experiment_dir / "trials").iterdir()
        if (path / "completed.json").is_file()
    )
    expected = len(METHODS) * 3 * 5
    if len(trial_dirs) != expected:
        raise ValueError(f"expected {expected} formal trials, found {len(trial_dirs)}")

    trials: List[Dict[str, object]] = []
    timeseries: List[Dict[str, object]] = []
    for trial_dir in trial_dirs:
        summary, samples = analyze_trial(trial_dir)
        trials.append(summary)
        timeseries.extend(samples)
    grouped_counts = defaultdict(int)
    for row in trials:
        grouped_counts[(row["method"], row["motion_style"])] += 1
    if any(count != 5 for count in grouped_counts.values()) or len(grouped_counts) != 6:
        raise ValueError(f"incomplete method/style cells: {dict(grouped_counts)}")

    summary = summarize(trials)
    summary_fields = ["method", "motion_style", "trials"] + [
        field
        for metric in SUMMARY_METRICS
        for field in (f"mean_{metric}", f"std_{metric}", f"valid_{metric}")
    ]
    write_csv(output_dir / "trial_summary.csv", TRIAL_FIELDS, trials)
    write_csv(output_dir / "method_style_summary.csv", summary_fields, summary)
    write_csv(output_dir / "timeseries.csv", TIMESERIES_FIELDS, timeseries)
    write_markdown_table(output_dir / "mean_std_table.md", summary)
    reliability = llm_reliability(experiment_dir)
    (output_dir / "llm_reliability.json").write_text(
        json.dumps(reliability, indent=2), encoding="utf-8"
    )
    plot_results(output_dir, trials, timeseries)
    report = {
        "status": "valid",
        "formal_trials": len(trials),
        "method_style_cells": {
            f"{method}/{style}": count
            for (method, style), count in sorted(grouped_counts.items())
        },
        "all_fixed_gains_equal_one": all(
            math.isclose(float(row["gain_multiplier"]), 1.0, abs_tol=1e-5)
            for row in trials if row["method"] == "fixed_gain"
        ),
        "llm_reliability": reliability,
    }
    (output_dir / "validation_report.json").write_text(
        json.dumps(report, indent=2), encoding="utf-8"
    )
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
