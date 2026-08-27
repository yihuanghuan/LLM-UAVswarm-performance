#!/usr/bin/env python3
"""Offline completeness, provenance, and protocol-fidelity auditor for E2."""

from __future__ import annotations

import argparse
from copy import deepcopy
import json
from pathlib import Path
from typing import Any, Dict, List, Tuple

from e2_common import (
    COMMITMENT_FIELDS, DATASET_CLASS, INVARIANT_FIELDS, NOT_FORMAL_RESULT,
    REPO_ROOT, WRAPPER_PATH, E2ToolingError, build_registered_snapshots,
    candidate_for_scenario, canonical_sha256, load_scenario_registry,
    numeric_equal, parse_trial_id, registered_trial_ids, scenario_index,
    sha256_file, utc_now, write_json_exclusive,
)
from e2_journal import AttemptJournal
from e2_provenance import PRODUCTION_SOURCE_PATHS, ProvenanceError, validate_provenance


def _load_json(path: Path) -> Dict[str, Any]:
    value = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise E2ToolingError(f"expected JSON object: {path}")
    return value


def _crt_from_executable(payload: Dict[str, Any] | None) -> Dict[str, Any] | None:
    if payload is None:
        return None
    return {"c": payload["c"], "r": payload["r"], "T": payload["T"]}


