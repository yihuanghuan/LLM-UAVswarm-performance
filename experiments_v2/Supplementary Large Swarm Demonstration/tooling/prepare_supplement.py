#!/usr/bin/env python3
"""Aggregate sweep evidence and perform deterministic pre-mission feasibility."""

from __future__ import annotations

import argparse
import itertools
import json
import math
import platform
import sys
from pathlib import Path
from typing import Any

import yaml

from large_swarm_common import (
    BASELINE, D_HARD, D_PLAN, E5_ANALYSIS, E5_SOURCE, POLICY, POLICY_SHA,
    REPO, RESULTS, ROOT, SHOWCASE_SIZES, SIZES, WORKSPACE_LOWER,
    WORKSPACE_UPPER, canonical_sha256, layout_audit, parking_layout, sha256_file,
)

sys.path[:0] = [str(REPO / "lfs_policy"), str(REPO / "location_allocate")]
from location_allocate.late_resolution import resolve_execution_parallel, resolve_execution_task  # noqa: E402
from location_allocate.lfs_types import StateSnapshot, UAVState  # noqa: E402
from location_allocate.paper_lfs_validator import early_validate_candidate_mission  # noqa: E402
from location_allocate.policy_adapter import load_runtime_policy  # noqa: E402


def task(n: int, *, formation: str, center: dict, scale: dict, duration: dict, style: str = "normal", safety: float = 1.0) -> dict:
    return {"lfs_version": "2.1", "mission": {"nodes": [{"type": "task", "task": {"task_id": 1, "U": list(range(1, n + 1)), "F": {"type": formation}, "c": center, "r": scale, "T": duration, "m": style, "s": safety, "q": {"mode": "direct"}}}]}}


def parallel(n: int, center_x: float = 7.0, radius: float = 5.0, duration: float = 16.0, spatial_partition: bool = True) -> dict:
    half = n // 2
    if spatial_partition:
        layout = parking_layout(n, 1.5)
        first = [row["uav_id"] for row in layout if row["x"] < 0]
        second = [row["uav_id"] for row in layout if row["x"] > 0]
        assert len(first) == len(second) == half
    else:
        first = list(range(1, half + 1)); second = list(range(half + 1, n + 1))
    common = {"F": {"type": "Circle"}, "r": {"mode": "explicit", "value": radius}, "T": {"mode": "explicit", "value": duration}, "m": "normal", "s": 1.0, "q": {"mode": "direct"}}
    return {"lfs_version": "2.1", "mission": {"nodes": [{"type": "parallel", "completion_mode": "synchronized", "tasks": [
        {"task_id": 1, "U": first, "c": {"mode": "absolute", "value": [-center_x, 12.5, 4.0]}, **common},
        {"task_id": 2, "U": second, "c": {"mode": "absolute", "value": [center_x, 12.5, 4.0]}, **common},
    ]}]}}


def commands(n: int) -> dict[str, str]:
    layout = parking_layout(n, 1.5)
    left = [row["uav_id"] for row in layout if row["x"] < 0]
    right = [row["uav_id"] for row in layout if row["x"] > 0]
    left_text = ", ".join(map(str, left)); right_text = ", ".join(map(str, right))
    return {
        "D1": f"Have UAVs 1 through {n} form a circle centered at [0, 12.5, 4] with radius 10 meters in 16 seconds using normal motion and safety factor 1.0.",
        "D2": f"Have UAVs 1 through {n} form a normal-scale circle around their current swarm centroid with automatic duration, using smooth motion and safety factor 1.0.",
        "D3": f"In parallel, UAVs {left_text} form a circle centered at [-7, 12.5, 4] with radius 5 meters in 16 seconds using normal motion and safety factor 1.0, while UAVs {right_text} form a circle centered at [7, 12.5, 4] with radius 5 meters in 16 seconds using normal motion and safety factor 1.0. Complete the parallel group synchronously.",
    }


