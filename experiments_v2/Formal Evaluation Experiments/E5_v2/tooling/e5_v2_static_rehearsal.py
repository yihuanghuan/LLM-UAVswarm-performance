#!/usr/bin/env python3
"""Deterministic synthetic/static rehearsal that cannot execute a formal command."""

from __future__ import annotations

import argparse
import subprocess
import tempfile
from pathlib import Path

from e5_v2_campaign_journal import CampaignJournal
from e5_v2_common import E5_DIR, flatten_conditions, load_yaml
from e5_v2_formal_adapter import assert_formal_attempt
from e5_v2_formal_backend import stop_process
from e5_v2_formal_common import (
    ATTEMPTS_ROOT, JOURNAL_ROOT, RAW_LEDGER_ROOT, REPO_ROOT, build_launch_plan,
    exclusive_json, load_attempt_specs, runtime_submission, sha256_file,
)
from e5_v2_formal_metrics import extract_metrics, synthetic_fixture
from e5_v2_raw_storage import (
    RawArchiveLedger, pre_raw_failure, raw_evidence_loss, verify_and_publish_raw,
)


AUDIT_JSON = E5_DIR / "E5_v2_static_rehearsal_audit.json"
AUDIT_MD = E5_DIR / "E5_v2_static_rehearsal_audit.md"


def _json_records(root: Path):
    return list(root.glob("*.json")) if root.exists() else []


def _publish_synthetic_attempt(root: Path, spec: dict, status: str):
    directory = root / f"{spec['campaign_position']:06d}__{spec['attempt_id']}"
    directory.mkdir(parents=True)
    exclusive_json(directory / "attempt.json", {
        "schema": "synthetic_rehearsal_only",
        "campaign_position": spec["campaign_position"],
        "attempt_id": spec["attempt_id"],
        "accepted_formal_result": False,
        "replacement_attempt": False,
        "attempt_status": status,
    })
    exclusive_json(directory / "compact_inventory.json", {
        "schema": "synthetic_rehearsal_compact_inventory"})
    return directory


