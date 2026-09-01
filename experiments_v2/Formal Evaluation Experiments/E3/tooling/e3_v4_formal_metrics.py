#!/usr/bin/env python3
"""Extract registered E3-v4 metrics from a future formal raw attempt."""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path

import numpy as np

from e3_v4_execution_deviation_metrics import (
    acceptance_records, command_payload, command_records, planning_commitment,
    pairwise_distance_metrics, raw_inventory, read_bag, vector,
    verify_delay, verify_reference,
)


def verify_none(records, spec: dict, interaction: dict) -> dict:
    mission = int(interaction["mission_id"])
    commands = {
        int(uid): command_records(records, int(uid), mission)
        for uid in spec["uav_ids"]
    }
    one_each = all(len(value) == 1 for value in commands.values())
    times = [value[0].timestamp for value in commands.values() if len(value) == 1]
    common = bool(times) and max(times) - min(times) <= 1e-6
    acknowledgments = {
        str(uid): [float(value.timestamp) for value in acceptance_records(
            records, int(uid), mission
        )] for uid in spec["uav_ids"]
    }
    ack = all(value for value in acknowledgments.values())
    commitment = planning_commitment(records, spec, min(times) if times else math.inf)
    return {
        "mechanism": "none",
        "verified": bool(one_each and common and ack and commitment["verified"]),
        "exactly_one_nominal_command_per_uav": one_each,
        "common_nominal_command_timestamp": common,
        "controller_acceptance_verified": ack,
        "acceptance_timestamps_s": acknowledgments,
        "command_payloads": {
            str(uid): [command_payload(value) for value in commands[int(uid)]]
            for uid in spec["uav_ids"]
        },
        "planning_commitment": commitment,
    }


