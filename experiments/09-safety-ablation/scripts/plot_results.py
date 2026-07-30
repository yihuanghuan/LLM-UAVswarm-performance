#!/usr/bin/env python3
"""Generate the pre-registered experiment 09 tables and figures."""

from __future__ import annotations

import argparse
import csv
from itertools import combinations
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from analysis_core import resample_odometry


VARIANTS = ["B0", "P", "E", "Full"]
COLORS = dict(B0="#777777", P="#4c78a8", E="#f58518", Full="#54a24b")


def save(fig, directory: Path, name: str) -> None:
    fig.tight_layout()
    for extension in ("png", "pdf"):
        fig.savefig(directory / f"{name}.{extension}", dpi=220)
    plt.close(fig)


def trial_dir(batch_dir: Path, scenario: str, variant: str) -> Path:
    candidates = sorted(
        (batch_dir / "raw" / scenario / variant).glob(
            "trial_*_seed_4201"))
    if len(candidates) != 1:
        raise FileNotFoundError(
            f"expected one representative trial for {scenario}/{variant}")
    return candidates[0]


def read_rows(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def ablation_table(data: pd.DataFrame, output: Path) -> None:
    metrics = [
        "mission_success", "safety_success", "actual_min_distance",
        "violation_count", "tracking_rmse", "mission_duration"]
    rows = []
    for (scenario, variant), group in data.groupby(["scenario", "variant"]):
        row = {"scenario": scenario, "variant": variant, "n": len(group)}
        for metric in metrics:
            values = pd.to_numeric(group[metric], errors="coerce")
            row[f"{metric}_mean"] = values.mean()
            row[f"{metric}_std"] = values.std(ddof=1)
        rows.append(row)
    pd.DataFrame(rows).to_csv(output, index=False)


def interaction_plot(data: pd.DataFrame, directory: Path) -> None:
    metrics = [
        ("actual_min_distance", "Minimum distance (m)"),
        ("mission_success", "Mission success"),
        ("tracking_rmse", "Tracking RMSE (m)"),
        ("mission_duration", "Mission duration (s)"),
    ]
    scenarios = sorted(data["scenario"].unique())
    fig, axes = plt.subplots(
        len(scenarios), len(metrics), figsize=(15, 3.3 * len(scenarios)),
        squeeze=False)
    for row, scenario in enumerate(scenarios):
        subset = data[data["scenario"] == scenario]
        for column, (metric, ylabel) in enumerate(metrics):
            axis = axes[row, column]
            for avoidance, variants, color in [
                ("off", ["B0", "P"], "#4c78a8"),
                ("iapf_dual", ["E", "Full"], "#f58518"),
            ]:
                means = [
                    pd.to_numeric(
                        subset[subset["variant"] == variant][metric],
                        errors="coerce").mean()
                    for variant in variants]
                axis.plot(
                    [0, 1], means, marker="o", label=avoidance, color=color)
            axis.set_xticks([0, 1], ["distance", "safety-aware"])
            axis.set_ylabel(ylabel)
            axis.set_title(scenario)
            axis.grid(alpha=0.25)
    axes[0, -1].legend(fontsize=8)
    save(fig, directory, "factorial_interaction")


def burden_plot(data: pd.DataFrame, directory: Path) -> None:
    metrics = [
        ("iapf_active_duration", "Active UAV-seconds"),
        ("max_position_offset", "Max position offset (m)"),
        ("max_acceleration_offset", "Max acceleration offset (m/s²)"),
        ("trajectory_deviation", "Trajectory deviation (m)"),
    ]
    scenarios = sorted(data["scenario"].unique())
    fig, axes = plt.subplots(2, 2, figsize=(12, 8))
    for axis, (metric, ylabel) in zip(axes.flat, metrics):
        positions, values, labels = [], [], []
        cursor = 1
        for scenario in scenarios:
            for variant in ("E", "Full"):
                values.append(pd.to_numeric(
                    data[(data["scenario"] == scenario)
                         & (data["variant"] == variant)][metric],
                    errors="coerce").dropna())
                positions.append(cursor)
                labels.append(f"{scenario}\n{variant}")
                cursor += 1
            cursor += 0.5
        boxes = axis.boxplot(values, positions=positions, patch_artist=True)
        for box, label in zip(boxes["boxes"], labels):
            box.set_facecolor(COLORS[label.rsplit("\n", 1)[-1]])
        axis.set_xticks(positions, labels, rotation=30, ha="right", fontsize=7)
        axis.set_ylabel(ylabel)
        axis.grid(alpha=0.25)
    save(fig, directory, "iapf_burden_e_vs_full")


def trajectory_plot(batch_dir: Path, directory: Path) -> None:
    scenarios = sorted(path.name for path in (batch_dir / "raw").iterdir())
    fig = plt.figure(figsize=(16, 4 * len(scenarios)))
    for row, scenario in enumerate(scenarios):
        for column, variant in enumerate(VARIANTS):
            axis = fig.add_subplot(
                len(scenarios), len(VARIANTS), row * len(VARIANTS) + column + 1,
                projection="3d")
            frame = pd.read_csv(trial_dir(batch_dir, scenario, variant) / "odom.csv")
            for uav_id, group in frame.groupby("uav_id"):
                axis.plot(group["x"], group["y"], group["z"], label=f"UAV{uav_id}")
            axis.set_title(f"{scenario} / {variant}")
            axis.set_xlabel("x")
            axis.set_ylabel("y")
            axis.set_zlabel("z")
    save(fig, directory, "representative_3d_trajectories")


def distance_activation_plot(batch_dir: Path, directory: Path) -> None:
    scenario = "s3_staggered_dynamic_crossing"
    fig, axes = plt.subplots(4, 1, figsize=(11, 12), sharex=True)
    for axis, variant in zip(axes, VARIANTS):
        directory_trial = trial_dir(batch_dir, scenario, variant)
        rows = read_rows(directory_trial / "odom.csv")
        timeline, positions = resample_odometry(rows, 20.0, 0.25)
        pair_series = [
            np.linalg.norm(positions[a] - positions[b], axis=1)
            for a, b in combinations(sorted(positions), 2)]
        minimum = np.min(np.stack(pair_series), axis=0)
        relative = timeline - timeline[0]
        axis.plot(relative, minimum, color="black", label="minimum distance")
        debug = pd.read_csv(directory_trial / "iapf_debug.csv")
        active = debug.groupby("timestamp")["iapf_active"].max()
        active_t = active.index.to_numpy(dtype=float) - timeline[0]
        axis.fill_between(
            active_t, 0.0, 1.5, where=active.astype(bool).to_numpy(),
            alpha=0.2, color=COLORS[variant], label="IAPF active")
        axis.axhline(1.5, color="#4c78a8", linestyle="--", label="r_iapf")
        axis.axhline(1.0, color="#f58518", linestyle="--", label="violation")
        axis.axhline(0.7, color="#e45756", linestyle="--", label="collision")
        axis.set_ylabel(f"{variant}\ndistance (m)")
        axis.grid(alpha=0.25)
    axes[0].legend(ncol=5, fontsize=8)
    axes[-1].set_xlabel("Mission time (s)")
    save(fig, directory, "pairwise_distance_and_iapf_activation")


def failure_plot(data: pd.DataFrame, directory: Path) -> None:
    counts = data.groupby(["variant", "failure_reason"]).size().unstack(fill_value=0)
    counts = counts.reindex(VARIANTS)
    fig, axis = plt.subplots(figsize=(8, 4.5))
    counts.plot(kind="bar", stacked=True, ax=axis)
    axis.set_ylabel("Trials")
    axis.set_xlabel("Variant")
    axis.legend(title="Failure reason", fontsize=8)
    axis.grid(axis="y", alpha=0.25)
    save(fig, directory, "failure_reasons")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("batch_dir", type=Path)
    args = parser.parse_args()
    data = pd.read_csv(args.batch_dir / "summaries" / "trial_summary.csv")
    data = data[data["phase"] == "formal"].copy()
    figure_dir = args.batch_dir / "figures"
    figure_dir.mkdir(parents=True, exist_ok=True)
    ablation_table(data, args.batch_dir / "summaries" / "main_ablation_table.csv")
    interaction_plot(data, figure_dir)
    burden_plot(data, figure_dir)
    trajectory_plot(args.batch_dir, figure_dir)
    distance_activation_plot(args.batch_dir, figure_dir)
    failure_plot(data, figure_dir)
    print(figure_dir)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
