#!/usr/bin/env python3
"""Continuously execute and transactionally retain the exact sealed 60-slot order."""

from __future__ import annotations

import argparse
import os
import shutil
import time
from pathlib import Path
from typing import Any, Dict

from e5_v2_campaign_journal import CampaignJournal
from e5_v2_formal_adapter import assert_formal_attempt
from e5_v2_formal_backend import run_physical_trial
from e5_v2_formal_common import (
    ANALYSIS_PATH, ATTEMPTS_ROOT, CLASSIFICATION_PATH, CONFIG_PATH,
    EXPECTED_ANALYSIS_SHA256, EXPECTED_ORDER_SHA256, EXPECTED_REGISTRY_SHA256,
    EXPECTED_SEED_SHA256, FORMAL_ROOT, RAW_POLICY_PATH, EvidenceIntegrityError,
    FormalInfrastructureError, canonical_sha256, exclusive_json, inventory, load_attempt_specs,
    load_json, load_yaml, sha256_file, validate_external_launch_authorization,
    verify_final_tooling_bundle, verify_frozen_identities,
)
from e5_v2_formal_metrics import extract_metrics, read_jsonl, read_rosbag_evidence
from e5_v2_raw_storage import (
    RawArchiveLedger, assert_no_pending_raw, pre_raw_failure, raw_evidence_loss,
    verify_and_publish_raw,
)
from e5_v2_common import POLICY_SHA256


def _stage_outcomes(backend: Dict[str, Any], traces):
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
    stages["semantic_candidate_comparison"] = {"success": candidate_valid,
                                                "scored_in_metrics": True}
    stages["resolver"] = {
        "success": candidate_valid and resolution_ok,
        "reason": (None if resolution_ok else
                   unresolved_rejection.get("rejection_reason")
                   if unresolved_rejection else
                   rejection.get("rejection_reason") if rejection else
                   "no successful resolution trace")}
    stages["geometry"] = {"success": stages["resolver"]["success"]}
    stages["planning"] = {"success": stages["resolver"]["success"]}
    stages["execution_profile_compilation"] = {
        "success": stages["resolver"]["success"]}
    stages["mission_dispatch"] = {
        "success": resolution_ok, "any_command_dispatched": bool(resolved)}
    stages["controller_px4"] = {
        "success": runtime_success if resolved else None,
        "reached": bool(resolved),
        "reason": semantic.get("terminal_error", {}).get("reason")}
    stages.setdefault("mission_completion", {"success": runtime_success})
    stages["scientific_terminal_reached"] = bool(
        candidate_valid and (runtime_success or rejection is not None
                             or semantic.get("terminal_error")))
    terminal_type = semantic.get("terminal_error", {}).get("type")
    stages["hard_failure"] = bool(
        backend.get("cleanup_errors") or (
            resolved and not runtime_success
            and terminal_type not in {"TimeoutError"}))
    stages["scientific_metrics"] = {"success": False, "pending": True}
    stages["evidence_archive_retention"] = {"success": False, "pending": True}
    return stages


def _copy_if_present(source: Path, target: Path) -> None:
    if source.is_file():
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)


def _make_read_only_tree(root: Path) -> None:
    for path in sorted(Path(root).rglob("*"), reverse=True):
        path.chmod(0o555 if path.is_dir() else 0o444)
    Path(root).chmod(0o555)