def run_rehearsal() -> dict:
    before = {
        "journal_records": len(_json_records(JOURNAL_ROOT)),
        "raw_ledger_records": len(_json_records(RAW_LEDGER_ROOT)),
        "attempt_directories": len([path for path in ATTEMPTS_ROOT.glob("*")
                                    if path.is_dir()]),
    }
    if any(before.values()):
        raise RuntimeError(f"formal state must be empty before rehearsal: {before}")
    specs = load_attempt_specs()
    registry = load_yaml(E5_DIR / "E5_v2_registry.yaml")
    commands = {item["scenario_id"]: item["exact_command"]
                for item in flatten_conditions(registry)}
    completed = []
    launch_ns, forbidden = set(), []
    for spec in specs:
        assert_formal_attempt(
            order_position=spec["campaign_position"], trial_id=spec["attempt_id"],
            seed=spec["seed"], n=spec["N"], scenario_id=spec["scenario_id"],
            substudy=spec["substudy"], task_family=spec.get("task_family"),
            completed_attempt_ids=completed)
        if spec["exact_command"] != commands[spec["scenario_id"]]:
            raise AssertionError("exact command changed during compilation")
        submission = runtime_submission(spec)
        forbidden.extend(key for key in submission if "ground_truth" in key
                         or key in {"candidate", "mission_json"})
        plan = build_launch_plan(spec, Path("/synthetic/e5_v2"))
        if plan["uav_ids"] != list(range(1, spec["N"] + 1)):
            raise AssertionError("dynamic launcher enumeration mismatch")
        launch_ns.add(spec["N"])
        completed.append(spec["attempt_id"])

    with tempfile.TemporaryDirectory(prefix="e5-v2-rehearsal-") as temporary:
        root = Path(temporary)
        attempts, journals, ledgers = root / "attempts", root / "journal", root / "ledger"
        journal = CampaignJournal(
            journals, attempts, synthetic_rehearsal=True)
        ledger = RawArchiveLedger(ledgers)
        first, second = specs[:2]
        first_dir = _publish_synthetic_attempt(attempts, first, "infrastructure_failure")
        first_raw = pre_raw_failure(first, "synthetic readiness failure")
        first_ledger = ledger.append(first_raw)
        journal.append({
            "campaign_position": 1, "attempt_id": first["attempt_id"],
            "seed": first["seed"], "N": first["N"],
            "scenario_id": first["scenario_id"], "substudy": first["substudy"],
            "task_family": first.get("task_family"),
            "attempt_status": "infrastructure_failure",
            "artifact_directory": first_dir.name,
            "attempt_sha256": sha256_file(first_dir / "attempt.json"),
            "compact_inventory_sha256": sha256_file(
                first_dir / "compact_inventory.json"),
            "raw_ledger_record": first_ledger.name,
            "raw_ledger_record_sha256": sha256_file(first_ledger),
        })
        if journal.state()["next_attempt"]["attempt_id"] != second["attempt_id"]:
            raise AssertionError("failed retained attempt did not consume slot")

        pending = root / "archive/.pending/second"
        (pending / "rosbag").mkdir(parents=True)
        (pending / "rosbag/metadata.yaml").write_text("synthetic: true\n", encoding="utf-8")
        (pending / "rosbag/synthetic.db3").write_bytes(b"synthetic-not-a-real-bag")
        verified = verify_and_publish_raw(second, pending, root / "archive")
        if verified["disposition"] != "RAW_ARCHIVE_VERIFIED":
            raise AssertionError("synthetic raw archive was not verified")
        loss = raw_evidence_loss(second, "synthetic evidence loss")
        if not loss["campaign_stop"]:
            raise AssertionError("raw evidence loss did not stop campaign")

        evidence = synthetic_fixture(int(first["N"]))
        evidence["candidate"] = first["candidate_semantic_ground_truth"]
        metrics = extract_metrics(first, {
            "infrastructure_readiness": {"success": True},
            "candidate_validation": {"success": True},
            "resolver": {"success": True}, "planning": {"success": True},
            "mission_completion": {"success": True},
            "scientific_terminal_reached": True, "hard_failure": False,
        }, evidence, "RAW_ARCHIVE_VERIFIED")
        if metrics["mission_success"]["value"] is not True:
            raise AssertionError("synthetic metric success fixture failed")
        na_metrics = extract_metrics(first, {
            "infrastructure_readiness": {"success": False},
            "candidate_validation": {"success": False},
            "resolver": {"success": False}, "planning": {"success": False},
            "mission_completion": {"success": False},
            "scientific_terminal_reached": False,
        }, {"candidate": None}, "PRE_RAW_ACQUISITION_INFRASTRUCTURE_FAILURE")
        if na_metrics["actual_d_min"]["value"] is not None:
            raise AssertionError("infrastructure failure received continuous zero/value")

        harmless = subprocess.Popen(["bash", "-c", "exec sleep 60"],
                                    start_new_session=True)
        cleanup_returncode = stop_process(harmless, 1.0)
        if harmless.poll() is None:
            raise AssertionError("scoped synthetic cleanup failed")

    after = {
        "journal_records": len(_json_records(JOURNAL_ROOT)),
        "raw_ledger_records": len(_json_records(RAW_LEDGER_ROOT)),
        "attempt_directories": len([path for path in ATTEMPTS_ROOT.glob("*")
                                    if path.is_dir()]),
    }
    if after != before:
        raise AssertionError("rehearsal mutated formal campaign state")
    return {
        "schema": "E5_v2_static_rehearsal_audit_v1",
        "result": "PASS", "accepted_formal_result": False,
        "formal_scientific_mission_executed": False,
        "registered_commands_physically_submitted": 0,
        "attempt_specs_resolved": len(specs),
        "identity_order_gate_checks": len(specs),
        "exact_commands_preserved": len(specs),
        "launcher_N_values": sorted(launch_ns),
        "candidate_ground_truth_runtime_injection_keys": forbidden,
        "synthetic_failed_attempt_consumes_slot": True,
        "synthetic_raw_archive_verification": "PASS",
        "synthetic_raw_loss_stops_campaign": True,
        "synthetic_metric_schema": "PASS",
        "synthetic_cleanup_returncode": cleanup_returncode,
        "formal_state_before": before, "formal_state_after": after,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--write-audit", action="store_true")
    args = parser.parse_args()
    result = run_rehearsal()
    if args.write_audit:
        if AUDIT_JSON.exists() or AUDIT_MD.exists():
            raise SystemExit("refusing to overwrite rehearsal audit")
        exclusive_json(AUDIT_JSON, result)
        AUDIT_MD.write_text(
            "# E5-v2 static/synthetic rehearsal audit\n\n"
            "Result: **PASS**\n\n"
            "All 60 exact registered specs passed the formal identity/order gate. "
            "Launcher generation covered N=8/12/16; a temporary synthetic journal "
            "confirmed that a failed retained attempt consumes its slot; temporary "
            "raw files exercised verified/loss dispositions; metric fixtures preserved "
            "NA semantics; and scoped cleanup passed.\n\n"
            "No registered command was physically submitted. `accepted_formal_result` "
            "remained false for rehearsal, and the real formal journal, archive ledger, "
            "and attempt directory counts remained 0/0/0.\n",
            encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
