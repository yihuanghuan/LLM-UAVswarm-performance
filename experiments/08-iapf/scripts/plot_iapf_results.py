#!/usr/bin/env python3
"""Generate experiment 08 v2 protocol figures."""

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


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def save(fig, directory: Path, name: str) -> None:
    fig.tight_layout()
    for extension in ("png", "pdf"):
        fig.savefig(directory / f"{name}.{extension}", dpi=220)
    plt.close(fig)


def paired_delta(
    data: pd.DataFrame, method_a: str, method_b: str, metric: str
) -> pd.DataFrame:
    subset = data[data["method"].isin([method_a, method_b])]
    pivot = subset.pivot_table(
        index=["scenario", "seed"], columns="method",
        values=metric, aggfunc="first").dropna()
    pivot["delta"] = pivot[method_b] - pivot[method_a]
    return pivot.reset_index()


def grouped_boxplot(
    data: pd.DataFrame, metric: str, methods: list[str],
    ylabel: str, directory: Path, name: str,
) -> None:
    scenarios = sorted(data["scenario"].unique())
    fig, axes = plt.subplots(
        1, len(scenarios), figsize=(5 * len(scenarios), 4), squeeze=False)
    for axis, scenario in zip(axes[0], scenarios):
        subset = data[data["scenario"] == scenario]
        values = [
            subset[subset["method"] == method][metric].dropna()
            for method in methods]
        axis.boxplot(values, labels=methods, showfliers=True)
        axis.set_title(scenario)
        axis.set_ylabel(ylabel)
        axis.tick_params(axis="x", rotation=25)
        axis.grid(alpha=0.25)
    save(fig, directory, name)


def representative_trial(
    batch_dir: Path, scenario: str, method: str
) -> Path:
    candidates = sorted(
        (batch_dir / "raw" / scenario / method).glob("trial_*_seed_*"))
    candidates = [
        path for path in candidates
        if json.loads(
            (path / "run_metadata.json").read_text(encoding="utf-8")
        ).get("phase") != "pilot"
    ]
    if not candidates:
        raise FileNotFoundError(f"no formal trial for {scenario}/{method}")
    return candidates[0]


def distance_timeseries(batch_dir: Path, directory: Path) -> None:
    scenario = "staggered_crossing_delay"
    methods = ["IAPF_OFF", "IAPF_ON"]
    fig, axes = plt.subplots(2, 1, figsize=(9, 7), sharex=True, sharey=True)
    for axis, method in zip(axes, methods):
        trial_dir = representative_trial(batch_dir, scenario, method)
        metadata = json.loads(
            (trial_dir / "run_metadata.json").read_text(encoding="utf-8"))
        timeline, positions = resample_odometry(
            read_csv(trial_dir / "odom.csv"),
            float(metadata["analysis"]["sample_hz"]),
            float(metadata["analysis"]["max_odom_gap"]))
        series = [
            np.linalg.norm(positions[a] - positions[b], axis=1)
            for a, b in combinations(sorted(positions), 2)]
        minimum = np.min(np.stack(series), axis=0)
        axis.plot(timeline - timeline[0], minimum, color="black")
        for threshold, color in [
            ("r_iapf", "tab:blue"), ("d_violation", "tab:orange"),
            ("d_collision", "tab:red")]:
            axis.axhline(
                metadata["safety_thresholds"][threshold], linestyle="--",
                color=color, label=threshold)
        axis.set_title(method)
        axis.set_ylabel("Minimum distance (m)")
        axis.grid(alpha=0.25)
    axes[0].legend(ncol=3, fontsize=8)
    axes[-1].set_xlabel("Time (s)")
    save(fig, directory, "fallback_distance_timeseries")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("batch_dir", type=Path)
    args = parser.parse_args()
    data = pd.read_csv(args.batch_dir / "summaries" / "trial_summary.csv")
    formal = data[data["phase"] != "pilot"].copy()
    figure_dir = args.batch_dir / "figures"
    figure_dir.mkdir(parents=True, exist_ok=True)

    nonintrusive = formal[formal["family"] == "nonintrusive"]
    grouped_boxplot(
        nonintrusive, "iapf_activation_ratio", ["IAPF_OFF", "IAPF_ON"],
        "IAPF activation ratio", figure_dir, "nonintrusive_activation")
    grouped_boxplot(
        nonintrusive, "completion_time", ["IAPF_OFF", "IAPF_ON"],
        "Completion time (s)", figure_dir, "nonintrusive_completion_time")

    fallback = formal[formal["family"] == "fallback"]
    fig, axes = plt.subplots(1, 2, figsize=(11, 4))
    for axis, metric, title in [
        (axes[0], "minimum_inter_agent_distance", "ON − OFF min distance"),
        (axes[1], "risk_integral", "OFF − ON risk integral")]:
        paired = paired_delta(fallback, "IAPF_OFF", "IAPF_ON", metric)
        if metric == "risk_integral":
            paired["delta"] *= -1.0
        scenarios = sorted(paired["scenario"].unique())
        axis.boxplot(
            [paired[paired["scenario"] == scenario]["delta"]
             for scenario in scenarios],
            labels=scenarios)
        axis.axhline(0.0, color="black", linewidth=0.8)
        axis.set_title(title)
        axis.tick_params(axis="x", rotation=25)
        axis.grid(alpha=0.25)
    save(fig, figure_dir, "fallback_paired_effects")

    complement = formal[formal["family"] == "complement"]
    grouped_boxplot(
        complement, "iapf_activation_ratio",
        ["DIST_OFF", "DIST_ON", "SAFE_OFF", "SAFE_ON"],
        "IAPF activation ratio", figure_dir, "assignment_iapf_complement")

    stress = formal[formal["family"] == "stress"]
    grouped_boxplot(
        stress, "minimum_inter_agent_distance",
        ["STRESS_OFF", "STRESS_ON"], "Minimum distance (m)",
        figure_dir, "stress_failure_boundary")

    ablation = formal[
        (formal["scenario"] == "staggered_crossing_delay")
        & formal["method"].isin(["IAPF_OFF", "ABL_POSITION", "IAPF_ON"])]
    grouped_boxplot(
        ablation.assign(scenario="two_agent_ablation"),
        "minimum_inter_agent_distance",
        ["IAPF_OFF", "ABL_POSITION", "IAPF_ON"],
        "Minimum distance (m)", figure_dir, "position_channel_ablation")

    distance_timeseries(args.batch_dir, figure_dir)

    paper = formal.groupby(["family", "method"]).agg(
        trial_count=("seed", "count"),
        success_rate=("mission_success", "mean"),
        min_distance=("minimum_inter_agent_distance", "median"),
        risk_integral=("risk_integral", "median"),
        activation_ratio=("iapf_activation_ratio", "median"),
        activation_events=("activation_event_count", "median"),
        unnecessary_rate=("unnecessary_intervention_rate", "median"),
        intervention_latency=("intervention_latency", "median"),
    ).reset_index()
    paper.to_csv(
        args.batch_dir / "summaries" / "paper_summary_table.csv", index=False)
    print(figure_dir)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
