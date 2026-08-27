"""Static and synthetic tests for experiment-only E2 tooling."""

from __future__ import annotations

from copy import deepcopy
import json
import os

import pytest

from e2_audit import audit_run
from e2_common import (
    CANONICAL_POLICY_SHA256, COMMITMENT_FIELDS, INVARIANT_FIELDS, POLICY_PATH,
    build_registered_snapshots, candidate_for_scenario, canonical_sha256,
    ensure_runtime_import_paths, global_order_positions, load_scenario_registry,
    registered_trial_ids, scenario_index,
)
from e2_journal import AttemptJournal
from e2_provenance import ProvenanceError, validate_provenance
from e2_runner import build_attempt_record
from e2_scorer import score_records


ensure_runtime_import_paths()
from e2_commitment_wrapper import build_commitment_pair  # noqa: E402
from location_allocate.policy_adapter import load_runtime_policy  # noqa: E402


@pytest.fixture(scope="module")
def registry():
    return load_scenario_registry()


@pytest.fixture(scope="module")
def policy():
    return load_runtime_policy(POLICY_PATH)[1]


def test_wrapper_preserves_input_late_and_invariants(registry, policy):
    scenario = scenario_index(registry)["E2-PES-01"]
    candidate = candidate_for_scenario(scenario)
    before = deepcopy(candidate)
    parse_snapshot, _, _, _ = build_registered_snapshots(
        scenario, "SHIFT", registry
    )
    pair = build_commitment_pair(candidate, parse_snapshot, policy)
    assert candidate == before
    assert pair.late_candidate == before
    assert set(
        key for key in before if pair.early_candidate[key] != pair.late_candidate[key]
    ).issubset(COMMITMENT_FIELDS)
    for field in INVARIANT_FIELDS:
        assert pair.early_candidate[field] == pair.late_candidate[field]
    assert pair.early_candidate["c"]["mode"] == "absolute"
    assert pair.early_candidate["r"]["mode"] == "explicit"
    assert pair.early_candidate["T"]["mode"] == "explicit"


def test_provenance_fails_closed_on_corrupt_expected_hash():
    with pytest.raises(ProvenanceError) as captured:
        validate_provenance(expected_policy_sha256="0" * 64)
    failed = {
        item["name"] for item in captured.value.report["checks"]
        if item["status"] == "FAIL"
    }
    assert "frozen_configuration_and_policy_hash" in failed
    assert CANONICAL_POLICY_SHA256 != "0" * 64


def test_trial_enumeration_exact_complete_population(registry):
    trial_ids = registered_trial_ids(registry=registry)
    assert len(trial_ids) == 120
    assert len(set(trial_ids)) == 120
    assert {trial.split("__", 1)[0] for trial in trial_ids} == set(
        scenario_index(registry)
    )
    assert {int(trial.rsplit("S", 1)[1]) for trial in trial_ids} == set(
        registry["seeds"]
    )
    assert {trial.split("__")[1] for trial in trial_ids} == {"SHIFT", "NO_SHIFT"}
    assert {trial.split("__")[2] for trial in trial_ids} == {"EARLY", "LATE"}


def test_snapshot_construction_matches_registry(registry):
    scenario = scenario_index(registry)["E2-DF-01"]
    _, _, parse_payload, no_shift_payload = build_registered_snapshots(
        scenario, "NO_SHIFT", registry
    )
    _, _, _, shift_payload = build_registered_snapshots(scenario, "SHIFT", registry)
    assert parse_payload["epoch_s"] == registry["common"]["parse_epoch_s"]
    assert no_shift_payload["epoch_s"] == registry["common"]["execute_epoch_s"]
    for uid, position in registry["common"]["parse_positions_m"].items():
        assert parse_payload["states"][str(uid)]["position_m"] == position
        assert no_shift_payload["states"][str(uid)]["position_m"] == position
    for uid, position in scenario["shifted_execute_positions_m"].items():
        assert shift_payload["states"][str(uid)]["position_m"] == position
    assert shift_payload["frame"] == "world ENU"
    assert canonical_sha256(shift_payload) == canonical_sha256(shift_payload)


