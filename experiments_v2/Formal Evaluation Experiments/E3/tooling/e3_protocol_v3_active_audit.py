#!/usr/bin/env python3
"""Deterministic compile-only activation audit for authoritative E3 protocol v3."""

from __future__ import annotations

import argparse
from dataclasses import asdict
import copy
import hashlib
import itertools
import json
import math
from pathlib import Path
import platform
import sys
from typing import Any, Dict

from e3_formal_backend import build_runtime_spec
from e3_trial_registry import (
    CONDITIONS,
    CONDITION_MAPPING,
    GLOBAL_REGISTRY_PATH,
    GLOBAL_REGISTRY_SHA256,
    ORDER_PATH,
    ORDER_SHA256,
    POLICY_PATH,
    POLICY_SHA256,
    PROTOCOL_PATH,
    PROTOCOL_SHA256,
    REGISTRY_PATH,
    REGISTRY_SHA256,
    build_exact_spec,
    canonical_sha256,
    load_registry,
    registered_trial_ids,
    scenario_index,
)


E3_DIR = Path(__file__).resolve().parent.parent
FORMAL_DIR = E3_DIR.parent
REPO_ROOT = FORMAL_DIR.parents[1]
DEMO_HARNESS = FORMAL_DIR / "formal_equivalent_demos/tooling/runtime_demo.py"
EXPECTED_TARGETS = [
    [-3.0, 4.0, 3.0],
    [3.0, 4.0, 3.0],
    [-2.0, 12.0, 3.0],
    [0.0, 12.0, 3.0],
]
DEMO_COMPATIBILITY_TRIALS = [
    "E3-A-01__P0_F0__S53101", "E3-A-01__P1_F0__S53101",
    "E3-A-02__P0_F0__S53101", "E3-A-02__P1_F0__S53101",
    "E3-C-01__P0_F0__S53101", "E3-C-01__P1_F0__S53101",
    "E3-C-02__P0_F0__S53101", "E3-C-02__P1_F0__S53101",
]


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _imports():
    for path in (REPO_ROOT / "location_allocate", REPO_ROOT / "lfs_policy"):
        if str(path) not in sys.path:
            sys.path.insert(0, str(path))
    from location_allocate.motion_limits import minimum_jerk_peaks
    from location_allocate.policy_adapter import load_runtime_policy
    return minimum_jerk_peaks, load_runtime_policy


def _per_uav(initial, targets, permutation):
    rows = []
    for index, target_index in enumerate(permutation):
        delta = [targets[target_index][axis] - initial[index][axis] for axis in range(3)]
        rows.append({
            "uav_id": index + 1,
            "initial_m": initial[index],
            "target_index_zero_based": target_index,
            "target_label": target_index + 1,
            "target_m": targets[target_index],
            "displacement_vector_m": delta,
            "displacement_m": math.dist(initial[index], targets[target_index]),
        })
    return rows