def audit_run(run_dir: Path, *, verify_current_provenance: bool = True) -> Dict[str, Any]:
    run_dir = Path(run_dir).resolve()
    checks: List[Dict[str, Any]] = []

    def record(name: str, passed: bool, evidence: Any) -> None:
        checks.append({
            "name": name,
            "status": "PASS" if passed else "FAIL",
            "evidence": evidence,
        })

    try:
        provenance = _load_json(run_dir / "provenance_manifest.json")
        score = _load_json(run_dir / "score.json")
        replay = _load_json(run_dir / "replay.json")
        journal = AttemptJournal(run_dir / "raw-journal")
        records = journal.read()
        snapshot = journal.snapshot()
        registry = load_scenario_registry()
        scenarios = scenario_index(registry)
        expected_ids = registered_trial_ids()
        expected_set = set(expected_ids)

        synthetic_labels_ok = all(
            item.get("dataset_class") == DATASET_CLASS
            and item.get("accepted_formal_result") is False
            and item.get("result_notice") == NOT_FORMAL_RESULT
            for item in [provenance, score, replay, *records]
        )
        record("synthetic_validation_labels", synthetic_labels_ok, {
            "record_count": len(records), "accepted_formal_result": False
        })

        trial_ids = [record_["identity"]["trial_id"] for record_ in records]
        population_ok = (
            len(records) == 120
            and len(set(trial_ids)) == 120
            and set(trial_ids) == expected_set
        )
        record("complete_registered_population_no_duplicates", population_ok, {
            "record_count": len(records),
            "unique_count": len(set(trial_ids)),
            "missing": sorted(expected_set - set(trial_ids)),
            "unregistered": sorted(set(trial_ids) - expected_set),
        })

        identity_ok = True
        input_ok = True
        invariant_ok = True
        provenance_ok = True
        resolver_ok = True
        per_trial = {}
        for attempt in records:
            identity = attempt["identity"]
            trial_id = identity["trial_id"]
            parsed = parse_trial_id(trial_id)
            scenario = scenarios.get(parsed["scenario_id"])
            identity_match = (
                scenario is not None
                and all(identity.get(key) == value for key, value in parsed.items())
                and identity.get("family_id") == scenario["family_id"]
            )
            identity_ok = identity_ok and identity_match
            if scenario is None:
                continue
            candidate = candidate_for_scenario(scenario)
            _, _, parse_payload, execute_payload = build_registered_snapshots(
                scenario, identity["state_condition"], registry
            )
            input_record = attempt["input"]
            this_input_ok = (
                input_record["english_command"] == scenario["english_command"]
                and input_record["candidate"] == candidate
                and input_record["candidate_hash"] == canonical_sha256(candidate)
                and input_record["parse_snapshot"] == parse_payload
                and input_record["parse_snapshot_hash"] == canonical_sha256(parse_payload)
                and input_record["execute_snapshot"] == execute_payload
                and input_record["execute_snapshot_hash"] == canonical_sha256(execute_payload)
                and input_record["registered_shift_operator"]
                == scenario["state_shift_operator"]
            )
            input_ok = input_ok and this_input_ok

            trace = attempt["commitment_trace"]
            early = trace["early_candidate"]
            late = trace["late_candidate"]
            changed = sorted(key for key in candidate if early[key] != late[key])
            this_invariant_ok = (
                late == candidate
                and set(changed).issubset(set(COMMITMENT_FIELDS))
                and all(early[field] == late[field] for field in INVARIANT_FIELDS)
                and early["c"].get("mode") == "absolute"
                and early["r"].get("mode") == "explicit"
                and early["T"].get("mode") == "explicit"
                and attempt["invariant_checks"]["all_invariant_fields_equal"] is True
                and attempt["invariant_checks"]["only_c_r_T_may_differ"] is True
                and attempt["invariant_checks"]["input_candidate_not_mutated"] is True
            )
            invariant_ok = invariant_ok and this_invariant_ok

            attempt_provenance = attempt["provenance"]
            artifact_hashes = provenance["artifact_hashes"]
            this_provenance_ok = (
                all(attempt_provenance.get(key) == value for key, value in artifact_hashes.items())
                and attempt_provenance.get("relevant_production_source_hashes")
                == provenance["production_source_hashes"]
                and attempt_provenance.get("canonical_policy_sha256")
                == provenance["canonical_policy_sha256"]
            )
            provenance_ok = provenance_ok and this_provenance_ok
            this_resolver_ok = (
                attempt_provenance.get("production_resolver")
                == "location_allocate.late_resolution.resolve_execution_task"
                and attempt_provenance.get("commitment_wrapper")
                == "harness/e2_commitment_wrapper.py:build_commitment_pair"
            )
            resolver_ok = resolver_ok and this_resolver_ok
            per_trial[trial_id] = {
                "identity": identity_match,
                "sealed_input": this_input_ok,
                "invariants": this_invariant_ok,
                "provenance": this_provenance_ok,
                "resolver_and_wrapper": this_resolver_ok,
            }

        record("trial_identity_matches_sealed_order", identity_ok, per_trial)
        record("candidate_and_snapshots_match_sealed_registry", input_ok, {
            "all_120_inputs_match": input_ok
        })
        record("early_late_invariants_and_only_commitment_fields", invariant_ok, {
            "invariant_fields": list(INVARIANT_FIELDS),
            "allowed_changed_fields": list(COMMITMENT_FIELDS),
        })
        record("attempt_provenance_matches_manifest", provenance_ok, {
            "all_120_attempts_match": provenance_ok
        })
        record("frozen_wrapper_and_production_resolver_recorded", resolver_ok, {
            "wrapper_sha256": sha256_file(WRAPPER_PATH),
            "resolver": "location_allocate.late_resolution.resolve_execution_task",
        })

        source_hashes_now = {
            relative: sha256_file(REPO_ROOT / relative)
            for relative in PRODUCTION_SOURCE_PATHS
        }
        frozen_sources_ok = (
            source_hashes_now == provenance["production_source_hashes"]
            and provenance.get("status") == "PASS"
        )
        record("production_sources_unmodified", frozen_sources_ok, {
            "source_count": len(source_hashes_now),
            "manifest_status": provenance.get("status"),
        })

        score_input_ok = (
            score.get("input_raw_journal") == snapshot
            and score.get("observed_attempt_count") == len(records)
            and score.get("registered_attempt_count") == 120
        )
        record("scorer_input_is_exact_frozen_raw_journal", score_input_ok, {
            "journal_snapshot": snapshot,
            "score_input": score.get("input_raw_journal"),
        })

        flags_ok = all(
            attempt["metric_flags"].get("correction_or_rejection")
            == (
                attempt["metric_flags"].get("correction")
                or attempt["metric_flags"].get("rejection")
            )
            and attempt["replay"]["deterministic_payload"]["metric_flags"]
            == attempt["metric_flags"]
            for attempt in records
        )
        record("metric_flags_and_combined_classification_consistent", flags_ok, {
            "attempt_count": len(records)
        })

        replay_ok = (
            replay.get("status") == "PASS"
            and replay.get("attempt_count") == 120
            and replay.get("exact_agreement_count") == 120
            and replay.get("exact_agreement_rate") == 1.0
            and replay.get("mismatches") == []
        )
        record("deterministic_replay_exact_agreement", replay_ok, replay)

        no_shift_ok = True
        shift_ok = True
        for attempt in records:
            identity = attempt["identity"]
            inp = attempt["input"]
            parse_states = inp["parse_snapshot"]["states"]
            execute_states = inp["execute_snapshot"]["states"]
            if identity["state_condition"] == "NO_SHIFT":
                no_shift_ok = no_shift_ok and all(
                    parse_states[uid]["position_m"] == execute_states[uid]["position_m"]
                    and parse_states[uid]["velocity_mps"] == execute_states[uid]["velocity_mps"]
                    for uid in parse_states
                ) and (
                    inp["parse_snapshot"]["epoch_s"] == 100.0
                    and inp["execute_snapshot"]["epoch_s"] == 102.0
                )
            else:
                scenario = scenarios[identity["scenario_id"]]
                _, _, _, expected_execute = build_registered_snapshots(
                    scenario, "SHIFT", registry
                )
                shift_ok = shift_ok and inp["execute_snapshot"] == expected_execute
        record("NO_SHIFT_exact_registered_control_state", no_shift_ok, {
            "parse_epoch_s": 100.0, "execute_epoch_s": 102.0
        })
        record("SHIFT_exact_registered_state_operator", shift_ok, {
            "all_SHIFT_snapshots_match_registry": shift_ok
        })

        paired: Dict[Tuple[str, int, str], Dict[str, Dict[str, Any]]] = {}
        for attempt in records:
            identity = attempt["identity"]
            key = (identity["scenario_id"], identity["seed"], identity["state_condition"])
            paired.setdefault(key, {})[identity["commitment_condition"]] = attempt
        qs_ok = True
        same_stack_ok = True
        for key, arms in paired.items():
            if len(arms) != 2:
                same_stack_ok = False
                continue
            early = arms["Early_Commitment"]
            late = arms["Information_Aligned_Late_Commitment"]
            same_stack_ok = same_stack_ok and (
                early["input"]["candidate_hash"] == late["input"]["candidate_hash"]
                and early["input"]["parse_snapshot_hash"] == late["input"]["parse_snapshot_hash"]
                and early["input"]["execute_snapshot_hash"] == late["input"]["execute_snapshot_hash"]
                and early["provenance"] == late["provenance"]
            )
            if key[0] == "E2-QS-01":
                qs_ok = qs_ok and (
                    early["replay"]["canonical_executable_payload"]
                    == late["replay"]["canonical_executable_payload"]
                )
        record("same_policy_allocator_geometry_stack_for_paired_arms", same_stack_ok, {
            "pair_count": len(paired)
        })
        record("E2_QS_01_invariance_control_preserved", qs_ok, {
            "pair_count": sum(key[0] == "E2-QS-01" for key in paired)
        })

        feasibility_controls_ok = True
        for attempt in records:
            identity = attempt["identity"]
            if (
                identity["scenario_id"] in {"E2-AT-01", "E2-DF-01"}
                and identity["state_condition"] == "SHIFT"
            ):
                scenario = scenarios[identity["scenario_id"]]
                executable = attempt["replay"]["canonical_executable_payload"]
                if identity["commitment_condition"] == "Early_Commitment":
                    expected_t = scenario[
                        "shifted_early_T_after_mandatory_feasibility_raise"
                    ]
                    feasibility_controls_ok = feasibility_controls_ok and (
                        executable is not None
                        and numeric_equal(executable["T"], expected_t)
                        and attempt["metric_flags"]["correction"] is True
                        and attempt["geometry_allocation_feasibility_trace"][
                            "mandatory_T_raise"
                        ] is True
                    )
                else:
                    expected_t = scenario["shifted_late_resolution"]["T"]
                    feasibility_controls_ok = feasibility_controls_ok and (
                        executable is not None
                        and numeric_equal(executable["T"], expected_t)
                        and attempt["metric_flags"]["correction"] is False
                    )
        all_success_hard_feasible = all(
            (not attempt["metric_flags"]["executable_grounding_success"])
            or attempt["geometry_allocation_feasibility_trace"][
                "frozen_feasibility_result"
            ]["post_resolution_hard_feasible"]
            for attempt in records
        )
        record("AT_DF_mandatory_feasibility_logic_and_no_bypass", (
            feasibility_controls_ok and all_success_hard_feasible
        ), {
            "registered_T_values_preserved": feasibility_controls_ok,
            "successful_attempts_pass_hard_gate": all_success_hard_feasible,
        })

        record("all_attempts_retained", len(records) == 120, {
            "registered": 120, "retained": len(records),
            "failed_attempts": [
                attempt["identity"]["trial_id"] for attempt in records
                if not attempt["metric_flags"]["executable_grounding_success"]
            ],
        })

        if verify_current_provenance:
            try:
                current = validate_provenance()
            except ProvenanceError as exc:
                record("current_fail_closed_provenance", False, exc.report)
            else:
                hashes_match = (
                    current["artifact_hashes"] == provenance["artifact_hashes"]
                    and current["production_source_hashes"]
                    == provenance["production_source_hashes"]
                )
                record("current_fail_closed_provenance", hashes_match, {
                    "status": current["status"], "hashes_match_run_manifest": hashes_match
                })
    except Exception as exc:
        record("auditor_internal_error", False, {
            "type": type(exc).__name__, "message": str(exc)
        })

    passed = all(item["status"] == "PASS" for item in checks)
    return {
        "audit_type": "E2_synthetic_validation_audit_v1",
        "audited_at_utc": utc_now(),
        "run_dir": str(run_dir),
        "dataset_class": DATASET_CLASS,
        "accepted_formal_result": False,
        "result_notice": NOT_FORMAL_RESULT,
        "status": "PASS" if passed else "FAIL",
        "formal_execution_readiness_from_this_audit": passed,
        "scientific_conclusion_from_synthetic_data": "forbidden",
        "checks": checks,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("run_dir", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--skip-current-provenance", action="store_true")
    args = parser.parse_args()
    report = audit_run(
        args.run_dir, verify_current_provenance=not args.skip_current_provenance
    )
    if args.output:
        write_json_exclusive(args.output, report)
    else:
        print(json.dumps(report, ensure_ascii=False, sort_keys=True, indent=2))
    return 0 if report["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
