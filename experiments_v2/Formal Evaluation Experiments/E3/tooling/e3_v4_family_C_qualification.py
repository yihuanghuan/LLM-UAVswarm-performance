#!/usr/bin/env python3
"""Append-only, F0-only qualification for E3-v4 deterministic Family C."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
import subprocess
from typing import Any

import yaml

from e3_trial_registry import POLICY_PATH, canonical_sha256, sha256_file
from e3_v4_execution_deviation_qualification import (
    ALLOWED, E3_DIR, OLD_REGISTRY_PATH, REPO_ROOT, SEEDS_PATH,
    QualificationError, build_deviation_runtime_spec, execute_spec, load_yaml,
)

GRID_PATH = E3_DIR / "E3_v4_family_C_execution_deviation_grid.yaml"
DEFAULT_OUTPUT = E3_DIR / "results/qualification/family_C_execution_deviation_raw"


def git(*args: str) -> str:
    return subprocess.check_output(["git", *args], cwd=REPO_ROOT, text=True).strip()


def validate_registration(candidate_id: str, condition: str, seed: int):
    if condition not in ALLOWED:
        raise QualificationError("Family-C qualification is sealed to P0_F0/P1_F0")
    grid, seeds = load_yaml(GRID_PATH), load_yaml(SEEDS_PATH)
    if grid.get("status") != "FROZEN_BEFORE_PHYSICAL_SCREENING":
        raise QualificationError("Family-C grid is not frozen")
    if grid.get("F1_permitted") is not False or grid.get("formal_execution_permitted") is not False:
        raise QualificationError("Family-C grid is not sealed against F1/formal")
    if candidate_id not in grid["candidates"]:
        raise QualificationError(f"unregistered Family-C candidate: {candidate_id}")
    registered = [int(value) for value in grid["qualification_population"]["seeds"]]
    if int(seed) not in registered or registered != [int(value) for value in seeds["seeds"]]:
        raise QualificationError("unregistered or inconsistent qualification seed")
    dirty = git("status", "--porcelain", "--", str(GRID_PATH.relative_to(REPO_ROOT)))
    if dirty:
        raise QualificationError("physical execution refused for uncommitted Family-C grid")
    commit = git("log", "-1", "--format=%H", "--", str(GRID_PATH.relative_to(REPO_ROOT)))
    if not commit:
        raise QualificationError("physical execution refused before Family-C grid commit")
    return grid, grid["candidates"][candidate_id], commit


def build_candidate_spec(candidate_id: str, condition: str, seed: int) -> dict[str, Any]:
    grid, candidate, prereg_commit = validate_registration(candidate_id, condition, seed)
    geometry = grid["geometries"][candidate["geometry"]]
    mapping = ALLOWED[condition]
    if candidate["mechanism"] == "command_delay":
        manipulation = {
            "type": "command_delay",
            "affected_uavs": [int(value) for value in candidate["affected_uavs"]],
            "reference_uavs": [int(value) for value in candidate["reference_uavs"]],
            "delay_s": float(candidate["delay_s"]),
            "timing_basis": "ROS simulation time and execution-command header stamps",
            "random_component": None,
        }
    elif candidate["mechanism"] == "reference_deviation":
        manipulation = {
            "type": "reference_deviation",
            "affected_uav": int(candidate["affected_uav"]),
            "intended_pair": [int(value) for value in candidate["intended_pair"]],
            "start_s": float(candidate["start_s"]),
            "duration_s": float(candidate["duration_s"]),
            "offset_m": [float(value) for value in candidate["offset_m"]],
            "endpoint_semantics": "counterfactual registered nominal reference at reset time plus offset",
            "reset_semantics": "new validated command to original committed target",
            "timing_basis": "ROS simulation time and execution-command header stamps",
            "random_component": None,
        }
    else:
        raise QualificationError("unsupported Family-C mechanism")
    ids = [int(value) for value in geometry["uav_ids"]]
    duration = float(geometry["duration_s"])
    spec = {
        "spec_type": "E3_v4_family_C_execution_deviation_qualification_spec_v1",
        "fixture_class": "E3_v4_family_C_execution_deviation_candidate",
        "dataset_class": "calibration_pilot",
        "accepted_formal_result": False,
        "result_notice": "NOT_FORMAL_RESULT",
        "formal_cursor_consumed": False,
        "trial_id": f"E3V4C-{candidate_id}__{condition}__S{int(seed)}",
        "candidate_id": candidate_id,
        "scenario_id": candidate["scenario_id"],
        "condition": condition,
        "seed": int(seed),
        "family": "C_mixed_structural_and_residual_risk",
        "uav_ids": ids,
        "initial_positions_m": geometry["initial_positions_m"],
        "ordered_targets_m": geometry["ordered_targets_m"],
        "duration_s": duration,
        "staging": {"stable_continuous_s": 2.0, "scored": False},
        "scoring": {"t0": "first nominal interaction execution-command header timestamp",
                    "end_offset_s": duration + 2.0},
        "timeout_after_t0_s": duration + 6.0,
        "assignment_mode": mapping["assignment_mode"],
        "avoidance_mode": mapping["avoidance_mode"],
        "invariants": {
            "style": "normal", "safety_s": 1.0, "q": {"mode": "direct"},
            "lfs_runtime_mode": "candidate_v2", "control_mode": "ladrc_acceleration",
            "policy": "lfs_policy.paper_current.yaml",
        },
        "disturbance": manipulation,
        "manipulation": manipulation,
        "intended_pair": [int(value) for value in candidate["intended_pair"]],
        "structural_component_uavs": geometry["structural_component_uavs"],
        "residual_component_uavs": geometry["residual_component_uavs"],
        "delivery_tolerances": grid["delivery_tolerances"],
        "preregistration_commit": prereg_commit,
        "metric_log_schema": {
            "primary_metrics": ["actual_d_min", "predicted_d_min", "hard_risk_events",
                                "hard_risk_exposure_duration", "mission_success",
                                "intended_pair_attribution", "manipulation_delivery"],
            "raw_required": ["clock", "execution_commands", "startup_events",
                             "per_uav_position_3d", "per_uav_nominal_reference",
                             "hard_failures", "manipulation_event_ledger"],
        },
    }
    spec["registered_input_hash"] = canonical_sha256({
        "grid_sha256": sha256_file(GRID_PATH),
        "seed_registry_sha256": sha256_file(SEEDS_PATH),
        "candidate": candidate, "geometry": geometry,
        "condition": condition, "seed": int(seed),
    })
    spec["resolved_execution_spec_hash"] = canonical_sha256(spec)
    return spec


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--candidate", required=True)
    parser.add_argument("--condition", required=True)
    parser.add_argument("--seed", required=True, type=int)
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--retry-suffix")
    parser.add_argument("--dry-run-spec", action="store_true")
    args = parser.parse_args()
    spec = build_candidate_spec(args.candidate, args.condition, args.seed)
    if args.dry_run_spec:
        value = build_deviation_runtime_spec(spec)
    else:
        if args.retry_suffix is not None and not re.fullmatch(r"r[1-9][0-9]*", args.retry_suffix):
            raise QualificationError("retry suffix must match r[1-9][0-9]*")
        value = execute_spec(
            spec, args.output_root, args.retry_suffix,
            grid_path=GRID_PATH, seeds_path=SEEDS_PATH,
        )
    print(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if value.get("attempt_status", "success") == "success" else 2


if __name__ == "__main__":
    raise SystemExit(main())
