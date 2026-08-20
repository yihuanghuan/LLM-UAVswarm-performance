#!/usr/bin/env python3
"""Apply the preregistered deterministic C0-A lexicographic selection rule."""

from __future__ import annotations

import argparse
from collections import defaultdict
import json
import math
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SCHEDULE = ROOT / "trial_order_v3.json"


def percentile(values, probability):
    ordered = sorted(values)
    return ordered[max(0, math.ceil(probability * len(ordered)) - 1)]


def load_trials(artifact_root, stage):
    trials = []
    for metrics_path in sorted((artifact_root / "raw").glob("*/metrics.json")):
        metrics = json.loads(metrics_path.read_text(encoding="utf-8"))
        if metrics["stage"] != stage:
            continue
        trial_dir = metrics_path.parent
        trials.append({
            "metrics": metrics,
            "manifest": json.loads((trial_dir / "manifest.json").read_text(encoding="utf-8")),
            "spec": json.loads((trial_dir / "trial_spec.json").read_text(encoding="utf-8")),
        })
    return trials


def expected_ids(schedule, stage, state):
    entries = [entry for entry in schedule["entries"] if entry["stage"] == stage]
    if stage == "A1_CONFIRMATION":
        active = set(state["a1_confirmation_mapping"])
        entries = [entry for entry in entries if entry["candidate_id"] in active]
    elif stage == "A2_CONFIRMATION":
        active = set(state["a2_confirmation_mapping"])
        entries = [entry for entry in entries if entry["candidate_id"] in active]
    return {entry["trial_id"] for entry in entries}


def flatten_uavs(trials):
    return [item for trial in trials for item in trial["metrics"]["per_uav"]]


