#!/usr/bin/env python3
"""Generate the required experiment 08 publication figures."""

from __future__ import annotations

import argparse
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd


METHODS = [f"M{value}" for value in range(6)]


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
