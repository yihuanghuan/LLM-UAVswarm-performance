#!/usr/bin/env python3
"""Offline planning, isolation, and envelope audit for frozen Family C grid."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path
import sys

import numpy as np
import yaml

TOOLING = Path(__file__).resolve().parent
E3 = TOOLING.parent
REPO = E3.parents[2]
GRID = E3 / "E3_v4_family_C_execution_deviation_grid.yaml"
POLICY = REPO / "lfs_policy/config/lfs_policy.paper_current.yaml"
sys.path[:0] = [str(REPO / "location_allocate"), str(REPO / "lfs_policy")]

from location_allocate.policy_adapter import load_runtime_policy  # noqa: E402


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def canonical(value) -> str:
    return hashlib.sha256(json.dumps(
        value, sort_keys=True, separators=(",", ":")
    ).encode()).hexdigest()


def minimum_jerk(value):
    value = np.clip(value, 0.0, 1.0)
    return 10 * value**3 - 15 * value**4 + 6 * value**5


def segment(delta: np.ndarray, duration: float) -> dict:
    component = np.max(np.abs(delta))
    return {
        "delta_m": delta.tolist(), "duration_s": duration,
        "max_component_velocity_mps": float(component * 1.875 / duration),
        "max_component_acceleration_mps2": float(
            component * 10 * math.sqrt(3) / 3 / duration**2
        ),
        "max_component_jerk_mps3": float(component * 60 / duration**3),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    grid = yaml.safe_load(GRID.read_text())
    config, policy = load_runtime_policy(POLICY)
    safety = policy.resolve_safety(1.0)
    geometries = {}
    planning_pass = True
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
                "assignment": allocator.last_assignment,
                "assigned_targets_m": assigned,
                "predicted_hard_violations": int(metrics.hard_violations),
                "predicted_d_min_m": float(metrics.min_distance),
            }
        p0, p1 = modes["P0_F0"], modes["P1_F0"]
        structural = [0, 1, 2, 3]
        residual = [4, 5, 6, 7]
        isolation = all(p0["assignment"][i] in structural for i in structural)
        isolation &= all(p0["assignment"][i] in residual for i in residual)
        isolation &= all(p1["assignment"][i] in structural for i in structural)
        isolation &= all(p1["assignment"][i] in residual for i in residual)
        residual_unchanged = (
            p0["assignment"][4:] == [4, 5, 6, 7]
            and p1["assignment"][4:] == [4, 5, 6, 7]
        )
        passed = (
            p0["predicted_hard_violations"] >= 1
            and p1["predicted_hard_violations"] == 0
            and p1["predicted_d_min_m"] >= safety.d_plan - 1e-9
            and p0["assignment"][:4] != p1["assignment"][:4]
            and residual_unchanged and isolation
        )
        planning_pass &= passed
        geometries[name] = {
            "modes": modes, "cross_component_assignment_absent": isolation,
            "residual_component_identity_in_both_modes": residual_unchanged,
            "mixed_planning_gate_pass": passed,
        }

    candidates = {}
    envelope_pass = True
    for candidate_id, candidate in grid["candidates"].items():
        geometry = grid["geometries"][candidate["geometry"]]
        ids = geometry["uav_ids"]
        initial = np.asarray([geometry["initial_positions_m"][uid] for uid in ids])
        targets = np.asarray([geometry["ordered_targets_m"][uid] for uid in ids])
        duration = float(geometry["duration_s"])
        if candidate["mechanism"] == "command_delay":
            delay = float(candidate["delay_s"])
            t = np.linspace(0, duration + delay, 200001)
            positions = []
            for index, uid in enumerate(ids):
                shifted = delay if uid in candidate["affected_uavs"] else 0.0
                progress = minimum_jerk((t - shifted) / duration)
                positions.append(initial[index] + progress[:, None] * (targets[index] - initial[index]))
            first, second = [ids.index(uid) for uid in candidate["intended_pair"]]
            distance = np.linalg.norm(positions[first] - positions[second], axis=1)
            detail = {
                "ideal_intended_pair_d_min_m": float(np.min(distance)),
                "motion_envelope_pass": True,
            }
        else:
            affected = ids.index(int(candidate["affected_uav"]))
            start = float(candidate["start_s"])
            interval = float(candidate["duration_s"])
            at_start = initial[affected] + minimum_jerk(start / duration) * (
                targets[affected] - initial[affected]
            )
            counterfactual = initial[affected] + minimum_jerk(
                (start + interval) / duration
            ) * (targets[affected] - initial[affected])
            bias_target = counterfactual + np.asarray(candidate["offset_m"])
            bias = segment(bias_target - at_start, interval)
            reset = segment(targets[affected] - bias_target, duration - start - interval)
            limits = config.motion_limits
            passed = all(
                part["max_component_velocity_mps"] <= float(limits["velocity"]) + 1e-9
                and part["max_component_acceleration_mps2"] <= float(limits["acceleration"]) + 1e-9
                and part["max_component_jerk_mps3"] <= float(limits["jerk"]) + 1e-9
                for part in (bias, reset)
            )
            pair = ids.index(int(candidate["intended_pair"][0]))
            pair_at_reset = initial[pair] + minimum_jerk(
                (start + interval) / duration
            ) * (targets[pair] - initial[pair])
            detail = {
                "bias_endpoint_m": bias_target.tolist(),
                "ideal_intended_pair_distance_at_bias_endpoint_m": float(
                    np.linalg.norm(pair_at_reset - bias_target)
                ),
                "bias_segment": bias, "reset_segment": reset,
                "motion_envelope_pass": passed,
            }
        envelope_pass &= detail["motion_envelope_pass"]
        candidates[candidate_id] = detail
    expanded = [
        f"E3V4C-{candidate}__{condition}__S{seed}"
        for candidate in grid["execution_order"]["candidate_order"]
        for condition in grid["qualification_population"]["conditions"]
        for seed in grid["qualification_population"]["seeds"]
    ]
    result = {
        "schema": "E3_v4_family_C_offline_audit_v1",
        "status": "PASS" if planning_pass and envelope_pass and len(expanded) == 40
                  and canonical(expanded) == grid["execution_order"]["canonical_expanded_order_sha256"]
                  else "FAIL",
        "grid_sha256": sha(GRID), "policy_sha256": sha(POLICY),
        "safety": {"d_hard_m": safety.d_hard, "d_plan_m": safety.d_plan},
        "geometries": geometries, "candidates": candidates,
        "expanded_order": expanded, "expanded_order_sha256": canonical(expanded),
        "F1_attempt_count": 0, "formal_attempt_count": 0,
    }
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    print(result["status"])
    return 0 if result["status"] == "PASS" else 2


if __name__ == "__main__":
    raise SystemExit(main())
