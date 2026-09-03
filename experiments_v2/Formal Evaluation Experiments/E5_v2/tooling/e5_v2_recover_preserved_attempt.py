#!/usr/bin/env python3
"""Recover the preserved slot-1 transaction without any physical execution path."""

from __future__ import annotations

import argparse
import json
import os
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List

from e5_v2_campaign_journal import CampaignJournal
from e5_v2_common import E5_DIR, POLICY_SHA256, REPO_ROOT, sha256_file
from e5_v2_formal_common import (
    ATTEMPTS_ROOT, EXPECTED_ANALYSIS_SHA256, EXPECTED_ORDER_SHA256,
    EXPECTED_REGISTRY_SHA256, EXPECTED_SEED_SHA256, FORMAL_ROOT, JOURNAL_ROOT,
    RAW_LEDGER_ROOT, RECOVERY_BUNDLE_PATH, EvidenceIntegrityError,
    FormalInfrastructureError, canonical_sha256, exclusive_json, inventory,
    load_attempt_specs, load_json, verify_frozen_identities,
    verify_ros_python_environment,
)
from e5_v2_formal_metrics import extract_metrics, read_jsonl, read_rosbag_evidence
from e5_v2_raw_storage import RawArchiveLedger, verify_existing_raw_archive


SLOT1_ATTEMPT_ID = "E5V2-B-S2-N12-R1"
SLOT1_POSITION = 1
SLOT1_SEED = 5202036
SLOT1_N = 12
ORIGINAL_PHYSICAL_BUNDLE_SHA256 = (
    "422d82b593ba927dffaee3c14bcf8b6996304a8ae302cdc525ab3c525b786ecb"
)
EXPECTED_RAW_INVENTORY_SHA256 = (
    "ff97ad4ef665754e23fc90e06803844580bcfaacd2ae89034d3ecaf8bc56fbda"
)
EXPECTED_TRANSACTION_INVENTORY_SHA256 = (
    "2c0c1d9d961ccc63ffee0776f4b36c9ec0b111c9cb6f877b2e28dcc06bbc9152"
)
EXPECTED_RAW_FILES = [
    {
        "path": "rosbag/metadata.yaml", "bytes": 61225,
        "sha256": "73feae6d49b958a3586f76dbeabf95087d91e29e8d21063a7e9f3802dbd30603",
    },
    {
        "path": "rosbag/rosbag_0.db3", "bytes": 45821952,
        "sha256": "8c73098c6481d4a885cb42210b9d1808b06695fa3741aab4f60bbf6174694a5c",
    },
]
J_HARD_ADJUDICATION = {
    "status": "PREREGISTERED_ENDPOINT_UNAVAILABLE_DUE_TO_SEMANTIC_AMBIGUITY"
}


@dataclass(frozen=True)
class RecoveryContext:
    transaction_root: Path
    raw_archive: Path
    attempts_root: Path = ATTEMPTS_ROOT
    journal_root: Path = JOURNAL_ROOT
    ledger_root: Path = RAW_LEDGER_ROOT
    recovered_transactions_root: Path = FORMAL_ROOT / "recovered_transaction_evidence"
    recovery_bundle_path: Path = RECOVERY_BUNDLE_PATH
    make_read_only: bool = True
    synthetic_rehearsal: bool = False


def default_context() -> RecoveryContext:
    return RecoveryContext(
        transaction_root=FORMAL_ROOT / ".transactions" /
        "000001__E5V2-B-S2-N12-R1__1788405481555191643",
        raw_archive=Path(
            "/home/yihuang/learning/LLM_swarm_ws/e5_v2_formal_raw_archive_v1/"
            "attempts/000001__E5V2-B-S2-N12-R1"),
    )