def _synthetic_score_record(trial_id, condition, state, **flags):
    complete = {
        "executable_grounding_success": False,
        "state_consistency_violation": False,
        "dynamic_infeasibility": False,
        "correction": False,
        "rejection": False,
    }
    complete.update(flags)
    complete["correction_or_rejection"] = (
        complete["correction"] or complete["rejection"]
    )
    return {
        "identity": {
            "trial_id": trial_id,
            "commitment_condition": condition,
            "state_condition": state,
        },
        "metric_flags": complete,
    }


def test_scorer_known_synthetic_success_failure_cases():
    records = [
        _synthetic_score_record(
            "a", "Early_Commitment", "SHIFT",
            executable_grounding_success=True,
            state_consistency_violation=True,
            dynamic_infeasibility=True,
            correction=True,
        ),
        _synthetic_score_record(
            "b", "Early_Commitment", "SHIFT", rejection=True
        ),
        _synthetic_score_record(
            "c", "Information_Aligned_Late_Commitment", "SHIFT",
            executable_grounding_success=True,
        ),
        _synthetic_score_record(
            "d", "Information_Aligned_Late_Commitment", "NO_SHIFT",
            executable_grounding_success=True,
        ),
    ]
    score = score_records(records, require_complete=False)
    assert score["overall"]["attempt_denominator"] == 4
    assert score["overall"]["rates"]["executable_grounding_success"] == 0.75
    assert score["overall"]["rates"]["state_consistency_violation_rate"] == 0.25
    assert score["overall"]["rates"]["dynamic_infeasibility_rate"] == 0.25
    assert score["overall"]["rates"]["correction_or_rejection_rate"] == 0.5
    assert score["overall"]["rates"]["correction_rate"] == 0.25
    assert score["overall"]["rates"]["rejection_rate"] == 0.25


def test_runner_preserves_mandatory_T_raise_and_normal_late_resolution(registry, policy):
    provenance = validate_provenance()
    positions = global_order_positions()
    early_id = "E2-AT-01__SHIFT__EARLY__S52101"
    late_id = "E2-AT-01__SHIFT__LATE__S52101"
    early = build_attempt_record(early_id, registry, policy, provenance, positions[early_id], 1)
    late = build_attempt_record(late_id, registry, policy, provenance, positions[late_id], 2)
    expected = scenario_index(registry)["E2-AT-01"]
    assert early["metric_flags"]["correction"] is True
    assert early["geometry_allocation_feasibility_trace"]["mandatory_T_raise"] is True
    assert early["replay"]["canonical_executable_payload"]["T"] == pytest.approx(
        expected["shifted_early_T_after_mandatory_feasibility_raise"], abs=1e-12
    )
    assert late["metric_flags"]["correction"] is False
    assert late["replay"]["canonical_executable_payload"]["T"] == pytest.approx(
        expected["shifted_late_resolution"]["T"], abs=1e-12
    )


def test_auditor_rejects_incomplete_and_malformed_records(tmp_path):
    run_dir = tmp_path / "bad-run"
    run_dir.mkdir()
    for name in ("provenance_manifest.json", "score.json", "replay.json"):
        (run_dir / name).write_text("{}\n", encoding="utf-8")
    journal = AttemptJournal(run_dir / "raw-journal")
    journal.append({"record_type": "incomplete"})
    report = audit_run(run_dir, verify_current_provenance=False)
    assert report["status"] == "FAIL"

    record_path = run_dir / "raw-journal" / "000001-attempt.json"
    os.chmod(record_path, 0o644)
    malformed = json.loads(record_path.read_text(encoding="utf-8"))
    malformed["record_type"] = "tampered"
    record_path.write_text(json.dumps(malformed), encoding="utf-8")
    report = audit_run(run_dir, verify_current_provenance=False)
    assert report["status"] == "FAIL"
