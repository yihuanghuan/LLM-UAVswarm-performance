#!/usr/bin/env python3
"""Freeze compact F0-only evidence for the preregistered Family-C grid."""

from __future__ import annotations

import argparse
from collections import defaultdict
import json
import math
from pathlib import Path
from typing import Any

import yaml

from e3_v4_execution_deviation_freeze import (
    canonical_sha, file_sha, retry_rank, staging_audit,
)

TOOLING = Path(__file__).resolve().parent
E3 = TOOLING.parent
RAW = E3 / "results/qualification/family_C_execution_deviation_raw"
GRID = E3 / "E3_v4_family_C_execution_deviation_grid.yaml"
OFFLINE = E3 / "E3_v4_family_C_execution_deviation_offline_audit.json"


def registered_order(grid: dict[str, Any]) -> list[tuple[str, str, int]]:
    return [
        (candidate, condition, int(seed))
        for candidate in grid["execution_order"]["candidate_order"]
        for condition in grid["qualification_population"]["conditions"]
        for seed in grid["qualification_population"]["seeds"]
    ]


def candidate_summary(
    candidate: str, selected: list[dict[str, Any]], grid: dict[str, Any]
) -> dict[str, Any]:
    registered = grid["candidates"][candidate]
    intended_pair = "-".join(map(str, sorted(registered["intended_pair"])))
    by_condition: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for item in selected:
        if item["candidate_id"] == candidate:
            by_condition[item["condition"]].append(item)
    conditions: dict[str, Any] = {}
    all_attempts: list[dict[str, Any]] = []
    for condition in grid["qualification_population"]["conditions"]:
        items = sorted(by_condition[condition], key=lambda item: item["seed"])
        all_attempts.extend(items)
        pair_values = [item["realized"]["pair_diagnostics"][intended_pair]
                       for item in items]
        conditions[condition] = {
            "n": len(items),
            "intended_pair_event_seed_count": sum(
                value["event_count"] > 0 and value["exposure_duration_s"] > 0
                for value in pair_values
            ),
            "mission_success_count": sum(
                item["stability"]["mission_success"] for item in items
            ),
            "actual_d_min_m": [item["realized"]["d_min_m"] for item in items],
            "minimum_pairs": [item["realized"]["d_min_pair"] for item in items],
            "intended_pair_d_min_m": [
                value["minimum_distance_m"] for value in pair_values
            ],
            "intended_pair_event_count": [value["event_count"] for value in pair_values],
            "intended_pair_exposure_s": [
                value["exposure_duration_s"] for value in pair_values
            ],
            "maximum_staging_error_m": max(
                (item["staging_geometry"]["maximum_position_error_m"] for item in items),
                default=None,
            ),
        }
    planning = len(all_attempts) == 10 and all(
        (
            item["condition"] == "P0_F0"
            and item["predicted"]["hard_violations"] >= 1
        ) or (
            item["condition"] == "P1_F0"
            and item["predicted"]["hard_violations"] == 0
            and item["predicted"]["d_min_m"] >= 1.80 - 1e-6
        ) for item in all_attempts
    )
    delivery = len(all_attempts) == 10 and all(
        item["manipulation_delivery"]["verified"] for item in all_attempts
    )
    staging = len(all_attempts) == 10 and all(
        item["staging_geometry"]["verified"] for item in all_attempts
    )
    residual_events = all(
        3 <= conditions[condition]["intended_pair_event_seed_count"] <= 5
        for condition in conditions
    )
    intended = len(all_attempts) == 10 and all(
        item["attribution"]["intended_events_after_manipulation_start"]
        for item in all_attempts
    ) and all(
        item["attribution"]["only_intended_pair_has_hard_events"]
        for item in all_attempts if item["condition"] == "P1_F0"
    )
    preactivation = all(
        item.get("pre_activation") is None
        or item["pre_activation"]["hard_risk_pair_diagnostics"][intended_pair][
            "event_count"
        ] == 0
        for item in all_attempts
    )
    recoverable = all(
        conditions[condition]["mission_success_count"] >= 4
        for condition in conditions
    ) and all(
        not item["stability"]["failsafe_seen"]
        and not item["stability"]["actual_d_min_le_0p25_m"]
        and not item["stability"]["saturation_dominated"]
        for item in all_attempts
    )
    gates = {
        "mixed_planning_manipulation": planning,
        "deterministic_delivery": delivery,
        "staging_geometry": staging,
        "residual_risk_prevalence_both_P0_and_P1": residual_events,
        "nonzero_intended_pair_exposure": residual_events,
        "intended_pair_attribution": intended,
        "C02_pre_activation_intended_pair_safe": preactivation,
        "recoverable": recoverable,
    }
    return {
        "candidate_id": candidate,
        "mechanism": registered["mechanism"],
        "intended_pair": intended_pair,
        "conditions": conditions,
        "gates": gates,
        "qualified": all(gates.values()),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    grid = yaml.safe_load(GRID.read_text())
    offline = json.loads(OFFLINE.read_text())
    if offline.get("status") != "PASS":
        raise RuntimeError("offline planning audit is not PASS")
    if grid["F1_permitted"] is not False or grid["formal_execution_permitted"] is not False:
        raise RuntimeError("qualification grid is not sealed")

    manifests = []
    for path in sorted(RAW.glob("*/attempt.json")):
        value = json.loads(path.read_text())
        value["_path"] = path
        manifests.append(value)
    by_trial: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for value in manifests:
        by_trial[value["trial_id"]].append(value)

    selected_metrics = []
    adjudication = []
    missing = []
    for candidate, condition, seed in registered_order(grid):
        trial = f"E3V4C-{candidate}__{condition}__S{seed}"
        valid = []
        for manifest in sorted(by_trial[trial], key=retry_rank):
            attempt_dir = manifest["_path"].parent
            status = manifest.get("attempt_status")
            record = {
                "attempt_instance_id": manifest.get("attempt_instance_id"),
                "registered_trial_id": trial,
                "recorded_status": status,
                "retry_rank": retry_rank(manifest),
                "attempt_manifest_sha256": file_sha(manifest["_path"]),
            }
            metrics_path = attempt_dir / "qualification_metrics.json"
            if status != "success" or not metrics_path.is_file():
                record.update({"scientific_eligible": False,
                               "reason": "recorded_infrastructure_failure"})
                adjudication.append(record)
                continue
            metrics = json.loads(metrics_path.read_text())
            spec = json.loads((attempt_dir / "raw/runtime_spec.json").read_text())
            stage = json.loads((attempt_dir / "raw/stage_result.json").read_text())
            audit = staging_audit(attempt_dir, spec, stage)
            metrics["staging_geometry"] = audit
            metrics["attempt_instance_id"] = manifest["attempt_instance_id"]
            metrics["attempt_manifest_sha256"] = record["attempt_manifest_sha256"]
            record.update({
                "scientific_eligible": bool(audit["verified"]),
                "reason": "eligible" if audit["verified"] else "invalid_staging_geometry",
                "staging_geometry": audit,
            })
            adjudication.append(record)
            if audit["verified"]:
                valid.append(metrics)
        if not valid:
            missing.append(trial)
        else:
            selected_metrics.append(valid[-1])

    summaries = [
        candidate_summary(candidate, selected_metrics, grid)
        for candidate in grid["execution_order"]["candidate_order"]
    ]
    chosen = {}
    for scenario, mechanism in (("C01", "command_delay"),
                                ("C02", "reference_deviation")):
        passing = [value for value in summaries
                   if value["mechanism"] == mechanism and value["qualified"]]

        def magnitude(item: dict[str, Any]) -> float:
            value = grid["candidates"][item["candidate_id"]]
            return float(value["delay_s"]) if "delay_s" in value else math.dist(
                value["offset_m"], [0, 0, 0]
            )

        passing.sort(key=lambda item: (magnitude(item), item["candidate_id"]))
        chosen[scenario] = passing[0]["candidate_id"] if passing else None

    F1 = sum(manifest.get("condition") in ("P0_F1", "P1_F1") for manifest in manifests)
    formal = sum(
        manifest.get("accepted_formal_result") is True
        or manifest.get("dataset_class") == "formal"
        for manifest in manifests
    )
    compact_inventory = {
        manifest["attempt_instance_id"]: {
            "attempt_manifest_sha256": file_sha(manifest["_path"]),
            "raw_inventory_sha256": (manifest.get("metrics") or {}).get(
                "raw_inventory_sha256"
            ),
            "attempt_status": manifest.get("attempt_status"),
        } for manifest in manifests
    }
    evidence = {
        "schema": "E3_v4_family_C_execution_deviation_qualification_evidence_v1",
        "status": "PASS" if not missing and all(chosen.values()) else "BLOCKED",
        "dataset_class": "calibration_pilot",
        "accepted_formal_result": False,
        "formal_cursor_consumed": False,
        "grid_sha256": file_sha(GRID),
        "offline_planning_audit_sha256": file_sha(OFFLINE),
        "registered_attempt_count": 40,
        "retained_attempt_instance_count": len(manifests),
        "selected_scientific_attempt_count": len(selected_metrics),
        "missing_registered_trials": missing,
        "adjudication": adjudication,
        "candidate_summaries": summaries,
        "selected_candidates": chosen,
        "F1_attempt_count": F1,
        "formal_attempt_count": formal,
        "raw_data_retained_at": str(RAW.relative_to(E3)),
        "compact_raw_inventory": compact_inventory,
        "compact_raw_inventory_sha256": canonical_sha(compact_inventory),
    }
    if F1 or formal:
        raise RuntimeError("sealed F0/non-formal invariant violated")
    args.output.write_text(json.dumps(
        evidence, ensure_ascii=False, indent=2, sort_keys=True
    ) + "\n")
    print(json.dumps({
        "status": evidence["status"], "selected": chosen,
        "missing": missing, "retained": len(manifests),
        "F1": F1, "formal": formal,
    }, sort_keys=True))
    return 0 if evidence["status"] == "PASS" else 2


if __name__ == "__main__":
    raise SystemExit(main())