def _verify_bundle(path: Path) -> Dict[str, Any]:
    bundle = load_json(path)
    if bundle.get("schema") != "E5_v2_slot1_recovery_tooling_bundle_v1":
        raise FormalInfrastructureError("slot-1 recovery bundle schema mismatch")
    records = bundle.get("files", [])
    if not records or canonical_sha256(records) != bundle.get("bundle_sha256"):
        raise FormalInfrastructureError("slot-1 recovery bundle aggregate mismatch")
    for record in records:
        retained = REPO_ROOT / record["path"]
        if not retained.is_file() or sha256_file(retained) != record["sha256"]:
            raise FormalInfrastructureError(f"slot-1 recovery tooling drift: {retained}")
    return bundle


def _directory_count(root: Path) -> int:
    return len([path for path in Path(root).glob("*") if path.is_dir()])


def _stage_outcomes(backend: Dict[str, Any], traces: List[Dict[str, Any]]):
    stages = dict(backend.get("stage_outcomes", {}))
    semantic = backend.get("semantic_result", {})
    candidate_valid = semantic.get("candidate") is not None
    rejection = next((item for item in traces if item.get("rejection_stage")
                      or item.get("rejection_reason")), None)
    resolved = [item for item in traces
                if item.get("resolved_center") is not None
                and item.get("r_exec") is not None
                and item.get("t_exec") is not None
                and not item.get("rejection_reason")]
    resolved_task_ids = {item.get("task_id") for item in resolved}
    unresolved_rejection = next(
        (item for item in traces
         if (item.get("rejection_stage") or item.get("rejection_reason"))
         and item.get("task_id") not in resolved_task_ids), None)
    resolution_ok = bool(resolved) and unresolved_rejection is None
    runtime_success = bool(semantic.get("success"))
    stages.setdefault("semantic_frontend", {"success": candidate_valid})
    stages.setdefault("candidate_parsing", {"success": candidate_valid})
    stages.setdefault("candidate_validation", {"success": candidate_valid})
    stages["semantic_candidate_comparison"] = {
        "success": candidate_valid, "scored_in_metrics": True}
    stages["resolver"] = {
        "success": candidate_valid and resolution_ok,
        "reason": (None if resolution_ok else
                   unresolved_rejection.get("rejection_reason")
                   if unresolved_rejection else
                   rejection.get("rejection_reason") if rejection else
                   "no successful resolution trace"),
    }
    for key in ("geometry", "planning", "execution_profile_compilation"):
        stages[key] = {"success": stages["resolver"]["success"]}
    stages["mission_dispatch"] = {
        "success": resolution_ok, "any_command_dispatched": bool(resolved)}
    stages["controller_px4"] = {
        "success": runtime_success if resolved else None,
        "reached": bool(resolved),
        "reason": semantic.get("terminal_error", {}).get("reason"),
    }
    stages.setdefault("mission_completion", {"success": runtime_success})
    stages["scientific_terminal_reached"] = bool(
        candidate_valid and (runtime_success or rejection is not None
                             or semantic.get("terminal_error")))
    terminal_type = semantic.get("terminal_error", {}).get("type")
    stages["hard_failure"] = bool(
        backend.get("cleanup_errors") or (
            resolved and not runtime_success and terminal_type not in {"TimeoutError"}))
    stages["scientific_metrics"] = {"success": False, "pending": True}
    stages["evidence_archive_retention"] = {"success": False, "pending": True}
    return stages


