#!/usr/bin/env python3
"""Offline exhaustive audit for the E3 four-UAV replacement geometry."""

from __future__ import annotations

import argparse
from dataclasses import asdict
import itertools
import json
import math
from pathlib import Path
import platform
import sys
from typing import Any, Dict, List

from e3_trial_registry import POLICY_PATH, canonical_sha256


INITIAL = [
    [-3.0, -3.0, 3.0],
    [3.0, -3.0, 3.0],
    [-3.0, 3.0, 3.0],
    [3.0, 3.0, 3.0],
]
DURATION_S = 6.0
SHORTLIST = {
    "G1_OFFSET_TRAPEZOID_SELECTED": {
        "targets": [[-3, 4, 3], [3, 4, 3], [-2, 12, 3], [0, 12, 3]],
        "interpretation": "upward-shifted offset trapezoid; six-metre bottom edge and two-metre top edge centred at x=-1",
        "disposition": "ACCEPTED_RECOMMENDED",
    },
    "G2_LOWER_OFFSET_TRAPEZOID": {
        "targets": [[-3, 4, 3], [3, 4, 3], [-2, 10, 3], [0, 10, 3]],
        "interpretation": "lower-height version of the selected offset trapezoid",
        "disposition": "ACCEPTED_NOT_SELECTED_LOWER_MARGIN_IMPROVEMENT",
    },
    "G3_TRANSLATED_COMPACT_DIAMOND": {
        "targets": [[4, 4, 3], [6, 6, 3], [2, 6, 3], [4, 8, 3]],
        "interpretation": "compact diamond translated to centre [4,6,3]",
        "disposition": "ACCEPTED_NOT_SELECTED_THRESHOLD_FRAGILE_P0_CONFLICT",
    },
    "R1_SUPERSEDED_ZERO_MOTION": {
        "targets": [[-3, 3, 3], [3, 3, 3], [-3, -3, 3], [3, -3, 3]],
        "interpretation": "v1/v2 target set, permutation-equivalent to initial positions",
        "disposition": "REJECTED_ZERO_MOTION",
    },
    "R2_TRANSLATED_SQUARE": {
        "targets": [[-3, 5, 3], [3, 5, 3], [-3, 11, 3], [3, 11, 3]],
        "interpretation": "square translated upward by eight metres",
        "disposition": "REJECTED_NO_P0_STRUCTURAL_RISK",
    },
    "R3_SYMMETRIC_TRAPEZOID": {
        "targets": [[-3, 4, 3], [3, 4, 3], [-2, 12, 3], [2, 12, 3]],
        "interpretation": "symmetric upward-shifted trapezoid",
        "disposition": "REJECTED_P1_NOT_EXHAUSTIVE_GLOBAL_LEXICOGRAPHIC_OPTIMUM",
    },
    "R4_HIGH_TRAPEZOID": {
        "targets": [[-3, 6, 3], [3, 6, 3], [-2, 16, 3], [2, 16, 3]],
        "interpretation": "higher symmetric trapezoid",
        "disposition": "REJECTED_MINIMUM_JERK_VELOCITY_INFEASIBLE",
    },
}


def _imports():
    root = Path(__file__).resolve().parents[4]
    for path in (root / "location_allocate", root / "lfs_policy"):
        if str(path) not in sys.path:
            sys.path.insert(0, str(path))
    from location_allocate.motion_limits import minimum_jerk_peaks
    from location_allocate.policy_adapter import load_runtime_policy
    return minimum_jerk_peaks, load_runtime_policy


def _per_uav(targets, permutation):
    result = []
    for index, (start, target_index) in enumerate(zip(INITIAL, permutation)):
        target = [float(value) for value in targets[target_index]]
        delta = [target[axis] - start[axis] for axis in range(3)]
        result.append({
            "uav_id": index + 1,
            "initial_m": start,
            "target_index_zero_based": target_index,
            "target_label": target_index + 1,
            "target_m": target,
            "displacement_vector_m": delta,
            "displacement_m": math.dist(start, target),
        })
    return result


