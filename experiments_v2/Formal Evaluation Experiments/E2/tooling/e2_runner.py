#!/usr/bin/env python3
"""Run the complete registered E2 population as synthetic offline validation."""

from __future__ import annotations

import argparse
from copy import deepcopy
from dataclasses import asdict
import hashlib
import math
from pathlib import Path
import re
from typing import Any, Dict, List, Optional, Tuple

from e2_common import (
    BASELINE_COMMIT, BASELINE_TAG, CANONICAL_POLICY_SHA256, COMMITMENT_FIELDS,
    CONFIGURATION_ID, DATASET_CLASS, GLOBAL_REGISTRY_PATH, INVARIANT_FIELDS,
    NOT_FORMAL_RESULT, ORDER_TXT_PATH, PROTOCOL_PATH, REGISTRY_PATH, REPO_ROOT,
    SYNTHETIC_RESULTS_DIR, WRAPPER_PATH, E2ToolingError,
    build_registered_snapshots, candidate_for_scenario, canonical_sha256,
    crt_payload, ensure_runtime_import_paths, file_hash_manifest_payload,
    global_order_positions, json_safe, load_scenario_registry, load_yaml,
    numeric_equal, parse_trial_id, registered_trial_ids, scenario_index,
    sha256_file, utc_now, write_json_exclusive,
)
from e2_journal import AttemptJournal
from e2_provenance import validate_provenance
from e2_scorer import score_records


ensure_runtime_import_paths()
from e2_commitment_wrapper import build_commitment_pair  # noqa: E402
from location_allocate.late_resolution import (  # noqa: E402
    LateResolutionError, resolve_execution_task,
)
from location_allocate.policy_adapter import load_runtime_policy  # noqa: E402


class ProtocolInconsistencyError(E2ToolingError):
    """A sealed registry value disagrees with the frozen production resolver."""


def _exception_payload(exc: BaseException) -> Dict[str, Any]:
    return {
        "type": type(exc).__name__,
        "module": type(exc).__module__,
        "message": str(exc),
        "code": getattr(exc, "code", None),
        "diagnostics": json_safe(getattr(exc, "diagnostics", {})),
    }


def _executable_payload(task_id: int, resolved: Any) -> Dict[str, Any]:
    return {"task_id": int(task_id), **resolved.executable_lfs.as_dict()}


def _canonical_target_order(resolved: Any) -> List[List[float]]:
    assigned = [list(map(float, target)) for target in resolved.assigned_targets]
    assignment = list(resolved.trace.final_assignment)
    if sorted(assignment) != list(range(len(assigned))):
        raise E2ToolingError("frozen resolver returned invalid final assignment trace")
    targets: List[Optional[List[float]]] = [None] * len(assigned)
    for uav_index, target_index in enumerate(assignment):
        targets[target_index] = assigned[uav_index]
    if any(target is None for target in targets):
        raise E2ToolingError("could not reconstruct generated target order")
    return [target for target in targets if target is not None]


def _resolution_payload(resolved: Any, execute_snapshot: Any) -> Dict[str, Any]:
    executable = resolved.executable_lfs
    assigned = [list(map(float, target)) for target in resolved.assigned_targets]
    displacements = [
        {
            "uav_id": int(uid),
            "displacement_m": float(math.dist(
                execute_snapshot.states[int(uid)].position, target
            )),
        }
        for uid, target in zip(executable.uav_ids, resolved.assigned_targets)
    ]
    return {
        "executable": _executable_payload(resolved.trace.task_id, resolved),
        "trace": json_safe(resolved.trace),
        "generated_geometry_canonical_target_order_m": _canonical_target_order(resolved),
        "assigned_targets_m": assigned,
        "per_uav_execution_snapshot_displacement": displacements,
        "planning_metrics": asdict(resolved.planning_metrics),
        "final_metrics": asdict(resolved.final_metrics),
        "execution_profiles": [asdict(profile) for profile in resolved.profiles],
    }


def _committed_value(spec: Dict[str, Any], field: str) -> Any:
    required_mode = "absolute" if field == "c" else "explicit"
    if spec.get("mode") != required_mode:
        return None
    return deepcopy(spec.get("value"))