def verify_recovery_gate(
    context: RecoveryContext,
    expected_raw_sha: str = EXPECTED_RAW_INVENTORY_SHA256,
    expected_transaction_sha: str = EXPECTED_TRANSACTION_INVENTORY_SHA256,
) -> Dict[str, Any]:
    verify_frozen_identities()
    spec = load_attempt_specs()[0]
    expected_identity = {
        "campaign_position": SLOT1_POSITION, "attempt_id": SLOT1_ATTEMPT_ID,
        "seed": SLOT1_SEED, "N": SLOT1_N,
    }
    for key, value in expected_identity.items():
        if spec.get(key) != value:
            raise FormalInfrastructureError(f"slot-1 {key} mismatch")
    journal = CampaignJournal(
        context.journal_root, context.attempts_root,
        synthetic_rehearsal=context.synthetic_rehearsal)
    ledger = RawArchiveLedger(context.ledger_root)
    if journal.validate() or ledger.validate() or _directory_count(context.attempts_root):
        raise FormalInfrastructureError(
            "slot-1 recovery requires empty journal, ledger, and published attempts")
    if not context.transaction_root.is_dir():
        raise EvidenceIntegrityError("preserved slot-1 transaction missing")
    tx_inventory = inventory(context.transaction_root)
    if (len(tx_inventory) != 30 or sum(item["bytes"] for item in tx_inventory) != 633319
            or canonical_sha256(tx_inventory) != expected_transaction_sha):
        raise EvidenceIntegrityError("preserved slot-1 transaction inventory mismatch")
    raw_inventory = inventory(context.raw_archive)
    if (raw_inventory != EXPECTED_RAW_FILES
            or canonical_sha256(raw_inventory) != expected_raw_sha):
        raise EvidenceIntegrityError("preserved slot-1 raw inventory mismatch")
    backend = load_json(context.transaction_root / "backend_result.json")
    backend_spec = backend.get("spec", {})
    for key, value in expected_identity.items():
        if backend_spec.get(key) != value:
            raise FormalInfrastructureError(f"preserved backend slot-1 {key} mismatch")
    if backend.get("formal_execution_tooling_bundle_sha256") != (
            ORIGINAL_PHYSICAL_BUNDLE_SHA256):
        raise FormalInfrastructureError("original physical tooling bundle mismatch")
    bundle = _verify_bundle(context.recovery_bundle_path)
    return {
        "spec": spec, "backend": backend, "transaction_inventory": tx_inventory,
        "raw_inventory": raw_inventory, "recovery_bundle": bundle,
    }


def _read_confirmed_evidence(gate: Dict[str, Any], context: RecoveryContext):
    trace_path = context.transaction_root / "ros_home/candidate_resolution_trace.jsonl"
    traces = read_jsonl(trace_path)
    stages = _stage_outcomes(gate["backend"], traces)
    evidence = {
        "candidate": gate["backend"].get("semantic_result", {}).get("candidate"),
        "latencies_s": gate["backend"].get("semantic_result", {}).get(
            "latencies_s", {}),
    }
    evidence.update(read_rosbag_evidence(
        context.raw_archive / "rosbag", gate["spec"]["uav_ids"], trace_path))
    metrics = extract_metrics(
        gate["spec"], stages, evidence, "RAW_ARCHIVE_VERIFIED")
    if metrics.get("J_hard") != {
        "available": False, "value": None,
        "reason": "preregistered continuous endpoint unavailable due to "
                  "pre-analysis semantic ambiguity",
    }:
        raise FormalInfrastructureError("J_hard availability adjudication not enforced")
    return traces, stages, metrics


def dry_validate(context: RecoveryContext | None = None) -> Dict[str, Any]:
    context = context or default_context()
    verify_ros_python_environment()
    gate = verify_recovery_gate(context)
    verify_existing_raw_archive(gate["spec"], context.raw_archive,
                                gate["raw_inventory"])
    _read_confirmed_evidence(gate, context)
    return {
        "status": "PASS", "published": False,
        "attempt_id": SLOT1_ATTEMPT_ID,
        "raw_integrity": "PASS", "transaction_integrity": "PASS",
        "required_message_types_resolved": True,
        "scientific_metric_values_printed": False,
        "physical_execution_invoked": False,
    }


def _copy_if_present(source: Path, target: Path) -> None:
    if source.is_file():
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)


def _make_read_only_tree(root: Path) -> None:
    for path in sorted(Path(root).rglob("*"), reverse=True):
        path.chmod(0o555 if path.is_dir() else 0o444)
    Path(root).chmod(0o555)