def geometry_audit(registry, policy, safety):
    minimum_jerk_peaks, _ = _imports()
    scenario = scenario_index(registry)["E3-A-01"]
    initial = [
        [float(value) for value in scenario["initial_positions_m"][uid]]
        for uid in scenario["uav_ids"]
    ]
    targets = [
        [float(value) for value in scenario["ordered_targets_m"][uid]]
        for uid in scenario["uav_ids"]
    ]
    evaluator = policy.allocator_factory(safety.d_hard, safety.d_plan)
    exhaustive = []
    for permutation in itertools.permutations(range(4)):
        metrics = evaluator.evaluate(initial, targets, permutation, scenario["duration_s"])
        per_uav = _per_uav(initial, targets, permutation)
        maximum = max(row["displacement_m"] for row in per_uav)
        peaks = minimum_jerk_peaks(maximum, scenario["duration_s"])
        exhaustive.append({
            "permutation_zero_based": list(permutation),
            "permutation_target_labels": [value + 1 for value in permutation],
            "N_hard": metrics.hard_violations,
            "J_margin": metrics.margin_cost,
            "J_distance": metrics.distance,
            "predicted_minimum_3d_distance_m": metrics.min_distance,
            "maximum_displacement_m": maximum,
            "minimum_jerk_peaks": asdict(peaks),
            "motion_feasibility": (
                peaks.velocity <= policy.profile.motion_limits.velocity + 1e-12
                and peaks.acceleration <= policy.profile.motion_limits.acceleration + 1e-12
                and peaks.jerk <= policy.profile.motion_limits.jerk + 1e-12
            ),
        })
    assignments = {}
    for label, mode in (("P0", "distance_hungarian"), ("P1", "safety_aware")):
        allocator = policy.allocator_factory(safety.d_hard, safety.d_plan)
        _assigned, metrics = allocator.allocate_mode_with_metrics(
            initial, targets, scenario["duration_s"], mode=mode
        )
        permutation = list(allocator.last_assignment)
        exhaustive_row = next(
            row for row in exhaustive if row["permutation_zero_based"] == permutation
        )
        assignments[label] = {
            "assignment_mode": mode,
            "permutation_zero_based": permutation,
            "permutation_target_labels": [value + 1 for value in permutation],
            "per_uav": _per_uav(initial, targets, permutation),
            "N_hard": metrics.hard_violations,
            "J_margin": metrics.margin_cost,
            "J_distance": metrics.distance,
            "predicted_minimum_3d_distance_m": metrics.min_distance,
            "maximum_displacement_m": exhaustive_row["maximum_displacement_m"],
            "minimum_jerk_peaks": exhaustive_row["minimum_jerk_peaks"],
            "motion_feasibility": exhaustive_row["motion_feasibility"],
        }
    minimum_distance = min(row["J_distance"] for row in exhaustive)
    distance_optima = [
        row for row in exhaustive
        if abs(row["J_distance"] - minimum_distance) <= 1e-9
    ]
    global_lex = min(
        exhaustive,
        key=lambda row: (row["N_hard"], row["J_margin"], row["J_distance"]),
    )
    p0, p1 = assignments["P0"], assignments["P1"]
    checks = {
        "active_targets_equal_reviewed_targets": targets == EXPECTED_TARGETS,
        "A01_C01_targets_identical": (
            scenario["ordered_targets_m"]
            == scenario_index(registry)["E3-C-01"]["ordered_targets_m"]
        ),
        "P0_unique_distance_optimum": (
            len(distance_optima) == 1
            and distance_optima[0]["permutation_zero_based"] == p0["permutation_zero_based"]
        ),
        "P1_global_lexicographic_optimum": (
            global_lex["permutation_zero_based"] == p1["permutation_zero_based"]
        ),
        "P0_N_hard_2": p0["N_hard"] == 2,
        "P1_N_hard_0": p1["N_hard"] == 0,
        "P0_nonzero_motion": all(row["displacement_m"] > 0 for row in p0["per_uav"]),
        "P1_nonzero_motion": all(row["displacement_m"] > 0 for row in p1["per_uav"]),
        "P0_motion_feasible": p0["motion_feasibility"],
        "P1_motion_feasible": p1["motion_feasibility"],
    }
    return {
        "status": "PASS" if all(checks.values()) else "FAIL",
        "checks": checks,
        "assignments": assignments,
        "P0_distance_optimum_count": len(distance_optima),
        "global_lexicographic_best_permutation_zero_based": global_lex[
            "permutation_zero_based"
        ],
        "exhaustive_24_assignments": exhaustive,
    }