def _correction_classification(
    selected_candidate: Dict[str, Any], resolved: Any,
) -> Dict[str, Any]:
    executable = crt_payload(resolved.executable_lfs)
    corrected_fields = []
    for field in COMMITMENT_FIELDS:
        requested = _committed_value(selected_candidate[field], field)
        if requested is not None and not numeric_equal(requested, executable[field]):
            corrected_fields.append(field)
    corrections = list(resolved.trace.corrections)
    return {
        "correction": bool(corrected_fields),
        "corrected_committed_fields": corrected_fields,
        "correction_reason": "; ".join(corrections) if corrected_fields else None,
        "production_trace_corrections": corrections,
        "mandatory_T_raise": "T" in corrected_fields,
        "normal_late_resolution_counted_as_correction": False,
    }


def _rejection_is_dynamic(exception: Dict[str, Any]) -> bool:
    text = " ".join(
        str(exception.get(key) or "") for key in ("code", "message", "diagnostics")
    ).lower()
    return any(token in text for token in (
        "dynamic", "timing", "duration", "trajectory", "d_hard", "geometry",
        "workspace", "feasib", "safety",
    ))


def _assert_registered_resolutions(
    scenario: Dict[str, Any], state_condition: str,
    interpretation_crt: Dict[str, Any], late_crt: Dict[str, Any],
) -> None:
    if not numeric_equal(interpretation_crt, scenario["parse_commitment"]):
        raise ProtocolInconsistencyError(
            f"{scenario['scenario_id']} frozen parse commitment disagrees with "
            "the frozen production resolver"
        )
    expected_late = (
        scenario["parse_commitment"] if state_condition == "NO_SHIFT"
        else scenario["shifted_late_resolution"]
    )
    if not numeric_equal(late_crt, expected_late):
        raise ProtocolInconsistencyError(
            f"{scenario['scenario_id']} {state_condition} frozen Late resolution "
            "disagrees with the frozen production resolver"
        )


def _record_provenance(manifest: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "baseline_tag": BASELINE_TAG,
        "baseline_commit": BASELINE_COMMIT,
        "configuration_id": CONFIGURATION_ID,
        "canonical_policy_sha256": CANONICAL_POLICY_SHA256,
        **manifest["artifact_hashes"],
        "relevant_production_source_hashes": manifest["production_source_hashes"],
        "production_resolver": "location_allocate.late_resolution.resolve_execution_task",
        "commitment_wrapper": "harness/e2_commitment_wrapper.py:build_commitment_pair",
    }


