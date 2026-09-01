#!/usr/bin/env python3
"""Freeze compact, F0-only Family-B qualification evidence from retained attempts."""

from __future__ import annotations

import argparse
from collections import defaultdict
import hashlib
import json
import math
import os
from pathlib import Path
import sys
from typing import Any

import yaml

TOOLING = Path(__file__).resolve().parent
E3 = TOOLING.parent
FORMAL = E3.parent
RAW = E3 / "results/qualification/execution_deviation_raw"
GRID = E3 / "E3_v4_family_B_execution_deviation_grid.yaml"
OFFLINE = E3 / "E3_v4_family_B_execution_deviation_offline_audit.json"
ANALYSIS = FORMAL / "analysis_freeze/tooling"
INTERFACE = Path(
    "/home/yihuang/learning/LLM_swarm_ws/formal_install_v1/uav_swarm_interfaces"
)
sys.path[:0] = [
    str(INTERFACE / "local/lib/python3.10/dist-packages"), str(ANALYSIS)
]
os.environ["LD_LIBRARY_PATH"] = ":".join(filter(None, (
    str(INTERFACE / "lib"), os.environ.get("LD_LIBRARY_PATH", "")
)))

from rosbag_evidence import read_bag  # noqa: E402


def file_sha(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def canonical_sha(value: Any) -> str:
    return hashlib.sha256(json.dumps(
        value, sort_keys=True, separators=(",", ":")
    ).encode()).hexdigest()


def retry_rank(manifest: dict[str, Any]) -> int:
    value = manifest.get("retry_suffix")
    return int(value[1:]) if isinstance(value, str) and value.startswith("r") else 0


def registered_order(grid: dict[str, Any]) -> list[tuple[str, str, int]]:
    return [
        (candidate, condition, int(seed))
        for candidate in grid["execution_order"]["candidate_order"]
        for condition in grid["qualification_population"]["conditions"]
        for seed in grid["qualification_population"]["seeds"]
    ]


def point(message) -> tuple[float, float, float]:
    value = message.pose.pose.position
    return float(value.x), float(value.y), float(value.z)


def staging_audit(
    attempt_dir: Path, spec: dict[str, Any], stage: dict[str, Any]
) -> dict[str, Any]:
    gate = stage.get("stage_global_geometry_gate")
    if gate and gate.get("verified") is True:
        positions = {
            int(uid): tuple(float(x) for x in value)
            for uid, value in gate["final_global_positions_m"].items()
        }
        source = "online_fail_closed_stage_gate"
        statuses = stage.get("final_status", {})
        stable = all(
            value is not None
            and bool(value.get("is_hover_stable"))
            and not bool(value.get("failsafe", False))
            for value in statuses.values()
        ) and len(statuses) == len(positions)
    else:
        interaction = json.loads(
            (attempt_dir / "raw/interaction_result.json").read_text()
        )
        mission = int(interaction["mission_id"])
        topics = tuple(
            [f"/uav{uid}/startup_event" for uid in spec["uav_ids"]]
            + [f"/uav{uid}/swarm_state" for uid in spec["uav_ids"]]
            + [f"/uav{uid}/status" for uid in spec["uav_ids"]]
        )
        records = read_bag(
            attempt_dir / "raw/rosbag", lambda topic: topic in topics
        )
        acceptances = [
            record for record in records
            if record.topic.endswith("/startup_event")
            and int(record.message.mission_id) == mission
            and str(record.message.event) == "command_accepted"
        ]
        if not acceptances:
            raise RuntimeError("nominal interaction acceptance unavailable")
        t0 = min(float(record.timestamp) for record in acceptances)
        positions = {}
        for uid in spec["uav_ids"]:
            samples = [
                record for record in records
                if record.topic == f"/uav{uid}/swarm_state"
            ]
            if not samples:
                raise RuntimeError(f"uav{uid} staging position unavailable")
            sample = min(samples, key=lambda item: abs(float(item.timestamp) - t0))
            if abs(float(sample.timestamp) - t0) > 0.10:
                raise RuntimeError(f"uav{uid} staging position is stale")
            positions[int(uid)] = point(sample.message)
        stage_mission = int(stage["mission_id"])
        boundary_status = {}
        for uid in spec["uav_ids"]:
            samples = [
                record for record in records
                if record.topic == f"/uav{uid}/status"
                and float(record.timestamp) < t0
                and int(record.message.mission_id) == stage_mission
            ]
            if not samples:
                raise RuntimeError(f"uav{uid} pre-interaction stage status unavailable")
            sample = max(samples, key=lambda item: float(item.timestamp))
            if t0 - float(sample.timestamp) > 0.20:
                raise RuntimeError(f"uav{uid} pre-interaction stage status is stale")
            boundary_status[int(uid)] = sample.message
        stable = all(
            bool(value.is_hover_stable) and not bool(value.failsafe)
            for value in boundary_status.values()
        )
        source = "posthoc_interaction_boundary_from_retained_bag"
    expected = {
        int(uid): tuple(float(x) for x in value)
        for uid, value in zip(spec["uav_ids"], spec["initial_positions_m"])
    }
    errors = {
        str(uid): math.dist(positions[uid], expected[uid]) for uid in expected
    }
    maximum = max(errors.values())
    return {
        "verified": maximum <= 0.30 and stable,
        "source": source,
        "position_tolerance_m": 0.30,
        "per_uav_position_error_m": errors,
        "maximum_position_error_m": maximum,
        "frozen_controller_stable_and_no_failsafe": stable,
    }


def candidate_summary(
    candidate: str, selected: list[dict[str, Any]], grid: dict[str, Any]
) -> dict[str, Any]:
    by_condition = defaultdict(list)
    for item in selected:
        if item["candidate_id"] == candidate:
            by_condition[item["condition"]].append(item)
    conditions = {}
    all_attempts = []
    for condition in grid["qualification_population"]["conditions"]:
        items = sorted(by_condition[condition], key=lambda item: item["seed"])
        all_attempts.extend(items)
        conditions[condition] = {
            "n": len(items),
            "event_seed_count": sum(
                item["attribution"]["intended_pair_event_count"] > 0
                and item["attribution"]["intended_pair_exposure_s"] > 0
                for item in items
            ),
            "mission_success_count": sum(
                item["stability"]["mission_success"] for item in items
            ),
            "d_min_m": [item["realized"]["d_min_m"] for item in items],
            "intended_pair_exposure_s": [
                item["attribution"]["intended_pair_exposure_s"] for item in items
            ],
            "minimum_pairs": [item["realized"]["d_min_pair"] for item in items],
            "maximum_staging_error_m": max(
                (item["staging_geometry"]["maximum_position_error_m"] for item in items),
                default=None,
            ),
        }
    planning = all(
        item["predicted"]["hard_violations"] == 0
        and item["predicted"]["d_min_m"] >= 1.80 - 1e-6
        for item in all_attempts
    )
    delivery = len(all_attempts) == 10 and all(
        item["manipulation_delivery"]["verified"] for item in all_attempts
    )
    staging = len(all_attempts) == 10 and all(
        item["staging_geometry"]["verified"] for item in all_attempts
    )
    intended = len(all_attempts) == 10 and all(
        item["attribution"]["only_intended_pair_has_hard_events"]
        and item["attribution"]["intended_pair_is_global_minimum"]
        and item["attribution"]["intended_events_after_manipulation_start"]
        for item in all_attempts
    )
    events = all(
        3 <= conditions[condition]["event_seed_count"] <= 5
        for condition in conditions
    )
    preactivation = all(
        item.get("pre_activation") is None
        or item["pre_activation"]["hard_risk_event_count"] == 0
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
        "planning_safe": planning,
        "deterministic_delivery": delivery,
        "staging_geometry": staging,
        "residual_risk_prevalence": events,
        "nonzero_exposure": events,
        "intended_pair_attribution": intended,
        "B02_pre_activation_safe": preactivation,
        "recoverable": recoverable,
    }
    return {
        "candidate_id": candidate,
        "mechanism": grid["candidates"][candidate]["mechanism"],
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
    by_trial = defaultdict(list)
    for value in manifests:
        by_trial[value["trial_id"]].append(value)

    selected_metrics = []
    adjudication = []
    missing = []
    for candidate, condition, seed in registered_order(grid):
        trial = f"E3V4B-{candidate}__{condition}__S{seed}"
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
            if status != "success" or not (attempt_dir / "qualification_metrics.json").is_file():
                record.update({"scientific_eligible": False,
                               "reason": "recorded_infrastructure_failure"})
                adjudication.append(record)
                continue
            metrics = json.loads((attempt_dir / "qualification_metrics.json").read_text())
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
    for mechanism, prefix in (("command_delay", "B01"), ("reference_deviation", "B02")):
        passing = [
            value for value in summaries
            if value["mechanism"] == mechanism and value["qualified"]
        ]
        def deviation_magnitude(item: dict[str, Any]) -> float:
            registered = grid["candidates"][item["candidate_id"]]
            if "delay_s" in registered:
                return float(registered["delay_s"])
            return math.dist(registered["offset_m"], [0, 0, 0])

        passing.sort(key=lambda item: (
            deviation_magnitude(item), item["candidate_id"]
        ))
        chosen[prefix] = passing[0]["candidate_id"] if passing else None

    F1 = sum(
        manifest.get("condition") in ("P0_F1", "P1_F1")
        or (manifest.get("metrics") or {}).get("feedback") == "F1"
        for manifest in manifests
    )
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
        "schema": "E3_v4_family_B_execution_deviation_qualification_evidence_v1",
        "status": "PASS" if not missing and all(chosen.values()) else "BLOCKED",
        "dataset_class": "calibration_pilot",
        "accepted_formal_result": False,
        "formal_cursor_consumed": False,
        "grid_sha256": file_sha(GRID),
        "offline_planning_audit_sha256": file_sha(OFFLINE),
        "registered_attempt_count": 60,
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
    args.output.write_text(
        json.dumps(evidence, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    )
    print(json.dumps({
        "status": evidence["status"], "selected": chosen,
        "missing": missing, "retained": len(manifests),
        "F1": F1, "formal": formal,
    }, sort_keys=True))
    return 0 if evidence["status"] == "PASS" else 2


if __name__ == "__main__":
    raise SystemExit(main())