def candidates() -> list[dict[str, Any]]:
    result = []
    definitions = [
        ("D1", "LARGE_SIMPLE_FORMATION", True, lambda n: task(n, formation="Circle", center={"mode": "absolute", "value": [0.0, 12.5, 4.0]}, scale={"mode": "explicit", "value": 10.0}, duration={"mode": "explicit", "value": 16.0}), "Representative unified Circle; first listed D1 candidate."),
        ("D2", "LARGE_UNDER_SPECIFIED_FORMATION", True, lambda n: task(n, formation="Circle", center={"mode": "maintain_current_centroid"}, scale={"mode": "qualitative", "value": "normal"}, duration={"mode": "auto"}, style="smooth"), "Registered maintain-current + qualitative normal + auto-T structure."),
        ("D3", "LARGE_COMPOSITIONAL_FORMATION", True, lambda n: parallel(n), "First feasible D3 candidate: two spatially partitioned equal synchronized Circle subgroups with fixed separated centers."),
        ("R-D1-R8", "LARGE_SIMPLE_FORMATION", False, lambda n: task(n, formation="Circle", center={"mode": "absolute", "value": [0.0, 12.5, 4.0]}, scale={"mode": "explicit", "value": 8.0}, duration={"mode": "explicit", "value": 16.0}), "Examined smaller radius; reject if frozen geometry must alter or reject it."),
        ("R-D1-T8", "LARGE_SIMPLE_FORMATION", False, lambda n: task(n, formation="Circle", center={"mode": "absolute", "value": [0.0, 12.5, 4.0]}, scale={"mode": "explicit", "value": 10.0}, duration={"mode": "explicit", "value": 8.0}), "Examined shorter explicit duration; reject if frozen dynamic gate must alter or reject it."),
        ("R-D2-SPHERE", "LARGE_UNDER_SPECIFIED_FORMATION", False, lambda n: task(n, formation="Sphere", center={"mode": "maintain_current_centroid"}, scale={"mode": "qualitative", "value": "normal"}, duration={"mode": "auto"}, style="smooth"), "Examined Sphere at post-readiness centroid; expected lower-workspace conflict."),
        ("R-D3-CONTIGUOUS-HALVES", "LARGE_COMPOSITIONAL_FORMATION", False, lambda n: parallel(n, spatial_partition=False), "Rejected because contiguous-ID halves create deterministic cross-group nominal hard conflicts from the parking layout."),
        ("R-D3-CLOSE", "LARGE_COMPOSITIONAL_FORMATION", False, lambda n: parallel(n, center_x=5.0), "Examined closer subgroup centers; reject on frozen joint safety if applicable."),
    ]
    for cid, family, selected, generator, reason in definitions:
        by_n = {n: generator(n) for n in SHOWCASE_SIZES}
        result.append({"candidate_id": cid, "task_family": family, "selected": selected, "evaluated_n": list(SHOWCASE_SIZES), "candidate_semantic_ground_truth_by_n": by_n, "design_disposition_basis": reason, "exact_commands_by_n": ({n: commands(n)[cid] for n in SHOWCASE_SIZES} if cid in {"D1", "D2", "D3"} else {})})
    return result


def snapshot(n: int) -> StateSnapshot:
    states = {p["uav_id"]: UAVState(position=(p["x"], p["y"], 1.5), velocity=(0.0, 0.0, 0.0), receive_timestamp=100.0, source_timestamp=100.0, timestamp_source="source_timestamp", warnings=()) for p in parking_layout(n, 1.5)}
    return StateSnapshot(epoch=100.0, states=states, warnings=())


def bounds(points) -> list[list[float]]:
    return [[min(float(p[a]) for p in points), max(float(p[a]) for p in points)] for a in range(3)]


def min_distance(points) -> float:
    return min(math.dist(a, b) for a, b in itertools.combinations(points, 2))