def publish_recovery(context: RecoveryContext | None = None) -> Dict[str, Any]:
    context = context or default_context()
    dry_validate(context)
    gate = verify_recovery_gate(context)
    spec, backend = gate["spec"], gate["backend"]
    traces, stages, metrics = _read_confirmed_evidence(gate, context)
    recovery_sha = gate["recovery_bundle"]["bundle_sha256"]
    disposition = verify_existing_raw_archive(
        spec, context.raw_archive, gate["raw_inventory"])
    disposition.update({
        "verification_passes": 4,
        "recovered_existing_verified_archive": True,
        "original_physical_execution_tooling_bundle_sha256":
            ORIGINAL_PHYSICAL_BUNDLE_SHA256,
    })
    stages["scientific_metrics"] = {"success": True}
    stages["evidence_archive_retention"] = {
        "success": True, "disposition": "RAW_ARCHIVE_VERIFIED"}

    staging = context.attempts_root.parent / (
        ".slot1_recovery_staging__000001__E5V2-B-S2-N12-R1")
    if staging.exists():
        raise FormalInfrastructureError("slot-1 recovery staging already exists")
    staging.mkdir(parents=True)
    semantic = backend.get("semantic_result", {})
    exclusive_json(staging / "runtime_provenance.json", {
        "runtime_pin": backend.get("runtime_pin"),
        "process_counts_before": backend.get("process_counts_before"),
        "process_counts_after_cleanup": backend.get("process_counts_after_cleanup"),
        "launch_plan": backend.get("launch_plan"),
        "physical_execution_tooling_bundle_sha256": ORIGINAL_PHYSICAL_BUNDLE_SHA256,
        "transaction_recovery_tooling_bundle_sha256": recovery_sha,
        "recovered_from_preserved_physical_attempt": True,
        "physical_rerun": False,
        "recovery_after_formal_blocker": True,
    })
    exclusive_json(staging / "semantic_result.json", semantic)
    exclusive_json(staging / "candidate.json", {
        "source": "real_semantic_frontend", "fallback_used": False,
        "ground_truth_injected": False, "candidate": semantic.get("candidate"),
        "candidate_correctness": metrics["candidate_correctness"],
    })
    exclusive_json(staging / "resolution.json", {"records": traces})
    exclusive_json(staging / "planning.json", {
        "resolver": stages["resolver"], "geometry": stages["geometry"],
        "planning": stages["planning"],
        "execution_profile_compilation": stages["execution_profile_compilation"],
    })
    exclusive_json(staging / "mission_result.json", {
        "mission_dispatch": stages["mission_dispatch"],
        "controller_px4": stages["controller_px4"],
        "mission_completion": stages["mission_completion"],
    })
    exclusive_json(staging / "metrics.json", metrics)
    exclusive_json(staging / "raw_inventory.json", {
        "file_inventory": disposition["file_inventory"],
        "inventory_sha256": disposition["inventory_sha256"],
    })
    exclusive_json(staging / "storage_disposition.json", disposition)
    for name in (
        "agent.log", "sitl.log", "controllers.log", "rosbag.log",
        "semantic_worker.log", "readiness.stdout.json", "readiness.stderr.log",
        "llm_parse_log.csv", "llm_raw_responses.jsonl",
    ):
        _copy_if_present(context.transaction_root / name,
                         staging / "compact_logs" / name)
    _copy_if_present(context.transaction_root / "backend_result.json",
                     staging / "backend_result.json")

    attempt_status = (
        "infrastructure_failure" if metrics["infrastructure_failure"] else
        "mission_success" if metrics["mission_success"]["value"] else
        "scientific_failure")
    attempt = {
        "schema": "E5_v2_formal_attempt_v1",
        "campaign_position": spec["campaign_position"],
        "attempt_id": spec["attempt_id"], "seed": spec["seed"], "N": spec["N"],
        "substudy": spec["substudy"], "scenario_id": spec["scenario_id"],
        "task_family": spec.get("task_family"),
        "accepted_formal_result": not context.synthetic_rehearsal,
        "replacement_attempt": False,
        "attempt_status": attempt_status, "stage_outcomes": stages,
        "registry_sha256": EXPECTED_REGISTRY_SHA256,
        "seed_registry_sha256": EXPECTED_SEED_SHA256,
        "order_sha256": EXPECTED_ORDER_SHA256,
        "analysis_contract_sha256": EXPECTED_ANALYSIS_SHA256,
        "policy_sha256": POLICY_SHA256,
        "formal_execution_tooling_bundle_sha256": ORIGINAL_PHYSICAL_BUNDLE_SHA256,
        "physical_execution_tooling_bundle_sha256": ORIGINAL_PHYSICAL_BUNDLE_SHA256,
        "transaction_recovery_tooling_bundle_sha256": recovery_sha,
        "production_baseline": spec["production_baseline"],
        "raw_storage_disposition": "RAW_ARCHIVE_VERIFIED",
        "recovered_from_preserved_physical_attempt": True,
        "physical_rerun": False,
        "recovery_after_formal_blocker": True,
        "endpoint_adjudications": {"J_hard": J_HARD_ADJUDICATION},
    }
    exclusive_json(staging / "attempt.json", attempt)
    compact_records = inventory(staging)
    required = {
        "attempt.json", "runtime_provenance.json", "semantic_result.json",
        "candidate.json", "resolution.json", "planning.json",
        "mission_result.json", "metrics.json", "raw_inventory.json",
        "storage_disposition.json", "backend_result.json",
    }
    if not required.issubset({item["path"] for item in compact_records}):
        raise EvidenceIntegrityError("mandatory recovered compact evidence missing")
    exclusive_json(staging / "compact_inventory.json", {
        "schema": "E5_v2_compact_inventory_v1", "files": compact_records,
        "inventory_sha256": canonical_sha256(compact_records),
    })
    for record in compact_records:
        if sha256_file(staging / record["path"]) != record["sha256"]:
            raise EvidenceIntegrityError("recovered compact evidence changed")

    artifact_name = "000001__E5V2-B-S2-N12-R1"
    final_directory = context.attempts_root / artifact_name
    if final_directory.exists():
        raise FormalInfrastructureError("slot-1 formal attempt already published")
    context.attempts_root.mkdir(parents=True, exist_ok=True)
    os.rename(staging, final_directory)
    if context.make_read_only:
        _make_read_only_tree(final_directory)

    ledger = RawArchiveLedger(context.ledger_root)
    ledger_path = ledger.append(disposition)
    journal = CampaignJournal(
        context.journal_root, context.attempts_root,
        synthetic_rehearsal=context.synthetic_rehearsal)
    journal_path = journal.append({
        "campaign_position": spec["campaign_position"],
        "attempt_id": spec["attempt_id"], "seed": spec["seed"], "N": spec["N"],
        "scenario_id": spec["scenario_id"], "substudy": spec["substudy"],
        "task_family": spec.get("task_family"), "attempt_status": attempt_status,
        "artifact_directory": artifact_name,
        "attempt_sha256": sha256_file(final_directory / "attempt.json"),
        "compact_inventory_sha256": sha256_file(
            final_directory / "compact_inventory.json"),
        "raw_ledger_record": ledger_path.name,
        "raw_ledger_record_sha256": sha256_file(ledger_path),
    })
    context.recovered_transactions_root.mkdir(parents=True, exist_ok=True)
    recovered_transaction = context.recovered_transactions_root / context.transaction_root.name
    if recovered_transaction.exists():
        raise FormalInfrastructureError("recovered transaction evidence already exists")
    os.rename(context.transaction_root, recovered_transaction)
    if context.make_read_only:
        _make_read_only_tree(recovered_transaction)
    return {
        "status": "PASS", "published": True,
        "attempt_id": SLOT1_ATTEMPT_ID, "physical_rerun": False,
        "journal_path": str(journal_path), "ledger_path": str(ledger_path),
        "artifact_path": str(final_directory),
        "recovered_transaction_path": str(recovered_transaction),
        "recovery_bundle_sha256": recovery_sha,
        "scientific_metric_values_printed": False,
        "physical_execution_invoked": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--dry-run", action="store_true")
    mode.add_argument("--publish", action="store_true")
    args = parser.parse_args()
    result = dry_validate() if args.dry_run else publish_recovery()
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
