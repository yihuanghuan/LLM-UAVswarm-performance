#!/usr/bin/env python3
"""Summarize and plot experiment 04 assignment results."""

from __future__ import annotations

import argparse
import csv
import json
import math
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Iterable, List, Sequence

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402


METHOD_ORDER = [
    "random",
    "nearest_neighbor",
    "hungarian_distance",
    "hungarian_crossing_penalty",
    "safety_aware_local_swap",
]
METHOD_LABELS = {
    "random": "Random",
    "nearest_neighbor": "Nearest Neighbor",
    "hungarian_distance": "Hungarian-Distance",
    "hungarian_crossing_penalty": "Hungarian + crossing penalty",
    "safety_aware_local_swap": "Hungarian + safety-aware local swap",
}
SUMMARY_FIELDS = [
    "scope",
    "method",
    "trials",
    "mean_total_path_length",
    "mean_avg_path_length",
    "mean_xy_crossings",
    "mean_proximity_crossings",
    "mean_min_distance",
    "median_min_distance",
    "mean_safety_violation_count",
    "mean_critical_violation_count",
    "mean_arrival_time_variance",
    "failed_assignment_ratio",
    "critical_failed_assignment_ratio",
    "mean_compute_time_ms",
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Analyze experiment 04 raw assignment results.")
    parser.add_argument("--input-dir", required=True, help="Directory containing assignment_trials.csv.")
    return parser.parse_args()


def read_csv(path: Path) -> List[Dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def load_scenarios(path: Path) -> Dict[tuple[str, int], Dict[str, object]]:
    scenarios: Dict[tuple[str, int], Dict[str, object]] = {}
    with path.open(encoding="utf-8") as handle:
        for line in handle:
            item = json.loads(line)
            scenarios[(str(item["scenario"]), int(item["trial_id"]))] = item
    return scenarios


def values(rows: Iterable[Dict[str, str]], field: str) -> List[float]:
    return [float(row[field]) for row in rows]


def mean(rows: Sequence[Dict[str, str]], field: str) -> float:
    return float(np.mean(values(rows, field)))


def summarize(rows: Sequence[Dict[str, str]]) -> List[Dict[str, object]]:
    grouped: Dict[tuple[str, str], List[Dict[str, str]]] = defaultdict(list)
    for row in rows:
        grouped[(row["scenario"], row["method"])].append(row)
        grouped[("ALL", row["method"])].append(row)

    summary: List[Dict[str, object]] = []
    scopes = sorted({row["scenario"] for row in rows}) + ["ALL"]
    for scope in scopes:
        for method in METHOD_ORDER:
            items = grouped.get((scope, method), [])
            if not items:
                continue
            summary.append({
                "scope": scope,
                "method": method,
                "trials": len(items),
                "mean_total_path_length": mean(items, "total_path_length"),
                "mean_avg_path_length": mean(items, "avg_path_length"),
                "mean_xy_crossings": mean(items, "xy_crossings"),
                "mean_proximity_crossings": mean(items, "proximity_crossings"),
                "mean_min_distance": mean(items, "min_distance"),
                "median_min_distance": float(np.median(values(items, "min_distance"))),
                "mean_safety_violation_count": mean(items, "safety_violation_count"),
                "mean_critical_violation_count": mean(items, "critical_violation_count"),
                "mean_arrival_time_variance": mean(items, "arrival_time_variance"),
                "failed_assignment_ratio": mean(items, "failed_assignment"),
                "critical_failed_assignment_ratio": mean(items, "critical_failed_assignment"),
                "mean_compute_time_ms": mean(items, "compute_time_ms"),
            })
    return summary


def write_summary(rows: Sequence[Dict[str, object]], path: Path) -> None:
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=SUMMARY_FIELDS)
        writer.writeheader()
        for row in rows:
            writer.writerow({
                key: f"{value:.6f}" if isinstance(value, float) else value
                for key, value in row.items()
            })


def save_figure(fig: plt.Figure, output_dir: Path, name: str) -> List[str]:
    outputs: List[str] = []
    for suffix in ("png", "pdf"):
        filename = f"{name}.{suffix}"
        fig.savefig(output_dir / filename, dpi=220, bbox_inches="tight")
        outputs.append(filename)
    plt.close(fig)
    return outputs


def method_rows(rows: Sequence[Dict[str, str]], method: str) -> List[Dict[str, str]]:
    return [row for row in rows if row["method"] == method]


def plot_min_distance(rows: Sequence[Dict[str, str]], output_dir: Path) -> List[str]:
    data = [values(method_rows(rows, method), "min_distance") for method in METHOD_ORDER]
    fig, ax = plt.subplots(figsize=(11, 5.5))
    ax.boxplot(data, tick_labels=[METHOD_LABELS[item] for item in METHOD_ORDER], showfliers=False)
    ax.set_ylabel("Minimum inter-agent distance (m)")
    ax.set_title("Nominal Trajectory Minimum Distance")
    ax.grid(axis="y", alpha=0.25)
    ax.tick_params(axis="x", rotation=16)
    fig.tight_layout()
    return save_figure(fig, output_dir, "fig_min_distance_boxplot")


def plot_crossings(rows: Sequence[Dict[str, str]], output_dir: Path) -> List[str]:
    xy = [float(np.mean(values(method_rows(rows, method), "xy_crossings"))) for method in METHOD_ORDER]
    prox = [float(np.mean(values(method_rows(rows, method), "proximity_crossings"))) for method in METHOD_ORDER]
    x = np.arange(len(METHOD_ORDER))
    fig, ax = plt.subplots(figsize=(11, 5.5))
    ax.bar(x - 0.2, xy, width=0.4, label="XY segment crossings")
    ax.bar(x + 0.2, prox, width=0.4, label="Proximity conflicts")
    ax.set_xticks(x, [METHOD_LABELS[item] for item in METHOD_ORDER], rotation=16)
    ax.set_ylabel("Mean count per assignment")
    ax.set_title("Assignment Crossing Comparison")
    ax.legend()
    ax.grid(axis="y", alpha=0.25)
    fig.tight_layout()
    return save_figure(fig, output_dir, "fig_crossing_count_bar")


def plot_pareto(summary: Sequence[Dict[str, object]], output_dir: Path) -> List[str]:
    overall = {str(row["method"]): row for row in summary if row["scope"] == "ALL"}
    fig, ax = plt.subplots(figsize=(8.5, 6.0))
    for method in METHOD_ORDER:
        item = overall[method]
        ax.scatter(item["mean_total_path_length"], item["mean_min_distance"], s=85)
        ax.annotate(
            METHOD_LABELS[method],
            (item["mean_total_path_length"], item["mean_min_distance"]),
            xytext=(5, 5),
            textcoords="offset points",
            fontsize=8,
        )
    ax.set_xlabel("Mean total path length (m), lower is better")
    ax.set_ylabel("Mean minimum distance (m), higher is better")
    ax.set_title("Path Length–Safety Pareto Comparison")
    ax.grid(alpha=0.25)
    fig.tight_layout()
    return save_figure(fig, output_dir, "fig_path_safety_pareto")


def select_qualitative_trial(rows: Sequence[Dict[str, str]]) -> int:
    crossing = [row for row in rows if row["scenario"] == "crossing-prone"]
    grouped: Dict[int, Dict[str, Dict[str, str]]] = defaultdict(dict)
    for row in crossing:
        grouped[int(row["trial_id"])][row["method"]] = row

    def score(trial_id: int) -> tuple[float, float, int]:
        items = grouped[trial_id]
        plain = items["hungarian_distance"]
        safe = items["safety_aware_local_swap"]
        violation_gain = float(plain["safety_violation_count"]) - float(safe["safety_violation_count"])
        crossing_gain = float(plain["xy_crossings"]) - float(safe["xy_crossings"])
        return violation_gain, crossing_gain, -trial_id

    if not grouped:
        raise ValueError("No crossing-prone trials are available for the qualitative figure")
    return max(grouped, key=score)


def plot_qualitative(
    rows: Sequence[Dict[str, str]],
    scenarios: Dict[tuple[str, int], Dict[str, object]],
    output_dir: Path,
) -> tuple[List[str], int]:
    trial_id = select_qualitative_trial(rows)
    scenario = scenarios[("crossing-prone", trial_id)]
    initial = np.asarray(scenario["initial"], dtype=float)
    targets = np.asarray(scenario["targets"], dtype=float)
    selected = {
        row["method"]: row
        for row in rows
        if row["scenario"] == "crossing-prone" and int(row["trial_id"]) == trial_id
    }

    fig, axes = plt.subplots(2, 3, figsize=(14, 9), sharex=True, sharey=True)
    for ax, method in zip(axes.ravel(), METHOD_ORDER):
        assignment = json.loads(selected[method]["assignment"])
        ax.scatter(initial[:, 0], initial[:, 1], marker="o", label="Initial", color="#4C78A8")
        ax.scatter(targets[:, 0], targets[:, 1], marker="^", label="Target", color="#F58518")
        for uav_index, target_index in enumerate(assignment):
            ax.plot(
                [initial[uav_index, 0], targets[target_index, 0]],
                [initial[uav_index, 1], targets[target_index, 1]],
                linewidth=1.2,
                alpha=0.8,
            )
        ax.set_title(
            f"{METHOD_LABELS[method]}\n"
            f"XY={selected[method]['xy_crossings']}, "
            f"violations={selected[method]['safety_violation_count']}"
        )
        ax.grid(alpha=0.2)
        ax.set_aspect("equal", adjustable="box")
    axes[1, 2].axis("off")
    axes[0, 0].legend(fontsize="small")
    fig.supxlabel("X (m)")
    fig.supylabel("Y (m)")
    fig.suptitle(f"Crossing-prone Trial {trial_id}: Assignment Paths (XY Projection)")
    fig.tight_layout()
    return save_figure(fig, output_dir, "fig_qualitative_crossing_prone"), trial_id


def write_markdown_table(summary: Sequence[Dict[str, object]], path: Path) -> None:
    overall = [row for row in summary if row["scope"] == "ALL"]
    lines = [
        "# Experiment 04 Assignment Baseline Summary",
        "",
        "| Method | Total path (m) | Avg path (m) | XY crossings | Min distance (m) | "
        "Safety violations | Critical violations | Safety-margin failure | Critical failure | "
        "Arrival variance (s²) | Compute (ms) |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for row in overall:
        lines.append(
            f"| {METHOD_LABELS[str(row['method'])]} "
            f"| {row['mean_total_path_length']:.3f} "
            f"| {row['mean_avg_path_length']:.3f} "
            f"| {row['mean_xy_crossings']:.3f} "
            f"| {row['mean_min_distance']:.3f} "
            f"| {row['mean_safety_violation_count']:.3f} "
            f"| {row['mean_critical_violation_count']:.3f} "
            f"| {row['failed_assignment_ratio']:.3f} "
            f"| {row['critical_failed_assignment_ratio']:.3f} "
            f"| {row['mean_arrival_time_variance']:.3f} "
            f"| {row['mean_compute_time_ms']:.3f} |"
        )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def analyze(input_dir: Path) -> Dict[str, object]:
    trials_path = input_dir / "assignment_trials.csv"
    scenarios_path = input_dir / "scenario_points.jsonl"
    rows = read_csv(trials_path)
    if not rows:
        raise ValueError("assignment_trials.csv contains no rows")
    scenarios = load_scenarios(scenarios_path)
    summary = summarize(rows)

    outputs = ["assignment_summary.csv", "table_assignment_baselines.md"]
    write_summary(summary, input_dir / outputs[0])
    write_markdown_table(summary, input_dir / outputs[1])
    outputs.extend(plot_min_distance(rows, input_dir))
    outputs.extend(plot_crossings(rows, input_dir))
    outputs.extend(plot_pareto(summary, input_dir))
    qualitative_outputs, selected_trial = plot_qualitative(rows, scenarios, input_dir)
    outputs.extend(qualitative_outputs)

    manifest: Dict[str, object] = {
        "experiment": "experiments_04",
        "created_at_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "input_files": [trials_path.name, scenarios_path.name, "run_config.json"],
        "output_files": outputs,
        "row_count": len(rows),
        "qualitative_scenario": "crossing-prone",
        "qualitative_trial_id": selected_trial,
    }
    (input_dir / "analysis_manifest.json").write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    return manifest


def main() -> int:
    manifest = analyze(Path(parse_args().input_dir))
    print(f"Analyzed {manifest['row_count']} rows; generated {len(manifest['output_files'])} artifacts")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
