from __future__ import annotations

from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))

from e3_v4_formal_adapter import AdapterError, adapter_identity, validate_context
from e3_v4_trial_registry import (
    ORDER_SHA256, POLICY_SHA256, REGISTRY_SHA256, SEEDS_SHA256,
    build_exact_runtime_spec, registered_trial_ids,
)


def test_exact_360_order_and_complete_blocks():
    values = registered_trial_ids()
    assert len(values) == len(set(values)) == 360
    for scene in ("E3-A-01", "E3-A-02", "E3-B-01", "E3-B-02", "E3-C-01", "E3-C-02"):
        for condition in ("P0_F0", "P0_F1", "P1_F0", "P1_F1"):
            assert sum(value.startswith(f"{scene}__{condition}__") for value in values) == 15


@pytest.mark.parametrize(
    "prefix,mechanism,predicted_hard",
    [
        ("E3-A-01__P0_F0", "none", 2),
        ("E3-A-02__P1_F1", "none", 0),
        ("E3-B-01__P0_F1", "command_delay", 0),
        ("E3-B-02__P1_F0", "reference_deviation", 0),
        ("E3-C-01__P0_F0", "command_delay", 2),
        ("E3-C-02__P1_F1", "reference_deviation", 0),
    ],
)
def test_registered_runtime_semantics(prefix, mechanism, predicted_hard):
    trial = next(value for value in registered_trial_ids() if value.startswith(prefix))
    runtime = build_exact_runtime_spec(trial)
    assert runtime["manipulation"]["type"] == mechanism
    assert runtime["allocator_diagnostics"]["hard_violations"] == predicted_hard


def test_candidate_registry_refuses_formal_launch():
    trial = registered_trial_ids()[0]
    identity = adapter_identity()
    context = {
        "trial_id": trial,
        "campaign_position": 1,
        "execution_mode": "formal",
        "dataset_class": "formal_evaluation",
        "formal_launch_authorized": True,
        "runner_commit": identity["commit"],
        "runner_source_sha256": identity["source_sha256"],
        "runner_tooling_bundle_sha256": identity["execution_tooling"]["bundle_sha256"],
        "registry_sha256": REGISTRY_SHA256,
        "formal_seed_registry_sha256": SEEDS_SHA256,
        "order_sha256": ORDER_SHA256,
        "policy_sha256": POLICY_SHA256,
        "attempt_output_dir": "/not-used",
    }
    with pytest.raises(AdapterError, match="pending human registry activation"):
        validate_context(trial, context)