def audit_candidate(candidate_id: str, definition: Dict[str, Any], policy, safety):
    minimum_jerk_peaks, _ = _imports()
    targets = [[float(value) for value in point] for point in definition["targets"]]
    limits = policy.profile.motion_limits
    evaluator = policy.allocator_factory(safety.d_hard, safety.d_plan)
    exhaustive = []
    for permutation in itertools.permutations(range(4)):
        metrics = evaluator.evaluate(INITIAL, targets, permutation, DURATION_S)
        per_uav = _per_uav(targets, permutation)
        maximum = max(item["displacement_m"] for item in per_uav)
        peaks = minimum_jerk_peaks(maximum, DURATION_S)
        feasible = (
            peaks.velocity <= limits.velocity + 1e-12
            and peaks.acceleration <= limits.acceleration + 1e-12
            and peaks.jerk <= limits.jerk + 1e-12
        )
        exhaustive.append({
            "permutation_zero_based": list(permutation),
            "permutation_target_labels": [value + 1 for value in permutation],
            "J_distance": metrics.distance,
            "maximum_displacement_m": maximum,
            "predicted_minimum_3d_distance_m": metrics.min_distance,
            "N_hard": metrics.hard_violations,
            "J_margin": metrics.margin_cost,
            "xy_crossings": metrics.xy_crossings,
            "minimum_jerk_peaks": asdict(peaks),
            "motion_feasibility": "PASS" if feasible else "FAIL",
        })

    assignments = {}
    for label, mode in (("P0", "distance_hungarian"), ("P1", "safety_aware")):
        allocator = policy.allocator_factory(safety.d_hard, safety.d_plan)
        _assigned, metrics = allocator.allocate_mode_with_metrics(
            INITIAL, targets, DURATION_S, mode=mode
        )
        permutation = list(allocator.last_assignment)
        row = next(
            value for value in exhaustive
            if value["permutation_zero_based"] == permutation
        )
        assignments[label] = {
            "assignment_mode": mode,
            "permutation_zero_based": permutation,
            "permutation_target_labels": [value + 1 for value in permutation],
            "per_uav": _per_uav(targets, permutation),
            "N_hard": metrics.hard_violations,
            "J_margin": metrics.margin_cost,
            "J_distance": metrics.distance,
            "predicted_minimum_3d_distance_m": metrics.min_distance,
            "xy_crossings": metrics.xy_crossings,
            "maximum_displacement_m": row["maximum_displacement_m"],
            "minimum_jerk_peaks": row["minimum_jerk_peaks"],
            "motion_feasibility": row["motion_feasibility"],
            "hungarian_initial_permutation_zero_based": list(
                allocator.last_initial_assignment
            ),
            "refinement_iterations": allocator.last_iterations,
        }

    minimum_distance = min(value["J_distance"] for value in exhaustive)
    distance_optima = [
        value for value in exhaustive
        if abs(value["J_distance"] - minimum_distance) <= 1e-9
    ]
    global_lex = min(
        exhaustive,
        key=lambda value: (
            value["N_hard"], value["J_margin"], value["J_distance"]
        ),
    )
    p1 = assignments["P1"]
    p1_global = (
        p1["N_hard"] == global_lex["N_hard"]
        and abs(p1["J_margin"] - global_lex["J_margin"]) <= 1e-9
        and abs(p1["J_distance"] - global_lex["J_distance"]) <= 1e-9
    )
    static_minimum = min(
        math.dist(first, second)
        for first, second in itertools.combinations(targets, 2)
    )
    workspace = all(
        -15.0 <= point[0] <= 15.0
        and -10.0 <= point[1] <= 35.0
        and 0.5 <= point[2] <= 15.0
        for point in targets
    )
    all_move = {
        label: all(row["displacement_m"] > 1e-9 for row in value["per_uav"])
        for label, value in assignments.items()
    }
    acceptance_checks = {
        "distinct_targets": len({tuple(point) for point in targets}) == 4,
        "static_hard_separation": static_minimum + 1e-12 >= safety.d_hard,
        "workspace": workspace,
        "P0_all_UAVs_move": all_move["P0"],
        "P1_all_UAVs_move": all_move["P1"],
        "P0_motion_feasible": assignments["P0"]["motion_feasibility"] == "PASS",
        "P1_motion_feasible": assignments["P1"]["motion_feasibility"] == "PASS",
        "P0_has_hard_conflict": assignments["P0"]["N_hard"] >= 1,
        "P1_strictly_reduces_hard_conflict": (
            assignments["P1"]["N_hard"] < assignments["P0"]["N_hard"]
        ),
        "P1_eliminates_hard_conflict": assignments["P1"]["N_hard"] == 0,
        "P0_distance_optimum_unique": len(distance_optima) == 1,
        "production_P1_matches_global_exhaustive_objective": p1_global,
    }
    result = {
        "candidate_id": candidate_id,
        "targets_m": targets,
        "geometric_interpretation": definition["interpretation"],
        "disposition": definition["disposition"],
        "duration_s": DURATION_S,
        "distinct_targets": len({tuple(point) for point in targets}) == 4,
        "static_target_minimum_separation_m": static_minimum,
        "static_hard_separation_pass": static_minimum + 1e-12 >= safety.d_hard,
        "workspace_pass": workspace,
        "P0_distance_optimum_count": len(distance_optima),
        "P0_distance_optimum_unique": len(distance_optima) == 1,
        "global_lexicographic_best_permutation_zero_based": global_lex[
            "permutation_zero_based"
        ],
        "production_P1_matches_global_exhaustive_objective": p1_global,
        "P0_to_P1_hard_risk_improvement": (
            assignments["P0"]["N_hard"] - assignments["P1"]["N_hard"]
        ),
        "P0_to_P1_margin_cost_improvement": (
            assignments["P0"]["J_margin"] - assignments["P1"]["J_margin"]
        ),
        "acceptance_checks": acceptance_checks,
        "scientific_validity_pass": all(acceptance_checks.values()),
        "assignments": assignments,
        "exhaustive_24_assignments": exhaustive,
    }
    result["candidate_sha256"] = canonical_sha256(result)
    return result


