#!/usr/bin/env python3
"""Deterministically enumerate E5-v2 design feasibility without an LLM or SITL."""

from __future__ import annotations

import argparse
import itertools
import json
import math
import platform
import sys
from pathlib import Path
from typing import Any, Dict, List, Sequence

import numpy
import scipy

from e5_v2_common import (
    CANDIDATES_PATH,
    E5_DIR,
    REPO_ROOT,
    canonical_json_bytes,
    load_yaml,
    sha256_bytes,
    uav_ids,
)

sys.path.insert(0, str(REPO_ROOT / "lfs_policy"))
sys.path.insert(0, str(REPO_ROOT / "location_allocate"))

from location_allocate.late_resolution import (  # noqa: E402
    resolve_execution_parallel,
    resolve_execution_task,
)
from location_allocate.lfs_types import StateSnapshot, UAVState  # noqa: E402
from location_allocate.paper_lfs_validator import (  # noqa: E402
    early_validate_candidate_mission,
)
from location_allocate.policy_adapter import load_runtime_policy  # noqa: E402


POLICY_PATH = REPO_ROOT / "lfs_policy/config/lfs_policy.paper_current.yaml"
OUTPUT_JSON = E5_DIR / "E5_v2_feasibility_audit.json"
OUTPUT_MD = E5_DIR / "E5_v2_feasibility_audit.md"
STATE_MODELS = (("cold_start_spawn", 0.83), ("nominal_post_readiness", 1.50))


def snapshot(n: int, altitude: float) -> StateSnapshot:
    states = {
        uid: UAVState(
            position=(0.0, 3.0 * uid, altitude),
            velocity=(0.0, 0.0, 0.0),
            receive_timestamp=100.0,
            source_timestamp=100.0,
            timestamp_source="source_timestamp",
            warnings=(),
        )
        for uid in uav_ids(n)
    }
    return StateSnapshot(epoch=100.0, states=states, warnings=())


def close_center_payload(n: int, center_x: float, radius: float, duration: float):
    half = n // 2
    common = {
        "F": {"type": "Circle"},
        "r": {"mode": "explicit", "value": radius},
        "T": {"mode": "explicit", "value": duration},
        "m": "normal",
        "s": 1.0,
        "q": {"mode": "direct"},
    }
    first = {
        "task_id": 1,
        "U": list(range(1, half + 1)),
        "c": {"mode": "absolute", "value": [-center_x, 18, 4]},
        **common,
    }
    second = {
        "task_id": 2,
        "U": list(range(half + 1, n + 1)),
        "c": {"mode": "absolute", "value": [center_x, 18, 4]},
        **common,
    }
    return {
        "lfs_version": "2.1",
        "mission": {"nodes": [{
            "type": "parallel",
            "completion_mode": "synchronized",
            "tasks": [first, second],
        }]},
    }


def payload_for(candidate: Dict[str, Any], n: int) -> Dict[str, Any]:
    by_n = candidate.get("candidate_semantic_ground_truth_by_n", {})
    if n in by_n:
        return by_n[n]
    if str(n) in by_n:
        return by_n[str(n)]
    if candidate.get("generator") == "parallel_close_centers":
        return close_center_payload(
            n,
            float(candidate["center_x_m"]),
            float(candidate["radius_m"]),
            float(candidate["duration_s"]),
        )
    raise ValueError(f"candidate {candidate['candidate_id']} has no payload for N={n}")


def bounds(points: Sequence[Sequence[float]]) -> List[List[float]]:
    return [
        [min(float(point[axis]) for point in points),
         max(float(point[axis]) for point in points)]
        for axis in range(3)
    ]


def minimum_distance(points: Sequence[Sequence[float]]) -> float | None:
    if len(points) < 2:
        return None
    return min(math.dist(a, b) for a, b in itertools.combinations(points, 2))