def finalize_attempt(spec: Dict[str, Any], backend: Dict[str, Any],
                     transaction_root: Path, journal: CampaignJournal,
                     ledger: RawArchiveLedger, bundle_sha: str,
                     archive_root: Path) -> Dict[str, Any]:
    trace_path = Path(backend["resolution_trace_path"]) if backend.get(
        "resolution_trace_path") else None
    traces = read_jsonl(trace_path) if trace_path else []
    stages = _stage_outcomes(backend, traces)
    raw_started = bool(backend.get("raw_acquisition_started"))
    if not raw_started:
        disposition = pre_raw_failure(
            spec, backend.get("backend_error", {}).get("reason", "readiness failed"),
            Path(backend.get("launch_plan", {}).get("raw_pending_root", ""))
            if backend.get("launch_plan") else None,
            archive_root)
    else:
        try:
            disposition = verify_and_publish_raw(
                spec, Path(backend["launch_plan"]["raw_pending_root"]), archive_root)
        except EvidenceIntegrityError as exc:
            disposition = raw_evidence_loss(
                spec, str(exc), Path(backend["launch_plan"]["raw_pending_root"]),
                archive_root)

    evidence = {"candidate": backend.get("semantic_result", {}).get("candidate"),
                "latencies_s": backend.get("semantic_result", {}).get("latencies_s", {})}
    if disposition["disposition"] == "RAW_ARCHIVE_VERIFIED":
        try:
            evidence.update(read_rosbag_evidence(
                Path(disposition["archive_reference"]) / "rosbag", spec["uav_ids"],
                trace_path))
        except Exception as exc:
            # Acquisition began, so an unreadable required bag is evidence loss.
            disposition = raw_evidence_loss(
                spec, f"metric raw read failed: {exc}", archive_root=archive_root,
                existing_archive=Path(disposition["archive_reference"]))
    metrics = extract_metrics(spec, stages, evidence, disposition["disposition"])
    stages["scientific_metrics"] = {
        "success": disposition["disposition"] != "RAW_EVIDENCE_LOSS"}
    stages["evidence_archive_retention"] = {
        "success": disposition["disposition"] in {
            "RAW_ARCHIVE_VERIFIED", "PRE_RAW_ACQUISITION_INFRASTRUCTURE_FAILURE"},
        "disposition": disposition["disposition"]}

    staging = transaction_root / "compact_attempt"
    staging.mkdir()
    semantic = backend.get("semantic_result", {})
    exclusive_json(staging / "runtime_provenance.json", {
        "runtime_pin": backend.get("runtime_pin"),
        "process_counts_before": backend.get("process_counts_before"),
        "process_counts_after_cleanup": backend.get("process_counts_after_cleanup"),
        "launch_plan": backend.get("launch_plan"),
        "formal_execution_tooling_bundle_sha256": bundle_sha,
    })
    exclusive_json(staging / "semantic_result.json", semantic)
    exclusive_json(staging / "candidate.json", {
        "source": "real_semantic_frontend", "fallback_used": False,
        "ground_truth_injected": False, "candidate": semantic.get("candidate"),
        "candidate_correctness": metrics["candidate_correctness"]})
    exclusive_json(staging / "resolution.json", {"records": traces})
    exclusive_json(staging / "planning.json", {
        "resolver": stages["resolver"], "geometry": stages["geometry"],
        "planning": stages["planning"],
        "execution_profile_compilation": stages["execution_profile_compilation"]})
    exclusive_json(staging / "mission_result.json", {
        "mission_dispatch": stages["mission_dispatch"],
        "controller_px4": stages["controller_px4"],
        "mission_completion": stages["mission_completion"]})
    exclusive_json(staging / "metrics.json", metrics)
    exclusive_json(staging / "raw_inventory.json", {
        "file_inventory": disposition.get("file_inventory", []),
        "inventory_sha256": disposition.get("inventory_sha256")})
    exclusive_json(staging / "storage_disposition.json", disposition)
    for name in ("agent.log", "sitl.log", "controllers.log", "rosbag.log",
                 "semantic_worker.log", "readiness.stdout.json",
                 "readiness.stderr.log", "llm_parse_log.csv",
                 "llm_raw_responses.jsonl"):
        _copy_if_present(transaction_root / name, staging / "compact_logs" / name)
    _copy_if_present(transaction_root / "backend_result.json",
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
        "accepted_formal_result": True, "replacement_attempt": False,
        "attempt_status": attempt_status, "stage_outcomes": stages,
        "registry_sha256": EXPECTED_REGISTRY_SHA256,
        "seed_registry_sha256": EXPECTED_SEED_SHA256,
        "order_sha256": EXPECTED_ORDER_SHA256,
        "analysis_contract_sha256": EXPECTED_ANALYSIS_SHA256,
        "policy_sha256": POLICY_SHA256,
        "formal_execution_tooling_bundle_sha256": bundle_sha,
        "production_baseline": spec["production_baseline"],
        "raw_storage_disposition": disposition["disposition"],
    }
    exclusive_json(staging / "attempt.json", attempt)
    required = {
        "attempt.json", "runtime_provenance.json", "semantic_result.json",
        "candidate.json", "resolution.json", "planning.json",
        "mission_result.json", "metrics.json", "raw_inventory.json",
        "storage_disposition.json",
    }
    compact_records = inventory(staging)
    present = {item["path"] for item in compact_records}
    if not required.issubset(present):
        raise EvidenceIntegrityError(
            f"mandatory compact evidence missing: {sorted(required - present)}")
    exclusive_json(staging / "compact_inventory.json", {
        "schema": "E5_v2_compact_inventory_v1",
        "files": compact_records,
        "inventory_sha256": canonical_sha256(compact_records),
    })
    for record in compact_records:
        if sha256_file(staging / record["path"]) != record["sha256"]:
            raise EvidenceIntegrityError("compact evidence changed during verification")
    artifact_name = f"{spec['campaign_position']:06d}__{spec['attempt_id']}"
    final_directory = ATTEMPTS_ROOT / artifact_name
    if final_directory.exists():
        raise FormalInfrastructureError(f"attempt artifact already exists: {final_directory}")
    final_directory.parent.mkdir(parents=True, exist_ok=True)
    os.rename(staging, final_directory)
    _make_read_only_tree(final_directory)
    ledger_path = ledger.append(disposition)
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
    return {"attempt": attempt, "metrics": metrics, "disposition": disposition,
            "journal_path": str(journal_path), "artifact_path": str(final_directory)}