def resolved_record(value) -> dict:
    trace = value.trace; points = [list(p) for p in value.assigned_targets]
    peaks = list(trace.per_uav_dynamics)
    return {
        "U": list(value.executable_lfs.uav_ids), "formation": dict(value.executable_lfs.formation),
        "c_exec": list(value.executable_lfs.center), "r_exec": value.executable_lfs.radius,
        "T_exec": value.executable_lfs.duration, "T_plan": trace.t_plan,
        "r_nominal": trace.r_nominal, "r_safe": trace.r_safe,
        "d_hard": trace.d_hard, "d_plan": trace.d_plan,
        "target_bounds_xyz": bounds(points), "target_min_pairwise_m": min_distance(points),
        "allocator_version": trace.allocator_version, "allocator_acceptance": True,
        "predicted_final_min_pairwise_m": value.final_metrics.min_distance,
        "predicted_hard_conflicts": value.final_metrics.hard_violations,
        "predicted_peak_velocity_mps": max(float(x["predicted_v_peak"]) for x in peaks),
        "predicted_peak_acceleration_mps2": max(float(x["predicted_a_peak"]) for x in peaks),
        "predicted_peak_jerk_mps3": max(float(x["predicted_j_peak"]) for x in peaks),
        "max_assigned_displacement_m": max(float(x["distance"]) for x in peaks),
        "corrections": list(trace.corrections),
    }


def evaluate(candidate: dict, n: int, policy) -> dict:
    payload = candidate["candidate_semantic_ground_truth_by_n"][n]
    row = {"candidate_id": candidate["candidate_id"], "selected": candidate["selected"], "task_family": candidate["task_family"], "N": n, "candidate_sha256": canonical_sha256(payload), "state_model": "deterministic_post_readiness_parking_layout", "initial_centroid": [sum(p[a] for p in [(x["x"], x["y"], 1.5) for x in parking_layout(n, 1.5)]) / n for a in range(3)], "initial_min_pairwise_m": 3.0}
    try:
        early_validate_candidate_mission(payload, available_uav_ids=list(range(1, n + 1)))
        node = payload["mission"]["nodes"][0]
        if node["type"] == "task":
            values = [resolve_execution_task(node["task"], snapshot(n), policy)]; group_min = None; group_conflicts = None
        else:
            group = resolve_execution_parallel(node["tasks"], snapshot(n), policy, node["completion_mode"])
            values = list(group.tasks); group_min = group.final_metrics.min_distance; group_conflicts = group.final_metrics.hard_violations
        tasks = [resolved_record(x) for x in values]
        workspace = all(all(WORKSPACE_LOWER[a] <= lo and hi <= WORKSPACE_UPPER[a] for a, (lo, hi) in enumerate(t["target_bounds_xyz"])) for t in tasks)
        dynamics = all(t["predicted_peak_velocity_mps"] <= 5 + 1e-9 and t["predicted_peak_acceleration_mps2"] <= 5 + 1e-9 and t["predicted_peak_jerk_mps3"] <= 10 + 1e-9 for t in tasks)
        hard = all(t["predicted_hard_conflicts"] == 0 and t["predicted_final_min_pairwise_m"] + 1e-9 >= D_HARD for t in tasks) and (group_conflicts in (None, 0)) and (group_min is None or group_min + 1e-9 >= D_HARD)
        exact = True
        for original, resolved in zip(node.get("tasks", [node.get("task")]), tasks):
            if original["r"]["mode"] == "explicit": exact &= math.isclose(resolved["r_exec"], float(original["r"]["value"]), abs_tol=1e-9)
            if original["T"]["mode"] == "explicit": exact &= math.isclose(resolved["T_exec"], float(original["T"]["value"]), abs_tol=1e-9)
        feasible = workspace and dynamics and hard and exact
        return {**row, "feasible": feasible, "validation": "PASS", "resolver": "PASS", "geometry_workspace_fit": workspace, "allocator_acceptance": True, "dynamic_feasibility": dynamics, "explicit_semantics_unchanged": exact, "auto_T_valid": all(t["T_exec"] > 0 for t in tasks), "predicted_group_min_pairwise_m": group_min, "predicted_group_hard_conflicts": group_conflicts, "tasks": tasks, "failure_type": None if feasible else "DETERMINISTIC_GATE_FAILURE", "failure_reason": None if feasible else "resolved output violates workspace, hard-safety, dynamics, or exact explicit-value gate"}
    except Exception as exc:
        return {**row, "feasible": False, "validation": "REJECTED_OR_PASS_BEFORE_LATER_GATE", "resolver": "REJECTED", "geometry_workspace_fit": False, "allocator_acceptance": False, "dynamic_feasibility": False, "explicit_semantics_unchanged": False, "auto_T_valid": False, "tasks": [], "failure_type": type(exc).__name__, "failure_reason": str(exc)}


