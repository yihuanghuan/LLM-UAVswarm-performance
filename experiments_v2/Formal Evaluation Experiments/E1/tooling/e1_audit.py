#!/usr/bin/env python3
"""Post-run completeness and integrity auditor for sealed E1 runs."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Dict, List

from e1_common import load_dataset, load_order, utc_now
from e1_journal import EventJournal
from e1_provenance import ProvenanceError, validate_provenance
from e1_run_state import RunState


REQUIRED_PROVENANCE_CHECKS = {
    "immutable_baseline_tag_and_commit",
    "branch_descends_from_runtime_baseline",
    "source_final_preflight_commit",
    "approved_e1_assets_byte_identical",
    "human_approved_final_preflight_gate",
    "canonical_policy_sha256",
    "sealed_dataset",
    "sealed_inference_permutation",
    "frozen_prompt_and_few_shot_hashes",
    "frozen_schema_parser_and_loader_hashes",
    "sealed_client_environment_lock_hashes",
    "frozen_model_decoding_and_retry_configuration",
    "production_runtime_tree_unchanged",
    "e1_branch_change_scope",
}


def audit_run(
    run_dir: Path,
    *,
    verify_current_provenance: bool = True,
    require_no_infrastructure_failures: bool = True,
) -> Dict[str, Any]:
    run_dir = Path(run_dir)
    journal = EventJournal(run_dir / "journal")
    checks: List[Dict[str, Any]] = []

    def record(name: str, passed: bool, evidence: Any) -> None:
        checks.append({
            "name": name,
            "status": "PASS" if passed else "FAIL",
            "evidence": evidence,
        })

    try:
        events = journal.read()
        order = load_order()
        state = RunState.build(events, order)
        record("append_only_hash_chain", True, {
            "event_count": len(events),
            "chain_head_sha256": (
                events[-1]["_event_sha256"] if events else None
            ),
            "sequence_is_contiguous": True,
        })

        dataset = load_dataset()
        valid_count = sum(item["valid"] is True for item in dataset)
        invalid_count = sum(item["valid"] is False for item in dataset)
        record("sealed_dataset_denominators", (
            len(dataset) == 120 and valid_count == 96 and invalid_count == 24
        ), {
            "commands": len(dataset),
            "expected_valid": valid_count,
            "expected_invalid": invalid_count,
        })

        terminal_ids = state.terminal_ids()
        record("exact_terminal_command_set", (
            len(terminal_ids) == 120
            and len(set(terminal_ids)) == 120
            and set(terminal_ids) == {item["id"] for item in dataset}
        ), {
            "terminal_count": len(terminal_ids),
            "unique_terminal_count": len(set(terminal_ids)),
        })
        record("registered_inference_order", terminal_ids == order, {
            "observed": terminal_ids,
            "expected": order,
        })

        attempts_complete = True
        retry_contract = True
        per_command = {}
        for terminal in state.terminals:
            command_id = terminal["command_id"]
            attempts = state.attempts_for(command_id)
            attempts_complete = attempts_complete and all(
                attempt.started is not None
                and attempt.provider_result is not None
                and attempt.completed is not None
                for attempt in attempts
            )
            attempts_complete = attempts_complete and [
                attempt.attempt_index for attempt in attempts
            ] == list(range(1, len(attempts) + 1))
            outcome = terminal["outcome"]
            if outcome == "accepted":
                retry_contract = retry_contract and (
                    1 <= len(attempts) <= 3
                    and attempts[-1].completed.get("schema_valid") is True
                )
            elif outcome == "rejected":
                retry_contract = retry_contract and (
                    len(attempts) == 3
                    and attempts[-1].completed.get("schema_valid") is not True
                    and attempts[-1].provider_result.get("provider_status")
                    == "returned"
                )
            else:
                retry_contract = retry_contract and len(attempts) <= 3
            per_command[command_id] = {
                "attempts": len(attempts),
                "outcome": outcome,
            }
        record("every_attempt_retained", attempts_complete, {
            "attempt_count": len(state.attempts),
            "all_have_start_provider_result_and_completion": attempts_complete,
        })
        record("retry_accounting", retry_contract, per_command)

        infrastructure_ids = [
            terminal["command_id"] for terminal in state.terminals
            if terminal["outcome"] == "infrastructure_failure"
        ]
        record(
            "no_infrastructure_failures",
            not infrastructure_ids or not require_no_infrastructure_failures,
            {"command_ids": infrastructure_ids},
        )

        provenance = state.provenance or {}
        validation_report = provenance.get("validation_report", {})
        recorded_checks = {
            check.get("name"): check.get("status")
            for check in validation_report.get("checks", [])
            if isinstance(check, dict)
        }
        required_checks = set(REQUIRED_PROVENANCE_CHECKS)
        if provenance.get("run_mode") == "real_provider":
            required_checks.update({
                "active_client_environment_lock",
                "real_provider_credential_present",
            })
        provenance_ok = (
            validation_report.get("status") == "PASS"
            and required_checks.issubset(recorded_checks)
            and all(
                recorded_checks[name] == "PASS"
                for name in required_checks
            )
            and provenance.get("accepted_formal_result") is False
            and provenance.get("result_status") in {
                "synthetic_not_formal",
                "pending_post_run_completeness_audit",
            }
        )
        record("complete_recorded_provenance", provenance_ok, {
            "run_mode": provenance.get("run_mode"),
            "dataset_class": provenance.get("dataset_class"),
            "recorded_check_names": sorted(recorded_checks),
            "pre_audit_result_status": provenance.get("result_status"),
        })

        if verify_current_provenance:
            try:
                current = validate_provenance(
                    require_clean=True,
                    verify_environment=True,
                )
            except ProvenanceError as exc:
                record("frozen_artifacts_unchanged_post_run", False, exc.report)
            else:
                record("frozen_artifacts_unchanged_post_run", True, current)
    except Exception as exc:
        record("auditor_internal_error", False, {
            "type": type(exc).__name__,
            "message": str(exc),
        })

    passed = all(check["status"] == "PASS" for check in checks)
    return {
        "audit_type": "E1_post_run_completeness_audit_v1",
        "audited_at_utc": utc_now(),
        "run_dir": str(run_dir.resolve()),
        "status": "PASS" if passed else "FAIL",
        "eligible_for_formal_scoring": passed,
        "accepted_formal_result_created_by_auditor": False,
        "checks": checks,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("run_dir", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    report = audit_run(args.run_dir)
    serialized = json.dumps(report, indent=2, ensure_ascii=False) + "\n"
    if args.output:
        with args.output.open("x", encoding="utf-8") as stream:
            stream.write(serialized)
    else:
        print(serialized, end="")
    return 0 if report["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
