#!/usr/bin/env python3
"""Generate all required PNG/PDF figures for experiment 10."""

from __future__ import annotations

import argparse
import math
from collections import defaultdict
from pathlib import Path
from typing import Dict, List, Sequence

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

from summarize_system_trials import distance_series, number  # noqa: E402
from system_common import (  # noqa: E402
    CONFIG_PATH, REPO_ROOT, TASK_NAMES, load_yaml, read_csv,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--batch-id", required=True)
    parser.add_argument("--config", default=str(CONFIG_PATH))
    parser.add_argument("--results-root")
    return parser.parse_args()


def save(fig: plt.Figure, root: Path, name: str) -> None:
    root.mkdir(parents=True, exist_ok=True)
    for suffix in ("png", "pdf"):
        fig.savefig(root / f"{name}.{suffix}", dpi=180, bbox_inches="tight")
    plt.close(fig)


def representative_trial(batch_root: Path, task: str) -> Path:
    summary = read_csv(batch_root / "summaries" / "system_trial_summary.csv")
    candidates = [row for row in summary if row["task_type"] == task]
    if not candidates:
        raise ValueError(f"no summary rows for {task}")
    successful = [
        row for row in candidates
        if row["overall_success"].strip().lower() in {"true", "1"}]
    row = (successful or candidates)[0]
    path = batch_root / "raw" / task / f"trial_{int(row['trial_id']):02d}"
    if not path.is_dir():
        raise FileNotFoundError(f"representative trial is missing: {path}")
    return path


def trajectory_plot(trial_dir: Path, figures: Path, task: str) -> None:
    rows = read_csv(trial_dir / "odom.csv")
    by_uav: Dict[int, List[dict]] = defaultdict(list)
    for row in rows:
        by_uav[int(float(row["uav_id"]))].append(row)
    if len(by_uav) != 8:
        raise ValueError(f"{trial_dir}: expected 8 UAV trajectories")
    fig = plt.figure(figsize=(8, 6))
    axis = fig.add_subplot(111, projection="3d")
    for uid in sorted(by_uav):
        samples = sorted(by_uav[uid], key=lambda row: number(row, "timestamp"))
        axis.plot(
            [number(row, "x") for row in samples],
            [number(row, "y") for row in samples],
            [number(row, "z") for row in samples],
            linewidth=1.2, label=f"UAV{uid}")
    axis.set_xlabel("X (m)")
    axis.set_ylabel("Y (m)")
    axis.set_zlabel("Z (m)")
    axis.set_title(f"Representative 3D trajectory: {task}")
    axis.legend(ncol=2, fontsize="small")
    save(fig, figures, f"trajectory_3d_{task}")


def mixed_timeline(trial_dir: Path, figures: Path) -> None:
    rows = read_csv(trial_dir / "mission_events.csv")
    starts = {
        int(number(row, "stage_id")): number(row, "timestamp")
        for row in rows if row["event"] == "stage_start"}
    ends = {
        int(number(row, "stage_id")): number(row, "timestamp")
        for row in rows if row["event"] == "stage_end"}
    if set(starts) != {1, 2, 3} or set(ends) != {1, 2, 3}:
        raise ValueError("mixed task timeline does not contain all three stages")
    fig, axis = plt.subplots(figsize=(9, 3.8))
    for index, stage in enumerate((1, 2, 3)):
        axis.barh(
            index, ends[stage] - starts[stage], left=starts[stage],
            height=0.55, color=("#4c78a8", "#f58518", "#54a24b")[index])
    axis.set_yticks([0, 1, 2], ["Parallel formation", "Region exchange", "Merge"])
    axis.set_xlabel("Trial time (s)")
    axis.set_title("Task E multi-stage execution timeline")
    axis.grid(axis="x", alpha=0.25)
    save(fig, figures, "mixed_task_timeline")


def dense_safety(trial_dir: Path, figures: Path, config: dict) -> None:
    odom = read_csv(trial_dir / "odom.csv")
    iapf = read_csv(trial_dir / "iapf_debug.csv")
    distances = distance_series(odom)
    if not distances or not iapf:
        raise ValueError("dense task lacks distance or IAPF data")
    bins: Dict[float, int] = defaultdict(int)
    for row in iapf:
        if str(row["iapf_active"]).lower() in {"true", "1"}:
            bins[round(number(row, "timestamp"), 1)] += 1
    fig, axes = plt.subplots(2, 1, figsize=(9, 6), sharex=True)
    axes[0].plot(
        [row[0] for row in distances], [row[1] for row in distances],
        color="#4c78a8", linewidth=1.4)
    axes[0].axhline(
        float(config["safety"]["violation_distance"]), color="#e45756",
        linestyle="--", label="violation")
    axes[0].axhline(
        float(config["safety"]["iapf_enter_distance"]), color="#f58518",
        linestyle=":", label="IAPF enter")
    axes[0].set_ylabel("Minimum distance (m)")
    axes[0].legend()
    axes[0].grid(alpha=0.25)
    axes[1].step(sorted(bins), [bins[key] for key in sorted(bins)], where="post")
    axes[1].set_ylabel("Active UAV count")
    axes[1].set_xlabel("Trial time (s)")
    axes[1].set_ylim(-0.2, 8.5)
    axes[1].grid(alpha=0.25)
    fig.suptitle("Task D minimum distance and IAPF activity")
    save(fig, figures, "dense_task_safety_iapf")


def boxplot(
    rows: Sequence[dict], field: str, ylabel: str, figures: Path, name: str,
) -> None:
    values = []
    labels = []
    for task in TASK_NAMES:
        samples = [
            number(row, field) for row in rows if row["task_type"] == task
            and math.isfinite(number(row, field))]
        if not samples:
            raise ValueError(f"no finite {field} samples for {task}")
        values.append(samples)
        labels.append(task.replace("task_", "").split("_")[0].upper())
    fig, axis = plt.subplots(figsize=(8, 4.8))
    axis.boxplot(values, labels=labels, showmeans=True)
    axis.set_xlabel("Task")
    axis.set_ylabel(ylabel)
    axis.set_title(ylabel + " by task")
    axis.grid(axis="y", alpha=0.25)
    save(fig, figures, name)


def main() -> int:
    args = parse_args()
    config = load_yaml(Path(args.config).resolve())
    results_root = Path(args.results_root).resolve() if args.results_root else (
        REPO_ROOT / config["paths"]["results_root"]).resolve()
    batch_root = results_root / args.batch_id
    figures = batch_root / "figures"
    for task in TASK_NAMES:
        trajectory_plot(representative_trial(batch_root, task), figures, task)
    mixed_timeline(
        representative_trial(batch_root, "task_e_mixed"), figures)
    dense_safety(
        representative_trial(batch_root, "task_d_dense"), figures, config)
    rows = read_csv(batch_root / "summaries" / "system_trial_summary.csv")
    boxplot(rows, "completion_time", "Completion time (s)", figures,
            "completion_time_boxplot")
    boxplot(rows, "tracking_rmse", "Controller tracking RMSE (m)", figures,
            "tracking_rmse_boxplot")
    boxplot(rows, "min_distance", "Minimum inter-agent distance (m)", figures,
            "minimum_distance_boxplot")
    boxplot(rows, "arrival_spread", "Arrival spread (s)", figures,
            "arrival_spread_boxplot")
    print(f"generated required figures in {figures}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