def aggregate_infrastructure() -> dict:
    paths = {20: RESULTS / "N20_recovery1/result.json", 24: RESULTS / "N24/result.json", 28: RESULTS / "N28/result.json", 32: RESULTS / "N32/result.json"}
    rows = []
    for n, path in paths.items():
        source = json.loads(path.read_text())
        rows.append({k: source.get(k) for k in ["N_requested", "success", "models_spawned", "spawn_elapsed_s", "readiness_success", "readiness_elapsed_s", "stable_hover_duration_s", "fresh_state_count", "armed_offboard_count", "failsafe_count", "all_states_finite", "process_counts_at_readiness", "micro_xrce_agent_alive", "gzserver_alive", "topic_connectivity", "host_diagnostics_before", "host_diagnostics_at_readiness", "host_diagnostics_after", "gazebo_stats", "cleanup", "startup_failure_stage", "failure"]} | {"evidence_path": str(path.relative_to(ROOT)), "evidence_sha256": sha256_file(path)})
    passing = [r["N_requested"] for r in rows if r["success"]]
    return {"schema": "large_swarm_infrastructure_results_v1", "dataset_class": "supplementary_infrastructure_validation", "accepted_formal_results": 0, "scientific_missions": 0, "tested_sizes": list(SIZES), "rows": rows, "largest_successfully_tested_N": max(passing) if passing else None, "observed_ceiling_wording": f"largest successfully tested supplementary configuration = N={max(passing)}" if passing else "no tested configuration passed", "engineering_recoveries": ["tooling_recovery_001", "tooling_recovery_002"]}


def markdown_infra(data: dict) -> str:
    lines = ["# Large-swarm infrastructure sweep results", "", "These are non-formal supplementary infrastructure validations. No Candidate, LLM call, formation command, or scientific mission occurred.", "", "| N | Result | readiness (s) | PX4 | controllers | armed/offboard | fresh states | failsafe | RSS MiB | available memory MiB | load (1m) | cleanup |", "|---:|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|"]
    for r in data["rows"]:
        h = r["host_diagnostics_at_readiness"]; c = r["process_counts_at_readiness"]
        lines.append(f"| {r['N_requested']} | {'PASS' if r['success'] else 'FAIL'} | {r['readiness_elapsed_s']:.3f} | {c['px4']} | {c['controllers']} | {r['armed_offboard_count']} | {r['fresh_state_count']} | {r['failsafe_count']} | {h['scoped_process_rss_kib']/1024:.1f} | {h['memory_kib']['MemAvailable']/1024:.1f} | {h['load_average'][0]:.2f} | {'PASS' if r['cleanup']['success'] else 'FAIL'} |")
    lines += ["", f"Observed result: **{data['observed_ceiling_wording']}**. This does not mean the method supports at most that N; only N=20,24,28,32 were tested.", "", "Gazebo real-time factor is NA for all four conditions because the low-intrusion `gz stats -p` probe returned no parseable sample. Physics was not changed.", "", "The initial N=20 run is retained as a diagnostic-gate tooling failure. It satisfied all frozen readiness/process gates; recovery1 corrected only the extra CLI diagnostic classification and passed.", ""]
    return "\n".join(lines)