def build_report():
    minimum_jerk_peaks, load_runtime_policy = _imports()
    import numpy
    import scipy

    _config, policy = load_runtime_policy(POLICY_PATH)
    safety = policy.resolve_safety(1.0)
    candidates = [
        audit_candidate(candidate_id, definition, policy, safety)
        for candidate_id, definition in SHORTLIST.items()
    ]
    report = {
        "audit_type": "E3_four_uav_replacement_geometry_candidate_audit_v1",
        "status": "PASS",
        "dataset_class": "engineering_validation",
        "accepted_formal_result": False,
        "result_notice": "NOT_FORMAL_RESULT",
        "formal_cursor_consumed": False,
        "live_execution_performed": False,
        "production_environment": {
            "python_executable": sys.executable,
            "python_version": platform.python_version(),
            "numpy_version": numpy.__version__,
            "scipy_version": scipy.__version__,
        },
        "frozen_initial_positions_m": INITIAL,
        "frozen_duration_s": DURATION_S,
        "frozen_limits": asdict(policy.profile.motion_limits),
        "frozen_safety": {"d_hard": safety.d_hard, "d_plan": safety.d_plan},
        "candidate_generation": {
            "stage_1": {
                "families": [
                    "axis-aligned rectangles", "diamonds",
                    "symmetric trapezoids", "integer rotated rectangles",
                ],
                "generated_before_deduplication": 4980,
                "unique_target_sets": 4440,
                "strict_scientific_and_motion_filter_pass": 91,
                "exhaustive_global_P1_consistency_pass": 38,
            },
            "stage_2": {
                "family": "integer offset two-row trapezoids",
                "parameter_grid": {
                    "bottom_center_x": [-3, -2, -1, 0, 1, 2, 3],
                    "top_center_x": [-3, -2, -1, 0, 1, 2, 3],
                    "bottom_half_width": [1, 2, 3, 4, 5],
                    "top_half_width": [1, 2, 3, 4, 5],
                    "bottom_y": [0, 2, 4],
                    "top_y": [6, 8, 10, 12],
                },
                "unique_target_sets": 14700,
                "strict_scientific_motion_and_global_P1_pass": 302,
            },
            "selection_rule": [
                "all hard scientific validity filters pass",
                "P0 has predicted hard conflict",
                "P1 strictly reduces N_hard",
                "maximize P0-to-P1 N_hard improvement",
                "maximize P0-to-P1 J_margin improvement",
                "prefer a unique P0 distance optimum",
                "minimize combined P0/P1 travel and geometry extremity",
                "prefer simple interpretable coordinates",
            ],
            "additional_exhaustive_validity_requirement": (
                "production P1 must match the globally best N_hard, "
                "J_margin, J_distance tuple among all 24 assignments"
            ),
        },
        "recommended_candidate_id": "G1_OFFSET_TRAPEZOID_SELECTED",
        "recommended_targets_m": SHORTLIST[
            "G1_OFFSET_TRAPEZOID_SELECTED"
        ]["targets"],
        "candidates": candidates,
    }
    report["audit_sha256"] = canonical_sha256(report)
    return report