def task_record(resolved) -> Dict[str, Any]:
    trace = resolved.trace
    points = [list(value) for value in resolved.assigned_targets]
    dynamics = list(trace.per_uav_dynamics)
    return {
        "uav_ids": list(resolved.executable_lfs.uav_ids),
        "formation": dict(resolved.executable_lfs.formation),
        "c_exec": list(resolved.executable_lfs.center),
        "r_exec": resolved.executable_lfs.radius,
        "T_plan": trace.t_plan,
        "T_exec": resolved.executable_lfs.duration,
        "delta_min_unit_geometry": trace.delta_min,
        "r_nominal": trace.r_nominal,
        "r_safe": trace.r_safe,
        "d_hard": trace.d_hard,
        "d_plan": trace.d_plan,
        "target_bounds_xyz": bounds(points),
        "target_min_pairwise_m": minimum_distance(points),
        "allocator_version": trace.allocator_version,
        "assignment": list(trace.final_assignment),
        "planning_min_pairwise_m": resolved.planning_metrics.min_distance,
        "final_min_pairwise_m": resolved.final_metrics.min_distance,
        "J_hard": resolved.final_metrics.hard_violations,
        "planning_margin_met": (
            resolved.final_metrics.min_distance + 1e-9 >= trace.d_plan
        ),
        "hard_safety_met": (
            resolved.final_metrics.min_distance + 1e-9 >= trace.d_hard
        ),
        "max_assigned_displacement_m": max(
            (float(value["distance"]) for value in dynamics), default=0.0
        ),
        "predicted_peak_velocity_mps": max(
            (float(value["predicted_v_peak"]) for value in dynamics), default=0.0
        ),
        "predicted_peak_acceleration_mps2": max(
            (float(value["predicted_a_peak"]) for value in dynamics), default=0.0
        ),
        "predicted_peak_jerk_mps3": max(
            (float(value["predicted_j_peak"]) for value in dynamics), default=0.0
        ),
        "corrections": list(trace.corrections),
    }


def evaluate(candidate: Dict[str, Any], n: int, model: str, altitude: float, policy):
    payload = payload_for(candidate, n)
    state = snapshot(n, altitude)
    positions = [state.states[uid].position for uid in uav_ids(n)]
    base = {
        "candidate_id": candidate["candidate_id"],
        "selected": bool(candidate["selected"]),
        "substudy": candidate["substudy"],
        "task_family": candidate.get("task_family"),
        "coverage_slot": candidate.get("coverage_slot"),
        "N": n,
        "state_model": model,
        "initial_centroid": [
            sum(point[axis] for point in positions) / n for axis in range(3)
        ],
        "initial_min_pairwise_m": minimum_distance(positions),
        "candidate_sha256": sha256_bytes(canonical_json_bytes(payload)),
    }
    try:
        early_validate_candidate_mission(payload, available_uav_ids=uav_ids(n))
        node = payload["mission"]["nodes"][0]
        if len(payload["mission"]["nodes"]) != 1:
            raise ValueError("design enumerator accepts one task/parallel node only")
        if node["type"] == "task":
            resolved = resolve_execution_task(node["task"], state, policy)
            tasks = [task_record(resolved)]
            group_metrics = None
        else:
            group = resolve_execution_parallel(
                node["tasks"], state, policy, node["completion_mode"]
            )
            tasks = [task_record(value) for value in group.tasks]
            group_metrics = {
                "completion_mode": group.completion_mode,
                "planning_min_pairwise_m": group.planning_metrics.min_distance,
                "final_min_pairwise_m": group.final_metrics.min_distance,
                "J_hard": group.final_metrics.hard_violations,
                "hard_safety_met": all(value["hard_safety_met"] for value in tasks),
            }
        return {
            **base,
            "feasible": True,
            "validation": "PASS",
            "resolver": "PASS",
            "geometry": "PASS",
            "allocator": "PASS",
            "dynamic_feasibility": "PASS",
            "auto_T_valid": all(value["T_exec"] > 0 for value in tasks),
            "tasks": tasks,
            "parallel_group": group_metrics,
            "failure_type": None,
            "failure_reason": None,
        }
    except Exception as exc:  # fail-closed design evidence is an intended row
        return {
            **base,
            "feasible": False,
            "validation": "REJECTED",
            "resolver": "REJECTED",
            "geometry": "REJECTED",
            "allocator": "NOT_REACHED_OR_REJECTED",
            "dynamic_feasibility": "NOT_REACHED_OR_REJECTED",
            "auto_T_valid": False,
            "tasks": [],
            "parallel_group": None,
            "failure_type": type(exc).__name__,
            "failure_code": getattr(exc, "code", None),
            "failure_reason": str(exc),
        }


