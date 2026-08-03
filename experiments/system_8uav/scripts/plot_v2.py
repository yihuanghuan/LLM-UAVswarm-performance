#!/usr/bin/env python3
"""Generate the required experiment-10 v2 PNG and PDF figures."""

from __future__ import annotations

import argparse
import csv
import math
from collections import defaultdict
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

TASKS = [
    "task_a_simple", "task_b_sequential", "task_c_grouped",
    "task_d_dense", "task_e_mixed",
]


def rows(path):
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def value(row, key):
    try:
        return float(row[key])
    except (KeyError, TypeError, ValueError):
        return float("nan")


def save(fig, root, name):
    fig.tight_layout()
    fig.savefig(root / f"{name}.png", dpi=180)
    fig.savefig(root / f"{name}.pdf")
    plt.close(fig)


def boxplot(root, data, metric, name, ylabel):
    fig, ax = plt.subplots(figsize=(8, 4.5))
    groups = [
        [sample for row in data if row["task_type"] == task
         and math.isfinite(sample := value(row, metric))]
        for task in TASKS
    ]
    ax.boxplot(groups, tick_labels=["A", "B", "C", "D", "E"])
    ax.set(xlabel="Task", ylabel=ylabel)
    ax.grid(axis="y", alpha=.25)
    save(fig, root, name)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("batch_root", type=Path)
    args = parser.parse_args()
    batch = args.batch_root.resolve()
    summaries, figures = batch / "summaries", batch / "figures"
    figures.mkdir(parents=True, exist_ok=True)
    mission = rows(summaries / "mission_timing_summary.csv")
    stage = rows(summaries / "stage_phase_timing.csv")
    attempts = rows(summaries / "attempt_summary.csv")
    readiness = rows(summaries / "readiness_summary.csv")
    semantic = rows(summaries / "semantic_summary.csv")
    outliers = rows(summaries / "outlier_summary.csv")
    boxplot(figures, mission, "mission_wall_time", "mission_wall_time_boxplot", "Wall time (s)")
    boxplot(figures, stage, "trajectory_finish_spread", "trajectory_finish_spread_boxplot", "Spread (s)")
    boxplot(figures, stage, "stable_arrival_spread", "stable_arrival_spread_boxplot", "Spread (s)")

    totals = defaultdict(lambda: [[], []])
    for row in stage:
        reference = value(row, "reference_execution_time")
        stabilization = value(row, "stabilization_delay")
        if math.isfinite(reference):
            totals[row["task_type"]][0].append(reference)
        if math.isfinite(stabilization):
            totals[row["task_type"]][1].append(stabilization)
    fig, ax = plt.subplots(figsize=(8, 4.5))
    x = range(len(TASKS))
    ref = [sum(totals[t][0]) / len(totals[t][0]) if totals[t][0] else 0
           for t in TASKS]
    stable = [sum(totals[t][1]) / len(totals[t][1]) if totals[t][1] else 0
              for t in TASKS]
    ax.bar(x, ref, label="Reference execution")
    ax.bar(x, stable, bottom=ref, label="Stabilization")
    ax.set_xticks(list(x), ["A", "B", "C", "D", "E"])
    ax.set_ylabel("Mean stage time (s)")
    ax.legend()
    save(fig, figures, "phase_time_decomposition")

    failures = defaultdict(int)
    for row in readiness:
        if row["readiness_success"].lower() != "true":
            failures[row["condition"] or "unknown"] += 1
    fig, ax = plt.subplots(figsize=(8, 4.5))
    if failures:
        labels = list(failures)
        ax.bar(labels, [failures[k] for k in labels])
        ax.tick_params(axis="x", rotation=25)
        ax.set_ylabel("Attempts")
    else:
        ax.text(.5, .5, f"No readiness failures ({len(attempts)}/{len(attempts)} passed)",
                ha="center", va="center", transform=ax.transAxes, fontsize=14)
        ax.set_axis_off()
    save(fig, figures, "readiness_failure_classification")

    latency = defaultdict(list)
    success = defaultdict(list)
    for row in semantic:
        sample = value(row, "latency_ms")
        if math.isfinite(sample):
            latency[row["task_type"]].append(sample)
        success[row["task_type"]].append(row["semantic_valid"].lower() == "true")
    fig, axes = plt.subplots(1, 2, figsize=(10, 4.5))
    axes[0].bar(range(5), [sum(success[t]) / len(success[t]) if success[t] else 0 for t in TASKS])
    axes[0].set_xticks(range(5), ["A", "B", "C", "D", "E"])
    axes[0].set_ylabel("Semantic success fraction")
    axes[1].boxplot([latency[t] for t in TASKS], tick_labels=["A", "B", "C", "D", "E"])
    axes[1].set_ylabel("LLM latency (ms)")
    save(fig, figures, "llm_parsing_success_latency")

    flagged_attempts = sorted({
        row["attempt_id"] for row in outliers
        if row["is_outlier"].lower() == "true"
    })
    fig, ax = plt.subplots(figsize=(9, 4.5))
    labels = flagged_attempts or ["none"]
    phase_values = {
        phase: [
            sum(value(row, phase) for row in stage
                if row["attempt_id"] == attempt_id
                and math.isfinite(value(row, phase)))
            for attempt_id in flagged_attempts
        ] or [0]
        for phase in ("planning_time", "reference_execution_time",
                      "stabilization_delay")
    }
    bottom = [0] * len(labels)
    for phase, phase_label in (
        ("planning_time", "Planning"),
        ("reference_execution_time", "Reference execution"),
        ("stabilization_delay", "Stabilization"),
    ):
        ax.bar(labels, phase_values[phase], bottom=bottom, label=phase_label)
        bottom = [left + height for left, height in zip(bottom, phase_values[phase])]
    ax.tick_params(axis="x", rotation=70)
    ax.set_ylabel("Stage time (s)")
    ax.legend()
    save(fig, figures, "outlier_phase_decomposition")

    # Detailed Task D and E figures are generated directly from raw streams.
    for task, name in (("task_d_dense", "task_d_safety_iapf"),
                       ("task_e_mixed", "task_e_success_timeline")):
        task_attempts = [
            row for row in attempts if row["task_type"] == task
            and row["entered_execution"].lower() == "true"]
        fig, ax = plt.subplots(figsize=(9, 4.5))
        if task == "task_d_dense" and task_attempts:
            selected = next(
                (row for row in task_attempts
                 if row["overall_success"].lower() == "true"),
                task_attempts[0])
            raw = Path(selected["path"])
            data = rows(raw / "iapf_debug.csv")
            by_time = defaultdict(list)
            active_by_time = defaultdict(list)
            for row in data:
                timestamp = round(value(row, "timestamp"), 1)
                distance = value(row, "nearest_neighbor_distance")
                if math.isfinite(timestamp) and math.isfinite(distance):
                    by_time[timestamp].append(distance)
                if math.isfinite(timestamp):
                    active_by_time[timestamp].append(
                        row["iapf_active"].lower() == "true")
            times = sorted(by_time)
            ax.plot(times, [min(by_time[t]) for t in times], label="Minimum neighbor distance")
            ax.axhline(1.0, color="r", linestyle="--", label="Violation threshold")
            ax.axhline(1.5, color="orange", linestyle=":", label="IAPF enter")
            active_ax = ax.twinx()
            active_ax.step(
                times, [int(any(active_by_time[t])) for t in times],
                where="post", color="tab:green", alpha=.55, label="IAPF active")
            active_ax.set_ylim(-.05, 1.15)
            active_ax.set_yticks([0, 1], ["inactive", "active"])
            handles, labels = ax.get_legend_handles_labels()
            active_handles, active_labels = active_ax.get_legend_handles_labels()
            ax.legend(handles + active_handles, labels + active_labels)
            ax.set_ylabel("Distance (m)")
        elif task_attempts:
            selected = next(
                (row for row in task_attempts if row["overall_success"].lower() == "true"),
                task_attempts[0])
            timeline = [row for row in stage if row["attempt_id"] == selected["attempt_id"]]
            for index, row in enumerate(timeline):
                ax.barh(index, value(row, "stage_wall_time"),
                        left=value(row, "stage_start_time"))
            ax.set_yticks(range(len(timeline)),
                          [f"Stage {row['stage_id']}" for row in timeline])
            ax.set_xlabel("Attempt-relative time (s)")
        save(fig, figures, name)
    print(f"generated figures in {figures}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