def build_attempt_record(
    trial_id: str, registry: Dict[str, Any], policy: Any,
    provenance_manifest: Dict[str, Any], global_position: int,
    validation_position: int,
) -> Dict[str, Any]:
    identity = parse_trial_id(trial_id)
    scenario = scenario_index(registry)[identity["scenario_id"]]
    identity["family_id"] = str(scenario["family_id"])
    candidate = candidate_for_scenario(scenario)
    candidate_before = deepcopy(candidate)
    parse_snapshot, execute_snapshot, parse_payload, execute_payload = (
        build_registered_snapshots(scenario, identity["state_condition"], registry)
    )
    candidate_hash = canonical_sha256(candidate)
    parse_hash = canonical_sha256(parse_payload)
    execute_hash = canonical_sha256(execute_payload)

    pair = None
    interpretation = None
    selected = None
    late_reference = None
    selected_exception = None
    try:
        pair = build_commitment_pair(candidate, parse_snapshot, policy)
        if candidate != candidate_before:
            raise E2ToolingError("sealed wrapper mutated its input Candidate")
        interpretation = pair.interpretation_resolution
        selected_candidate = (
            pair.early_candidate
            if identity["commitment_condition"] == "Early_Commitment"
            else pair.late_candidate
        )
        selected = resolve_execution_task(
            deepcopy(selected_candidate), execute_snapshot, policy
        )
        late_reference = (
            selected if identity["commitment_condition"]
            == "Information_Aligned_Late_Commitment"
            else resolve_execution_task(
                deepcopy(pair.late_candidate), execute_snapshot, policy
            )
        )
        _assert_registered_resolutions(
            scenario, identity["state_condition"],
            crt_payload(interpretation.executable_lfs),
            crt_payload(late_reference.executable_lfs),
        )
    except ProtocolInconsistencyError:
        raise
    except Exception as exc:
        selected_exception = _exception_payload(exc)

    early_candidate = deepcopy(pair.early_candidate) if pair is not None else None
    late_candidate = deepcopy(pair.late_candidate) if pair is not None else deepcopy(candidate)
    selected_candidate = (
        early_candidate if identity["commitment_condition"] == "Early_Commitment"
        else late_candidate
    )
    invariant_checks = {
        f"{field}_equality": (
            pair is not None and pair.early_candidate[field] == pair.late_candidate[field]
        )
        for field in INVARIANT_FIELDS
    }
    invariant_checks["all_invariant_fields_equal"] = all(invariant_checks.values())
    changed_fields = sorted(
        key for key in candidate
        if pair is not None and pair.early_candidate.get(key) != pair.late_candidate.get(key)
    )
    invariant_checks["only_c_r_T_may_differ"] = set(changed_fields).issubset(
        set(COMMITMENT_FIELDS)
    )
    invariant_checks["input_candidate_not_mutated"] = candidate == candidate_before

    if selected is not None and late_reference is not None and interpretation is not None:
        selected_crt = crt_payload(selected.executable_lfs)
        late_crt = crt_payload(late_reference.executable_lfs)
        parse_crt = crt_payload(interpretation.executable_lfs)
        correction = _correction_classification(selected_candidate, selected)
        executable = _executable_payload(candidate["task_id"], selected)
        executable_hash = canonical_sha256(executable)
        resolution = _resolution_payload(selected, execute_snapshot)
        rejection = False
        rejection_reason = None
        state_violation = not numeric_equal(selected_crt, late_crt)
        dynamic_infeasibility = bool(correction["correction"])
        grounding_success = True
        hard_feasible = (
            resolved_hard_feasible
            if (resolved_hard_feasible := selected.trace.final_assignment_metrics.get(
                "hard_feasible"
            )) is not None else selected.final_metrics.hard_violations == 0
        )
    else:
        selected_crt = None
        late_crt = (
            crt_payload(late_reference.executable_lfs)
            if late_reference is not None else None
        )
        parse_crt = (
            crt_payload(interpretation.executable_lfs)
            if interpretation is not None else None
        )
        correction = {
            "correction": False,
            "corrected_committed_fields": [],
            "correction_reason": None,
            "production_trace_corrections": [],
            "mandatory_T_raise": False,
            "normal_late_resolution_counted_as_correction": False,
        }
        executable = None
        executable_hash = None
        resolution = None
        rejection = True
        rejection_reason = selected_exception
        state_violation = False
        dynamic_infeasibility = _rejection_is_dynamic(selected_exception or {})
        grounding_success = False
        hard_feasible = False

    flags = {
        "executable_grounding_success": grounding_success,
        "state_consistency_violation": state_violation,
        "dynamic_infeasibility": dynamic_infeasibility,
        "correction": bool(correction["correction"]),
        "rejection": rejection,
        "correction_or_rejection": bool(correction["correction"] or rejection),
    }
    replay_payload = {
        "candidate_hash": candidate_hash,
        "parse_snapshot_hash": parse_hash,
        "execute_snapshot_hash": execute_hash,
        "early_committed_c_r_T": (
            {field: deepcopy(early_candidate[field]) for field in COMMITMENT_FIELDS}
            if early_candidate is not None else None
        ),
        "late_execution_resolved_c_r_T": late_crt,
        "executable_payload_hash": executable_hash,
        "metric_flags": flags,
        "correction_classification": correction,
        "rejection_classification": rejection_reason,
    }
    return {
        "record_type": "E2_attempt_v1",
        "dataset_class": DATASET_CLASS,
        "accepted_formal_result": False,
        "result_notice": NOT_FORMAL_RESULT,
        "identity": identity,
        "order_trace": {
            "global_sealed_order_position": int(global_position),
            "E2_filtered_validation_position": int(validation_position),
            "filtering_is_formal_execution_order": False,
        },
        "seed_trace": {
            "registered_seed": identity["seed"],
            "rng_consumers": [],
            "status": "seed_not_supported_no_rng_consumed_by_offline_resolver",
        },
        "provenance": _record_provenance(provenance_manifest),
        "input": {
            "english_command": scenario["english_command"],
            "candidate": candidate,
            "candidate_hash": candidate_hash,
            "parse_snapshot": parse_payload,
            "parse_snapshot_hash": parse_hash,
            "execute_snapshot": execute_payload,
            "execute_snapshot_hash": execute_hash,
            "registered_shift_operator": scenario["state_shift_operator"],
        },
        "commitment_trace": {
            "candidate_c_r_T": {field: deepcopy(candidate[field]) for field in COMMITMENT_FIELDS},
            "parse_time_interpretation_resolution_c_r_T": parse_crt,
            "parse_time_interpretation_trace": (
                json_safe(interpretation.trace) if interpretation is not None else None
            ),
            "parse_time_committed_c_r_T_for_Early": (
                {field: deepcopy(early_candidate[field]) for field in COMMITMENT_FIELDS}
                if early_candidate is not None else None
            ),
            "execution_time_resolved_c_r_T": selected_crt,
            "late_execution_resolved_c_r_T": late_crt,
            "late_reference_role": "state-consistency diagnostic; not an additional registered attempt",
            "early_candidate": early_candidate,
            "late_candidate": late_candidate,
            "selected_candidate": selected_candidate,
            "executable_output": executable,
        },
        "invariant_checks": {
            **invariant_checks,
            "early_late_changed_fields": changed_fields,
        },
        "geometry_allocation_feasibility_trace": {
            "resolution": resolution,
            "frozen_feasibility_result": {
                "post_resolution_hard_feasible": bool(hard_feasible),
                "already_committed_request_feasible_without_change": not dynamic_infeasibility,
            },
            "mandatory_T_raise": bool(correction["mandatory_T_raise"]),
            "correction_flag": bool(correction["correction"]),
            "correction_reason": correction["correction_reason"],
            "rejection_flag": rejection,
            "rejection_reason": rejection_reason,
        },
        "metric_flags": flags,
        "replay": {
            "canonical_executable_payload": executable,
            "executable_payload_hash": executable_hash,
            "deterministic_payload": replay_payload,
            "deterministic_payload_hash": canonical_sha256(replay_payload),
        },
    }


