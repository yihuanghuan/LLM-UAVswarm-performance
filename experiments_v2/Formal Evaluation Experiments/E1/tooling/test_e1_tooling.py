"""Mock-only validation for the sealed E1 formal tooling."""

from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

import e1_provenance
import e1_runner
from e1_audit import REQUIRED_PROVENANCE_CHECKS, audit_run
from e1_common import (
    BASELINE_COMMIT,
    BASELINE_TAG,
    SOURCE_PREFLIGHT_COMMIT,
    E1ToolingError,
    load_dataset,
    load_order,
)
from e1_journal import EventJournal
from e1_provenance import ProvenanceError
from e1_run_state import RunState
from e1_runner import E1Runner
from e1_scorer import (
    candidates_equal,
    premature_commitment_counts,
    score_run_state,
    semantic_field_matches,
)


class SimulatedCrash(BaseException):
    pass


def provenance_report():
    return {
        "status": "PASS",
        "source_final_preflight_commit": SOURCE_PREFLIGHT_COMMIT,
        "runtime_baseline_tag": BASELINE_TAG,
        "runtime_baseline_commit": BASELINE_COMMIT,
        "checks": [
            {"name": name, "status": "PASS", "evidence": "synthetic-test"}
            for name in sorted(REQUIRED_PROVENANCE_CHECKS)
        ],
    }


def returned(raw_response, *, prompt=10, completion=5):
    return {
        "raw_response": (
            raw_response if isinstance(raw_response, str)
            else json.dumps(raw_response, separators=(",", ":"))
        ),
        "model": "synthetic-fixture-model",
        "response_id": "synthetic-response-id",
        "finish_reason": "stop",
        "usage": {
            "prompt_tokens": prompt,
            "completion_tokens": completion,
            "total_tokens": prompt + completion,
        },
    }


def provider_timeout():
    return {"exception": {
        "type": "SyntheticProviderTimeout",
        "message": "synthetic retained infrastructure failure",
    }}


def test_runner_enforces_permutation_and_finishes_retries_before_advancing(tmp_path):
    dataset = {record["id"]: record for record in load_dataset()}
    first, second = load_order()[:2]
    fixtures = {
        first: [returned("not-json"), returned(dataset[first]["ground_truth"])],
        second: [returned(dataset[second]["ground_truth"])],
    }
    runner = E1Runner(
        tmp_path / "run",
        mock_mode=True,
        fixture_commands=fixtures,
    )
    state = runner.run(max_new_commands=2, provenance_report=provenance_report())

    assert state.terminal_ids() == [first, second]
    assert len(state.attempts_for(first)) == 2
    assert len(state.attempts_for(second)) == 1
    events = runner.journal.read()
    first_terminal_sequence = next(
        event["sequence"] for event in events
        if event["event_type"] == "command_terminal"
        and event["payload"]["command_id"] == first
    )
    second_start_sequence = next(
        event["sequence"] for event in events
        if event["event_type"] == "attempt_started"
        and event["payload"]["command_id"] == second
    )
    assert first_terminal_sequence < second_start_sequence
    journal_files = sorted((tmp_path / "run" / "journal").glob("[0-9]*.json"))
    before_resume = {path.name: path.read_bytes() for path in journal_files}
    runner.run(max_new_commands=0, provenance_report=provenance_report())
    after_resume = {
        path.name: path.read_bytes()
        for path in (tmp_path / "run" / "journal").glob("[0-9]*.json")
    }
    assert after_resume == before_resume


def test_run_state_rejects_out_of_permutation_attempt(tmp_path):
    order = load_order()
    journal = EventJournal(tmp_path / "journal")
    journal.append("provenance", {
        "run_mode": "mock_synthetic",
        "dataset_class": "synthetic_validation",
    })
    journal.append("attempt_started", {
        "command_id": order[1],
        "attempt_index": 1,
        "request_metadata": {},
    })
    with pytest.raises(E1ToolingError, match="violates inference order"):
        RunState.build(journal.read(), order)


