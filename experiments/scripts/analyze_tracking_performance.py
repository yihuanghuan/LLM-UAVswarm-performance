#!/usr/bin/env python3
"""Analyze closed-loop Gazebo trajectory tracking trials for experiment 06."""

from __future__ import annotations

import argparse
import csv
import json
import math
from collections import defaultdict
from pathlib import Path
from statistics import mean, pvariance
from typing import Dict, Iterable, List, Sequence, Tuple


POSITION_THRESHOLD_M = 0.3
VELOCITY_THRESHOLD_MPS = 0.3
SETTLING_DWELL_S = 1.0

UAV_FIELDS = [
    "trial_id", "scenario", "method", "repeat", "uav_id", "samples",
    "requested_duration_s", "tracking_rmse_m", "max_tracking_error_m",
    "arrival_time_s", "settling_time_s", "overshoot_m",
    "max_actual_velocity_mps", "max_actual_acceleration_mps2",
    "final_position_error_m",
]
TRIAL_FIELDS = [
    "trial_id", "scenario", "method", "repeat", "num_uav",
    "mean_tracking_rmse_m", "max_tracking_error_m", "mean_arrival_time_s",
    "arrival_time_variance_s2", "mean_settling_time_s", "max_overshoot_m",
    "mean_final_position_error_m", "all_arrived", "all_settled",
]
METHOD_FIELDS = [
    "scenario", "method", "trials", "uav_outcomes",
    "mean_tracking_rmse_m", "std_tracking_rmse_m", "max_tracking_error_m",
    "mean_arrival_time_s", "arrival_time_variance_s2",
    "mean_settling_time_s", "mean_overshoot_m",
    "mean_final_position_error_m", "arrival_success_rate", "settling_success_rate",
]
TIMESERIES_FIELDS = [
    "trial_id", "scenario", "method", "repeat", "uav_id", "elapsed_time_s",
    "reference_x", "reference_y", "reference_z",
    "actual_x", "actual_y", "actual_z", "tracking_error_m",
    "actual_speed_mps", "actual_acceleration_mps2",
]


def parse_float(value: object, default: float = math.nan) -> float:
    try:
        result = float(str(value).strip())
    except (TypeError, ValueError):
        return default
    return result if math.isfinite(result) else default


def finite(values: Iterable[float]) -> List[float]:
    return [value for value in values if math.isfinite(value)]


def safe_mean(values: Iterable[float]) -> float:
    valid = finite(values)
    return mean(valid) if valid else math.nan


def safe_variance(values: Iterable[float]) -> float:
    valid = finite(values)
    return pvariance(valid) if valid else math.nan


def vector(row: Dict[str, str], prefix: str) -> Tuple[float, float, float]:
    return tuple(parse_float(row.get(f"{prefix}_{axis}")) for axis in "xyz")  # type: ignore


def norm(values: Sequence[float]) -> float:
    return math.sqrt(sum(value * value for value in values))