def _run_id_default() -> str:
    stamp = utc_now().replace("-", "").replace(":", "").replace(".", "")
    return f"E2-synthetic-v1-{stamp}"


def run_synthetic_validation(run_id: str, output_root: Path) -> Path:
    if not re.fullmatch(r"[A-Za-z0-9._-]+", run_id):
        raise E2ToolingError("run ID contains unsafe characters")
    output_root = Path(output_root).resolve()
    expected_root = SYNTHETIC_RESULTS_DIR.resolve()
    if output_root != expected_root:
        raise E2ToolingError(
            f"synthetic output root must be {expected_root}; got {output_root}"
        )
    run_dir = output_root / run_id
    run_dir.mkdir(parents=True, exist_ok=False)

    provenance = validate_provenance()
    provenance["run_id"] = run_id
    provenance["formal_execution_enabled"] = False
    provenance["global_formal_trial_cursor_consumed"] = False
    write_json_exclusive(run_dir / "provenance_manifest.json", provenance)

    registry = load_scenario_registry()
    trial_ids = registered_trial_ids()
    positions = global_order_positions()
    config, policy = load_runtime_policy(
        REPO_ROOT / "lfs_policy" / "config" / "lfs_policy.paper_current.yaml"
    )
    if config.configuration_id != CONFIGURATION_ID or config.policy_hash != CANONICAL_POLICY_SHA256:
        raise E2ToolingError("loaded runtime policy identity disagrees with frozen provenance")

    journal = AttemptJournal(run_dir / "raw-journal")
    first_payloads: Dict[str, Dict[str, Any]] = {}
    for validation_position, trial_id in enumerate(trial_ids, start=1):
        payload = build_attempt_record(
            trial_id, registry, policy, provenance, positions[trial_id], validation_position
        )
        journal.append(payload)
        first_payloads[trial_id] = payload["replay"]["deterministic_payload"]

    records = journal.read()
    replay_mismatches = []
    for validation_position, trial_id in enumerate(trial_ids, start=1):
        replayed = build_attempt_record(
            trial_id, registry, policy, provenance, positions[trial_id], validation_position
        )["replay"]["deterministic_payload"]
        if replayed != first_payloads[trial_id]:
            replay_mismatches.append({
                "trial_id": trial_id,
                "first_hash": canonical_sha256(first_payloads[trial_id]),
                "replay_hash": canonical_sha256(replayed),
            })
    replay_report = {
        "replay_type": "E2_deterministic_replay_v1",
        "dataset_class": DATASET_CLASS,
        "accepted_formal_result": False,
        "result_notice": NOT_FORMAL_RESULT,
        "attempt_count": len(trial_ids),
        "exact_agreement_count": len(trial_ids) - len(replay_mismatches),
        "exact_agreement_rate": (
            (len(trial_ids) - len(replay_mismatches)) / len(trial_ids)
        ),
        "status": "PASS" if not replay_mismatches else "FAIL",
        "compared_fields": [
            "Candidate canonical hash", "parse snapshot hash", "execute snapshot hash",
            "Early committed c/r/T", "Late execution-resolved c/r/T",
            "executable payload hash", "metric flags",
            "correction/rejection classification",
        ],
        "mismatches": replay_mismatches,
    }
    write_json_exclusive(run_dir / "replay.json", replay_report)
    if replay_mismatches:
        raise E2ToolingError("deterministic replay mismatch; formal execution remains blocked")

    snapshot = journal.snapshot()
    score = score_records(records, journal_snapshot=snapshot)
    write_json_exclusive(run_dir / "score.json", score)

    from e2_audit import audit_run
    audit = audit_run(run_dir, verify_current_provenance=True)
    write_json_exclusive(run_dir / "audit.json", audit)
    if audit["status"] != "PASS":
        raise E2ToolingError("synthetic audit failed; formal execution remains blocked")

    failed = score["failed_synthetic_attempts"]
    result_manifest = {
        "manifest_type": "E2_synthetic_validation_result_manifest_v1",
        "run_id": run_id,
        "created_at_utc": utc_now(),
        "dataset_class": DATASET_CLASS,
        "accepted_formal_result": False,
        "result_notice": NOT_FORMAL_RESULT,
        "scientific_conclusion": "forbidden_from_synthetic_validation",
        "formal_global_order_modified": False,
        "formal_global_trial_cursor_consumed": False,
        "E2_filter_used_for_validation_only": True,
        "E2_filter_claimed_as_formal_execution_order": False,
        "registered_attempt_count": 120,
        "retained_attempt_count": len(records),
        "failed_synthetic_attempt_count": len(failed),
        "failed_synthetic_trial_ids": failed,
        "deterministic_replay_status": replay_report["status"],
        "deterministic_replay_exact_agreement_rate": replay_report[
            "exact_agreement_rate"
        ],
        "synthetic_audit_status": audit["status"],
        "raw_journal_snapshot": snapshot,
        "outputs": [
            "raw-journal/", "provenance_manifest.json", "score.json",
            "replay.json", "audit.json", "result_manifest.json",
            "file_hash_manifest.json",
        ],
    }
    write_json_exclusive(run_dir / "result_manifest.json", result_manifest)
    hashes = file_hash_manifest_payload(run_dir, exclude=("file_hash_manifest.json",))
    write_json_exclusive(run_dir / "file_hash_manifest.json", hashes)
    return run_dir


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--synthetic-validation", action="store_true", required=True)
    parser.add_argument("--run-id", default=_run_id_default())
    parser.add_argument("--output-root", type=Path, default=SYNTHETIC_RESULTS_DIR)
    args = parser.parse_args()
    run_dir = run_synthetic_validation(args.run_id, args.output_root)
    print(run_dir)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
