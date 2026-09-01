#!/usr/bin/env python3
"""Offline planning and motion-envelope audit for the frozen Family-B grid."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path
import sys

import numpy as np
import yaml

TOOLING_DIR = Path(__file__).resolve().parent
E3_DIR = TOOLING_DIR.parent
REPO_ROOT = E3_DIR.parents[2]
sys.path[:0] = [str(REPO_ROOT / "location_allocate"), str(REPO_ROOT / "lfs_policy")]

from location_allocate.policy_adapter import load_runtime_policy  # noqa: E402

GRID = E3_DIR / "E3_v4_family_B_execution_deviation_grid.yaml"
POLICY = REPO_ROOT / "lfs_policy/config/lfs_policy.paper_current.yaml"


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def canonical_sha256(value) -> str:
    return hashlib.sha256(json.dumps(
        value, sort_keys=True, separators=(",", ":")
    ).encode()).hexdigest()


def minimum_jerk(value):
    value = np.clip(value, 0.0, 1.0)
    return 10.0 * value**3 - 15.0 * value**4 + 6.0 * value**5


def delay_counterfactual(geometry: dict, delay: float) -> dict:
    ids = [int(value) for value in geometry["uav_ids"]]
    index2, index3 = ids.index(2), ids.index(3)
    initial = np.asarray([geometry["initial_positions_m"][uid] for uid in ids])
    targets = np.asarray([geometry["ordered_targets_m"][uid] for uid in ids])
    duration = float(geometry["duration_s"])
    time = np.linspace(0.0, duration + delay, 200001)
    p2 = minimum_jerk(time / duration)
    p3 = minimum_jerk((time - delay) / duration)
    pos2 = initial[index2] + p2[:, None] * (targets[index2] - initial[index2])
    pos3 = initial[index3] + p3[:, None] * (targets[index3] - initial[index3])
    distance = np.linalg.norm(pos2 - pos3, axis=1)
    index = int(np.argmin(distance))
    return {
        "ideal_execution_deviation_pair_2_3_min_m": float(distance[index]),
        "ideal_minimum_time_s": float(time[index]),
        "registered_delay_s": float(delay),
    }


def segment_envelope(delta: np.ndarray, duration: float) -> dict:
    # Exact extrema for scalar minimum jerk: velocity 1.875, acceleration
    # 10*sqrt(3)/3, and endpoint jerk 60 in normalized time.
    component = np.abs(delta)
    return {
        "delta_m": delta.tolist(),
        "duration_s": float(duration),
        "max_component_velocity_mps": float(np.max(component) * 1.875 / duration),
        "max_component_acceleration_mps2": float(
            np.max(component) * (10.0 * math.sqrt(3.0) / 3.0) / duration**2
        ),
        "max_component_jerk_mps3": float(np.max(component) * 60.0 / duration**3),
    }


def reference_counterfactual(geometry: dict, candidate: dict) -> dict:
    uid = int(candidate["affected_uav"])
    initial = np.asarray(geometry["initial_positions_m"][uid], dtype=float)
    target = np.asarray(geometry["ordered_targets_m"][uid], dtype=float)
    duration = float(geometry["duration_s"])
    start = float(candidate["start_s"])
    interval = float(candidate["duration_s"])
    p_start = float(minimum_jerk(start / duration))
    p_reset = float(minimum_jerk((start + interval) / duration))
    at_start = initial + p_start * (target - initial)
    counterfactual_reset = initial + p_reset * (target - initial)
    bias_target = counterfactual_reset + np.asarray(candidate["offset_m"], dtype=float)
    reset_duration = duration - start - interval
    bias_segment = segment_envelope(bias_target - at_start, interval)
    reset_segment = segment_envelope(target - bias_target, reset_duration)
    pair2 = np.asarray(geometry["initial_positions_m"][2], dtype=float)
    pair2_target = np.asarray(geometry["ordered_targets_m"][2], dtype=float)
    pair2_at_reset = pair2 + p_reset * (pair2_target - pair2)
    return {
        "counterfactual_activation_reference_m": at_start.tolist(),
        "counterfactual_reset_reference_m": counterfactual_reset.tolist(),
        "registered_bias_endpoint_m": bias_target.tolist(),
        "ideal_pair_2_3_distance_at_bias_endpoint_m": float(
            np.linalg.norm(pair2_at_reset - bias_target)
        ),
        "bias_segment": bias_segment,
        "reset_segment": reset_segment,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    grid = yaml.safe_load(GRID.read_text())
    config, policy = load_runtime_policy(POLICY)
    safety = policy.resolve_safety(1.0)
    geometries = {}
    all_planning_pass = True
    for name, geometry in grid["geometries"].items():
        ids = [int(value) for value in geometry["uav_ids"]]
        initial = [geometry["initial_positions_m"][uid] for uid in ids]
        targets = [geometry["ordered_targets_m"][uid] for uid in ids]
        modes = {}
        for condition, mode in (("P0_F0", "distance_hungarian"),
                                ("P1_F0", "safety_aware")):
            allocator = policy.allocator_factory(safety.d_hard, safety.d_plan)
            assigned, metrics = allocator.allocate_mode_with_metrics(
                initial, targets, float(geometry["duration_s"]), mode=mode
            )
            modes[condition] = {
                "assignment_mode": mode,
                "assignment": allocator.last_assignment,
                "assigned_targets_m": assigned,
                "predicted_d_min_m": float(metrics.min_distance),
                "predicted_hard_violations": int(metrics.hard_violations),
                "planning_margin_met": metrics.min_distance + 1e-9 >= safety.d_plan,
                "hard_feasible": metrics.hard_violations == 0,
            }
        same = modes["P0_F0"]["assignment"] == modes["P1_F0"]["assignment"]
        passed = same and all(
            value["predicted_hard_violations"] == 0
            and value["predicted_d_min_m"] + 1e-9 >= safety.d_plan
            for value in modes.values()
        )
        all_planning_pass = all_planning_pass and passed
        geometries[name] = {
            "modes": modes,
            "same_assignment": same,
            "planning_gate_pass": passed,
        }
    candidates = {}
    motion_pass = True
    limits = config.motion_limits
    for candidate_id, candidate in grid["candidates"].items():
        geometry = grid["geometries"][candidate["geometry"]]
        if candidate["mechanism"] == "command_delay":
            detail = delay_counterfactual(geometry, float(candidate["delay_s"]))
            detail["motion_envelope_pass"] = True
        else:
            detail = reference_counterfactual(geometry, candidate)
            segments = [detail["bias_segment"], detail["reset_segment"]]
            detail["motion_limits"] = {
                "velocity_mps": float(limits["velocity"]),
                "acceleration_mps2": float(limits["acceleration"]),
                "jerk_mps3": float(limits["jerk"]),
            }
            detail["motion_envelope_pass"] = all(
                segment["max_component_velocity_mps"] <= float(limits["velocity"]) + 1e-9
                and segment["max_component_acceleration_mps2"] <= float(limits["acceleration"]) + 1e-9
                and segment["max_component_jerk_mps3"] <= float(limits["jerk"]) + 1e-9
                for segment in segments
            )
        motion_pass = motion_pass and detail["motion_envelope_pass"]
        candidates[candidate_id] = detail
    candidate_order = grid["execution_order"]["candidate_order"]
    conditions = grid["qualification_population"]["conditions"]
    seeds = grid["qualification_population"]["seeds"]
    expanded = [
        f"E3V4B-{candidate}__{condition}__S{seed}"
        for candidate in candidate_order for condition in conditions for seed in seeds
    ]
    expanded_sha = canonical_sha256(expanded)
    order_pass = (
        len(expanded) == int(grid["execution_order"]["expanded_attempt_count"])
        and expanded_sha == grid["execution_order"]["canonical_expanded_order_sha256"]
    )
    result = {
        "schema": "E3_v4_family_B_execution_deviation_offline_audit_v1",
        "status": "PASS" if all_planning_pass and motion_pass and order_pass else "FAIL",
        "grid_sha256": sha256_file(GRID),
        "policy_sha256": sha256_file(POLICY),
        "thresholds_m": {"d_hard": safety.d_hard, "d_plan": safety.d_plan},
        "geometries": geometries,
        "candidates": candidates,
        "all_planning_gates_pass": all_planning_pass,
        "all_reference_command_segments_within_frozen_motion_limits": motion_pass,
        "execution_order": {
            "attempt_count": len(expanded),
            "canonical_sha256": expanded_sha,
            "matches_registry": order_pass,
            "attempts": expanded,
        },
        "F1_attempt_count": 0,
        "formal_attempt_count": 0,
    }
    if args.output.exists():
        raise FileExistsError(args.output)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    return 0 if result["status"] == "PASS" else 2


if __name__ == "__main__":
    raise SystemExit(main())
