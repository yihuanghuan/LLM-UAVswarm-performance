#!/usr/bin/env python3
"""Compile-only consistency audit for the unactivated E3 v3 geometry candidate."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import platform
import sys
from typing import Any, Dict

import yaml

from e3_formal_backend import build_runtime_spec
from e3_trial_registry import (
    CONDITIONS,
    ORDER_PATH,
    POLICY_PATH,
    build_exact_spec,
    canonical_sha256,
)


E3_DIR = Path(__file__).resolve().parent.parent
FORMAL_DIR = E3_DIR.parent
V2_PROTOCOL = FORMAL_DIR / "protocols" / "E3_protocol_v2.yaml"
V2_REGISTRY = E3_DIR / "e3_factorial_registry_v2.yaml"
V3_PROTOCOL = FORMAL_DIR / "protocols" / "E3_protocol_v3_candidate.yaml"
V3_REGISTRY = E3_DIR / "e3_factorial_registry_v3_candidate.yaml"


def _yaml(path: Path) -> Dict[str, Any]:
    value = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise RuntimeError(f"expected mapping: {path}")
    return value


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _scenario_map(registry):
    return {item["scenario_id"]: item for item in registry["scenarios"]}


def _trial_ids(registry):
    return [
        f"{scenario['scenario_id']}__{condition}__S{seed}"
        for scenario in registry["scenarios"]
        for condition in CONDITIONS
        for seed in registry["paired_seeds"]
    ]


def build_report() -> Dict[str, Any]:
    import numpy
    import scipy

    v2 = _yaml(V2_REGISTRY)
    v3 = _yaml(V3_REGISTRY)
    v2_scenarios = _scenario_map(v2)
    v3_scenarios = _scenario_map(v3)
    v2_ids = _trial_ids(v2)
    v3_ids = _trial_ids(v3)
    global_order = ORDER_PATH.read_text(encoding="utf-8").splitlines()
    global_e3 = [item for item in global_order if item.startswith("E3-")]

    cells = []
    compiled = 0
    compile_failures = []
    representative = {}
    for scenario in v3["scenarios"]:
        scenario_id = scenario["scenario_id"]
        for condition in CONDITIONS:
            trial_id = f"{scenario_id}__{condition}__S{v3['paired_seeds'][0]}"
            spec = build_exact_spec(trial_id, registry=v3)
            runtime = build_runtime_spec(spec)
            diagnostics = runtime["allocator_diagnostics"]
            cell = {
                "scenario_id": scenario_id,
                "family": scenario["family"],
                "condition": condition,
                "assignment_mode": runtime["assignment_mode"],
                "avoidance_mode": runtime["avoidance_mode"],
                "duration_s": runtime["duration_s"],
                "permutation_zero_based": diagnostics["final_assignment"],
                "N_hard": diagnostics["hard_violations"],
                "J_margin": diagnostics["margin_cost"],
                "J_distance": diagnostics["distance"],
                "predicted_minimum_3d_distance_m": diagnostics["min_distance"],
                "profile_count": len(runtime["profiles"]),
                "compile_status": "PASS",
            }
            cells.append(cell)
            representative[(scenario_id, condition)] = cell

    for trial_id in v3_ids:
        try:
            build_runtime_spec(build_exact_spec(trial_id, registry=v3))
            compiled += 1
        except Exception as exc:  # retained in the audit if encountered
            compile_failures.append({"trial_id": trial_id, "error": repr(exc)})

    family_checks = []
    for scenario in v3["scenarios"]:
        scenario_id = scenario["scenario_id"]
        p0 = representative[(scenario_id, "P0_F0")]
        p1 = representative[(scenario_id, "P1_F0")]
        disturbed = bool(scenario["disturbance"]["affected_uavs"])
        family = scenario["family"]
        if family == "A_predictable_structural_risk":
            passed = (
                p0["N_hard"] > p1["N_hard"]
                and p1["N_hard"] == 0
                and not disturbed
            )
            interpretation = "predictable structural risk with P1 mitigation"
        elif family == "B_residual_execution_risk":
            passed = p0["N_hard"] == p1["N_hard"] == 0 and disturbed
            interpretation = "nominally safe assignment plus registered disturbance"
        elif family == "C_mixed_risk":
            passed = (
                p0["N_hard"] > p1["N_hard"]
                and p1["N_hard"] == 0
                and disturbed
            )
            interpretation = "structural risk with P1 mitigation plus disturbance"
        else:
            passed = False
            interpretation = "unknown family"
        family_checks.append({
            "scenario_id": scenario_id,
            "family": family,
            "registered_disturbance_present": disturbed,
            "P0_N_hard": p0["N_hard"],
            "P1_N_hard": p1["N_hard"],
            "P0_predicted_minimum_3d_distance_m": p0[
                "predicted_minimum_3d_distance_m"
            ],
            "P1_predicted_minimum_3d_distance_m": p1[
                "predicted_minimum_3d_distance_m"
            ],
            "interpretation": interpretation,
            "family_consistency": "PASS" if passed else "FAIL",
        })

    unaffected = ("E3-A-02", "E3-B-01", "E3-B-02", "E3-C-02")
    unaffected_checks = {
        scenario_id: v2_scenarios[scenario_id] == v3_scenarios[scenario_id]
        for scenario_id in unaffected
    }
    affected_invariants = {}
    for scenario_id in ("E3-A-01", "E3-C-01"):
        old, new = v2_scenarios[scenario_id], v3_scenarios[scenario_id]
        affected_invariants[scenario_id] = {
            "initial_positions_unchanged": (
                old["initial_positions_m"] == new["initial_positions_m"]
            ),
            "duration_unchanged": old["duration_s"] == new["duration_s"] == 6.0,
            "uav_ids_unchanged": old["uav_ids"] == new["uav_ids"],
            "disturbance_unchanged": old["disturbance"] == new["disturbance"],
            "candidate_targets_m": new["ordered_targets_m"],
        }

    population = {
        "scenario_count": len(v3["scenarios"]),
        "condition_count": len(CONDITIONS),
        "seed_count": len(v3["paired_seeds"]),
        "trial_count": len(v3_ids),
        "unique_trial_count": len(set(v3_ids)),
        "seeds_unchanged": v2["paired_seeds"] == v3["paired_seeds"],
        "trial_ids_unchanged": set(v2_ids) == set(v3_ids),
        "global_E3_membership_unchanged": set(global_e3) == set(v3_ids),
        "global_E3_order_unchanged": global_e3 == [
            item for item in global_order if item in set(v3_ids)
        ],
        "global_610_line_count": len(global_order),
        "global_order_sha256": _sha(ORDER_PATH),
    }
    overall_pass = (
        compiled == 360
        and not compile_failures
        and len(cells) == 24
        and all(item["family_consistency"] == "PASS" for item in family_checks)
        and all(unaffected_checks.values())
        and all(
            all(value for key, value in checks.items() if key != "candidate_targets_m")
            for checks in affected_invariants.values()
        )
        and population["scenario_count"] == 6
        and population["condition_count"] == 4
        and population["seed_count"] == 15
        and population["trial_count"] == population["unique_trial_count"] == 360
        and population["seeds_unchanged"]
        and population["trial_ids_unchanged"]
        and population["global_E3_membership_unchanged"]
        and population["global_610_line_count"] == 610
    )
    report = {
        "audit_type": "E3_protocol_v3_candidate_compile_only_consistency_audit_v1",
        "status": "PASS" if overall_pass else "FAIL",
        "dataset_class": "engineering_validation",
        "accepted_formal_result": False,
        "result_notice": "NOT_FORMAL_RESULT",
        "formal_cursor_consumed": False,
        "live_execution_performed": False,
        "candidate_not_frozen_or_activated": True,
        "production_environment": {
            "python_executable": sys.executable,
            "python_version": platform.python_version(),
            "numpy_version": numpy.__version__,
            "scipy_version": scipy.__version__,
        },
        "identities": {
            "v2_protocol_sha256": _sha(V2_PROTOCOL),
            "v2_registry_sha256": _sha(V2_REGISTRY),
            "v3_candidate_protocol_sha256": _sha(V3_PROTOCOL),
            "v3_candidate_registry_sha256": _sha(V3_REGISTRY),
            "policy_sha256": _sha(POLICY_PATH),
        },
        "compile_validation": {
            "registered_specs_checked": len(v3_ids),
            "pass_count": compiled,
            "fail_count": len(compile_failures),
            "failures": compile_failures,
        },
        "scenario_condition_cells": cells,
        "family_consistency": family_checks,
        "unaffected_scenarios_byte_semantically_identical": unaffected_checks,
        "affected_scenario_invariants": affected_invariants,
        "population_invariants": population,
    }
    report["audit_sha256"] = canonical_sha256(report)
    return report


def render_markdown(report: Dict[str, Any]) -> str:
    lines = [
        "# E3 protocol v3 candidate consistency audit",
        "",
        f"Status: **{report['status']}**",
        "",
        "This is compile-only engineering validation. The candidate is not frozen or active.",
        "",
        "## Scenario-family consistency",
        "",
        "| Scenario | Family | P0 N_hard | P1 N_hard | P0 d_min | P1 d_min | Disturbance | Result |",
        "|---|---|---:|---:|---:|---:|---|---|",
    ]
    for row in report["family_consistency"]:
        lines.append(
            f"| {row['scenario_id']} | {row['family']} | {row['P0_N_hard']} | "
            f"{row['P1_N_hard']} | {row['P0_predicted_minimum_3d_distance_m']:.6f} | "
            f"{row['P1_predicted_minimum_3d_distance_m']:.6f} | "
            f"{row['registered_disturbance_present']} | {row['family_consistency']} |"
        )
    compile_row = report["compile_validation"]
    population = report["population_invariants"]
    lines.extend([
        "",
        "## Compile and population invariants",
        "",
        f"- Production compile-only specs: {compile_row['pass_count']}/{compile_row['registered_specs_checked']} PASS.",
        f"- Population: {population['scenario_count']} scenarios × {population['condition_count']} conditions × {population['seed_count']} seeds = {population['trial_count']} trials.",
        f"- Trial IDs unchanged: {population['trial_ids_unchanged']}.",
        f"- Global order line count: {population['global_610_line_count']}; SHA-256 `{population['global_order_sha256']}`.",
        "- No physical runtime was launched.",
        "",
        f"Canonical audit SHA-256: `{report['audit_sha256']}`",
        "",
    ])
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--json-output", required=True, type=Path)
    parser.add_argument("--markdown-output", required=True, type=Path)
    args = parser.parse_args()
    report = build_report()
    args.json_output.write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    args.markdown_output.write_text(render_markdown(report), encoding="utf-8")
    print(json.dumps({
        "status": report["status"],
        "compiled": report["compile_validation"]["pass_count"],
        "audit_sha256": report["audit_sha256"],
    }, sort_keys=True))
    return 0 if report["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