def extract(raw_dir: Path) -> dict:
    raw_dir = raw_dir.resolve()
    spec = json.loads((raw_dir / "runtime_spec.json").read_text())
    interaction = json.loads((raw_dir / "interaction_result.json").read_text())
    physical = json.loads((raw_dir / "physical_result.json").read_text())
    if spec.get("dataset_class") != "formal_evaluation":
        raise ValueError("formal extractor refuses non-formal data")
    if spec.get("accepted_formal_result") is not True:
        raise ValueError("formal accepted-result marker missing")
    if spec.get("condition") not in ("P0_F0", "P0_F1", "P1_F0", "P1_F1"):
        raise ValueError("unregistered factorial condition")
    suffixes = (
        "/execution_command", "/startup_event", "/control_tracking_debug",
        "/swarm_state", "/status", "/manipulation_event",
    )
    records = read_bag(raw_dir / "rosbag", lambda topic: topic.endswith(suffixes))
    mechanism = spec["manipulation"]["type"]
    if mechanism == "none":
        delivery = verify_none(records, spec, interaction)
    elif mechanism == "command_delay":
        delivery = verify_delay(records, spec, interaction)
    elif mechanism == "reference_deviation":
        delivery = verify_reference(records, spec, interaction)
    else:
        raise ValueError(f"unsupported manipulation: {mechanism}")
    if not delivery["verified"]:
        raise ValueError("registered manipulation/commitment delivery not verified")

    mission = int(interaction["mission_id"])
    acceptances = [
        record for uid in spec["uav_ids"]
        for record in acceptance_records(records, int(uid), mission)
    ]
    if not acceptances:
        raise ValueError("nominal controller-acceptance evidence missing")
    t0 = min(record.timestamp for record in acceptances)
    end = t0 + float(spec["duration_s"]) + 2.0
    distance, coverage = pairwise_distance_metrics(
        records, [int(value) for value in spec["uav_ids"]], t0, end,
        float(spec["allocator_diagnostics"]["d_hard"]),
    )
    risk = distance["hard_risk_pair_diagnostics"]
    intended_key = (
        "-".join(map(str, sorted(spec["intended_pair"])))
        if spec.get("intended_pair") else None
    )
    intended = risk.get(intended_key) if intended_key else None
    event_pairs = [
        pair for pair, detail in risk.items() if int(detail["event_count"]) > 0
    ]
    if mechanism in ("none", "command_delay"):
        manipulation_start = t0
    else:
        bias_mission = int(interaction["bias_mission_id"])
        affected = int(spec["manipulation"]["affected_uav"])
        bias_acceptances = acceptance_records(records, affected, bias_mission)
        if not bias_acceptances:
            raise ValueError("bias acceptance unavailable for realized-time alignment")
        manipulation_start = min(record.timestamp for record in bias_acceptances)
    pre_activation = None
    if mechanism == "reference_deviation":
        pre_distance, pre_coverage = pairwise_distance_metrics(
            records, [int(value) for value in spec["uav_ids"]], t0,
            manipulation_start, float(spec["allocator_diagnostics"]["d_hard"]),
        )
        pre_activation = {
            "d_min_m": float(pre_distance["actual_d_min"]["value"]),
            "d_min_pair": pre_distance["actual_d_min"]["pair"],
            "hard_risk_event_count": int(pre_distance["hard_risk_event_count"]["value"]),
            "hard_risk_exposure_pair_s": float(
                pre_distance["hard_risk_exposure_duration"]["value"]
            ),
            "hard_risk_pair_diagnostics": pre_distance["hard_risk_pair_diagnostics"],
            "coverage": pre_coverage,
        }
    statuses = [record for record in records if record.topic.endswith("/status")]
    failsafe = any(bool(record.message.failsafe) for record in statuses)
    debug = [
        record for record in records
        if record.topic.endswith("/control_tracking_debug")
        and t0 <= record.timestamp <= end
    ]
    near_limit = [bool(np.any(np.abs(vector(record.message.ladrc_output)) >= 4.95))
                  for record in debug]
    saturation_fraction = float(sum(near_limit) / len(near_limit)) if near_limit else None
    inventory, inventory_sha = raw_inventory(raw_dir)
    return {
        "schema": "E3_v4_formal_attempt_metrics_v1",
        "dataset_class": "formal_evaluation",
        "accepted_formal_result": True,
        "formal_cursor_consumed": False,
        "trial_id": spec["trial_id"],
        "scenario_id": spec["scenario_id"],
        "condition": spec["condition"],
        "feedback": "F1" if spec["avoidance_mode"] != "off" else "F0",
        "seed": int(spec["seed"]),
        "predicted": {
            "d_min_m": float(spec["allocator_diagnostics"]["min_distance"]),
            "hard_violations": int(spec["allocator_diagnostics"]["hard_violations"]),
            "assignment": spec["allocator_diagnostics"]["final_assignment"],
        },
        "realized": {
            "d_min_m": float(distance["actual_d_min"]["value"]),
            "d_min_pair": distance["actual_d_min"]["pair"],
            "d_min_time_relative_s": float(distance["actual_d_min"]["timestamp"] - t0),
            "hard_risk_event_count": int(distance["hard_risk_event_count"]["value"]),
            "hard_risk_exposure_pair_s": float(
                distance["hard_risk_exposure_duration"]["value"]
            ),
            "any_pair_hard_risk_duration_s": float(
                distance["any_pair_hard_risk_duration"]["value"]
            ),
            "pair_diagnostics": risk,
        },
        "attribution": {
            "intended_pair": intended_key,
            "intended_pair_event_count": int(intended["event_count"]) if intended else None,
            "intended_pair_exposure_s": float(intended["exposure_duration_s"]) if intended else None,
            "intended_pair_is_global_minimum": (
                distance["actual_d_min"]["pair"] == intended_key
                if intended_key else None
            ),
            "pairs_with_hard_events": event_pairs,
        },
        "manipulation_delivery": delivery,
        "pre_activation": pre_activation,
        "coverage": coverage,
        "stability": {
            "physical_attempt_status": physical.get("attempt_status"),
            "interaction_termination_reason": interaction.get("termination_reason"),
            "mission_success": bool(
                physical.get("attempt_status") == "success"
                and interaction.get("success")
                and interaction.get("termination_reason") == "SUCCESS"
                and not failsafe
            ),
            "failsafe_seen": failsafe,
            "actual_d_min_le_0p25_m": float(distance["actual_d_min"]["value"]) <= 0.25,
            "control_debug_sample_count": len(debug),
            "near_acceleration_limit_sample_fraction": saturation_fraction,
            "saturation_dominated": (
                saturation_fraction is not None and saturation_fraction >= 0.20
            ),
        },
        "runtime_spec_sha256": spec["runtime_spec_sha256"],
        "raw_inventory": inventory,
        "raw_inventory_sha256": inventory_sha,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("raw_dir", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = extract(args.raw_dir)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    print(json.dumps({"trial_id": result["trial_id"], "status": "PASS"}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