def build_report():
    import numpy
    import scipy

    minimum_jerk_peaks, load_runtime_policy = _imports()
    registry = load_registry()
    scenarios = scenario_index(registry)
    _config, policy = load_runtime_policy(POLICY_PATH)
    safety = policy.resolve_safety(1.0)
    geometry = geometry_audit(registry, policy, safety)
    cells = []
    cell_pass_count = 0
    for scenario_id, scenario in scenarios.items():
        for condition in CONDITIONS:
            spec = build_exact_spec(
                f"{scenario_id}__{condition}__S{registry['paired_seeds'][0]}"
            )
            runtime = build_runtime_spec(spec)
            diagnostics = runtime["allocator_diagnostics"]
            family = scenario["family"]
            disturbed = bool(scenario["disturbance"]["affected_uavs"])
            is_p0 = condition.startswith("P0")
            if family == "A_predictable_structural_risk":
                passed = (diagnostics["hard_violations"] > 0 if is_p0 else diagnostics["hard_violations"] == 0) and not disturbed
                intended_role = "predictable structural risk"
            elif family == "B_residual_execution_risk":
                passed = diagnostics["hard_violations"] == 0 and disturbed
                intended_role = "nominal-safe plus disturbance"
            elif family == "C_mixed_risk":
                passed = (diagnostics["hard_violations"] > 0 if is_p0 else diagnostics["hard_violations"] == 0) and disturbed
                intended_role = "structural risk plus disturbance"
            else:
                passed = False
                intended_role = "unknown"
            cell_pass_count += int(passed)
            cells.append({
                "scenario_id": scenario_id,
                "condition": condition,
                "family": family,
                "intended_role": intended_role,
                "assignment_mode": runtime["assignment_mode"],
                "avoidance_mode": runtime["avoidance_mode"],
                "duration_s": runtime["duration_s"],
                "registered_disturbance_present": disturbed,
                "permutation_zero_based": diagnostics["final_assignment"],
                "N_hard": diagnostics["hard_violations"],
                "J_margin": diagnostics["margin_cost"],
                "J_distance": diagnostics["distance"],
                "predicted_minimum_3d_distance_m": diagnostics["min_distance"],
                "status": "PASS" if passed else "FAIL",
            })

    trial_ids = registered_trial_ids()
    compile_failures = []
    compile_pass = 0
    for trial_id in trial_ids:
        try:
            spec = build_exact_spec(trial_id)
            identity = {
                "scenario_id": spec["scenario_id"],
                "condition": spec["condition"],
                "seed": spec["seed"],
            }
            expected = copy.deepcopy(spec)
            resolved_hash = expected.pop("resolved_execution_spec_hash")
            if resolved_hash != canonical_sha256(expected):
                raise RuntimeError("resolved execution spec hash mismatch")
            scenario = scenarios[identity["scenario_id"]]
            if spec["duration_s"] != float(scenario["duration_s"]):
                raise RuntimeError("duration mismatch")
            if spec["assignment_mode"] != CONDITION_MAPPING[identity["condition"]]["assignment_mode"]:
                raise RuntimeError("assignment mode mismatch")
            disturbance = scenario["disturbance"]
            if spec["disturbance"]["affected_uavs"] != disturbance["affected_uavs"]:
                raise RuntimeError("disturbance UAV mismatch")
            runtime = build_runtime_spec(spec)
            if len(runtime["profiles"]) != len(spec["uav_ids"]):
                raise RuntimeError("profile count mismatch")
            compile_pass += 1
        except Exception as exc:
            compile_failures.append({"trial_id": trial_id, "error": repr(exc)})

    demo_source = DEMO_HARNESS.read_text(encoding="utf-8")
    label_checks = {
        "dataset_class_engineering_validation": '"dataset_class": "engineering_validation"' in demo_source,
        "accepted_formal_result_false": '"accepted_formal_result": False' in demo_source,
        "result_notice": '"result_notice": NOTICE' in demo_source,
        "formal_cursor_consumed_false": '"formal_cursor_consumed": False' in demo_source,
    }
    demo_rows = []
    for trial_id in DEMO_COMPATIBILITY_TRIALS:
        spec = dict(build_exact_spec(trial_id))
        spec["dataset_class"] = "engineering_validation"
        runtime = build_runtime_spec(spec)
        demo_rows.append({
            "trial_id": trial_id,
            "spec_type": spec["spec_type"],
            "runtime_spec_type": runtime["runtime_spec_type"],
            "dataset_class": runtime["dataset_class"],
            "profile_count": len(runtime["profiles"]),
            "status": "PASS",
        })

    order = ORDER_PATH.read_text(encoding="utf-8").splitlines()
    global_e3 = [item for item in order if item.startswith("E3-")]
    population = {
        "scenario_count": len(scenarios),
        "condition_count": len(CONDITIONS),
        "seed_count": len(registry["paired_seeds"]),
        "trial_count": len(trial_ids),
        "unique_trial_count": len(set(trial_ids)),
        "global_order_count": len(order),
        "global_E3_membership_matches": set(global_e3) == set(trial_ids),
        "global_seed_registry_sha256": _sha(GLOBAL_REGISTRY_PATH),
        "global_seed_registry_hash_matches": _sha(GLOBAL_REGISTRY_PATH) == GLOBAL_REGISTRY_SHA256,
        "global_order_sha256": _sha(ORDER_PATH),
        "global_order_hash_matches": _sha(ORDER_PATH) == ORDER_SHA256,
    }
    numeric = {
        "python_executable": sys.executable,
        "python_version": platform.python_version(),
        "numpy_version": numpy.__version__,
        "scipy_version": scipy.__version__,
    }
    numeric_pass = (
        numeric["python_version"] == "3.10.12"
        and numeric["numpy_version"] == "1.24.4"
        and numeric["scipy_version"] == "1.8.0"
    )
    overall = (
        geometry["status"] == "PASS"
        and cell_pass_count == 24
        and compile_pass == 360
        and not compile_failures
        and all(label_checks.values())
        and all(row["status"] == "PASS" for row in demo_rows)
        and population["scenario_count"] == 6
        and population["condition_count"] == 4
        and population["seed_count"] == 15
        and population["trial_count"] == population["unique_trial_count"] == 360
        and population["global_order_count"] == 610
        and population["global_E3_membership_matches"]
        and population["global_seed_registry_hash_matches"]
        and population["global_order_hash_matches"]
        and numeric_pass
    )
    report = {
        "audit_type": "E3_protocol_v3_active_compile_only_audit_v1",
        "status": "PASS" if overall else "FAIL",
        "dataset_class": "engineering_validation",
        "accepted_formal_result": False,
        "result_notice": "NOT_FORMAL_RESULT",
        "formal_cursor_consumed": False,
        "live_execution_performed": False,
        "active_identity": {
            "protocol_path": str(PROTOCOL_PATH.relative_to(REPO_ROOT)),
            "protocol_sha256": PROTOCOL_SHA256,
            "registry_path": str(REGISTRY_PATH.relative_to(REPO_ROOT)),
            "registry_sha256": REGISTRY_SHA256,
            "policy_sha256": POLICY_SHA256,
        },
        "production_numeric_environment": numeric,
        "production_numeric_environment_status": "PASS" if numeric_pass else "FAIL",
        "reviewed_geometry_revalidation": geometry,
        "scenario_condition_audit": {
            "cell_count": len(cells),
            "pass_count": cell_pass_count,
            "fail_count": len(cells) - cell_pass_count,
            "cells": cells,
        },
        "production_compile_validation": {
            "checked": len(trial_ids),
            "pass_count": compile_pass,
            "fail_count": len(compile_failures),
            "failures": compile_failures,
        },
        "demo_harness_compile_only_compatibility": {
            "label_checks": label_checks,
            "classes_checked": demo_rows,
        },
        "population_invariants": population,
    }
    report["audit_sha256"] = canonical_sha256(report)
    return report


