from __future__ import annotations

from pathlib import Path

import pytest

from e3_formal_adapter import (
    FormalAdapterError, adapter_identity, run_exact_trial,
)
from e3_trial_registry import (
    ORDER_SHA256, POLICY_SHA256, PROTOCOL_SHA256, REGISTRY_SHA256,
    build_exact_spec, registered_trial_ids,
)


def context(trial_id, root, **changes):
    identity = adapter_identity()
    order = Path(__file__).resolve().parents[2] / "simulation_trial_order_v1.txt"
    value = {
        "execution_mode": "spec_rehearsal",
        "dataset_class": "synthetic_validation",
        "formal_launch_authorized": False,
        "trial_id": trial_id,
        "global_trial_position": order.read_text().splitlines().index(trial_id) + 1,
        "runner_commit": identity["commit"],
        "runner_source_sha256": identity["source_sha256"],
        "policy_sha256": POLICY_SHA256,
        "protocol_sha256": PROTOCOL_SHA256,
        "registry_sha256": REGISTRY_SHA256,
        "global_trial_order_sha256": ORDER_SHA256,
        "attempt_output_dir": str(root),
    }
    value.update(changes)
    return value


def test_complete_spec_reconstruction_is_deterministic_and_global_registered():
    ids = registered_trial_ids()
    assert len(ids) == len(set(ids)) == 360
    assert [build_exact_spec(value) for value in ids] == [build_exact_spec(value) for value in ids]


def test_spec_rehearsal_retains_nonformal_artifact_without_suite_journal(tmp_path):
    trial = registered_trial_ids()[0]
    descriptor = run_exact_trial(trial, context(trial, tmp_path / "attempt"))
    assert descriptor["accepted_formal_result"] is False
    assert descriptor["dataset_class"] == "synthetic_validation"
    assert descriptor["suite_journal_mutated"] is False
    artifact = Path(descriptor["artifact_path"]).read_text()
    assert '"result_notice":"NOT_FORMAL_RESULT"' in artifact
    assert not list(tmp_path.rglob("*journal*"))


def test_duplicate_attempt_is_refused(tmp_path):
    trial = registered_trial_ids()[0]; ctx = context(trial, tmp_path / "attempt")
    run_exact_trial(trial, ctx)
    with pytest.raises(FormalAdapterError, match="duplicate"):
        run_exact_trial(trial, ctx)


@pytest.mark.parametrize("trial", ["garbage", "E2-CENTER-01__NO_SHIFT__EARLY__S21001"])
def test_unknown_and_wrong_family_refused(trial, tmp_path):
    good = registered_trial_ids()[0]
    with pytest.raises(Exception):
        run_exact_trial(trial, context(good, tmp_path / "attempt", trial_id=trial))


@pytest.mark.parametrize("field,value", [
    ("global_trial_position", 611), ("runner_commit", "0" * 40),
    ("runner_source_sha256", "0" * 64), ("policy_sha256", "0" * 64),
    ("protocol_sha256", "0" * 64), ("registry_sha256", "0" * 64),
    ("global_trial_order_sha256", "0" * 64),
])
def test_provenance_or_position_mismatch_refused(field, value, tmp_path):
    trial = registered_trial_ids()[0]
    with pytest.raises(FormalAdapterError):
        run_exact_trial(trial, context(trial, tmp_path / "attempt", **{field: value}))


def test_formal_mode_is_fail_closed_without_final_gate(tmp_path):
    trial = registered_trial_ids()[0]
    with pytest.raises(FormalAdapterError, match="authorization"):
        run_exact_trial(trial, context(
            trial, tmp_path / "attempt", execution_mode="formal",
            dataset_class="formal_evaluation", formal_launch_authorized=False,
            launch_gate_status="READY_FOR_FORMAL_LAUNCH"))
    assert not (tmp_path / "attempt").exists()


def test_failure_injection_is_non_scientific_but_retained(tmp_path):
    trial = registered_trial_ids()[0]
    descriptor = run_exact_trial(trial, context(
        trial, tmp_path / "attempt", failure_injection="infrastructure_failure"))
    assert descriptor["attempt_status"] == "infrastructure_failure"
    assert descriptor["accepted_formal_result"] is False


def test_wrench_compatibility_shim_inherits_all_sealed_behavior():
    from e3_wrench_compat import HumbleCompatibleE3WrenchDriver, E3WrenchDriver
    assert HumbleCompatibleE3WrenchDriver._on_clock is E3WrenchDriver._on_clock
    assert HumbleCompatibleE3WrenchDriver._on_arm is E3WrenchDriver._on_arm
    assert HumbleCompatibleE3WrenchDriver._publish is E3WrenchDriver._publish
    assert set(HumbleCompatibleE3WrenchDriver.__dict__) - {
        "__module__", "__doc__", "publishers", "create_subscription"
    } == set()
