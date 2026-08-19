#!/usr/bin/env python3
"""Aggregate immutable per-trial C0-A v2 metrics without redefining them."""

from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import json
from pathlib import Path
from statistics import median


def trial_worst(metrics):
    uavs = metrics.get("per_uav", [])
    if not uavs:
        return None
    return {
        "tracking_rmse_m": max(item["tracking_rmse_m"] for item in uavs),
        "maximum_tracking_error_m": max(item["maximum_tracking_error_m"] for item in uavs),
        "final_error_m": max(item["final_error_m"] for item in uavs),
        "saturation_ratio": max(
            max(item["acceleration_saturation_ratio_per_axis"]) for item in uavs
        ),
        "roll_peak_deg": max(item["roll_peak_deg"] for item in uavs),
        "pitch_peak_deg": max(item["pitch_peak_deg"] for item in uavs),
        "post_rms_m": max(item["post_trajectory_rms_m"] for item in uavs),
        "peak_to_peak_m": max(
            max(item["post_trajectory_peak_to_peak_per_axis_m"]) for item in uavs
        ),
        "last_first_rms_ratio": max(
            item["post_trajectory_last_first_rms_ratio"] for item in uavs
        ),
        "zero_crossings": max(
            max(item["post_trajectory_zero_crossings_per_axis"]) for item in uavs
        ),
        "command_jerk_p99_5_mps3": max(
            item["command_jerk_p99_5_mps3"] for item in uavs
        ),
        "minimum_separation_m": metrics.get("minimum_inter_uav_distance_m"),
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--artifact-root", type=Path, required=True)
    args = parser.parse_args()
    root = args.artifact_root.resolve()
    state = json.loads((root / "campaign_state.json").read_text(encoding="utf-8"))
    trials = []
    for path in sorted((root / "raw").glob("*/metrics.json")):
        metrics = json.loads(path.read_text(encoding="utf-8"))
        manifest = json.loads((path.parent / "manifest.json").read_text(encoding="utf-8"))
        trials.append({
            "trial_id": metrics["trial_id"],
            "stage": metrics["stage"],
            "candidate_id": metrics["candidate_id"],
            "scenario_id": metrics["scenario_id"],
            "seed": metrics["seed"],
            "hard_pass": metrics["hard_pass"],
            "hard_failures": metrics["hard_failures"],
            "termination_reason": manifest["termination_reason"],
            "worst": trial_worst(metrics),
        })
    valid = [trial for trial in trials if trial["worst"] is not None]
    numeric_fields = (
        "tracking_rmse_m", "maximum_tracking_error_m", "final_error_m",
        "saturation_ratio", "roll_peak_deg", "pitch_peak_deg", "post_rms_m",
        "peak_to_peak_m", "last_first_rms_ratio", "zero_crossings",
        "command_jerk_p99_5_mps3",
    )
    distributions = {}
    for field in numeric_fields:
        values = [trial["worst"][field] for trial in valid]
        distributions[field] = {
            "count": len(values),
            "median": median(values) if values else None,
            "worst": max(values) if values else None,
        }
    separation = [
        trial["worst"]["minimum_separation_m"] for trial in valid
        if trial["worst"]["minimum_separation_m"] is not None
    ]
    distributions["minimum_separation_m"] = {
        "count": len(separation),
        "median": median(separation) if separation else None,
        "worst": min(separation) if separation else None,
    }
    by_stage = defaultdict(list)
    for trial in trials:
        by_stage[trial["stage"]].append(trial)
    aggregate = {
        "calibration_id": "C0-A",
        "protocol_version": "C0-A-prereg-v2",
        "campaign_status": state.get("campaign_status"),
        "formal_trials_executed": len(trials),
        "stage_counts": {
            stage: {
                "executed": len(items),
                "passed": sum(item["hard_pass"] for item in items),
                "failed": sum(not item["hard_pass"] for item in items),
            }
            for stage, items in sorted(by_stage.items())
        },
        "failure_counts": dict(sorted(Counter(
            failure for trial in trials for failure in trial["hard_failures"]
        ).items())),
        "termination_counts": dict(sorted(Counter(
            trial["termination_reason"] for trial in trials
        ).items())),
        "distributions": distributions,
        "state": state,
        "trials": trials,
    }
    output = root / "metrics" / "aggregate_v2.json"
    output.write_text(json.dumps(aggregate, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({
        "output": str(output),
        "formal_trials_executed": len(trials),
        "campaign_status": state.get("campaign_status"),
    }, sort_keys=True))


if __name__ == "__main__":
    main()