def render_markdown(report):
    geometry = report["reviewed_geometry_revalidation"]["assignments"]
    lines = [
        "# E3 protocol v3 active compile-only audit",
        "",
        f"Status: **{report['status']}**",
        "",
        "No PX4/Gazebo process or live demo was launched.",
        "",
        "## Reviewed four-UAV geometry",
        "",
        "| Mode | Permutation | N_hard | J_margin | J_distance | d_min (m) | D_max (m) | v/a/j peaks |",
        "|---|---|---:|---:|---:|---:|---:|---|",
    ]
    for label in ("P0", "P1"):
        row = geometry[label]
        peaks = row["minimum_jerk_peaks"]
        lines.append(
            f"| {label} | `{row['permutation_zero_based']}` | {row['N_hard']} | "
            f"{row['J_margin']:.12f} | {row['J_distance']:.12f} | "
            f"{row['predicted_minimum_3d_distance_m']:.12f} | "
            f"{row['maximum_displacement_m']:.12f} | "
            f"{peaks['velocity']:.12f} / {peaks['acceleration']:.12f} / {peaks['jerk']:.12f} |"
        )
    lines.extend([
        "",
        "## E3-wide validation",
        "",
        f"- Scenario-condition consistency: {report['scenario_condition_audit']['pass_count']}/{report['scenario_condition_audit']['cell_count']} PASS.",
        f"- Production compile: {report['production_compile_validation']['pass_count']}/{report['production_compile_validation']['checked']} PASS.",
        f"- Demo compile-only classes: {len(report['demo_harness_compile_only_compatibility']['classes_checked'])}/8 PASS.",
        "- Population: 6 scenarios × 4 conditions × 15 seeds = 360 trials; global order remains 610 entries.",
        "",
        f"Canonical audit SHA-256: `{report['audit_sha256']}`",
        "",
    ])
    return "\n".join(lines)


def main():
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
        "cells": report["scenario_condition_audit"]["pass_count"],
        "compiled": report["production_compile_validation"]["pass_count"],
        "audit_sha256": report["audit_sha256"],
    }, sort_keys=True))
    return 0 if report["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
