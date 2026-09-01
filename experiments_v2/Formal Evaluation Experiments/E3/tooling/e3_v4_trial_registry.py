"""Exact E3-v4 registry/order resolver; no execution or campaign cursor logic."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import re
from typing import Any

import yaml

from e3_formal_backend import build_runtime_spec

TOOLING = Path(__file__).resolve().parent
E3 = TOOLING.parent
REPO = E3.parents[2]
REGISTRY = E3 / "e3_factorial_registry_v4.yaml"
SEEDS = E3 / "E3_v4_formal_paired_seeds.yaml"
ORDER = E3 / "E3_v4_formal_trial_order.txt"
ORDER_META = E3 / "E3_v4_formal_trial_order.yaml"
POLICY = REPO / "lfs_policy/config/lfs_policy.paper_current.yaml"
REGISTRY_SHA256 = "2b3dccc2ad27cf317029c2b7b014bca3a8b28fc8c0a196fd4c2e5abe0be9d4b7"
SEEDS_SHA256 = "665600871ad3fb6cff324ab3ef9144b0d84b42acc19505283679b6ae01586841"
ORDER_SHA256 = "60ee30a7100b53c4964e3f9f086ff3d137fb41282eebc4439760bf17f033b39b"
ORDER_META_SHA256 = "90b4c6358d087303f05701b6c138d59b64a3ac784642cd0c2df4e757cb3e5e4c"
POLICY_SHA256 = "6b47d27f4253d7311e79ea51f6dd1cf0d0182e6df24374a94abae0aa6a135858"
OLD_V3_SHA256 = "b56344c6cd257e99851523d640d9a89d6def994884877e2303d8fab836e0faf2"
EXPECTED_REGISTRY_STATUS = "SEALED_FOR_FORMAL_EXECUTION"
TRIAL = re.compile(r"^(E3-[ABC]-0[12])__(P[01]_F[01])__S([0-9]+)$")
DELIVERY_TOLERANCES = {
    "command_delay_s": 0.05,
    "reference_activation_time_s": 0.05,
    "reference_duration_s": 0.05,
    "target_coordinate_m": 0.000001,
    "controller_acceptance_timeout_ros_s": 1.0,
    "effective_reference_endpoint_tolerance_m": 0.15,
}


class RegistryError(RuntimeError):
    pass


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def canonical_sha256(value: Any) -> str:
    return hashlib.sha256(json.dumps(
        value, sort_keys=True, separators=(",", ":")
    ).encode()).hexdigest()


def _load() -> tuple[dict, dict, dict]:
    expected = {
        REGISTRY: REGISTRY_SHA256, SEEDS: SEEDS_SHA256, ORDER: ORDER_SHA256,
        ORDER_META: ORDER_META_SHA256, POLICY: POLICY_SHA256,
    }
    mismatches = {str(path): sha256_file(path) for path, wanted in expected.items()
                  if not path.is_file() or sha256_file(path) != wanted}
    if mismatches:
        raise RegistryError(f"frozen E3-v4 artifact mismatch: {mismatches}")
    registry = yaml.safe_load(REGISTRY.read_text())
    seeds = yaml.safe_load(SEEDS.read_text())
    order_meta = yaml.safe_load(ORDER_META.read_text())
    if registry["status"] != EXPECTED_REGISTRY_STATUS:
        raise RegistryError("unexpected sealed registry status")
    if order_meta["attempt_count"] != 360 or order_meta["unique_attempt_count"] != 360:
        raise RegistryError("order cardinality mismatch")
    return registry, seeds, order_meta


def registered_trial_ids() -> list[str]:
    _load()
    values = ORDER.read_text().splitlines()
    if len(values) != 360 or len(set(values)) != 360:
        raise RegistryError("registered trial order is not exactly 360 unique IDs")
    return values


def build_exact_spec(trial_id: str) -> dict[str, Any]:
    registry, seed_registry, _meta = _load()
    match = TRIAL.fullmatch(trial_id)
    if not match or trial_id not in set(registered_trial_ids()):
        raise RegistryError(f"unregistered E3-v4 trial: {trial_id}")
    scenario_id, condition, seed_text = match.groups()
    seed = int(seed_text)
    if seed not in seed_registry["paired_seeds"]:
        raise RegistryError("trial uses an unregistered formal seed")
    scene = next(
        value for value in registry["scenarios"]
        if value["scenario_id"] == scenario_id
    )
    mapping = registry["factorial_mapping"]["conditions"][condition]
    duration = float(scene["duration_s"])
    manipulation = dict(scene["manipulation"])
    spec = {
        "spec_type": "E3_v4_registered_formal_spec_v1",
        "fixture_class": "E3_v4_registered_formal_scene",
        "dataset_class": "formal_evaluation",
        "accepted_formal_result": True,
        "formal_cursor_consumed": False,
        "trial_id": trial_id,
        "candidate_id": scenario_id,
        "scenario_id": scenario_id,
        "condition": condition,
        "seed": seed,
        "family": scene["family"],
        "uav_ids": [int(value) for value in scene["uav_ids"]],
        "initial_positions_m": scene["initial_positions_m"],
        "ordered_targets_m": scene["ordered_targets_m"],
        "duration_s": duration,
        "staging": {"stable_continuous_s": 2.0, "scored": False},
        "scoring": {
            "t0": "first nominal interaction execution-command header timestamp",
            "end_offset_s": duration + 2.0,
        },
        "timeout_after_t0_s": duration + 6.0,
        "assignment_mode": mapping["assignment_mode"],
        "avoidance_mode": mapping["avoidance_mode"],
        "invariants": {
            "style": "normal", "safety_s": 1.0, "q": {"mode": "direct"},
            "lfs_runtime_mode": "candidate_v2",
            "control_mode": "ladrc_acceleration",
            "policy": "lfs_policy.paper_current.yaml",
        },
        "disturbance": manipulation,
        "manipulation": manipulation,
        "intended_pair": [int(value) for value in scene.get("intended_pair", [])],
        "delivery_tolerances": DELIVERY_TOLERANCES,
        "registry_sha256": REGISTRY_SHA256,
        "formal_seed_registry_sha256": SEEDS_SHA256,
        "order_sha256": ORDER_SHA256,
        "metric_log_schema": {
            "primary_metrics": [
                "actual_d_min", "predicted_d_min", "hard_risk_events",
                "hard_risk_exposure_duration", "mission_success",
                "intended_pair_attribution", "manipulation_delivery",
            ],
            "raw_required": [
                "clock", "execution_commands", "startup_events",
                "per_uav_position_3d", "per_uav_nominal_reference",
                "hard_failures", "manipulation_event_ledger",
            ],
        },
    }
    spec["registered_input_hash"] = canonical_sha256({
        "registry_sha256": REGISTRY_SHA256,
        "formal_seed_registry_sha256": SEEDS_SHA256,
        "order_sha256": ORDER_SHA256,
        "scene": scene, "condition": condition, "seed": seed,
    })
    spec["resolved_execution_spec_hash"] = canonical_sha256(spec)
    return spec


def build_exact_runtime_spec(trial_id: str) -> dict[str, Any]:
    spec = build_exact_spec(trial_id)
    runtime = build_runtime_spec(spec)
    runtime.update({
        "runtime_spec_type": "E3_v4_registered_physical_runtime_spec_v1",
        "spec_type": spec["spec_type"],
        "candidate_id": spec["candidate_id"],
        "scenario_id": spec["scenario_id"],
        "condition": spec["condition"],
        "family": spec["family"],
        "manipulation": spec["manipulation"],
        "intended_pair": spec["intended_pair"],
        "delivery_tolerances": spec["delivery_tolerances"],
        "registered_input_hash": spec["registered_input_hash"],
        "registry_sha256": REGISTRY_SHA256,
        "formal_seed_registry_sha256": SEEDS_SHA256,
        "order_sha256": ORDER_SHA256,
        "accepted_formal_result": True,
        "formal_cursor_consumed": False,
    })
    runtime["runtime_spec_sha256"] = canonical_sha256(runtime)
    return runtime
