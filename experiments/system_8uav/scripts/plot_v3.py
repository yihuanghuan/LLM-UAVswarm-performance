#!/usr/bin/env python3
"""Generate experiment-10 v3 success-filtered PNG and PDF figures."""

from __future__ import annotations

import argparse
import csv
import math
from collections import defaultdict
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402


TASKS = [
    "task_a_simple", "task_b_sequential", "task_c_grouped",
    "task_d_dense", "task_e_mixed",
]


def rows(path: Path):
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def value(row, key):
    try:
        result = float(row[key])
        return result if math.isfinite(result) else math.nan
    except (KeyError, TypeError, ValueError):
        return math.nan


def save(fig, root: Path, name: str):
    fig.tight_layout()
    fig.savefig(root / f"{name}.png", dpi=180)
    fig.savefig(root / f"{name}.pdf")
    plt.close(fig)


def boxplot(root, data, metric, name, ylabel):
    groups = [
        [sample for row in data if row["task_type"] == task
         and math.isfinite(sample := value(row, metric))]
        for task in TASKS
    ]
    fig, ax = plt.subplots(figsize=(8, 4.5))
    ax.boxplot(groups, tick_labels=["A", "B", "C", "D", "E"])
    ax.set(xlabel="Task", ylabel=ylabel)
    ax.grid(axis="y", alpha=.25)
    save(fig, root, name)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("batch_root", type=Path)
    parser.add_argument("--summaries-dir")
    parser.add_argument("--figures-dir")
    args = parser.parse_args()
    batch = args.batch_root.resolve()
    summaries = (
        Path(args.summaries_dir).resolve() if args.summaries_dir
        else batch / "summaries")
    figures = (
        Path(args.figures_dir).resolve() if args.figures_dir
        else batch / "figures")
    figures.mkdir(parents=True, exist_ok=True)

    attempts = rows(summaries / "attempt_summary.csv")
    mission = rows(summaries / "mission_timing_summary.csv")
    stage = rows(summaries / "stage_phase_timing.csv")
    readiness = rows(summaries / "readiness_summary.csv")
    semantic = rows(summaries / "semantic_summary.csv")
    outlier = rows(summaries / "outlier_summary.csv")
    eligible_attempts = {
        row["attempt_id"] for row in mission
        if row["main_analysis_eligible"].lower() == "true"}
    eligible_mission = [
        row for row in mission if row["attempt_id"] in eligible_attempts]
    eligible_stage = [
        row for row in stage if row["attempt_id"] in eligible_attempts
        and row["valid"].lower() == "true"]

    boxplot(figures, eligible_mission, "mission_wall_time",
            "mission_wall_time_boxplot", "Wall time (s)")
    boxplot(figures, eligible_stage, "trajectory_finish_spread",
            "trajectory_finish_spread_boxplot", "Spread (s)")
    boxplot(figures, eligible_stage, "stable_arrival_spread",
            "stable_arrival_spread_boxplot", "Spread (s)")

    phase = defaultdict(lambda: [[], []])
    for row in eligible_stage:
        for index, metric in enumerate(
                ("reference_execution_time", "stabilization_delay")):
            sample = value(row, metric)
            if math.isfinite(sample):
                phase[row["task_type"]][index].append(sample)
    reference = [
        sum(phase[task][0]) / len(phase[task][0]) if phase[task][0] else 0
        for task in TASKS]
    stabilization = [
        sum(phase[task][1]) / len(phase[task][1]) if phase[task][1] else 0
        for task in TASKS]
    fig, ax = plt.subplots(figsize=(8, 4.5))
    x = range(5)
    ax.bar(x, reference, label="Reference execution")
    ax.bar(x, stabilization, bottom=reference, label="Stabilization")
    ax.set_xticks(list(x), ["A", "B", "C", "D", "E"])
    ax.set_ylabel("Mean eligible-stage time (s)")
    ax.legend()
    save(fig, figures, "phase_time_decomposition")

    readiness_failures = defaultdict(int)
    for row in readiness:
        if row["readiness_success"].lower() != "true":
            readiness_failures[row["condition"] or "unknown"] += 1
    fig, ax = plt.subplots(figsize=(8, 4.5))
    if readiness_failures:
        ax.bar(list(readiness_failures), list(readiness_failures.values()))
        ax.tick_params(axis="x", rotation=25)
        ax.set_ylabel("Attempts")
    else:
        ax.text(.5, .5, f"No readiness failures ({len(attempts)}/{len(attempts)} passed)",
                ha="center", va="center", transform=ax.transAxes, fontsize=14)
        ax.set_axis_off()
    save(fig, figures, "readiness_failure_classification")

    failure_counts = defaultdict(int)
    for row in attempts:
        if row["failure_reason"] in {
            "dispatch_timeout", "reference_finish_timeout",
                "stabilization_timeout", "stage_data_stale"}:
            failure_counts[(row["task_type"], row["failure_reason"])] += 1
    fig, ax = plt.subplots(figsize=(9, 4.5))
    bottoms = [0] * 5
    for reason in (
        "dispatch_timeout", "reference_finish_timeout",
            "stabilization_timeout", "stage_data_stale"):
        values = [failure_counts[(task, reason)] for task in TASKS]
        ax.bar(range(5), values, bottom=bottoms, label=reason)
        bottoms = [a + b for a, b in zip(bottoms, values)]
    ax.set_xticks(range(5), ["A", "B", "C", "D", "E"])
    ax.set_ylabel("Attempts")
    ax.legend()
    save(fig, figures, "stage_timeout_classification")

    latency, success = defaultdict(list), defaultdict(list)
    for row in semantic:
        success[row["task_type"]].append(row["semantic_valid"].lower() == "true")
        sample = value(row, "latency_ms")
        if row["llm_called"].lower() == "true" and math.isfinite(sample):
            latency[row["task_type"]].append(sample)
    fig, axes = plt.subplots(1, 2, figsize=(10, 4.5))
    axes[0].bar(range(5), [
        sum(success[t]) / len(success[t]) if success[t] else 0 for t in TASKS])
    axes[0].set_xticks(range(5), ["A", "B", "C", "D", "E"])
    axes[0].set_ylabel("Semantic success fraction")
    axes[1].boxplot([latency[t] for t in TASKS], tick_labels=["A", "B", "C", "D", "E"])
    axes[1].set_ylabel("LLM latency (ms; replay excluded)")
    save(fig, figures, "llm_parsing_success_latency")

    flagged = sorted({
        row["attempt_id"] for row in outlier
        if row["is_outlier"].lower() == "true"})
    labels = flagged or ["none"]
    fig, ax = plt.subplots(figsize=(9, 4.5))
    bottom = [0] * len(labels)
    for metric, label in (
        ("planning_time", "Planning"),
        ("reference_execution_time", "Reference execution"),
            ("stabilization_delay", "Stabilization")):
        values = [sum(
            value(row, metric) for row in eligible_stage
            if row["attempt_id"] == attempt and math.isfinite(value(row, metric)))
            for attempt in flagged] or [0]
        ax.bar(labels, values, bottom=bottom, label=label)
        bottom = [a + b for a, b in zip(bottom, values)]
    ax.tick_params(axis="x", rotation=70)
    ax.set_ylabel("Stage time (s)")
    ax.legend()
    save(fig, figures, "outlier_phase_decomposition")

    for task, name in (
        ("task_d_dense", "task_d_safety_iapf"),
        ("task_e_mixed", "task_e_success_timeline"),
    ):
        candidates = [
            row for row in attempts if row["task_type"] == task
            and row["attempt_id"] in eligible_attempts]
        fig, ax = plt.subplots(figsize=(9, 4.5))
        if task == "task_d_dense" and candidates:
            data = rows(Path(candidates[0]["path"]) / "iapf_debug.csv")
            by_time, active = defaultdict(list), defaultdict(list)
            for row in data:
                timestamp = round(value(row, "timestamp"), 1)
                distance = value(row, "nearest_neighbor_distance")
                if math.isfinite(timestamp) and math.isfinite(distance):
                    by_time[timestamp].append(distance)
                    active[timestamp].append(row["iapf_active"].lower() == "true")
            times = sorted(by_time)
            ax.plot(times, [min(by_time[t]) for t in times], label="Minimum distance")
            ax.axhline(1.0, color="r", linestyle="--", label="Violation")
            ax.axhline(1.5, color="orange", linestyle=":", label="IAPF enter")
            active_ax = ax.twinx()
            active_ax.step(times, [int(any(active[t])) for t in times],
                           where="post", color="tab:green", alpha=.55, label="IAPF active")
            active_ax.set_yticks([0, 1], ["inactive", "active"])
            handles, labels_ = ax.get_legend_handles_labels()
            extra, extra_labels = active_ax.get_legend_handles_labels()
            ax.legend(handles + extra, labels_ + extra_labels)
            ax.set_ylabel("Distance (m)")
        elif candidates:
            selected = candidates[0]
            timeline = [
                row for row in eligible_stage
                if row["attempt_id"] == selected["attempt_id"]]
            for index, row in enumerate(timeline):
                ax.barh(index, value(row, "stage_wall_time"),
                        left=value(row, "stage_start_time"))
            ax.set_yticks(range(len(timeline)), [
                f"Stage {row['stage_id']}" for row in timeline])
            ax.set_xlabel("Attempt-relative time (s)")
        else:
            ax.text(.5, .5, "No eligible trial", ha="center", va="center",
                    transform=ax.transAxes)
            ax.set_axis_off()
        save(fig, figures, name)
    print(f"generated v3 figures in {figures}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