def read_csv(path: Path) -> List[Dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def metrics_files(csv_dir: Path) -> List[Path]:
    files = sorted(csv_dir.glob("uav*_trajectory_metrics.csv"))
    if not files:
        raise FileNotFoundError(f"no trajectory metrics CSV files in {csv_dir}")
    return files


def first_sustained_time(
    times: Sequence[float], conditions: Sequence[bool], dwell_s: float
) -> float:
    """Return the beginning of the first continuously true interval of dwell_s."""
    start: float | None = None
    previous: float | None = None
    for current, condition in zip(times, conditions):
        if not math.isfinite(current):
            continue
        # A gap greater than 0.35 s indicates missing 10 Hz telemetry and
        # invalidates continuity.
        if previous is not None and current - previous > 0.35:
            start = None
        if condition:
            if start is None:
                start = current
            if current - start >= dwell_s:
                return start
        else:
            start = None
        previous = current
    return math.nan


def analyze_uav_rows(
    rows: Sequence[Dict[str, str]], metadata: Dict[str, object]
) -> Tuple[Dict[str, object], List[Dict[str, object]]]:
    rows = sorted(rows, key=lambda row: parse_float(row.get("elapsed_time")))
    rows = [row for row in rows if math.isfinite(parse_float(row.get("elapsed_time")))]
    if not rows:
        raise ValueError("trajectory metrics contain no finite elapsed_time samples")

    first = rows[0]
    duration = parse_float(first.get("requested_duration"))
    if not math.isfinite(duration) or duration <= 0.0:
        raise ValueError("requested_duration must be positive")

    uav_id = int(parse_float(first.get("uav_id")))
    start = vector(first, "start_pos")
    target = vector(first, "target_pos")
    displacement = tuple(target[i] - start[i] for i in range(3))
    distance = norm(displacement)
    direction = (
        tuple(component / distance for component in displacement)
        if distance > 1e-9 else (0.0, 0.0, 0.0)
    )

    samples: List[Dict[str, object]] = []
    target_errors: List[float] = []
    times: List[float] = []
    speeds: List[float] = []
    tracking_errors: List[float] = []
    overshoots: List[float] = []
    previous_time = math.nan
    previous_velocity = (math.nan, math.nan, math.nan)

    for row in rows:
        elapsed = parse_float(row.get("elapsed_time"))
        reference = vector(row, "reference_pos")
        actual = vector(row, "actual_pos")
        velocity = vector(row, "actual_velocity")
        error = parse_float(row.get("tracking_error"))
        if not math.isfinite(error):
            error = norm(tuple(reference[i] - actual[i] for i in range(3)))
        speed = norm(velocity)
        acceleration = math.nan
        if math.isfinite(previous_time) and elapsed > previous_time:
            dv = tuple(velocity[i] - previous_velocity[i] for i in range(3))
            acceleration = norm(dv) / (elapsed - previous_time)
        previous_time = elapsed
        previous_velocity = velocity

        target_error = norm(tuple(target[i] - actual[i] for i in range(3)))
        progress = sum((actual[i] - start[i]) * direction[i] for i in range(3))
        overshoot = max(0.0, progress - distance)
        times.append(elapsed)
        speeds.append(speed)
        target_errors.append(target_error)
        tracking_errors.append(error)
        overshoots.append(overshoot)
        samples.append({
            **{key: metadata[key] for key in ("trial_id", "scenario", "method", "repeat")},
            "uav_id": uav_id,
            "elapsed_time_s": elapsed,
            "reference_x": reference[0], "reference_y": reference[1], "reference_z": reference[2],
            "actual_x": actual[0], "actual_y": actual[1], "actual_z": actual[2],
            "tracking_error_m": error,
            "actual_speed_mps": speed,
            "actual_acceleration_mps2": acceleration,
        })

    tracking_window = [
        tracking_errors[index]
        for index, elapsed in enumerate(times)
        if 0.0 <= elapsed <= duration
    ]
    if not tracking_window:
        raise ValueError("no tracking samples fall inside the commanded duration")
    stable = [
        target_errors[index] < POSITION_THRESHOLD_M
        and speeds[index] < VELOCITY_THRESHOLD_MPS
        for index in range(len(times))
    ]
    arrival = next((times[index] for index, condition in enumerate(stable) if condition), math.nan)
    settling = first_sustained_time(times, stable, SETTLING_DWELL_S)
    accelerations = finite(
        parse_float(str(sample["actual_acceleration_mps2"])) for sample in samples
    )
    summary: Dict[str, object] = {
        **{key: metadata[key] for key in ("trial_id", "scenario", "method", "repeat")},
        "uav_id": uav_id,
        "samples": len(rows),
        "requested_duration_s": duration,
        "tracking_rmse_m": math.sqrt(mean(value * value for value in tracking_window)),
        "max_tracking_error_m": max(tracking_window),
        "arrival_time_s": arrival,
        "settling_time_s": settling,
        "overshoot_m": max(overshoots),
        "max_actual_velocity_mps": max(speeds),
        "max_actual_acceleration_mps2": max(accelerations) if accelerations else math.nan,
        "final_position_error_m": target_errors[-1],
    }
    return summary, samples


def analyze_trial(trial_dir: Path) -> Tuple[List[Dict[str, object]], List[Dict[str, object]]]:
    config_path = trial_dir / "trial_config.json"
    if not config_path.is_file():
        raise FileNotFoundError(f"missing {config_path}")
    config = json.loads(config_path.read_text(encoding="utf-8"))
    metadata = {
        "trial_id": config["trial_id"],
        "scenario": config["scenario"],
        "method": config["method"],
        "repeat": int(config["repeat"]),
    }
    csv_dir = trial_dir / "bag_csv"
    summaries: List[Dict[str, object]] = []
    samples: List[Dict[str, object]] = []
    for path in metrics_files(csv_dir):
        summary, timeseries = analyze_uav_rows(read_csv(path), metadata)
        summaries.append(summary)
        samples.extend(timeseries)
    expected = int(config["num_uav"])
    if len(summaries) != expected:
        raise ValueError(
            f"{config['trial_id']} expected {expected} UAV summaries, got {len(summaries)}"
        )
    return summaries, samples


def summarize_trials(uav_rows: Sequence[Dict[str, object]]) -> List[Dict[str, object]]:
    grouped: Dict[str, List[Dict[str, object]]] = defaultdict(list)
    for row in uav_rows:
        grouped[str(row["trial_id"])].append(row)
    output: List[Dict[str, object]] = []
    for trial_id, rows in sorted(grouped.items()):
        first = rows[0]
        arrivals = [float(row["arrival_time_s"]) for row in rows]
        settlings = [float(row["settling_time_s"]) for row in rows]
        output.append({
            "trial_id": trial_id,
            "scenario": first["scenario"],
            "method": first["method"],
            "repeat": first["repeat"],
            "num_uav": len(rows),
            "mean_tracking_rmse_m": safe_mean(float(row["tracking_rmse_m"]) for row in rows),
            "max_tracking_error_m": max(float(row["max_tracking_error_m"]) for row in rows),
            "mean_arrival_time_s": safe_mean(arrivals),
            "arrival_time_variance_s2": safe_variance(arrivals),
            "mean_settling_time_s": safe_mean(settlings),
            "max_overshoot_m": max(float(row["overshoot_m"]) for row in rows),
            "mean_final_position_error_m": safe_mean(
                float(row["final_position_error_m"]) for row in rows
            ),
            "all_arrived": len(finite(arrivals)) == len(rows),
            "all_settled": len(finite(settlings)) == len(rows),
        })
    return output


def summarize_methods(uav_rows: Sequence[Dict[str, object]]) -> List[Dict[str, object]]:
    grouped: Dict[Tuple[str, str], List[Dict[str, object]]] = defaultdict(list)
    for row in uav_rows:
        grouped[(str(row["scenario"]), str(row["method"]))].append(row)
    output: List[Dict[str, object]] = []
    for (scenario, method), rows in sorted(grouped.items()):
        rmse = [float(row["tracking_rmse_m"]) for row in rows]
        arrivals = [float(row["arrival_time_s"]) for row in rows]
        settlings = [float(row["settling_time_s"]) for row in rows]
        output.append({
            "scenario": scenario,
            "method": method,
            "trials": len({str(row["trial_id"]) for row in rows}),
            "uav_outcomes": len(rows),
            "mean_tracking_rmse_m": safe_mean(rmse),
            "std_tracking_rmse_m": math.sqrt(safe_variance(rmse)),
            "max_tracking_error_m": max(float(row["max_tracking_error_m"]) for row in rows),
            "mean_arrival_time_s": safe_mean(arrivals),
            "arrival_time_variance_s2": safe_variance(arrivals),
            "mean_settling_time_s": safe_mean(settlings),
            "mean_overshoot_m": safe_mean(float(row["overshoot_m"]) for row in rows),
            "mean_final_position_error_m": safe_mean(
                float(row["final_position_error_m"]) for row in rows
            ),
            "arrival_success_rate": len(finite(arrivals)) / len(rows),
            "settling_success_rate": len(finite(settlings)) / len(rows),
        })
    return output


def write_csv(path: Path, fieldnames: Sequence[str], rows: Sequence[Dict[str, object]]) -> None:
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def write_table(path: Path, rows: Sequence[Dict[str, object]]) -> None:
    lines = [
        "# Experiment 06 tracking comparison",
        "",
        "| Scenario | Method | Trials | RMSE (m) | Max error (m) | Settling (s) | Overshoot (m) |",
        "| --- | --- | ---: | ---: | ---: | ---: | ---: |",
    ]
    for row in rows:
        lines.append(
            f"| {row['scenario']} | {row['method']} | {row['trials']} | "
            f"{float(row['mean_tracking_rmse_m']):.3f} | "
            f"{float(row['max_tracking_error_m']):.3f} | "
            f"{float(row['mean_settling_time_s']):.3f} | "
            f"{float(row['mean_overshoot_m']):.3f} |"
        )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def plot_results(
    output_dir: Path,
    uav_rows: Sequence[Dict[str, object]],
    timeseries: Sequence[Dict[str, object]],
) -> None:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import numpy as np

    methods = ["px4_step", "linear_ladrc", "minimum_jerk_ladrc"]
    scenarios = ["single_uav", "five_uav_circle", "eight_uav_line_to_circle"]
    colors = dict(zip(methods, ("#777777", "#1f77b4", "#d62728")))
    trial_rows = summarize_trials(uav_rows)

    fig, axes = plt.subplots(1, 3, figsize=(13, 4), sharey=False)
    for axis, scenario in zip(axes, scenarios):
        data = [
            [float(row["mean_tracking_rmse_m"]) for row in trial_rows
             if row["scenario"] == scenario and row["method"] == method]
            for method in methods
        ]
        axis.boxplot(data, tick_labels=["PX4 step", "Linear+LADRC", "MJ+LADRC"])
        axis.set_title(scenario.replace("_", " "))
        axis.set_ylabel("Tracking RMSE (m)")
        axis.grid(alpha=0.25)
    fig.tight_layout()
    for suffix in ("png", "pdf"):
        fig.savefig(output_dir / f"fig_rmse_boxplot.{suffix}", dpi=220)
    plt.close(fig)

    fig, axes = plt.subplots(1, 3, figsize=(14, 4))
    for axis, scenario in zip(axes, scenarios):
        for method in methods:
            selected = [
                row for row in timeseries
                if row["scenario"] == scenario and row["method"] == method
            ]
            bins: Dict[float, List[float]] = defaultdict(list)
            for row in selected:
                time_bin = round(float(row["elapsed_time_s"]) * 10.0) / 10.0
                bins[time_bin].append(float(row["tracking_error_m"]))
            x = sorted(bins)
            y = [mean(bins[value]) for value in x]
            axis.plot(x, y, label=method, color=colors[method], linewidth=1.4)
        axis.set_title(scenario.replace("_", " "))
        axis.set_xlabel("Elapsed time (s)")
        axis.set_ylabel("Mean tracking error (m)")
        axis.grid(alpha=0.25)
    axes[-1].legend(fontsize=8)
    fig.tight_layout()
    for suffix in ("png", "pdf"):
        fig.savefig(output_dir / f"fig_tracking_error.{suffix}", dpi=220)
    plt.close(fig)

    fig, axes = plt.subplots(2, 3, figsize=(14, 7), sharex="col")
    for column, scenario in enumerate(scenarios):
        for method in methods:
            selected = [
                row for row in timeseries
                if row["scenario"] == scenario and row["method"] == method
            ]
            for row_index, field in enumerate(
                ("actual_speed_mps", "actual_acceleration_mps2")
            ):
                bins: Dict[float, List[float]] = defaultdict(list)
                for row in selected:
                    value = float(row[field])
                    if math.isfinite(value):
                        time_bin = round(float(row["elapsed_time_s"]) * 10.0) / 10.0
                        bins[time_bin].append(value)
                x = sorted(bins)
                y = [mean(bins[value]) for value in x]
                axes[row_index, column].plot(
                    x, y, label=method, color=colors[method], linewidth=1.2
                )
        axes[0, column].set_title(scenario.replace("_", " "))
        axes[1, column].set_xlabel("Elapsed time (s)")
        axes[0, column].set_ylabel("Mean speed (m/s)")
        axes[1, column].set_ylabel("Mean acceleration (m/s²)")
        axes[0, column].grid(alpha=0.25)
        axes[1, column].grid(alpha=0.25)
    axes[0, -1].legend(fontsize=8)
    fig.tight_layout()
    for suffix in ("png", "pdf"):
        fig.savefig(output_dir / f"fig_velocity_acceleration.{suffix}", dpi=220)
    plt.close(fig)

    # Representative median-RMSE trial for each scenario/method, UAV with the
    # lowest ID, plotted as reference versus actual in 3D.
    fig = plt.figure(figsize=(14, 10))
    for index, (scenario, method) in enumerate(
        ((scenario, method) for scenario in scenarios for method in methods), start=1
    ):
        axis = fig.add_subplot(3, 3, index, projection="3d")
        candidates = [
            row for row in uav_rows
            if row["scenario"] == scenario and row["method"] == method
        ]
        if not candidates:
            axis.set_axis_off()
            continue
        ordered = sorted(candidates, key=lambda row: float(row["tracking_rmse_m"]))
        chosen = ordered[len(ordered) // 2]
        selected = [
            row for row in timeseries
            if row["trial_id"] == chosen["trial_id"] and row["uav_id"] == chosen["uav_id"]
        ]
        selected.sort(key=lambda row: float(row["elapsed_time_s"]))
        axis.plot(
            [float(row["reference_x"]) for row in selected],
            [float(row["reference_y"]) for row in selected],
            [float(row["reference_z"]) for row in selected],
            "--", color="black", label="reference",
        )
        axis.plot(
            [float(row["actual_x"]) for row in selected],
            [float(row["actual_y"]) for row in selected],
            [float(row["actual_z"]) for row in selected],
            color=colors[method], label="actual",
        )
        axis.set_title(f"{scenario}\n{method}", fontsize=9)
        if index == 3:
            axis.legend(fontsize=7)
    fig.tight_layout()
    for suffix in ("png", "pdf"):
        fig.savefig(output_dir / f"fig_3d_tracking.{suffix}", dpi=220)
    plt.close(fig)


def analyze_experiment(input_root: Path, output_dir: Path) -> None:
    trial_dirs = sorted(
        path.parent for path in input_root.rglob("completed.json")
        if "rejected" not in path.parts
    )
    if not trial_dirs:
        raise FileNotFoundError(f"no completed trials under {input_root}")
    uav_rows: List[Dict[str, object]] = []
    timeseries: List[Dict[str, object]] = []
    for trial_dir in trial_dirs:
        trial_uavs, trial_samples = analyze_trial(trial_dir)
        uav_rows.extend(trial_uavs)
        timeseries.extend(trial_samples)
    trial_rows = summarize_trials(uav_rows)
    method_rows = summarize_methods(uav_rows)
    output_dir.mkdir(parents=True, exist_ok=True)
    write_csv(output_dir / "uav_trial_summary.csv", UAV_FIELDS, uav_rows)
    write_csv(output_dir / "trial_summary.csv", TRIAL_FIELDS, trial_rows)
    write_csv(output_dir / "method_summary.csv", METHOD_FIELDS, method_rows)
    write_csv(output_dir / "tracking_timeseries.csv", TIMESERIES_FIELDS, timeseries)
    write_table(output_dir / "table_tracking_comparison.md", method_rows)
    plot_results(output_dir, uav_rows, timeseries)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input_root", type=Path)
    parser.add_argument("--output-dir", type=Path)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    output_dir = args.output_dir or args.input_root
    analyze_experiment(args.input_root.resolve(), output_dir.resolve())
    print(f"Wrote tracking analysis to {output_dir.resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
