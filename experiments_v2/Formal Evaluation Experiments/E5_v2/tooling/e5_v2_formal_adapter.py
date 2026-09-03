#!/usr/bin/env python3
"""Fail-closed authorization and order gate for future E5-v2 formal trials.

This module deliberately contains no mission-execution backend and creates no
journal or result. A separate formal launch authorization remains required.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Dict, Iterable

from e5_v2_activation_common import (
    ACTIVATION_MANIFEST_PATH,
    CANDIDATE_COMMIT,
    CANDIDATE_REGISTRY_SHA256,
    candidate_scientific_payload_sha256,
    sealed_scientific_payload_sha256,
)
from e5_v2_common import (
    ORDER_PATH,
    POLICY_SHA256,
    REGISTRY_PATH,
    REPO_ROOT,
    SEED_REGISTRY_PATH,
    load_yaml,
    ordered_attempts,
    sha256_file,
)


EXPECTED_SEALED_REGISTRY_SHA256 = (
    "e915575f23b1bd83810f3a8e5aa8092806b9076960c5a2f1fc2bb5faa73ad985"
)
EXPECTED_SEED_REGISTRY_SHA256 = (
    "1815deba3fab9c756603a358b4a3900b67ffb9bcb3e9f757282ab8894595d0cb"
)
EXPECTED_ORDER_SHA256 = (
    "4ec9ee0e8de0cc4b015bfd3858365fe8bf0a07aeddcb591ab6f91221a7bb8f69"
)
EXPECTED_ANALYSIS_CONTRACT_SHA256 = (
    "05802cb32e8dc2f990d9e0144f2cfd118b87228ab0c441578e084aeefc0d008a"
)
EXPECTED_SCIENTIFIC_PAYLOAD_SHA256 = (
    "96ab0893ee099c1003f6a5aad6896decde97c4b9c8d885d38141b8a4dbae81ed"
)
EXPECTED_ACTIVATION_MANIFEST_SHA256 = (
    "8981f91063d22a5f96e20ccf7b1c0fda3c729102d7c4ae998d0f07c861abc6f9"
)


class FormalActivationError(RuntimeError):
    """Raised before any formal side effect when a frozen gate fails."""


def _require_equal(actual: Any, expected: Any, label: str) -> None:
    if actual != expected:
        raise FormalActivationError(
            f"{label} mismatch: expected {expected!r}, got {actual!r}"
        )


def assert_formal_activation(
    registry_path: Path = REGISTRY_PATH,
    activation_record_path: Path | None = ACTIVATION_MANIFEST_PATH,
) -> Dict[str, Any]:
    """Validate the exact sealed registry and activation identities."""
    registry_path = registry_path.resolve()
    registry = load_yaml(registry_path)
    _require_equal(
        registry.get("status"), "SEALED_FOR_FORMAL_EXECUTION", "registry status"
    )
    _require_equal(
        sha256_file(registry_path),
        EXPECTED_SEALED_REGISTRY_SHA256,
        "sealed registry SHA-256",
    )
    if activation_record_path is None or not activation_record_path.is_file():
        raise FormalActivationError("human activation manifest is required")
    _require_equal(
        sha256_file(activation_record_path.resolve()),
        EXPECTED_ACTIVATION_MANIFEST_SHA256,
        "activation manifest SHA-256",
    )
    activation = load_yaml(activation_record_path.resolve())
    _require_equal(
        activation.get("human_decision", {}).get("approved"),
        True,
        "human approval",
    )
    _require_equal(
        activation.get("human_decision", {}).get("decision"),
        "activate_candidate_for_formal_execution",
        "human decision",
    )
    _require_equal(
        activation.get("candidate_commit"), CANDIDATE_COMMIT, "candidate commit"
    )
    _require_equal(
        activation.get("candidate_registry_sha256"),
        CANDIDATE_REGISTRY_SHA256,
        "candidate registry SHA-256",
    )
    _require_equal(
        activation.get("sealed_registry_sha256"),
        EXPECTED_SEALED_REGISTRY_SHA256,
        "manifest sealed registry SHA-256",
    )
    _require_equal(
        activation.get("candidate_scientific_payload_sha256"),
        EXPECTED_SCIENTIFIC_PAYLOAD_SHA256,
        "candidate scientific payload SHA-256",
    )
    _require_equal(
        activation.get("sealed_scientific_payload_sha256"),
        EXPECTED_SCIENTIFIC_PAYLOAD_SHA256,
        "sealed scientific payload SHA-256",
    )
    _require_equal(
        candidate_scientific_payload_sha256(),
        EXPECTED_SCIENTIFIC_PAYLOAD_SHA256,
        "committed candidate scientific payload SHA-256",
    )
    _require_equal(
        sealed_scientific_payload_sha256(),
        EXPECTED_SCIENTIFIC_PAYLOAD_SHA256,
        "current scientific payload SHA-256",
    )
    _require_equal(
        sha256_file(SEED_REGISTRY_PATH),
        EXPECTED_SEED_REGISTRY_SHA256,
        "formal seed registry SHA-256",
    )
    _require_equal(
        sha256_file(ORDER_PATH), EXPECTED_ORDER_SHA256, "formal order SHA-256"
    )
    _require_equal(
        sha256_file(REPO_ROOT / "experiments_v2/Formal Evaluation Experiments/"
                    "E5_v2/E5_v2_analysis_contract.md"),
        EXPECTED_ANALYSIS_CONTRACT_SHA256,
        "analysis contract SHA-256",
    )
    _require_equal(
        sha256_file(REPO_ROOT / "lfs_policy/config/lfs_policy.paper_current.yaml"),
        POLICY_SHA256,
        "production policy SHA-256",
    )
    _require_equal(
        registry.get("accepted_formal_results_created"),
        False,
        "accepted-formal-result state",
    )
    _require_equal(
        registry.get("formal_execution_started"), False, "formal-execution state"
    )
    return registry


def assert_formal_attempt(
    *,
    order_position: int,
    trial_id: str,
    seed: int,
    n: int,
    scenario_id: str,
    substudy: str,
    task_family: str | None,
    completed_attempt_ids: Iterable[str] = (),
    registry_path: Path = REGISTRY_PATH,
    activation_record_path: Path | None = ACTIVATION_MANIFEST_PATH,
) -> Dict[str, Any]:
    """Validate the exact next registered attempt without executing it."""
    assert_formal_activation(registry_path, activation_record_path)
    expected_order = ordered_attempts(load_yaml(registry_path))
    completed = list(completed_attempt_ids)
    if len(completed) != len(set(completed)):
        raise FormalActivationError("completed-attempt prefix contains duplicates")
    exact_prefix = [item["attempt_id"] for item in expected_order[:len(completed)]]
    _require_equal(completed, exact_prefix, "completed-attempt order prefix")
    expected_position = len(completed) + 1
    _require_equal(order_position, expected_position, "next formal order position")
    if order_position < 1 or order_position > len(expected_order):
        raise FormalActivationError("formal order is exhausted or out of range")
    expected = expected_order[order_position - 1]
    if trial_id in completed:
        raise FormalActivationError("replacement/repeated formal attempt refused")
    _require_equal(trial_id, expected["attempt_id"], "trial ID")
    _require_equal(int(seed), int(expected["seed"]), "formal seed")
    _require_equal(int(n), int(expected["N"]), "swarm size N")
    _require_equal(scenario_id, expected["scenario_id"], "scenario ID")
    _require_equal(substudy, expected["substudy"], "substudy")
    _require_equal(task_family, expected.get("task_family"), "task family")
    return dict(expected)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--registry", type=Path, default=REGISTRY_PATH)
    parser.add_argument(
        "--activation-record", type=Path, default=ACTIVATION_MANIFEST_PATH
    )
    modes = parser.add_mutually_exclusive_group(required=True)
    modes.add_argument("--authorization-check", action="store_true")
    modes.add_argument("--attempt-check", action="store_true")
    parser.add_argument("--order-position", type=int)
    parser.add_argument("--trial-id")
    parser.add_argument("--seed", type=int)
    parser.add_argument("--n", type=int)
    parser.add_argument("--scenario-id")
    parser.add_argument("--substudy")
    parser.add_argument("--task-family")
    parser.add_argument("--completed-attempt-id", action="append", default=[])
    args = parser.parse_args()
    try:
        if args.authorization_check:
            assert_formal_activation(args.registry, args.activation_record)
            expected = None
        else:
            required = {
                "order_position": args.order_position,
                "trial_id": args.trial_id,
                "seed": args.seed,
                "n": args.n,
                "scenario_id": args.scenario_id,
                "substudy": args.substudy,
            }
            missing = [key for key, value in required.items() if value is None]
            if missing:
                raise FormalActivationError(
                    f"attempt check missing required fields: {missing}"
                )
            task_family = None if args.task_family in (None, "-") else args.task_family
            expected = assert_formal_attempt(
                order_position=args.order_position,
                trial_id=args.trial_id,
                seed=args.seed,
                n=args.n,
                scenario_id=args.scenario_id,
                substudy=args.substudy,
                task_family=task_family,
                completed_attempt_ids=args.completed_attempt_id,
                registry_path=args.registry,
                activation_record_path=args.activation_record,
            )
    except FormalActivationError as exc:
        print(json.dumps({
            "authorized": False,
            "accepted_formal_result": False,
            "formal_execution_started": False,
            "error": str(exc),
        }, sort_keys=True))
        return 2
    print(json.dumps({
        "authorized": True,
        "accepted_formal_result": False,
        "formal_execution_started": False,
        "validated_attempt": expected,
        "notice": (
            "Static gate passed; no mission backend was invoked and separate "
            "formal launch authorization remains required."
        ),
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