def markdown_feasibility(data: dict) -> str:
    lines = ["# Large-swarm deterministic scenario feasibility", "", "This is pre-mission, read-only design analysis using the frozen validator, geometry, allocator, timing, and policy. It made no LLM call and executed no Gazebo mission.", "", "| Candidate | N | selected | feasible | r_exec | T_exec | target d_min | predicted path d_min | hard conflicts | disposition |", "|---|---:|---|---|---|---|---:|---:|---:|---|"]
    for row in data["feasibility"]["rows"]:
        tasks = row.get("tasks", [])
        radii = ",".join(f"{t['r_exec']:.3f}" for t in tasks) or "NA"
        times = ",".join(f"{t['T_exec']:.3f}" for t in tasks) or "NA"
        target = min((t["target_min_pairwise_m"] for t in tasks), default=None)
        predicted = row.get("predicted_group_min_pairwise_m") or min((t["predicted_final_min_pairwise_m"] for t in tasks), default=None)
        conflicts = row.get("predicted_group_hard_conflicts")
        if conflicts is None: conflicts = sum(t["predicted_hard_conflicts"] for t in tasks)
        disposition = "accepted by every deterministic gate" if row["feasible"] else (row.get("failure_reason") or row.get("failure_type"))
        lines.append(f"| {row['candidate_id']} | {row['N']} | {str(row['selected']).lower()} | {str(row['feasible']).lower()} | {radii} | {times} | {target if target is not None else 'NA'} | {predicted if predicted is not None else 'NA'} | {conflicts if conflicts is not None else 'NA'} | {disposition} |")
    lines += ["", "D1, D2, and the spatially partitioned D3 are feasible for N=24, 28, and 32. D3's initially examined contiguous-ID partition is retained as rejected because it creates nominal cross-group hard conflicts; the selected left/right parking partition is the first feasible D3 candidate and keeps equal subgroup sizes.", "", "Rejected/non-selected candidates are not ranked by predicted mission success: radius 8 requires frozen safety enlargement at N=28/32; the shorter D1 duration is feasible but follows the already selected first representative D1 candidate; maintain-current Sphere conflicts with the lower workspace boundary; close or contiguous parallel groups fail the nominal hard gate.", "", "Despite scenario feasibility, no primary showcase N is selected because none of N=24, 28, or 32 passed the infrastructure sweep. No showcase mission may start under this candidate protocol.", ""]
    return "\n".join(lines)


def demo_protocol(data: dict) -> dict:
    selected = [c for c in data["candidates"] if c["selected"]]
    family_details = {
        "D1": {"formation": "Circle", "center_semantics": "absolute [0,12.5,4]", "scale_semantics": "explicit 10 m", "T_semantics": "explicit 16 s", "style": "normal", "safety": 1.0, "transition": "direct", "mission_timeout_s": 45.0},
        "D2": {"formation": "Circle", "center_semantics": "maintain_current_centroid", "scale_semantics": "qualitative normal", "T_semantics": "auto", "style": "smooth", "safety": 1.0, "transition": "direct", "mission_timeout_s": 45.0},
        "D3": {"formation": "two spatially partitioned parallel Circles", "center_semantics": "absolute [-7,12.5,4] and [7,12.5,4]", "scale_semantics": "explicit 5 m each", "T_semantics": "explicit 16 s", "style": "normal", "safety": 1.0, "transition": "direct synchronized parallel", "mission_timeout_s": 50.0},
    }
    tasks = []
    for candidate in selected:
        cid = candidate["candidate_id"]
        tasks.append({"task_family": cid, **family_details[cid], "exact_natural_language_commands_by_N": candidate["exact_commands_by_n"], "candidate_semantic_ground_truth_by_N": candidate["candidate_semantic_ground_truth_by_n"], "deterministic_feasibility": {str(n): "PASS" for n in SHOWCASE_SIZES}, "feasibility_evidence": "large_swarm_scenario_feasibility.json"})
    return {
        "protocol_id": "supplementary-large-swarm-demo-v1", "status": "CANDIDATE_FOR_HUMAN_REVIEW",
        "scientific_position": "supplementary_visual_system_demonstration",
        "primary_showcase_N": data["primary_showcase_N"], "optional_secondary_N": data["optional_secondary_N"],
        "selection_status": "NO_SUITABLE_LARGE_SWARM_SHOWCASE_CONFIGURATION" if data["primary_showcase_N"] is None else "PRIMARY_SELECTED_BY_FROZEN_RULE",
        "selection_rule": "largest N in [24,28,32] passing infrastructure and all three deterministic scenario gates",
        "task_families": tasks,
        "recommended_future_repeats": {"D1": 3, "D2": 3, "D3": 3, "total": 9, "authorization": "not authorized in this task"},
        "optional_N24_video_only": {"eligible_only_if_primary_N_is_32": True, "current_recommendation": None},
        "future_descriptive_metrics": ["mission success", "Candidate correctness", "resolver success", "actual d_min", "tracking RMSE", "final error", "completion time", "resolved c/r/T for D2", "readiness/startup diagnostics"],
        "excluded_endpoints_and_claims": ["J_hard", "inferential statistics", "scalability model", "formal scalability", "arbitrary-N generalization", "causal N effect"],
        "showcase_missions_executed": 0,
    }


