#!/usr/bin/env python3
"""Generate the required experiment 08 publication figures."""

from __future__ import annotations

import argparse
import csv
import json
from itertools import combinations
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from analysis_core import resample_odometry


METHODS = [f"M{value}" for value in range(6)]
REPRESENTATIVE_TRIAL = 1


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def representative_trial(
    batch_dir: Path, scenario: str, method: str
) -> Path:
    candidates = [
        path for path in sorted(
            (batch_dir / "raw" / scenario / method).glob(
                f"trial_{REPRESENTATIVE_TRIAL:02d}_seed_*"))
        if json.loads(
            (path / "run_metadata.json").read_text(encoding="utf-8")
        ).get("phase") == "main"
    ]
    if len(candidates) != 1:
        raise FileNotFoundError(
            f"expected one representative trial for {scenario}/{method}, "
            f"found {len(candidates)}")
    return candidates[0]


def resampled_trial(
    trial_dir: Path,
) -> tuple[np.ndarray, dict[int, np.ndarray], dict[str, object]]:
    metadata = json.loads(
        (trial_dir / "run_metadata.json").read_text(encoding="utf-8"))
    analysis = metadata["analysis"]
    timeline, positions = resample_odometry(
        read_csv(trial_dir / "odom.csv"),
        float(analysis["sample_hz"]),
        float(analysis["max_odom_gap"]),
    )
    return timeline, positions, metadata


def minimum_distance_series(
    positions: dict[int, np.ndarray],
) -> tuple[np.ndarray, tuple[int, int], int]:
    series = {
        pair: np.linalg.norm(positions[pair[0]] - positions[pair[1]], axis=1)
        for pair in combinations(sorted(positions), 2)
    }
    stacked = np.stack(list(series.values()))
    flat_index = int(np.argmin(stacked))
    pair_index, time_index = np.unravel_index(flat_index, stacked.shape)
    closest_pair = list(series)[pair_index]
    return np.min(stacked, axis=0), closest_pair, int(time_index)


def active_mask(trial_dir: Path, timeline: np.ndarray) -> np.ndarray:
    rows = read_csv(trial_dir / "iapf_debug.csv")
    by_time: dict[float, bool] = {}
    for row in rows:
        timestamp = float(row["timestamp"])
        active = row["iapf_active"].strip().lower() in ("1", "true", "yes")
        by_time[timestamp] = by_time.get(timestamp, False) or active
    if not by_time:
        return np.zeros(len(timeline), dtype=bool)
    times = np.asarray(sorted(by_time))
    states = np.asarray([by_time[value] for value in times], dtype=float)
    indices = np.searchsorted(times, timeline, side="left")
    indices = np.clip(indices, 0, len(times) - 1)
    previous = np.clip(indices - 1, 0, len(times) - 1)
    choose_previous = (
        np.abs(timeline - times[previous]) <= np.abs(times[indices] - timeline))
    indices[choose_previous] = previous[choose_previous]
    return states[indices].astype(bool)


def save(fig, directory: Path, name: str) -> None:
    fig.tight_layout()
    for extension in ("png", "pdf"):
        fig.savefig(directory / f"{name}.{extension}", dpi=220)
    plt.close(fig)


def boxplot(data: pd.DataFrame, metric: str, ylabel: str, directory: Path) -> None:
    scenarios = sorted(data["scenario"].unique())
    fig, axes = plt.subplots(
        1, len(scenarios), figsize=(5 * len(scenarios), 4), squeeze=False)
    for axis, scenario in zip(axes[0], scenarios):
        subset = data[data["scenario"] == scenario]
        values = [
            subset[subset["method"] == method][metric].dropna()
            for method in METHODS]
        axis.boxplot(values, labels=METHODS, showfliers=True)
        axis.set_title(scenario)
        axis.set_ylabel(ylabel)
        axis.grid(alpha=0.25)
    save(fig, directory, f"{metric}_distribution")


def plot_distance_timeseries(batch_dir: Path, directory: Path) -> None:
    methods = ["M0", "M1", "M2", "M3"]
    fig, axes = plt.subplots(
        len(methods), 1, figsize=(9, 10), sharex=True, sharey=True)
    threshold_styles = {
        "r_iapf": ("tab:blue", "--"),
        "d_violation": ("tab:orange", "--"),
        "d_collision": ("tab:red", ":"),
    }
    for axis, method in zip(axes, methods):
        trial_dir = representative_trial(batch_dir, "head_on", method)
        timeline, positions, metadata = resampled_trial(trial_dir)
        distance, _, _ = minimum_distance_series(positions)
        relative_time = timeline - timeline[0]
        axis.plot(relative_time, distance, color="black", linewidth=1.5)
        thresholds = metadata["safety_thresholds"]
        for name, (color, style) in threshold_styles.items():
            axis.axhline(
                float(thresholds[name]), color=color, linestyle=style,
                linewidth=1.0, label=name)
        active = active_mask(trial_dir, timeline)
        axis.fill_between(
            relative_time, 0.0, 1.0, where=active,
            transform=axis.get_xaxis_transform(), color="tab:green",
            alpha=0.14, label="IAPF active")
        axis.set_ylabel(f"{method}\ndistance (m)")
        axis.grid(alpha=0.25)
    axes[0].legend(ncol=4, fontsize=8, loc="upper right")
    axes[-1].set_xlabel("Time from first common odometry sample (s)")
    save(fig, directory, "head_on_distance_timeseries")


