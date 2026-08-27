"""Sealed E3 registry loading and deterministic exact-spec reconstruction."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import re
from typing import Any, Dict, List

import yaml

TOOLING_DIR = Path(__file__).resolve().parent
E3_DIR = TOOLING_DIR.parent
FORMAL_DIR = E3_DIR.parent
REPO_ROOT = FORMAL_DIR.parents[1]
PROTOCOL_PATH = FORMAL_DIR / "protocols" / "E3_protocol_v1.yaml"
REGISTRY_PATH = E3_DIR / "e3_factorial_registry_v1.yaml"
GLOBAL_REGISTRY_PATH = FORMAL_DIR / "e2_e5_scenario_seed_registry_v1.yaml"
ORDER_PATH = FORMAL_DIR / "simulation_trial_order_v1.txt"
POLICY_PATH = REPO_ROOT / "lfs_policy" / "config" / "lfs_policy.paper_current.yaml"

PROTOCOL_SHA256 = "68f134cbf41a5be30e83a0953daa1a8d74866939d0450f60ebb31298616f56d8"
REGISTRY_SHA256 = "48d66a07c744af4fad0f483ca24c72cf30dfbcaac9468e50ea3252ce6f76ea41"
GLOBAL_REGISTRY_SHA256 = "90313d33793940489edde631d397564378ae54fe3cfddf438e4a895d6132254d"
ORDER_SHA256 = "db28bf8d734e1f206987519e91ff27c67b2d9ab2971aeb68c4e13735762f1dce"
POLICY_SHA256 = "6b47d27f4253d7311e79ea51f6dd1cf0d0182e6df24374a94abae0aa6a135858"
CONDITIONS = ("P1_F1", "P1_F0", "P0_F1", "P0_F0")
CONDITION_MAPPING = {
    "P1_F1": {"assignment_mode": "safety_aware", "avoidance_mode": "iapf_dual"},
    "P1_F0": {"assignment_mode": "safety_aware", "avoidance_mode": "off"},
    "P0_F1": {"assignment_mode": "distance_hungarian", "avoidance_mode": "iapf_dual"},
    "P0_F0": {"assignment_mode": "distance_hungarian", "avoidance_mode": "off"},
}
TRIAL_RE = re.compile(r"^(E3-[ABC]-0[12])__(P[01]_F[01])__S(\d+)$")


class E3Error(RuntimeError):
    pass


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def canonical_bytes(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()


def canonical_sha256(value: Any) -> str:
    return hashlib.sha256(canonical_bytes(value)).hexdigest()


def load_yaml(path: Path) -> Dict[str, Any]:
    value = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise E3Error(f"expected mapping: {path}")
    return value


def load_registry() -> Dict[str, Any]:
    if sha256_file(PROTOCOL_PATH) != PROTOCOL_SHA256:
        raise E3Error("sealed E3 protocol hash mismatch")
    if sha256_file(REGISTRY_PATH) != REGISTRY_SHA256:
        raise E3Error("sealed E3 registry hash mismatch")
    if sha256_file(GLOBAL_REGISTRY_PATH) != GLOBAL_REGISTRY_SHA256:
        raise E3Error("sealed global seed registry hash mismatch")
    if sha256_file(ORDER_PATH) != ORDER_SHA256:
        raise E3Error("sealed global order hash mismatch")
    if sha256_file(POLICY_PATH) != POLICY_SHA256:
        raise E3Error("canonical policy hash mismatch")
    protocol, registry = load_yaml(PROTOCOL_PATH), load_yaml(REGISTRY_PATH)
    if protocol.get("status") != "SEALED" or registry.get("status") != "SEALED":
        raise E3Error("E3 protocol/registry is not SEALED")
    return registry


def scenario_index(registry: Dict[str, Any] | None = None) -> Dict[str, Dict[str, Any]]:
    registry = registry or load_registry()
    result = {item["scenario_id"]: item for item in registry["scenarios"]}
    if len(result) != 6:
        raise E3Error("E3 must contain exactly six unique scenarios")
    return result


def registered_trial_ids(registry: Dict[str, Any] | None = None) -> List[str]:
    registry = registry or load_registry()
    ids = [f"{scenario['scenario_id']}__{condition}__S{seed}"
           for scenario in registry["scenarios"]
           for condition in CONDITIONS
           for seed in registry["paired_seeds"]]
    if len(ids) != 360 or len(set(ids)) != 360:
        raise E3Error("E3 population is not exactly 360 unique trials")
    order = ORDER_PATH.read_text(encoding="utf-8").splitlines()
    filtered = [item for item in order if item.startswith("E3-")]
    if len(filtered) != 360 or set(filtered) != set(ids):
        raise E3Error("E3 population does not exactly match sealed global permutation")
    if any(order.count(item) != 1 for item in ids):
        raise E3Error("E3 trial does not appear exactly once in global permutation")
    return ids


def parse_trial_id(trial_id: str, registry: Dict[str, Any] | None = None) -> Dict[str, Any]:
    match = TRIAL_RE.fullmatch(str(trial_id))
    if match is None:
        if str(trial_id).startswith(("E2-", "E4A-", "E4B-", "E5-")):
            raise E3Error(f"wrong experiment family: {trial_id}")
        raise E3Error(f"malformed or unknown E3 trial: {trial_id}")
    scenario_id, condition, seed_text = match.groups()
    registry = registry or load_registry()
    scenarios = scenario_index(registry)
    seed = int(seed_text)
    if scenario_id not in scenarios:
        raise E3Error(f"unregistered E3 scenario: {scenario_id}")
    if condition not in CONDITIONS:
        raise E3Error(f"unregistered E3 condition: {condition}")
    if seed not in registry["paired_seeds"]:
        raise E3Error(f"unregistered E3 seed: {seed}")
    if trial_id not in set(registered_trial_ids(registry)):
        raise E3Error(f"unregistered E3 trial: {trial_id}")
    return {"scenario_id": scenario_id, "condition": condition, "seed": seed}


def build_exact_spec(trial_id: str, registry: Dict[str, Any] | None = None) -> Dict[str, Any]:
    registry = registry or load_registry()
    identity = parse_trial_id(trial_id, registry)
    scenario = scenario_index(registry)[identity["scenario_id"]]
    mapping = CONDITION_MAPPING[identity["condition"]]
    duration = float(scenario["duration_s"])
    disturbance = scenario["disturbance"]
    spec = {
        "spec_type": "E3_exact_execution_spec_v1",
        "trial_id": trial_id,
        "experiment": "E3",
        **identity,
        "family": scenario["family"],
        "input_level": registry["common_execution"]["input_level"],
        "uav_ids": scenario["uav_ids"],
        "initial_positions_m": scenario["initial_positions_m"],
        "ordered_targets_m": scenario["ordered_targets_m"],
        "duration_s": duration,
        "staging": {"stable_continuous_s": 2.0, "scored": False},
        "scoring": {"t0": "interaction_execution_command_timestamp",
                    "end_offset_s": duration + 2.0},
        "timeout_after_t0_s": duration + 6.0,
        "assignment_mode": mapping["assignment_mode"],
        "avoidance_mode": mapping["avoidance_mode"],
        "P0_fixed_target_ownership": False if identity["condition"].startswith("P0") else None,
        "invariants": {
            "style": "normal", "safety_s": 1.0, "q": {"mode": "direct"},
            "lfs_runtime_mode": "candidate_v2", "control_mode": "ladrc_acceleration",
            "policy": "lfs_policy.paper_current.yaml",
        },
        "disturbance": {
            "mechanism": registry["disturbance_contract"]["mechanism"],
            "model_overlay": registry["disturbance_contract"]["model_overlay"],
            "link": "base_link", "force_frame": "world",
            "waveform": "rectangular constant force", "torque": [0.0, 0.0, 0.0],
            "timing_basis": "/clock elapsed from /e3/disturbance_arm received at t0",
            "affected_uavs": disturbance["affected_uavs"],
            "vectors_N": disturbance["vector_N"],
            "onset_s": float(disturbance["onset_s"]),
            "duration_s": float(disturbance["duration_s"]),
            "zero_wrench_at_end": True, "random_component": None,
            "loaded_for_zero_force_family_A": True,
        },
        "metric_log_schema": {
            "primary_metrics": ["actual_d_min", "predicted_d_min", "hard_risk_events",
                "hard_risk_exposure_duration", "mission_success", "iapf_activation_time",
                "integral_delta_p", "integral_delta_a", "trajectory_deviation"],
            "raw_required": ["clock", "execution_command_t0", "per_uav_position_3d",
                "per_uav_nominal_reference", "per_uav_safe_reference", "iapf_active",
                "iapf_delta_p", "iapf_delta_a", "allocator_prediction", "completion_events",
                "hard_failures", "wrench_commands"],
        },
    }
    spec["registered_input_hash"] = canonical_sha256({
        "scenario": scenario, "condition": identity["condition"], "seed": identity["seed"]
    })
    spec["resolved_execution_spec_hash"] = canonical_sha256(spec)
    return spec