def assert_campaign_consistency(journal: CampaignJournal,
                                ledger: RawArchiveLedger,
                                archive_root: Path | None = None,
                                *, verify_archives: bool = False) -> Dict[str, Any]:
    state, raw_records = journal.state(), ledger.validate(
        verify_archives=verify_archives)
    if len(raw_records) != state["consumed_slots"]:
        raise FormalInfrastructureError("journal/raw-ledger length mismatch")
    for journal_record, raw_record in zip(journal.validate(), raw_records):
        if journal_record["attempt_id"] != raw_record["attempt_id"]:
            raise FormalInfrastructureError("journal/raw-ledger prefix mismatch")
    artifact_dirs = [path for path in ATTEMPTS_ROOT.iterdir()
                     if path.is_dir()] if ATTEMPTS_ROOT.exists() else []
    if len(artifact_dirs) != state["consumed_slots"]:
        raise FormalInfrastructureError("orphan or missing formal attempt directory")
    transactions = FORMAL_ROOT / ".transactions"
    if transactions.is_dir() and any(transactions.iterdir()):
        raise FormalInfrastructureError("unresolved formal transaction directory")
    if archive_root is not None:
        assert_no_pending_raw(archive_root)
    return state


def run_campaign(authorization_path: Path) -> int:
    verify_frozen_identities()
    bundle = verify_final_tooling_bundle()
    validate_external_launch_authorization(authorization_path)
    journal, ledger = CampaignJournal(), RawArchiveLedger()
    archive_root = Path(load_yaml(CONFIG_PATH)["runtime"]["raw_archive_root"])
    state = assert_campaign_consistency(
        journal, ledger, archive_root, verify_archives=True)
    specs = load_attempt_specs()
    for spec in specs[state["consumed_slots"]:]:
        state = assert_campaign_consistency(journal, ledger, archive_root)
        assert_formal_attempt(
            order_position=spec["campaign_position"], trial_id=spec["attempt_id"],
            seed=spec["seed"], n=spec["N"], scenario_id=spec["scenario_id"],
            substudy=spec["substudy"], task_family=spec.get("task_family"),
            completed_attempt_ids=state["completed_attempt_ids"])
        transaction = FORMAL_ROOT / ".transactions" / (
            f"{spec['campaign_position']:06d}__{spec['attempt_id']}__{time.time_ns()}")
        backend = run_physical_trial(spec, state["completed_attempt_ids"], transaction,
                                     authorization_path)
        retained = finalize_attempt(spec, backend, transaction, journal, ledger,
                                    bundle["bundle_sha256"], archive_root)
        try:
            shutil.rmtree(transaction)
        except Exception as exc:
            raise FormalInfrastructureError(
                f"consumed attempt retained but transaction cleanup failed: {exc}") from exc
        if retained["disposition"]["campaign_stop"]:
            raise EvidenceIntegrityError("RAW_EVIDENCE_LOSS consumed slot; campaign stopped")
        if backend.get("cleanup_errors"):
            raise FormalInfrastructureError("systematic runtime cleanup failure")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--formal", action="store_true", required=True)
    parser.add_argument("--launch-authorization", type=Path, required=True)
    args = parser.parse_args()
    return run_campaign(args.launch_authorization)


if __name__ == "__main__":
    raise SystemExit(main())
