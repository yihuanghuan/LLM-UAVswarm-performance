#!/usr/bin/env python3
"""Resolve one scheduled entry into immutable runtime configs and commands."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path
import sys

import yaml

ROOT = Path(__file__).resolve().parents[1]
REPOSITORY = ROOT.parents[3]
sys.path.insert(0, str(REPOSITORY / "location_allocate"))
sys.path.insert(0, str(REPOSITORY / "lfs_policy"))

from location_allocate.execution_profile_compiler import (
    compile_execution_profiles,
)
from location_allocate.lfs_types import ExecutableLFS
from location_allocate.policy_adapter import load_runtime_policy


DEFAULT_SCHEDULE = ROOT / "trial_order_v3.json"
DEFAULT_CONFIG = ROOT / "configs" / "c0a_prereg_v3.json"
BASE_POLICY = REPOSITORY / "lfs_policy" / "config" / "lfs_policy.paper_current.yaml"
BASE_CONTROLLER = (
    REPOSITORY / "minisnap_LADRC" / "ladrc_controller" / "config" / "ladrc_params.yaml"
)


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def minimum_duration(distance, v_limit, a_limit, j_limit, floor):
    return max(
        floor,
        1.875 * distance / v_limit,
        math.sqrt((10.0 / math.sqrt(3.0)) * distance / a_limit),
        (60.0 * distance / j_limit) ** (1.0 / 3.0),
    )


def vector_scale(vector, factor):
    return [round(float(value) * float(factor), 12) for value in vector]


def resolve_parameters(entry, state):
    stage = entry["stage"]
    parameters = dict(entry["candidate_parameters"])
    if stage == "A1_SCREENING":
        return parameters
    if stage == "A1_CONFIRMATION":
        mapped = state["a1_confirmation_mapping"][entry["candidate_id"]]
        return dict(state["a1_candidates"][mapped])
    if stage == "A2_SCREENING":
        return {**state["a1_winner"], **parameters}
    if stage == "A2_CONFIRMATION":
        mapped = state["a2_confirmation_mapping"][entry["candidate_id"]]
        return {**state["a1_winner"], **state["a2_candidates"][mapped]}
    if stage == "A3_VALIDATION":
        return {**state["a1_winner"], **state["a2_winner"], **parameters}
    if stage == "SCALE_VALIDATION":
        return {
            **state["a1_winner"],
            **state["a2_winner"],
            **state["a3_winner"],
        }
    raise ValueError(f"unsupported stage: {stage}")


def scenario_geometry(entry, registry):
    if entry["stage"] != "SCALE_VALIDATION":
        key = f"{entry['scenario_id']}:{entry['signed_displacement_id']}"
        displacement = registry["single_uav_cases"][key]
        starts = [list(registry["single_uav_start"])]
        targets = [[starts[0][axis] + displacement[axis] for axis in range(3)]]
        return [1], starts, targets, "single_origin"
    count = registry["scale"]["uav_counts"][entry["scenario_id"]]
    ids = list(range(1, count + 1))
    starts = [[-4.0, 3.0 * uid, 3.0] for uid in ids]
    targets = [[4.0, 3.0 * uid, 3.0] for uid in ids]
    return ids, starts, targets, "parallel_scale"


def resolved_clamps(entry, parameters):
    if entry["stage"] in {"A3_VALIDATION", "SCALE_VALIDATION"}:
        omega_low = parameters["omega_lower_multiplier"]
        omega_high = parameters["omega_upper_multiplier"]
        motion_multiplier = parameters["motion_clamp_multiplier"]
    else:
        omega_low, omega_high, motion_multiplier = 0.75, 1.25, 1.0
    return {
        "omega_c_min": vector_scale(parameters["omega_c"], omega_low),
        "omega_c_max": vector_scale(parameters["omega_c"], omega_high),
        "omega_o_min": vector_scale(parameters["omega_o"], omega_low),
        "omega_o_max": vector_scale(parameters["omega_o"], omega_high),
        "velocity_max": parameters["v_limit"] * motion_multiplier,
        "acceleration_max": parameters["a_limit"] * motion_multiplier,
        "jerk_max": parameters["j_limit"] * motion_multiplier,
        "omega_lower_multiplier": omega_low,
        "omega_upper_multiplier": omega_high,
        "motion_clamp_multiplier": motion_multiplier,
    }


def render(entry, state, registry, output):
    parameters = resolve_parameters(entry, state)
    uav_ids, starts, targets, layout = scenario_geometry(entry, registry)
    distance = max(math.dist(start, target) for start, target in zip(starts, targets))
    t_min = minimum_duration(
        distance,
        parameters["v_limit"],
        parameters["a_limit"],
        parameters["j_limit"],
        parameters["minimum_duration"],
    )
    duration = t_min * entry["duration_condition"]["value"]
    clamps = resolved_clamps(entry, parameters)

    policy = yaml.safe_load(BASE_POLICY.read_text(encoding="utf-8"))
    policy["configuration_id"] = f"paper-current-v7-{entry['candidate_id'].lower()}"
    policy["execution_profile"]["baseline_omega_c"] = parameters["omega_c"]
    policy["execution_profile"]["baseline_omega_o"] = parameters["omega_o"]
    policy["motion_limits"] = {
        "velocity": parameters["v_limit"],
        "acceleration": parameters["a_limit"],
        "jerk": parameters["j_limit"],
    }
    policy["timing"]["minimum_duration"] = parameters["minimum_duration"]
    hard = policy["controller_hard_clamps"]
    for key in (
        "omega_c_min", "omega_c_max", "omega_o_min", "omega_o_max",
        "velocity_max", "acceleration_max", "jerk_max",
    ):
        hard[key] = clamps[key]
    policy_path = output / "candidate_policy.yaml"
    policy_path.write_text(yaml.safe_dump(policy, sort_keys=False), encoding="utf-8")

    controller = yaml.safe_load(BASE_CONTROLLER.read_text(encoding="utf-8"))
    ros_parameters = controller["/**"]["ros__parameters"]
    ros_parameters["neighbor_uav_ids"] = uav_ids
    if entry["stage"] in {"A3_VALIDATION", "SCALE_VALIDATION"}:
        ros_parameters["max_velocity"] = parameters["v_limit"]
        ros_parameters["max_acceleration_x"] = parameters["a_limit"]
        ros_parameters["max_acceleration_y"] = parameters["a_limit"]
        ros_parameters["max_acceleration_z"] = parameters["a_limit"]
    controller_path = output / "controller_params.yaml"
    controller_path.write_text(
        yaml.safe_dump(controller, sort_keys=False), encoding="utf-8"
    )

    loaded, runtime_policy = load_runtime_policy(policy_path)
    safety = runtime_policy.resolve_safety(1.0)
    executable = ExecutableLFS(
        uav_ids=tuple(uav_ids),
        formation={"type": "c0a_registered_direct_targets"},
        center=(0.0, 0.0, 0.0),
        radius=0.0,
        duration=duration,
        motion_style="normal",
        safety_factor=1.0,
        trigger_semantics={"mode": "immediate"},
    )
    profiles = compile_execution_profiles(
        executable, starts, targets, runtime_policy.profile, safety.soft_iapf
    )
    serialized_profiles = []
    for profile in profiles:
        serialized_profiles.append({
            "duration": profile.duration,
            "style": profile.style,
            "omega_c": list(profile.omega_c),
            "omega_o": list(profile.omega_o),
            "velocity_limit": profile.velocity_limit,
            "acceleration_limit": profile.acceleration_limit,
            "jerk_limit": profile.jerk_limit,
            "iapf_enter_distance": profile.iapf_enter_distance,
            "iapf_exit_distance": profile.iapf_exit_distance,
            "iapf_repulsion_scale": profile.iapf_repulsion_scale,
            "configuration_id": profile.configuration_id,
            "style_gain": profile.style_gain,
            "task_gain": profile.task_gain,
        })

    spec = {
        "calibration_id": "C0-A",
        "protocol_version": registry["protocol_version"],
        "dataset_class": "calibration",
        "entry": entry,
        "resolved_candidate_parameters": parameters,
        "resolved_hard_clamps": clamps,
        "uav_ids": uav_ids,
        "world_starts": starts,
        "world_targets": targets,
        "layout": layout,
        "distance_m": distance,
        "t_min_s": t_min,
        "explicit_duration_s": duration,
        "profiles": serialized_profiles,
        "policy_configuration_id": loaded.configuration_id,
        "policy_sha256": sha256(policy_path),
        "controller_config_sha256": sha256(controller_path),
        "policy_path": str(policy_path.resolve()),
        "controller_params_path": str(controller_path.resolve()),
        "control_mode": "ladrc_acceleration",
        "motion_style": "normal",
        "style_gain": 1.0,
        "safety_factor": 1.0,
        "avoidance_mode": "iapf_dual",
        "iapf_escape_mode": "id_order",
        "seed_support": {
            "schedule": entry["seed"],
            "px4": "seed_not_supported",
            "gazebo": "seed_not_supported",
        },
        "zero_crossings_role": registry["zero_crossings_role"],
    }
    return spec


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--trial-id", required=True)
    parser.add_argument("--state", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--schedule", type=Path, default=DEFAULT_SCHEDULE)
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    args = parser.parse_args()
    schedule = json.loads(args.schedule.read_text(encoding="utf-8"))
    entries = [entry for entry in schedule["entries"] if entry["trial_id"] == args.trial_id]
    if len(entries) != 1:
        raise SystemExit(f"expected one scheduled entry for {args.trial_id}, got {len(entries)}")
    state = json.loads(args.state.read_text(encoding="utf-8"))
    registry = json.loads(args.config.read_text(encoding="utf-8"))
    args.output.mkdir(parents=True, exist_ok=False)
    spec = render(entries[0], state, registry, args.output)
    (args.output / "trial_spec.json").write_text(
        json.dumps(spec, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(json.dumps({
        "trial_id": args.trial_id,
        "duration_s": spec["explicit_duration_s"],
        "policy_sha256": spec["policy_sha256"],
    }, sort_keys=True))


if __name__ == "__main__":
    main()