def candidate_key(trials, parameters):
    uavs = flatten_uavs(trials)
    post_rms = max(item["post_trajectory_rms_m"] for item in uavs)
    peak_to_peak = max(
        max(item["post_trajectory_peak_to_peak_per_axis_m"]) for item in uavs
    )
    last_first = max(item["post_trajectory_last_first_rms_ratio"] for item in uavs)
    attitude_margin = min(
        30.0 - max(item["roll_peak_deg"], item["pitch_peak_deg"]) for item in uavs
    )
    separation_values = [
        trial["metrics"].get("minimum_inter_uav_distance_m") for trial in trials
        if trial["metrics"].get("minimum_inter_uav_distance_m") is not None
    ]
    safety_margin = min(separation_values) - 1.0 if separation_values else math.inf
    minimum_margin = min(attitude_margin / 30.0, safety_margin)
    attitude_ratio = max(
        max(item["roll_peak_deg"], item["pitch_peak_deg"]) / 30.0 for item in uavs
    )
    jerk_ratio = max(
        item["command_jerk_p99_5_mps3"] / (1.5 * parameters["j_limit"])
        for item in uavs
    )
    saturation_values = [max(item["acceleration_saturation_ratio_per_axis"]) for item in uavs]
    rms_values = [item["tracking_rmse_m"] for item in uavs]
    omega_norm = math.sqrt(sum(
        value * value for family in ("omega_c", "omega_o")
        for value in parameters[family]
    ))
    conservative = (
        parameters["a_limit"],
        parameters["j_limit"],
        parameters["v_limit"],
        omega_norm,
        -parameters["minimum_duration"],
    )
    return (
        post_rms,
        peak_to_peak,
        last_first,
        -minimum_margin,
        attitude_ratio,
        jerk_ratio,
        max(saturation_values),
        percentile(saturation_values, 0.95),
        max(rms_values),
        sorted(rms_values)[len(rms_values) // 2],
        max(item["maximum_tracking_error_m"] for item in uavs),
        max(item["final_error_m"] for item in uavs),
        *conservative,
        json.dumps(parameters, sort_keys=True, separators=(",", ":")),
    )


def evaluate_groups(trials, expected_count):
    groups = defaultdict(list)
    for trial in trials:
        groups[trial["manifest"]["candidate_id"]].append(trial)
    records = []
    for candidate_id, items in sorted(groups.items()):
        parameters = items[0]["spec"]["resolved_candidate_parameters"]
        complete = len(items) == expected_count
        hard_pass = complete and all(item["metrics"]["hard_pass"] for item in items)
        records.append({
            "candidate_id": candidate_id,
            "parameters": parameters,
            "trial_count": len(items),
            "expected_trial_count": expected_count,
            "complete": complete,
            "hard_pass": hard_pass,
            "failures": sorted({
                failure for item in items for failure in item["metrics"]["hard_failures"]
            }),
            "selection_key": list(candidate_key(items, parameters)) if hard_pass else None,
        })
    passing = sorted(
        (item for item in records if item["hard_pass"]),
        key=lambda item: tuple(item["selection_key"]),
    )
    for rank, item in enumerate(passing, 1):
        item["rank"] = rank
    return records, passing


def save_ranking(artifact_root, stage, payload):
    output = artifact_root / "metrics" / f"{stage.lower()}_ranking.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return output


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--stage", required=True, choices=(
        "A1_SCREENING", "A1_CONFIRMATION", "A2_SCREENING",
        "A2_CONFIRMATION", "A3_VALIDATION", "SCALE_VALIDATION",
    ))
    parser.add_argument("--artifact-root", type=Path, required=True)
    parser.add_argument("--state", type=Path, required=True)
    parser.add_argument("--schedule", type=Path, default=DEFAULT_SCHEDULE)
    args = parser.parse_args()
    state = json.loads(args.state.read_text(encoding="utf-8"))
    schedule = json.loads(args.schedule.read_text(encoding="utf-8"))
    trials = load_trials(args.artifact_root, args.stage)
    expected = expected_ids(schedule, args.stage, state)
    actual = {trial["manifest"]["trial_id"] for trial in trials}
    if actual != expected:
        missing = sorted(expected - actual)
        extra = sorted(actual - expected)
        raise SystemExit(f"stage is incomplete: missing={len(missing)} extra={len(extra)}")

    if args.stage == "SCALE_VALIDATION":
        by_scenario = defaultdict(list)
        for trial in trials:
            by_scenario[trial["manifest"]["scenario_id"]].append(trial)
        payload = {
            "stage": args.stage,
            "hard_pass": all(trial["metrics"]["hard_pass"] for trial in trials),
            "scenarios": {
                scenario: {
                    "passed": sum(item["metrics"]["hard_pass"] for item in items),
                    "total": len(items),
                    "hard_pass": len(items) == 5 and all(item["metrics"]["hard_pass"] for item in items),
                }
                for scenario, items in sorted(by_scenario.items())
            },
        }
        state["scale_validation"] = payload
        state["campaign_status"] = "PASS" if payload["hard_pass"] else "FREEZE_FAIL"
    elif args.stage == "A3_VALIDATION":
        records, passing = evaluate_groups(trials, 20)
        eligible = [item for item in passing if (
            item["parameters"]["omega_lower_multiplier"] <= 0.75
            and item["parameters"]["omega_upper_multiplier"] >= 1.20
        )]
        eligible.sort(key=lambda item: (
            item["parameters"]["motion_clamp_multiplier"],
            item["parameters"]["omega_upper_multiplier"]
            - item["parameters"]["omega_lower_multiplier"],
            item["parameters"]["omega_lower_multiplier"],
            item["parameters"]["omega_upper_multiplier"],
            tuple(item["selection_key"]),
        ))
        winner = eligible[0] if eligible else None
        payload = {"stage": args.stage, "candidates": records, "winner": winner}
        if winner is None:
            state["campaign_status"] = "NO_ACCEPTABLE_CONFIGURATION"
        else:
            state["a3_winner_id"] = winner["candidate_id"]
            state["a3_winner"] = winner["parameters"]
    else:
        expected_per_candidate = {
            "A1_SCREENING": 12,
            "A1_CONFIRMATION": 60,
            "A2_SCREENING": 63,
            "A2_CONFIRMATION": 180,
        }[args.stage]
        records, passing = evaluate_groups(trials, expected_per_candidate)
        payload = {"stage": args.stage, "candidates": records, "survivor_count": len(passing)}
        if not passing:
            state["campaign_status"] = "NO_ACCEPTABLE_CONFIGURATION"
        elif args.stage == "A1_SCREENING":
            selected = passing[:5]
            state["a1_candidates"] = {
                item["candidate_id"]: item["parameters"] for item in records
            }
            state["a1_survivors"] = [item["candidate_id"] for item in passing]
            state["a1_confirmation_mapping"] = {
                f"A1-RANK-{rank:02d}": item["candidate_id"]
                for rank, item in enumerate(selected, 1)
            }
            payload["confirmation_mapping"] = state["a1_confirmation_mapping"]
        elif args.stage == "A1_CONFIRMATION":
            winner = passing[0]
            concrete_id = state["a1_confirmation_mapping"][winner["candidate_id"]]
            state["a1_winner_id"] = concrete_id
            state["a1_winner"] = state["a1_candidates"][concrete_id]
            payload["winner"] = {**winner, "concrete_candidate_id": concrete_id}
        elif args.stage == "A2_SCREENING":
            selected = passing[:5]
            state["a2_candidates"] = {
                item["candidate_id"]: {
                    key: value for key, value in item["parameters"].items()
                    if key in {"v_limit", "a_limit", "j_limit", "minimum_duration"}
                }
                for item in records
            }
            state["a2_survivors"] = [item["candidate_id"] for item in passing]
            state["a2_confirmation_mapping"] = {
                f"A2-RANK-{rank:02d}": item["candidate_id"]
                for rank, item in enumerate(selected, 1)
            }
            payload["confirmation_mapping"] = state["a2_confirmation_mapping"]
        elif args.stage == "A2_CONFIRMATION":
            winner = passing[0]
            concrete_id = state["a2_confirmation_mapping"][winner["candidate_id"]]
            state["a2_winner_id"] = concrete_id
            state["a2_winner"] = state["a2_candidates"][concrete_id]
            payload["winner"] = {**winner, "concrete_candidate_id": concrete_id}
    ranking_path = save_ranking(args.artifact_root, args.stage, payload)
    args.state.write_text(json.dumps(state, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({
        "stage": args.stage,
        "campaign_status": state.get("campaign_status", "RUNNING"),
        "ranking": str(ranking_path),
    }, sort_keys=True))


if __name__ == "__main__":
    main()