def plot_representative_trajectories(
    batch_dir: Path, scenarios: list[str], directory: Path
) -> None:
    fig = plt.figure(figsize=(13, 11))
    for panel, scenario in enumerate(scenarios, start=1):
        axis = fig.add_subplot(2, 2, panel, projection="3d")
        trial_dir = representative_trial(batch_dir, scenario, "M3")
        _, positions, _ = resampled_trial(trial_dir)
        _, closest_pair, closest_index = minimum_distance_series(positions)
        debug = pd.read_csv(trial_dir / "iapf_debug.csv")
        assignment = pd.read_csv(trial_dir / "assignment.csv")
        colors = plt.get_cmap("tab10")

        for color_index, uav_id in enumerate(sorted(positions)):
            color = colors(color_index % 10)
            actual = positions[uav_id]
            axis.plot(
                actual[:, 0], actual[:, 1], actual[:, 2],
                color=color, linewidth=1.4,
                label=f"UAV {uav_id}" if panel == 1 else None)
            nominal_rows = debug[debug["uav_id"] == uav_id].sort_values(
                "timestamp")
            if not nominal_rows.empty:
                nominal = nominal_rows[
                    ["nominal_ref_x", "nominal_ref_y", "nominal_ref_z"]
                ].to_numpy(dtype=float)
                axis.plot(
                    nominal[:, 0], nominal[:, 1], nominal[:, 2],
                    color=color, linestyle="--", linewidth=0.9, alpha=0.7)
            assigned = assignment[assignment["uav_id"] == uav_id]
            if not assigned.empty:
                row = assigned.iloc[0]
                axis.scatter(
                    row["initial_x"], row["initial_y"], row["initial_z"],
                    color=color, marker="o", s=20)
                axis.scatter(
                    row["target_x"], row["target_y"], row["target_z"],
                    color=color, marker="*", s=55)

        for uav_id in closest_pair:
            point = positions[uav_id][closest_index]
            axis.scatter(
                point[0], point[1], point[2], color="black", marker="x",
                s=45, linewidth=1.6)
        axis.set_title(f"{scenario} (M3, trial {REPRESENTATIVE_TRIAL})")
        axis.set_xlabel("x (m)")
        axis.set_ylabel("y (m)")
        axis.set_zlabel("z (m)")
        axis.grid(alpha=0.25)

    fig.text(
        0.5, 0.01,
        "Solid: actual; dashed: nominal; circle: start; star: target; "
        "black x: closest approach",
        ha="center", fontsize=9)
    save(fig, directory, "representative_3d_trajectories")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("batch_dir", type=Path)
    args = parser.parse_args()
    summary_path = args.batch_dir / "summaries" / "trial_summary.csv"
    data = pd.read_csv(summary_path)
    main_data = data[
        (data["phase"] == "main") & data["method"].isin(METHODS)]
    figure_dir = args.batch_dir / "figures"
    figure_dir.mkdir(parents=True, exist_ok=True)

    plot_distance_timeseries(args.batch_dir, figure_dir)
    boxplot(
        main_data, "minimum_inter_agent_distance",
        "Minimum inter-agent distance (m)", figure_dir)
    boxplot(main_data, "risk_integral", "Risk integral", figure_dir)

    fig, axis = plt.subplots(figsize=(7, 5))
    for method in METHODS:
        subset = main_data[main_data["method"] == method]
        axis.scatter(
            subset["mean_trajectory_deviation"], subset["risk_integral"],
            label=method, alpha=0.75)
    axis.set_xlabel("Mean trajectory deviation (m)")
    axis.set_ylabel("Risk integral")
    axis.legend()
    axis.grid(alpha=0.25)
    save(fig, figure_dir, "safety_efficiency_tradeoff")

    burden = main_data[main_data["method"].isin(["M3", "M5"])]
    fig, axes = plt.subplots(1, 3, figsize=(12, 4))
    for axis, metric, title in zip(
        axes,
        ["iapf_activation_ratio", "mean_repulsion_norm", "recovery_time"],
        ["Activation ratio", "Mean repulsion", "Recovery time"],
    ):
        values = [
            burden[burden["method"] == method][metric].dropna()
            for method in ["M3", "M5"]]
        axis.boxplot(values, labels=["M3", "M5"])
        axis.set_title(title)
        axis.grid(alpha=0.25)
    save(fig, figure_dir, "local_intervention_burden")

    plot_representative_trajectories(
        args.batch_dir, sorted(main_data["scenario"].unique()), figure_dir)

    table = main_data.groupby("method").agg(
        success_rate=("mission_success", "mean"),
        min_distance=("minimum_inter_agent_distance", "median"),
        violation_events=("violation_event_count", "median"),
        risk_integral=("risk_integral", "median"),
        deviation=("mean_trajectory_deviation", "median"),
        recovery_time=("recovery_time", "median"),
        activation_ratio=("iapf_activation_ratio", "median"),
    ).reset_index()
    table.to_csv(args.batch_dir / "summaries" / "paper_summary_table.csv", index=False)
    print(figure_dir)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
