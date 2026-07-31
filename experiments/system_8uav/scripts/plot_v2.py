#!/usr/bin/env python3
"""Generate the required experiment-10 v2 PNG and PDF figures."""

from __future__ import annotations

import argparse
import csv
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
    groups = [[value(row, metric) for row in data if row["task_type"] == task]
              for task in TASKS]
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
    semantic = rows(summaries / "semantic_summary.csv")
    outliers = rows(summaries / "outlier_summary.csv")
    boxplot(figures, mission, "mission_wall_time", "mission_wall_time_boxplot", "Wall time (s)")
    boxplot(figures, stage, "trajectory_finish_spread", "trajectory_finish_spread_boxplot", "Spread (s)")
    boxplot(figures, stage, "stable_arrival_spread", "stable_arrival_spread_boxplot", "Spread (s)")

    totals = defaultdict(lambda: [0., 0.])
    for row in stage:
        totals[row["task_type"]][0] += value(row, "reference_execution_time")
        totals[row["task_type"]][1] += value(row, "stabilization_delay")
    fig, ax = plt.subplots(figsize=(8, 4.5))
    x = range(len(TASKS))
    ref = [totals[t][0] for t in TASKS]
    stable = [totals[t][1] for t in TASKS]
    ax.bar(x, ref, label="Reference execution")
    ax.bar(x, stable, bottom=ref, label="Stabilization")
    ax.set_xticks(list(x), ["A", "B", "C", "D", "E"])
    ax.set_ylabel("Accumulated time (s)")
    ax.legend()
    save(fig, figures, "phase_time_decomposition")

    failures = defaultdict(int)
    for row in attempts:
        if row["failure_reason"]:
            failures[row["failure_reason"]] += 1
    fig, ax = plt.subplots(figsize=(8, 4.5))
    labels = list(failures) or ["none"]
    ax.bar(labels, [failures[k] for k in failures] or [0])
    ax.tick_params(axis="x", rotation=25)
    ax.set_ylabel("Attempts")
    save(fig, figures, "readiness_failure_classification")

    latency = defaultdict(list)
    success = defaultdict(list)
    for row in semantic:
        latency[row["task_type"]].append(value(row, "latency_ms"))
        success[row["task_type"]].append(row["semantic_valid"].lower() == "true")
    fig, axes = plt.subplots(1, 2, figsize=(10, 4.5))
    axes[0].bar(range(5), [sum(success[t]) / len(success[t]) if success[t] else 0 for t in TASKS])
    axes[0].set_xticks(range(5), ["A", "B", "C", "D", "E"])
    axes[0].set_ylabel("Semantic success fraction")
    axes[1].boxplot([latency[t] for t in TASKS], tick_labels=["A", "B", "C", "D", "E"])
    axes[1].set_ylabel("LLM latency (ms)")
    save(fig, figures, "llm_parsing_success_latency")

    flagged = [row for row in outliers if row["is_outlier"].lower() == "true"]
    fig, ax = plt.subplots(figsize=(9, 4.5))
    labels = [f"{row['attempt_id']}:{row['metric']}" for row in flagged] or ["none"]
    ax.bar(labels, [value(row, "value") for row in flagged] or [0])
    ax.tick_params(axis="x", rotation=70)
    ax.set_ylabel("Flagged value")
    save(fig, figures, "outlier_phase_decomposition")

    # Detailed Task D and E figures are generated directly from raw streams.
    for task, name in (("task_d_dense", "task_d_safety_iapf"),
                       ("task_e_mixed", "task_e_success_timeline")):
        task_attempts = [
            row for row in attempts if row["task_type"] == task
            and row["entered_execution"].lower() == "true"]
        fig, ax = plt.subplots(figsize=(9, 4.5))
        if task == "task_d_dense" and task_attempts:
            raw = Path(task_attempts[0]["path"])
            data = rows(raw / "iapf_debug.csv")
            by_time = defaultdict(list)
            for row in data:
                by_time[round(value(row, "timestamp"), 1)].append(
                    value(row, "nearest_neighbor_distance"))
            times = sorted(by_time)
            ax.plot(times, [min(by_time[t]) for t in times], label="Minimum neighbor distance")
            ax.axhline(1.0, color="r", linestyle="--", label="Violation threshold")
            ax.axhline(1.5, color="orange", linestyle=":", label="IAPF enter")
            ax.legend()
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
