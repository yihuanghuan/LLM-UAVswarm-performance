#!/usr/bin/env python3
"""Build/check the candidate E3-v4 registry, paired seeds, and 360 order."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

import yaml

TOOLING = Path(__file__).resolve().parent
E3 = TOOLING.parent
V3 = E3 / "e3_factorial_registry_v3.yaml"
B = E3 / "E3_v4_family_B_registry.yaml"
C = E3 / "E3_v4_family_C_registry.yaml"
A_AUDIT = E3 / "E3_v4_family_A_compatibility_audit.json"
B_EVIDENCE = E3 / "E3_v4_family_B_execution_deviation_qualification_evidence.json"
C_EVIDENCE = E3 / "E3_v4_family_C_execution_deviation_qualification_evidence.json"
SEEDS = E3 / "E3_v4_formal_paired_seeds.yaml"
REGISTRY = E3 / "e3_factorial_registry_v4.yaml"
ORDER = E3 / "E3_v4_formal_trial_order.txt"
ORDER_META = E3 / "E3_v4_formal_trial_order.yaml"
POLICY_SHA = "6b47d27f4253d7311e79ea51f6dd1cf0d0182e6df24374a94abae0aa6a135858"
V3_SHA = "b56344c6cd257e99851523d640d9a89d6def994884877e2303d8fab836e0faf2"
PRODUCTION = "6cf402debf23851b1eff3edc6f3ab49eae7127c4"
SEED_NAMESPACE = "E3-v4-confirmatory-formal-paired-seed-v1"
ORDER_NAMESPACE = "E3-v4-confirmatory-order-v1"
CONDITIONS = ["P0_F0", "P0_F1", "P1_F0", "P1_F1"]


def sha_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def sha_file(path: Path) -> str:
    return sha_bytes(path.read_bytes())


def canonical_sha(value: Any) -> str:
    return sha_bytes(json.dumps(
        value, sort_keys=True, separators=(",", ":")
    ).encode())


def yaml_bytes(value: Any) -> bytes:
    return yaml.safe_dump(value, sort_keys=False, allow_unicode=True).encode()


def generate_seeds() -> list[int]:
    excluded = set(range(53101, 53116)) | {
        69707, 69912, 68907, 67442, 64654,
        76174, 77507, 78307, 77571, 76333,
    }
    values: list[int] = []
    counter = 0
    while len(values) < 15:
        digest = hashlib.sha256(f"{SEED_NAMESPACE}|{counter}".encode()).digest()
        candidate = 100000 + int.from_bytes(digest[:8], "big") % 900000
        if candidate not in excluded and candidate not in values:
            values.append(candidate)
        counter += 1
    return values


def normalize_positions(value: dict) -> dict[int, list[float]]:
    return {int(uid): [float(x) for x in point] for uid, point in value.items()}


def a_scenes(v3: dict) -> list[dict]:
    output = []
    for source in v3["scenarios"]:
        if source["scenario_id"] not in ("E3-A-01", "E3-A-02"):
            continue
        output.append({
            "scenario_id": source["scenario_id"],
            "family": "A_predictable_structural_risk",
            "label": source["label"],
            "uav_ids": [int(value) for value in source["uav_ids"]],
            "duration_s": float(source["duration_s"]),
            "initial_positions_m": normalize_positions(source["initial_positions_m"]),
            "ordered_targets_m": normalize_positions(source["ordered_targets_m"]),
            "structural_risk": source["structural_risk"],
            "manipulation": {"type": "none", "planner_input_includes_deviation": False},
            "source_E3_v3_scene_sha256": canonical_sha(source),
        })
    return output


def normalize_deviation(scene_id: str, source: dict, family: str) -> dict:
    manipulation = dict(source["manipulation"])
    mechanism = manipulation.pop("mechanism", source.get("mechanism"))
    if mechanism == "post_planning_command_delay":
        manipulation["type"] = "command_delay"
    elif mechanism == "post_planning_temporary_reference_deviation":
        manipulation["type"] = "reference_deviation"
        manipulation["start_s"] = manipulation.pop("activation_s_after_nominal_acceptance")
    else:
        raise RuntimeError(f"unsupported manipulation: {mechanism}")
    return {
        "scenario_id": scene_id,
        "family": family,
        "label": source.get("construction", source.get("selected_candidate")),
        "uav_ids": [int(value) for value in source["uav_ids"]],
        "duration_s": float(source["duration_s"]),
        "initial_positions_m": normalize_positions(source["initial_positions_m"]),
        "ordered_targets_m": normalize_positions(source["ordered_targets_m"]),
        "intended_pair": [int(value) for value in source.get(
            "intended_pair", source.get("intended_residual_pair")
        )],
        "manipulation": manipulation,
        "qualification_selected_candidate": source["selected_candidate"],
    }


def build() -> dict[Path, bytes]:
    v3 = yaml.safe_load(V3.read_text())
    b = yaml.safe_load(B.read_text())
    c = yaml.safe_load(C.read_text())
    seeds = generate_seeds()
    seed_registry = {
        "schema": "E3_v4_formal_paired_seeds_v1",
        "status": "FROZEN_BEFORE_FORMAL_EXECUTION",
        "dataset_class": "future_confirmatory_formal_population",
        "namespace": SEED_NAMESPACE,
        "generation": "for counter=0.., sha256(namespace|counter) first 64 bits modulo 900000 plus 100000; reject excluded/duplicate; take first 15",
        "excluded_E3_v3_formal_seeds": list(range(53101, 53116)),
        "excluded_qualification_seeds": [
            69707, 69912, 68907, 67442, 64654,
            76174, 77507, 78307, 77571, 76333,
        ],
        "paired_seed_semantics": "same scenario seed shared by all four P/F conditions",
        "paired_seeds": seeds,
        "paired_seed_count": 15,
        "canonical_seed_list_sha256": sha_bytes(
            ("\n".join(map(str, seeds)) + "\n").encode()
        ),
        "qualification_use_forbidden": True,
        "formal_execution_started": False,
    }
    scenes = a_scenes(v3)
    for scene_id in ("E3-B-01", "E3-B-02"):
        scenes.append(normalize_deviation(
            scene_id, b["scenarios"][scene_id], "B_residual_execution_risk"
        ))
    for scene_id in ("E3-C-01", "E3-C-02"):
        scenes.append(normalize_deviation(
            scene_id, c["scenarios"][scene_id], "C_mixed_risk"
        ))
    registry = {
        "registry_id": "E3-exact-factorial-v4",
        "status": "SEALED_FOR_FORMAL_EXECUTION",
        "supersedes_for_future_confirmation": "E3-exact-factorial-v3",
        "E3-v3_historical_results_remain_valid_and_immutable": True,
        "reason": [
            "residual-risk manipulation failure in E3-v3 Family B",
            "insufficient residual-risk persistence after planning in E3-v3 mixed-risk cases",
            "human-approved replacement by deterministic post-planning execution deviations",
        ],
        "production_baseline": PRODUCTION,
        "configuration_id": "paper-current-v11-c0-f-frozen",
        "policy_sha256": POLICY_SHA,
        "old_E3_v3_registry_sha256": V3_SHA,
        "scenario_count": 6,
        "paired_seeds": seeds,
        "paired_seeds_per_scenario_condition": 15,
        "sample_size_rule": "fixed before formal execution; no significance-triggered extension",
        "common_execution": {
            "input_level": "frozen allocator target set plus executable task fields; no LLM call",
            "frame": "world ENU",
            "style": "normal", "safety_s": 1.0, "q": {"mode": "direct"},
            "staging": "move to exact initial geometry, require frozen-controller stable state continuously for 2.0 s, then commit planning and start scored interaction",
            "staging_is_scored": False,
            "scoring_start": "first nominal interaction execution-command timestamp t0",
            "scoring_end": "t0 plus registered duration plus 2.0 s",
            "timeout": "registered duration plus 6.0 s after t0",
            "target_order": "authoritative allocator input order shown per scenario",
            "scenario_or_sample_extension_after_results": "forbidden",
        },
        "factorial_mapping": {
            "conditions": {
                "P0_F0": {"assignment_mode": "distance_hungarian", "avoidance_mode": "off"},
                "P0_F1": {"assignment_mode": "distance_hungarian", "avoidance_mode": "iapf_dual"},
                "P1_F0": {"assignment_mode": "safety_aware", "avoidance_mode": "off"},
                "P1_F1": {"assignment_mode": "safety_aware", "avoidance_mode": "iapf_dual"},
            },
            "feedback_parameters_frozen": {"iapf_escape_mode": "id_order", "iapf_filter_alpha": 0.20},
            "invariant_flags": {"lfs_runtime_mode": "candidate_v2", "control_mode": "ladrc_acceleration", "policy": "lfs_policy.paper_current.yaml"},
            "no_condition_specific_tuning": True,
        },
        "execution_deviation_contract": {
            "introduced_only_after_planning_commitment": True,
            "excluded_from_planner_input_and_prediction": True,
            "authoritative_timing": "ROS simulation time plus execution-command timestamps",
            "command_delay_tolerance_s": 0.05,
            "reference_activation_and_duration_tolerance_s": 0.05,
            "reference_endpoint_tolerance_m": 0.15,
            "activation_and_reset_acknowledgment_required": True,
            "delivery_failure_class": "INFRASTRUCTURE_FAILURE",
            "production_runtime_semantics_changed": False,
        },
        "qualification_provenance": {
            "family_A_audit_sha256": sha_file(A_AUDIT),
            "family_B_registry_sha256": sha_file(B),
            "family_B_evidence_sha256": sha_file(B_EVIDENCE),
            "family_C_registry_sha256": sha_file(C),
            "family_C_evidence_sha256": sha_file(C_EVIDENCE),
            "F1_attempt_count": 0,
            "formal_attempt_count": 0,
        },
        "scenarios": scenes,
        "failure_accounting": {
            "every_attempt_retained": True,
            "all_attempt_denominator": True,
            "no_replacement_seed": True,
            "setup_or_infrastructure_failure": "retained and separately labeled",
            "no_manual_trial_deletion": True,
            "append_only_journal": True,
        },
        "governance": {
            "scenario_selection_may_not_change_after_any_formal_outcome": True,
            "Full_Method_is_P1_F1": True,
            "production_runtime_modified": False,
            "accepted_formal_results_created": False,
            "formal_execution_requires_separate_human_authorization": True,
        },
    }
    seed_data = yaml_bytes(seed_registry)
    registry_data = yaml_bytes(registry)
    trial_ids = [
        f"{scene['scenario_id']}__{condition}__S{seed}"
        for scene in scenes for condition in CONDITIONS for seed in seeds
    ]
    ordered = sorted(trial_ids, key=lambda trial: hashlib.sha256(
        f"{ORDER_NAMESPACE}|{trial}".encode()
    ).digest())
    order_data = ("\n".join(ordered) + "\n").encode()
    counts = {
        scene["scenario_id"]: {
            condition: sum(
                trial.startswith(f"{scene['scenario_id']}__{condition}__")
                for trial in ordered
            ) for condition in CONDITIONS
        } for scene in scenes
    }
    order_meta = {
        "schema": "E3_v4_formal_trial_order_v1",
        "status": "FROZEN_BEFORE_FORMAL_EXECUTION",
        "campaign": "E3-v4 standalone confirmatory campaign",
        "generation": "ascending lexicographic order of sha256(namespace|trial_id) digest",
        "namespace": ORDER_NAMESPACE,
        "registry_sha256": sha_bytes(registry_data),
        "formal_seed_registry_sha256": sha_bytes(seed_data),
        "order_file": ORDER.name,
        "order_sha256": sha_bytes(order_data),
        "attempt_count": len(ordered),
        "unique_attempt_count": len(set(ordered)),
        "scenario_condition_counts": counts,
        "paired_seed_completeness": all(value == 15 for scene in counts.values() for value in scene.values()),
        "append_only_journal_required": True,
        "failed_attempts_retained": True,
        "replacement_seeds_forbidden": True,
        "significance_triggered_extension_forbidden": True,
        "old_Campaign_v2_cursor_modified": False,
        "formal_execution_started": False,
    }
    return {
        SEEDS: seed_data, REGISTRY: registry_data, ORDER: order_data,
        ORDER_META: yaml_bytes(order_meta),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--write", action="store_true")
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    if args.write == args.check:
        raise SystemExit("choose exactly one of --write/--check")
    artifacts = build()
    if args.write:
        for path, data in artifacts.items():
            path.write_bytes(data)
    else:
        failures = [str(path) for path, data in artifacts.items()
                    if not path.is_file() or path.read_bytes() != data]
        if failures:
            print(json.dumps({"status": "FAIL", "mismatches": failures}))
            return 2
    print(json.dumps({
        "status": "PASS", "artifacts": {
            path.name: sha_bytes(data) for path, data in artifacts.items()
        }
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