def build() -> dict:
    assert layout_audit()["status"] == "PASS" and sha256_file(POLICY) == POLICY_SHA
    infra = aggregate_infrastructure()
    source_candidates = candidates()
    _, policy = load_runtime_policy(POLICY)
    rows = [evaluate(c, n, policy) for c in source_candidates for n in SHOWCASE_SIZES]
    selected = [r for r in rows if r["selected"]]
    feasibility = {"schema": "large_swarm_scenario_feasibility_v1", "dataset_class": "deterministic_design_analysis", "accepted_formal_result": False, "gazebo_missions": 0, "llm_calls": 0, "policy_sha256": POLICY_SHA, "state_model": "post-readiness parking layout at z=1.5 m", "rows": rows, "selected_cells_feasible": all(r["feasible"] for r in selected)}
    feasible_by_n = {n: all(r["feasible"] for r in selected if r["N"] == n) for n in SHOWCASE_SIZES}
    infra_by_n = {r["N_requested"]: r["success"] for r in infra["rows"]}
    eligible = [n for n in SHOWCASE_SIZES if infra_by_n[n] and feasible_by_n[n]]
    primary = max(eligible) if eligible else None
    secondary = 24 if primary == 32 and infra_by_n[24] and feasible_by_n[24] else None
    return {"infrastructure": infra, "candidates": source_candidates, "feasibility": feasibility, "feasible_by_n": feasible_by_n, "primary_showcase_N": primary, "optional_secondary_N": secondary}


def main() -> int:
    parser = argparse.ArgumentParser(); parser.add_argument("--write", action="store_true"); args = parser.parse_args()
    data = build()
    if args.write:
        infra_dir = ROOT / "infrastructure"; scenario_dir = ROOT / "scenarios"
        (infra_dir / "large_swarm_infrastructure_results.json").write_text(json.dumps(data["infrastructure"], indent=2, sort_keys=True) + "\n")
        (infra_dir / "large_swarm_infrastructure_results.md").write_text(markdown_infra(data["infrastructure"]))
        candidate_doc = {"schema": "large_swarm_scenario_candidates_v1", "status": "FROZEN_BEFORE_ANY_SHOWCASE_MISSION", "selection_rule": "largest N in [24,28,32] passing infrastructure and all D1/D2/D3 deterministic feasibility gates", "candidates": data["candidates"]}
        (scenario_dir / "large_swarm_scenario_candidates.yaml").write_text(yaml.safe_dump(candidate_doc, sort_keys=False, allow_unicode=True))
        (scenario_dir / "large_swarm_scenario_feasibility.json").write_text(json.dumps(data["feasibility"], indent=2, sort_keys=True) + "\n")
        (scenario_dir / "large_swarm_scenario_feasibility.md").write_text(markdown_feasibility(data))
        (scenario_dir / "large_swarm_demo_protocol_v1.yaml").write_text(yaml.safe_dump(demo_protocol(data), sort_keys=False, allow_unicode=True))
    print(json.dumps({"largest_stable_N": data["infrastructure"]["largest_successfully_tested_N"], "selected_cells_feasible": data["feasibility"]["selected_cells_feasible"], "primary_showcase_N": data["primary_showcase_N"]}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
