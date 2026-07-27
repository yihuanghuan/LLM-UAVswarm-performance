#!/usr/bin/env python3
"""Export, validate, summarize, and plot experiment-05 trial bags."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import statistics
import sys
from collections import defaultdict
from pathlib import Path
from typing import Dict, Iterable, List

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402


REPO_ROOT = Path(__file__).resolve().parents[2]
TOOLS_DIR = REPO_ROOT / "tools/trajectory_metrics"
if str(TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(TOOLS_DIR))

from rosbag_to_csv import convert_bag  # noqa: E402


PROFILES = ["step", "linear", "trapezoidal", "minimum_jerk"]
COLORS = {
    "step": "#E45756",
    "linear": "#72B7B2",
    "trapezoidal": "#F2CF5B",
    "minimum_jerk": "#4C78A8",
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--input-dir",
        default=str(REPO_ROOT / "experiments/results/experiments_05"),
    )
    parser.add_argument("--skip-bag-export", action="store_true")
    return parser.parse_args()


def read_csv(path: Path) -> List[Dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def write_csv(path: Path, rows: Iterable[Dict[str, object]]) -> None:
    rows = list(rows)
    if not rows:
        raise ValueError(f"no rows for {path}")
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def number(row: Dict[str, str], key: str) -> float:
    try:
        return float(row.get(key, "nan"))
    except (TypeError, ValueError):
        return math.nan


def truth(value: object) -> bool:
    return str(value).lower() in {"true", "1", "yes"}


def finite_mean(values: Iterable[float]) -> float:
    valid = [value for value in values if math.isfinite(value)]
    return statistics.mean(valid) if valid else math.nan


def finite_stdev(values: Iterable[float]) -> float:
    valid = [value for value in values if math.isfinite(value)]
    return statistics.stdev(valid) if len(valid) > 1 else (0.0 if valid else math.nan)


def export_trial_bag(trial_dir: Path) -> Path:
    csv_dir = trial_dir / "bag_csv"
    expected = csv_dir / "uav1_trajectory_metrics.csv"
    if expected.is_file():
        return csv_dir
    convert_bag(
        trial_dir / "rosbag",
        csv_dir,
        [
            "/uav*/trajectory_metrics",
            "/uav*/swarm_command",
            "/uav*/status",
            "/uav*/odom",
        ],
    )
    return csv_dir


def analyze_trial(
    trial_dir: Path, export_bag: bool
) -> tuple[List[Dict[str, object]], List[Dict[str, object]]]:
    status = json.loads((trial_dir / "trial_status.json").read_text(encoding="utf-8"))
    profile = status["profile"]
    trial_id = status["trial_id"]
    csv_dir = export_trial_bag(trial_dir) if export_bag else trial_dir / "bag_csv"
    uav_rows: List[Dict[str, object]] = []
    timeseries: List[Dict[str, object]] = []
    for uav_id in range(1, 6):
        rows = read_csv(csv_dir / f"uav{uav_id}_trajectory_metrics.csv")
        if not rows:
            raise RuntimeError(f"{trial_id} UAV{uav_id} has no trajectory metrics")
        tracking_window_errors = []
        for row in rows:
            dx = number(row, "actual_pos_x") - number(row, "reference_pos_x")
            dy = number(row, "actual_pos_y") - number(row, "reference_pos_y")
            dz = number(row, "actual_pos_z") - number(row, "reference_pos_z")
            tracking_error = math.sqrt(dx * dx + dy * dy + dz * dz)
            elapsed = number(row, "elapsed_time")
            duration = number(row, "requested_duration")
            if 0.0 <= elapsed <= duration:
                tracking_window_errors.append(tracking_error)
            timeseries.append(
                {
                    "trial_id": trial_id,
                    "profile": profile,
                    "uav_id": uav_id,
                    "elapsed_time_s": elapsed,
                    "reference_x": number(row, "reference_pos_x"),
                    "reference_y": number(row, "reference_pos_y"),
                    "reference_z": number(row, "reference_pos_z"),
                    "actual_x": number(row, "actual_pos_x"),
                    "actual_y": number(row, "actual_pos_y"),
                    "actual_z": number(row, "actual_pos_z"),
                    "reference_speed": math.sqrt(
                        number(row, "reference_velocity_x") ** 2
                        + number(row, "reference_velocity_y") ** 2
                        + number(row, "reference_velocity_z") ** 2
                    ),
                    "reference_acceleration": math.sqrt(
                        number(row, "reference_acceleration_x") ** 2
                        + number(row, "reference_acceleration_y") ** 2
                        + number(row, "reference_acceleration_z") ** 2
                    ),
                    "reference_jerk": math.sqrt(
                        number(row, "reference_jerk_x") ** 2
                        + number(row, "reference_jerk_y") ** 2
                        + number(row, "reference_jerk_z") ** 2
                    ),
                    "tracking_error": tracking_error,
                }
            )
        final = rows[-1]
        uav_status = status["uavs"][str(uav_id)]
        arrival = uav_status["arrival_time_s"]
        uav_rows.append(
            {
                "trial_id": trial_id,
                "profile": profile,
                "uav_id": uav_id,
                "samples": len(rows),
                "path_length": number(final, "path_length"),
                "max_velocity": number(final, "max_velocity"),
                "max_acceleration": number(final, "max_acceleration"),
                "max_jerk": number(final, "max_jerk"),
                "integrated_squared_jerk": number(final, "integrated_squared_jerk"),
                "max_velocity_valid": truth(final.get("max_velocity_valid")),
                "max_acceleration_valid": truth(final.get("max_acceleration_valid")),
                "max_jerk_valid": truth(final.get("max_jerk_valid")),
                "integrated_squared_jerk_valid": truth(
                    final.get("integrated_squared_jerk_valid")
                ),
                "arrived": uav_status["arrived"],
                "arrival_time_s": arrival if arrival is not None else math.nan,
                "arrival_time_error_s": (
                    uav_status["arrival_time_error_s"]
                    if uav_status["arrival_time_error_s"] is not None
                    else math.nan
                ),
                "final_position_error_m": number(final, "final_position_error"),
                "tracking_rmse_m": math.sqrt(
                    finite_mean(value * value for value in tracking_window_errors)
                ),
                "tracking_max_error_m": max(tracking_window_errors),
            }
        )
    return uav_rows, timeseries


def build_trial_summary(uav_rows: List[Dict[str, object]]) -> List[Dict[str, object]]:
    grouped: Dict[str, List[Dict[str, object]]] = defaultdict(list)
    for row in uav_rows:
        grouped[str(row["trial_id"])].append(row)
    output = []
    for trial_id, rows in sorted(grouped.items()):
        arrivals = [
            float(row["arrival_time_s"])
            for row in rows
            if math.isfinite(float(row["arrival_time_s"]))
        ]
        output.append(
            {
                "trial_id": trial_id,
                "profile": rows[0]["profile"],
                "arrived_count": len(arrivals),
                "timeout_count": len(rows) - len(arrivals),
                "all_arrived": len(arrivals) == len(rows),
                "synchronization_error_s": (
                    max(arrivals) - min(arrivals) if len(arrivals) == len(rows) else math.nan
                ),
                "mean_arrival_error_s": finite_mean(
                    float(row["arrival_time_error_s"]) for row in rows
                ),
                "mean_final_position_error_m": finite_mean(
                    float(row["final_position_error_m"]) for row in rows
                ),
                "max_final_position_error_m": max(
                    float(row["final_position_error_m"]) for row in rows
                ),
                "mean_tracking_rmse_m": finite_mean(
                    float(row["tracking_rmse_m"]) for row in rows
                ),
            }
        )
    return output


def build_method_summary(trials: List[Dict[str, object]]) -> List[Dict[str, object]]:
    grouped: Dict[str, List[Dict[str, object]]] = defaultdict(list)
    for row in trials:
        grouped[str(row["profile"])].append(row)
    output = []
    for profile in PROFILES:
        rows = grouped[profile]
        output.append(
            {
                "profile": profile,
                "trials": len(rows),
                "successful_trials": sum(bool(row["all_arrived"]) for row in rows),
                "timeout_rate": sum(not bool(row["all_arrived"]) for row in rows) / len(rows),
                "synchronization_error_mean_s": finite_mean(
                    float(row["synchronization_error_s"]) for row in rows
                ),
                "synchronization_error_std_s": finite_stdev(
                    float(row["synchronization_error_s"]) for row in rows
                ),
                "arrival_error_mean_s": finite_mean(
                    float(row["mean_arrival_error_s"]) for row in rows
                ),
                "arrival_error_std_s": finite_stdev(
                    float(row["mean_arrival_error_s"]) for row in rows
                ),
                "final_position_error_mean_m": finite_mean(
                    float(row["mean_final_position_error_m"]) for row in rows
                ),
                "final_position_error_std_m": finite_stdev(
                    float(row["mean_final_position_error_m"]) for row in rows
                ),
                "tracking_rmse_mean_m": finite_mean(
                    float(row["mean_tracking_rmse_m"]) for row in rows
                ),
                "tracking_rmse_std_m": finite_stdev(
                    float(row["mean_tracking_rmse_m"]) for row in rows
                ),
            }
        )
    return output


def save_figure(fig: plt.Figure, root: Path, name: str) -> None:
    for suffix in ("png", "pdf"):
        fig.savefig(root / f"fig_{name}.{suffix}", dpi=180, bbox_inches="tight")
    plt.close(fig)


def plot_reference_profiles(timeseries: List[Dict[str, object]], root: Path) -> None:
    representatives = {}
    for profile in PROFILES:
        candidates = [
            row for row in timeseries
            if row["profile"] == profile
            and row["uav_id"] == 3
            and str(row["trial_id"]).endswith("r01")
            and 0.0 <= float(row["elapsed_time_s"]) <= 8.0
        ]
        representatives[profile] = sorted(
            candidates, key=lambda row: float(row["elapsed_time_s"])
        )
    fig, axes = plt.subplots(2, 2, figsize=(11, 7), sharex=True)
    fields = [
        ("reference_x", "Reference x (m)"),
        ("reference_speed", "Speed (m/s)"),
        ("reference_acceleration", "Acceleration magnitude (m/s²)"),
        ("reference_jerk", "Jerk magnitude (m/s³)"),
    ]
    for axis, (field, label) in zip(axes.ravel(), fields):
        for profile in PROFILES:
            rows = representatives[profile]
            axis.plot(
                [row["elapsed_time_s"] for row in rows],
                [row[field] for row in rows],
                label=profile,
                color=COLORS[profile],
            )
        axis.set_ylabel(label)
        axis.grid(alpha=0.25)
    axes[1, 0].set_xlabel("Time (s)")
    axes[1, 1].set_xlabel("Time (s)")
    axes[0, 1].legend(fontsize="small")
    save_figure(fig, root, "reference_profiles")


def plot_closed_loop(methods: List[Dict[str, object]], root: Path) -> None:
    fig, axes = plt.subplots(1, 3, figsize=(13, 4))
    fields = [
        ("synchronization_error_mean_s", "Synchronization error (s)"),
        ("final_position_error_mean_m", "Final position error (m)"),
        ("tracking_rmse_mean_m", "Tracking RMSE (m)"),
    ]
    for axis, (field, label) in zip(axes, fields):
        values = [float(row[field]) for row in methods]
        axis.bar(PROFILES, values, color=[COLORS[item] for item in PROFILES])
        axis.set_ylabel(label)
        axis.tick_params(axis="x", rotation=25)
        axis.grid(axis="y", alpha=0.25)
    save_figure(fig, root, "closed_loop_metrics")


def plot_smoothness(uav_rows: List[Dict[str, object]], root: Path) -> None:
    continuity = [-1, 0, 1, 2]
    representative = {
        profile: next(row for row in uav_rows if row["profile"] == profile)
        for profile in PROFILES
    }
    isj = [
        float(representative[profile]["integrated_squared_jerk"])
        if representative[profile]["integrated_squared_jerk_valid"]
        else 0.0
        for profile in PROFILES
    ]
    fig, axes = plt.subplots(1, 2, figsize=(11, 4.3))
    axes[0].bar(PROFILES, continuity, color=[COLORS[item] for item in PROFILES])
    axes[0].set_ylabel("Continuity order (-1 = discontinuous)")
    axes[0].tick_params(axis="x", rotation=25)
    bars = axes[1].bar(PROFILES, isj, color=[COLORS[item] for item in PROFILES])
    for index, profile in enumerate(PROFILES):
        if not representative[profile]["integrated_squared_jerk_valid"]:
            bars[index].set_hatch("//")
            axes[1].text(index, 0.0, "N/A", ha="center", va="bottom")
    axes[1].set_ylabel("Integrated squared jerk")
    axes[1].tick_params(axis="x", rotation=25)
    save_figure(fig, root, "smoothness")


def plot_3d(timeseries: List[Dict[str, object]], root: Path) -> None:
    fig = plt.figure(figsize=(12, 10))
    for index, profile in enumerate(PROFILES, start=1):
        axis = fig.add_subplot(2, 2, index, projection="3d")
        trial_rows = [
            row for row in timeseries
            if row["profile"] == profile and str(row["trial_id"]).endswith("r01")
        ]
        for uav_id in range(1, 6):
            rows = sorted(
                [row for row in trial_rows if row["uav_id"] == uav_id],
                key=lambda row: float(row["elapsed_time_s"]),
            )
            axis.plot(
                [row["actual_x"] for row in rows],
                [row["actual_y"] for row in rows],
                [row["actual_z"] for row in rows],
                label=f"UAV {uav_id}",
            )
            axis.plot(
                [row["reference_x"] for row in rows],
                [row["reference_y"] for row in rows],
                [row["reference_z"] for row in rows],
                color="black",
                alpha=0.25,
                linestyle="--",
            )
        axis.set_title(profile)
        axis.set_xlabel("x")
        axis.set_ylabel("y")
        axis.set_zlabel("z")
    handles, labels = fig.axes[0].get_legend_handles_labels()
    fig.legend(handles, labels, loc="lower center", ncol=5)
    save_figure(fig, root, "3d_trajectories")


def write_table(
    root: Path,
    uav_rows: List[Dict[str, object]],
    methods: List[Dict[str, object]],
) -> None:
    analytic = []
    for profile in PROFILES:
        rows = [row for row in uav_rows if row["profile"] == profile]
        analytic.append(
            (
                profile,
                max(float(row["max_velocity"]) for row in rows if row["max_velocity_valid"])
                if any(row["max_velocity_valid"] for row in rows) else "N/A",
                max(
                    float(row["max_acceleration"])
                    for row in rows
                    if row["max_acceleration_valid"]
                )
                if any(row["max_acceleration_valid"] for row in rows) else "N/A",
                max(float(row["max_jerk"]) for row in rows if row["max_jerk_valid"])
                if any(row["max_jerk_valid"] for row in rows) else "N/A",
                max(
                    float(row["integrated_squared_jerk"])
                    for row in rows
                    if row["integrated_squared_jerk_valid"]
                )
                if any(row["integrated_squared_jerk_valid"] for row in rows) else "N/A",
            )
        )
    lines = [
        "# Experiment 05 Results",
        "",
        "## Analytic reference metrics (worst case across UAV paths)",
        "",
        "| Profile | Max velocity | Max acceleration | Max jerk | Integrated squared jerk |",
        "| --- | ---: | ---: | ---: | ---: |",
    ]
    for row in analytic:
        values = [
            f"{value:.6f}" if isinstance(value, float) else value
            for value in row[1:]
        ]
        lines.append(f"| {row[0]} | {' | '.join(values)} |")
    lines.extend(
        [
            "",
            "N/A denotes a distributional boundary derivative, not a finite physical value.",
            "",
            "## Closed-loop metrics",
            "",
            "| Profile | Successful | Sync (s) | Final error (m) | Tracking RMSE (m) |",
            "| --- | ---: | ---: | ---: | ---: |",
        ]
    )
    for row in methods:
        lines.append(
            f"| {row['profile']} | {row['successful_trials']}/{row['trials']} | "
            f"{float(row['synchronization_error_mean_s']):.4f} | "
            f"{float(row['final_position_error_mean_m']):.4f} | "
            f"{float(row['tracking_rmse_mean_m']):.4f} |"
        )
    (root / "table_trajectory_comparison.md").write_text(
        "\n".join(lines) + "\n", encoding="utf-8"
    )


def write_manifest(root: Path) -> None:
    files = sorted(
        path for path in root.iterdir()
        if path.is_file() and path.name != "analysis_manifest.json"
    )
    manifest = {
        "files": [
            {
                "path": path.name,
                "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                "size_bytes": path.stat().st_size,
            }
            for path in files
        ]
    }
    (root / "analysis_manifest.json").write_text(
        json.dumps(manifest, indent=2), encoding="utf-8"
    )


def main() -> int:
    args = parse_args()
    root = Path(args.input_dir)
    trial_dirs = sorted(path for path in (root / "trials").iterdir() if path.is_dir())
    if len(trial_dirs) != 12:
        raise RuntimeError(f"expected 12 trial directories, found {len(trial_dirs)}")
    all_uav_rows = []
    all_timeseries = []
    for trial_dir in trial_dirs:
        uav_rows, timeseries = analyze_trial(trial_dir, not args.skip_bag_export)
        all_uav_rows.extend(uav_rows)
        all_timeseries.extend(timeseries)
    trial_summary = build_trial_summary(all_uav_rows)
    method_summary = build_method_summary(trial_summary)
    write_csv(root / "uav_trial_summary.csv", all_uav_rows)
    write_csv(root / "trajectory_timeseries.csv", all_timeseries)
    write_csv(root / "trial_summary.csv", trial_summary)
    write_csv(root / "method_summary.csv", method_summary)
    plot_reference_profiles(all_timeseries, root)
    plot_closed_loop(method_summary, root)
    plot_smoothness(all_uav_rows, root)
    plot_3d(all_timeseries, root)
    write_table(root, all_uav_rows, method_summary)
    write_manifest(root)
    print(f"Analyzed {len(trial_dirs)} trials and {len(all_uav_rows)} UAV outcomes")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