@pytest.mark.parametrize("crash_event_type", [
    "provider_result",
    "attempt_completed",
])
def test_crash_resume_replays_evidence_without_rerunning_completed_attempt(
    tmp_path, monkeypatch, crash_event_type
):
    records = {record["id"]: record for record in load_dataset()}
    command_id = load_order()[0]
    fixtures = {
        command_id: [
            returned("not-json"),
            returned(records[command_id]["ground_truth"]),
        ]
    }
    crashed = {"done": False}

    def crash_after_persisted_evidence(event):
        if (
            not crashed["done"]
            and event["event_type"] == crash_event_type
            and event["payload"]["attempt_index"] == 1
        ):
            crashed["done"] = True
            raise SimulatedCrash()

    provider_calls = []
    original_create = e1_runner._FixtureCompletions.create_for_attempt

    def counted_provider_call(self, attempt_index, **kwargs):
        provider_calls.append(attempt_index)
        return original_create(self, attempt_index, **kwargs)

    monkeypatch.setattr(
        e1_runner._FixtureCompletions,
        "create_for_attempt",
        counted_provider_call,
    )

    run_dir = tmp_path / "run"
    first_journal = EventJournal(run_dir / "journal", crash_after_persisted_evidence)
    first_runner = E1Runner(
        run_dir,
        mock_mode=True,
        fixture_commands=fixtures,
        journal=first_journal,
    )
    with pytest.raises(SimulatedCrash):
        first_runner.run(max_new_commands=1, provenance_report=provenance_report())

    before = {
        path.name: path.read_bytes()
        for path in (run_dir / "journal").glob("[0-9]*.json")
    }
    resumed = E1Runner(run_dir, mock_mode=True, fixture_commands=fixtures)
    state = resumed.run(max_new_commands=1, provenance_report=provenance_report())
    after = {
        path.name: path.read_bytes()
        for path in (run_dir / "journal").glob("[0-9]*.json")
    }

    assert state.terminal_ids() == [command_id]
    assert len(state.attempts_for(command_id)) == 2
    assert provider_calls == [1, 2]
    assert all(after[name] == contents for name, contents in before.items())


def test_ambiguous_attempt_resume_fails_closed_without_provider_call(
    tmp_path, monkeypatch
):
    command_id = load_order()[0]
    run_dir = tmp_path / "ambiguous-run"
    runner = E1Runner(
        run_dir,
        mock_mode=True,
        fixture_commands={command_id: [returned("must-not-be-called")]},
    )
    runner.run(max_new_commands=0, provenance_report=provenance_report())
    runner.journal.append("attempt_started", {
        "command_id": command_id,
        "attempt_index": 1,
        "inference_position": 1,
        "request_timestamp_utc": "2026-08-26T00:00:00.000Z",
        "request_metadata": {},
    })
    before = {
        path.name: path.read_bytes()
        for path in (run_dir / "journal").glob("[0-9]*.json")
    }
    provider_calls = []

    def forbidden_provider_call(*_args, **_kwargs):
        provider_calls.append(True)
        raise AssertionError("provider fixture must not be called")

    monkeypatch.setattr(
        e1_runner._FixtureCompletions,
        "create_for_attempt",
        forbidden_provider_call,
    )
    with pytest.raises(
        E1ToolingError,
        match=(
            "ambiguous formal attempt resume.*attempt_started exists without "
            "provider_result.*no provider request was issued.*human governance"
        ),
    ):
        runner.run(max_new_commands=1, provenance_report=provenance_report())

    after = {
        path.name: path.read_bytes()
        for path in (run_dir / "journal").glob("[0-9]*.json")
    }
    assert provider_calls == []
    assert after == before


def test_journal_detects_deletion_or_replacement_in_its_chain(tmp_path):
    journal = EventJournal(tmp_path / "journal")
    journal.append("provenance", {"value": 1})
    journal.append("command_terminal", {
        "command_id": "E1-0046",
        "inference_position": 1,
        "outcome": "infrastructure_failure",
        "attempts_total": 0,
    })
    first = sorted((tmp_path / "journal").glob("[0-9]*.json"))[0]
    first.write_text(first.read_text(encoding="utf-8").replace('"value":1', '"value":2'))
    with pytest.raises(E1ToolingError, match="hash-chain mismatch"):
        journal.read()


def test_sealed_normalization_ignores_parallel_order_u_order_ids_and_number_spelling():
    record = next(
        item for item in load_dataset()
        if item["valid"] and item["categories"]["mission_structure"] == "parallel"
    )
    truth = record["ground_truth"]
    predicted = copy.deepcopy(truth)
    node = next(node for node in predicted["mission"]["nodes"] if node["type"] == "parallel")
    node["tasks"].reverse()
    for index, task in enumerate(node["tasks"], start=1):
        task["task_id"] = 100 + index
        task["U"].reverse()
        task["s"] = float(task["s"])

    assert candidates_equal(predicted, truth)
    assert all(semantic_field_matches(predicted, truth).values())


def _terminal(command_id, position, outcome, candidate=None):
    return {
        "command_id": command_id,
        "inference_position": position,
        "outcome": outcome,
        "attempts_total": 0,
        "candidate": candidate or {"status": "unavailable"},
        "terminal_retry_outcome": {},
    }


