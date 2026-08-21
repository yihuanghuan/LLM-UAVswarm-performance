#!/usr/bin/env python3
"""Plot preregistered metric distributions from aggregate_v2.json."""

import argparse
import json
from pathlib import Path

import matplotlib.pyplot as plt


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--artifact-root", type=Path, required=True)
    args = parser.parse_args()
    root = args.artifact_root.resolve()
    data = json.loads((root / "metrics" / "aggregate_v2.json").read_text(encoding="utf-8"))
    trials = [trial for trial in data["trials"] if trial["worst"] is not None]
    figures = root / "figures"
    figures.mkdir(exist_ok=True)
    fields = (
        ("tracking_rmse_m", "Tracking RMSE (m)", 0.50),
        ("maximum_tracking_error_m", "Maximum error (m)", 1.00),
        ("final_error_m", "Final error (m)", 0.40),
        ("saturation_ratio", "Acceleration saturation ratio", 0.02),
        ("post_rms_m", "Post-trajectory RMS (m)", 0.25),
        ("command_jerk_p99_5_mps3", "Command jerk p99.5 (m/s^3)", None),
    )
    fig, axes = plt.subplots(3, 2, figsize=(13, 12), constrained_layout=True)
    stages = sorted({trial["stage"] for trial in trials})
    colors = {stage: plt.cm.tab10(index % 10) for index, stage in enumerate(stages)}
    for axis, (field, label, threshold) in zip(axes.ravel(), fields):
        for stage in stages:
            values = [trial["worst"][field] for trial in trials if trial["stage"] == stage]
            axis.plot(range(len(values)), values, ".", label=stage, color=colors[stage], alpha=0.6)
        if threshold is not None:
            axis.axhline(threshold, color="black", linestyle="--", linewidth=1)
        axis.set_title(label)
        axis.set_xlabel("within-stage preregistered execution index")
        axis.grid(alpha=0.25)
    handles, labels = axes[0, 0].get_legend_handles_labels()
    fig.legend(handles, labels, loc="outside upper center", ncol=3)
    output = figures / "c0a_v2_metric_distributions.png"
    fig.savefig(output, dpi=180)
    plt.close(fig)
    print(output)


if __name__ == "__main__":
    main()
