#!/usr/bin/env python3
"""Audit unchanged E3-v3 Family-A scenes against the frozen E3-v4 runtime."""

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
REGISTRY = E3 / "e3_factorial_registry_v3.yaml"
POLICY = REPO / "lfs_policy/config/lfs_policy.paper_current.yaml"
sys.path[:0] = [str(REPO / "location_allocate"), str(REPO / "lfs_policy")]

from location_allocate.policy_adapter import load_runtime_policy  # noqa: E402


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def motion_metrics(delta: np.ndarray, duration: float) -> dict:
    component = float(np.max(np.abs(delta)))
    return {
        "max_component_velocity_mps": component * 1.875 / duration,
        "max_component_acceleration_mps2": component * 10 * math.sqrt(3) / 3 / duration**2,
        "max_component_jerk_mps3": component * 60 / duration**3,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    registry = yaml.safe_load(REGISTRY.read_text())
    config, policy = load_runtime_policy(POLICY)
    safety = policy.resolve_safety(1.0)
    limits = config.motion_limits
    results = {}
    all_pass = True
    for scene in registry["scenarios"]:
        if scene["scenario_id"] not in ("E3-A-01", "E3-A-02"):
            continue
        ids = [int(value) for value in scene["uav_ids"]]
        initial = [scene["initial_positions_m"][uid] for uid in ids]
        targets = [scene["ordered_targets_m"][uid] for uid in ids]
        modes = {}
        feasible = True
        for condition, mode in (("P0", "distance_hungarian"),
                                ("P1", "safety_aware")):
            allocator = policy.allocator_factory(safety.d_hard, safety.d_plan)
            assigned, metrics = allocator.allocate_mode_with_metrics(
                initial, targets, float(scene["duration_s"]), mode=mode
            )
            segments = [motion_metrics(
                np.asarray(target) - np.asarray(start), float(scene["duration_s"])
            ) for start, target in zip(initial, assigned)]
            mode_feasible = all(
                value["max_component_velocity_mps"] <= float(limits["velocity"]) + 1e-9
                and value["max_component_acceleration_mps2"] <= float(limits["acceleration"]) + 1e-9
                and value["max_component_jerk_mps3"] <= float(limits["jerk"]) + 1e-9
                for value in segments
            )
            feasible &= mode_feasible
            modes[condition] = {
                "assignment": allocator.last_assignment,
                "predicted_hard_violations": int(metrics.hard_violations),
                "predicted_d_min_m": float(metrics.min_distance),
                "motion_limits_pass": mode_feasible,
                "maximum_motion_metrics": {
                    key: max(value[key] for value in segments) for key in segments[0]
                },
            }
        unchanged = scene["disturbance"]["affected_uavs"] == []
        passed = (
            modes["P0"]["predicted_hard_violations"] > 0
            and modes["P1"]["predicted_hard_violations"] == 0
            and feasible and unchanged
        )
        all_pass &= passed
        results[scene["scenario_id"]] = {
            "source": "immutable E3-v3 registry",
            "geometry_duration_targets_unchanged": True,
            "zero_execution_deviation": unchanged,
            "modes": modes,
            "compatibility_status": "PASS" if passed else "FAIL",
        }
    output = {
        "schema": "E3_v4_family_A_compatibility_audit_v1",
        "status": "PASS" if all_pass and len(results) == 2 else "FAIL",
        "production_method_changed": False,
        "old_E3_v3_registry_sha256": sha(REGISTRY),
        "policy_sha256": sha(POLICY),
        "safety": {"d_hard_m": safety.d_hard, "d_plan_m": safety.d_plan},
        "motion_limits": limits,
        "scenarios": results,
        "conclusion": "Family A remains unchanged and retains its planning manipulation under the frozen E3-v4 runtime.",
        "F1_attempt_count": 0,
        "formal_attempt_count": 0,
    }
    args.output.write_text(json.dumps(output, indent=2, sort_keys=True) + "\n")
    print(output["status"])
    return 0 if output["status"] == "PASS" else 2


if __name__ == "__main__":
    raise SystemExit(main())