def test_invalid_class_and_premature_commitment_scoring_are_frozen():
    dataset = load_dataset()
    records = {record["id"]: record for record in dataset}
    terminals = []
    order = load_order()
    changed_id = None
    expected_premature = 0
    for position, command_id in enumerate(order, start=1):
        record = records[command_id]
        if record["valid"]:
            candidate = copy.deepcopy(record["ground_truth"])
            if changed_id is None:
                task = candidate["mission"]["nodes"][0]["task"]
                truth_task = record["ground_truth"]["mission"]["nodes"][0]["task"]
                if truth_task["c"]["mode"] in {
                    "relative", "maintain_current_centroid", "auto"
                }:
                    task["c"] = {"mode": "absolute", "value": [0, 0, 0]}
                    expected_premature = 1
                    changed_id = command_id
            terminals.append(_terminal(command_id, position, "accepted", candidate))
        else:
            outcome = "accepted" if command_id == "E1-0097" else "rejected"
            candidate = (
                copy.deepcopy(next(item for item in dataset if item["valid"])["ground_truth"])
                if outcome == "accepted" else None
            )
            terminals.append(_terminal(command_id, position, outcome, candidate))
    assert changed_id is not None
    state = RunState(
        provenance={"dataset_class": "synthetic_validation"},
        terminals=terminals,
    )
    score = score_run_state(dataset, state)

    invalid = score["primary_metrics"]["invalid_rejection_rate"]
    assert invalid["numerator"] == 23
    assert invalid["denominator"] == 24
    assert invalid["per_expected_class"]["incomplete_instruction"] == {
        "rejected": 3, "total": 4, "rate": 0.75
    }
    premature = score["primary_metrics"][
        "premature_numerical_commitment_rate"
    ]
    assert premature["numerator"] == expected_premature == 1
    assert premature["denominator"] > premature["numerator"]


def test_premature_commitment_counts_exclude_qualitative_safety_rule():
    record = next(
        item for item in load_dataset()
        if item["valid"] and item["categories"].get("safety") == "qualitative_safer"
    )
    predicted = copy.deepcopy(record["ground_truth"])
    task = predicted["mission"]["nodes"][0]["task"]
    task["s"] = 2.0
    numerator, denominator = premature_commitment_counts(
        predicted, record["ground_truth"]
    )
    assert numerator == 0
    assert denominator >= 0


def test_provenance_hash_mismatch_fails_closed(monkeypatch):
    original = e1_provenance.sha256_file

    def wrong_dataset_hash(path: Path):
        if path.name == "e1_candidate_semantic_dataset_v1.jsonl":
            return "0" * 64
        return original(path)

    monkeypatch.setattr(e1_provenance, "sha256_file", wrong_dataset_hash)
    with pytest.raises(ProvenanceError) as raised:
        e1_provenance.validate_provenance(
            require_clean=False,
            verify_environment=False,
        )
    statuses = {
        check["name"]: check["status"]
        for check in raised.value.report["checks"]
    }
    assert statuses["sealed_dataset"] == "FAIL"


def test_complete_mock_run_audits_and_scores_without_provider(tmp_path):
    dataset = load_dataset()
    order = load_order()
    valid_infrastructure_id = next(
        command_id for command_id in order
        if next(item for item in dataset if item["id"] == command_id)["valid"]
    )
    invalid_infrastructure_id = "E1-0097"
    infrastructure_ids = {
        valid_infrastructure_id,
        invalid_infrastructure_id,
    }
    fixtures = {}
    for record in dataset:
        if record["id"] in infrastructure_ids:
            fixtures[record["id"]] = [provider_timeout() for _ in range(3)]
        elif record["valid"]:
            fixtures[record["id"]] = [returned(record["ground_truth"])]
        else:
            fixtures[record["id"]] = [
                returned("not-json"),
                returned("not-json"),
                returned("not-json"),
            ]
    run_dir = tmp_path / "complete-mock"
    runner = E1Runner(
        run_dir,
        mock_mode=True,
        fixture_commands=fixtures,
    )
    state = runner.run(provenance_report=provenance_report())

    assert len(state.terminals) == 120
    assert len(state.attempts) == 170
    assert {
        terminal["command_id"] for terminal in state.terminals
        if terminal["outcome"] == "infrastructure_failure"
    } == infrastructure_ids
    audit = audit_run(run_dir, verify_current_provenance=False)
    assert audit["status"] == "PASS"
    infrastructure_check = next(
        check for check in audit["checks"]
        if check["name"]
        == "infrastructure_failures_retained_and_accounted"
    )
    assert infrastructure_check["status"] == "PASS"
    assert infrastructure_check["evidence"]["count"] == 2
    assert infrastructure_check["evidence"][
        "command_denominator_contribution"
    ] == 2
    assert infrastructure_check["evidence"][
        "all_attempt_denominator_contribution"
    ] == 6
    assert set(infrastructure_check["evidence"]["commands"]) == infrastructure_ids
    score = score_run_state(dataset, state)
    primary = score["primary_metrics"]
    assert score["all_attempt_count"] == 170
    assert primary["schema_valid_rate"] == {
        "numerator": 95, "denominator": 96, "rate": 95 / 96
    }
    assert primary["semantic_field_accuracy"]["rate"] < 1.0
    assert primary["exact_semantic_task_accuracy"] == {
        "numerator": 95, "denominator": 96, "rate": 95 / 96
    }
    assert primary["invalid_rejection_rate"]["numerator"] == 23
    assert primary["invalid_rejection_rate"]["denominator"] == 24
    assert primary["invalid_rejection_rate"]["rate"] == 23 / 24
    assert primary["premature_numerical_commitment_rate"]["numerator"] == 0