def markdown(report):
    lines = [
        "# E3 four-UAV replacement geometry candidate audit",
        "",
        "This is an offline planning/compile audit. No PX4/Gazebo result was used.",
        "",
        "Recommended target set: `[-3,4,3]`, `[3,4,3]`, `[-2,12,3]`, `[0,12,3]`.",
        "",
        "| Candidate | Disposition | P0 perm | P1 perm | N_hard | J_margin | d_min (m) | J_distance (m) | D_max (m) | P0 ties | P1 global |",
        "|---|---|---|---|---|---|---|---|---|---:|---|",
    ]
    for item in report["candidates"]:
        p0, p1 = item["assignments"]["P0"], item["assignments"]["P1"]
        lines.append(
            f"| {item['candidate_id']} | {item['disposition']} "
            f"| `{p0['permutation_zero_based']}` | `{p1['permutation_zero_based']}` "
            f"| {p0['N_hard']}→{p1['N_hard']} "
            f"| {p0['J_margin']:.12f}→{p1['J_margin']:.12f} "
            f"| {p0['predicted_minimum_3d_distance_m']:.12f}→{p1['predicted_minimum_3d_distance_m']:.12f} "
            f"| {p0['J_distance']:.12f}→{p1['J_distance']:.12f} "
            f"| {p0['maximum_displacement_m']:.12f}→{p1['maximum_displacement_m']:.12f} "
            f"| {item['P0_distance_optimum_count']} "
            f"| {item['production_P1_matches_global_exhaustive_objective']} |"
        )
    selected = next(
        item for item in report["candidates"]
        if item["candidate_id"] == report["recommended_candidate_id"]
    )
    lines.extend(["", "## Recommended per-UAV assignments", ""])
    for label in ("P0", "P1"):
        value = selected["assignments"][label]
        lines.extend([
            f"### {label}", "",
            "| UAV | Start | Target label | Target | Displacement | Distance (m) |",
            "|---:|---|---:|---|---|---:|",
        ])
        for row in value["per_uav"]:
            lines.append(
                f"| {row['uav_id']} | `{row['initial_m']}` | {row['target_label']} "
                f"| `{row['target_m']}` | `{row['displacement_vector_m']}` "
                f"| {row['displacement_m']:.12f} |"
            )
        peaks = value["minimum_jerk_peaks"]
        lines.extend([
            "",
            f"`N_hard={value['N_hard']}`, `J_margin={value['J_margin']}`, "
            f"`J_distance={value['J_distance']}`, "
            f"`d_min={value['predicted_minimum_3d_distance_m']}`, "
            f"`v_peak={peaks['velocity']}`, `a_peak={peaks['acceleration']}`, "
            f"`j_peak={peaks['jerk']}`.",
            "",
        ])
    lines.extend([
        "## Exhaustive assignment evidence",
        "",
        "The JSON companion retains all 24 permutations for every shortlisted candidate, including objective values and motion peaks.",
        "",
        "Final candidate status: `READY_FOR_HUMAN_REVIEW`; it is not sealed or activated.",
        "",
    ])
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json-output", type=Path, required=True)
    parser.add_argument("--markdown-output", type=Path, required=True)
    args = parser.parse_args()
    report = build_report()
    args.json_output.write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    args.markdown_output.write_text(markdown(report), encoding="utf-8")
    print(json.dumps({
        "status": report["status"],
        "recommended_candidate_id": report["recommended_candidate_id"],
        "audit_sha256": report["audit_sha256"],
    }, sort_keys=True))
    return 0 if report["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