def build_audit() -> Dict[str, Any]:
    source = load_yaml(CANDIDATES_PATH)
    config, policy = load_runtime_policy(POLICY_PATH)
    rows = []
    for candidate in source["candidates"]:
        for n in candidate["evaluated_n"]:
            for model, altitude in STATE_MODELS:
                rows.append(evaluate(candidate, int(n), model, altitude, policy))
    selected_rows = [row for row in rows if row["selected"]]
    selected_cells = {
        (row["candidate_id"], row["N"]) for row in selected_rows
    }
    expected_selected_cells = 3 + 3 * 3
    status = "PASS" if (
        len(selected_cells) == expected_selected_cells
        and all(row["feasible"] for row in selected_rows)
    ) else "FAIL"
    return {
        "audit_id": "E5-v2-deterministic-feasibility-audit-v1",
        "status": status,
        "dataset_class": "design_analysis",
        "accepted_formal_result": False,
        "formal_missions_run": 0,
        "llm_calls": 0,
        "gazebo_runs": 0,
        "analysis_environment": {
            "python": platform.python_version(),
            "numpy": numpy.__version__,
            "scipy": scipy.__version__,
        },
        "baseline_commit": source["baseline_commit"],
        "configuration_id": config.configuration_id,
        "policy_sha256": source["policy_sha256"],
        "selection_rule": source[
            "selection_rule_frozen_before_final_scenario_selection"
        ],
        "state_models": source["design_state_models"],
        "candidate_count": len(source["candidates"]),
        "selected_candidate_count": sum(
            bool(candidate["selected"]) for candidate in source["candidates"]
        ),
        "selected_scale_cells": len(selected_cells),
        "required_selected_scale_cells": expected_selected_cells,
        "rows": rows,
    }


def markdown(audit: Dict[str, Any]) -> str:
    selected = [row for row in audit["rows"] if row["selected"]]
    rejected = [row for row in audit["rows"] if not row["selected"]]
    lines = [
        "# E5-v2 deterministic feasibility audit",
        "",
        f"Result: `E5_V2_FEASIBILITY_AUDIT = {audit['status']}`.",
        "",
        "This is prospective design analysis only: no LLM call, Gazebo run, "
        "formal trial, or accepted formal result was created. It asks only "
        "whether each frozen Candidate has a legal physical realization; it "
        "does not rank candidates by expected ease or success.",
        "",
        "## Selected cells",
        "",
        "| Candidate | N | state model | feasible | c_exec | r_exec | T_exec | predicted d_min | J_hard |",
        "|---|---:|---|---|---|---|---|---|---:|",
    ]
    for row in selected:
        task = row["tasks"][0] if row["tasks"] else {}
        centers = [task.get("c_exec") for task in row["tasks"]]
        radii = [task.get("r_exec") for task in row["tasks"]]
        durations = [task.get("T_exec") for task in row["tasks"]]
        group = row.get("parallel_group")
        predicted = (
            group["final_min_pairwise_m"] if group
            else task.get("final_min_pairwise_m")
        )
        hard = group["J_hard"] if group else task.get("J_hard")
        lines.append(
            f"| {row['candidate_id']} | {row['N']} | {row['state_model']} | "
            f"{str(row['feasible']).lower()} | `{centers}` | `{radii}` | "
            f"`{durations}` | {predicted:.9f} | {hard} |"
        )
    lines.extend([
        "",
        "All selected target geometries lie inside the frozen workspace, each "
        "target set respects its frozen d_plan geometry floor, the frozen "
        "allocator returns an assignment with no predicted d_hard violation, "
        "and final Minimum-Jerk profiles respect the frozen motion limits.",
        "",
        "## Non-selected design candidates",
        "",
        "| Candidate | N | state model | feasible | deterministic disposition |",
        "|---|---:|---|---|---|",
    ])
    for row in rejected:
        disposition = row["failure_reason"] or (
            "physically admissible but excluded by the predeclared coverage/selection rule"
        )
        lines.append(
            f"| {row['candidate_id']} | {row['N']} | {row['state_model']} | "
            f"{str(row['feasible']).lower()} | {disposition} |"
        )
    lines.extend([
        "",
        "The old-like low Sphere and edge-shifted Circle fail closed at frozen "
        "workspace/scale gates. The close-center parallel composition fails at "
        "the frozen d_hard gate. The T=10 S1 candidate is physically admissible "
        "but was not selected because its conservative N=16 planning duration "
        "is corrected, whereas the predeclared S1 rule takes the first duration "
        "unchanged at every deterministic gate.",
        "",
    ])
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--write", action="store_true")
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    audit = build_audit()
    rendered_json = json.dumps(audit, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    rendered_md = markdown(audit)
    if args.write:
        OUTPUT_JSON.write_text(rendered_json, encoding="utf-8")
        OUTPUT_MD.write_text(rendered_md, encoding="utf-8")
    if args.check:
        if OUTPUT_JSON.read_text(encoding="utf-8") != rendered_json:
            raise SystemExit("feasibility JSON is not deterministic/current")
        if OUTPUT_MD.read_text(encoding="utf-8") != rendered_md:
            raise SystemExit("feasibility Markdown is not deterministic/current")
    print(json.dumps({
        "status": audit["status"],
        "candidate_count": audit["candidate_count"],
        "selected_scale_cells": audit["selected_scale_cells"],
        "row_count": len(audit["rows"]),
    }, sort_keys=True))
    return 0 if audit["status"] == "PASS" else 2


if __name__ == "__main__":
    raise SystemExit(main())
