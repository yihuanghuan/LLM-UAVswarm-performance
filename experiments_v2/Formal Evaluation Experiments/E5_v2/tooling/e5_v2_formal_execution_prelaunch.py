#!/usr/bin/env python3
"""Generate/check the fail-closed E5-v2 formal execution prelaunch audit."""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
from pathlib import Path

from e5_v2_activation_common import sealed_scientific_payload_sha256
from e5_v2_common import (
    BASELINE_COMMIT, E5_DIR, OLD_E5_REGISTRY_PATH, OLD_E5_REGISTRY_SHA256,
    OLD_E5_SOURCE_COMMIT, POLICY_SHA256, PRODUCTION_METHOD_PATHS, REPO_ROOT,
    REGISTRY_PATH, load_yaml, sha256_file,
)
from e5_v2_formal_adapter import assert_formal_activation, assert_formal_attempt
from e5_v2_formal_common import (
    ANALYSIS_PATH, ATTEMPTS_ROOT, CONFIG_PATH, EXPECTED_ANALYSIS_SHA256, EXPECTED_ORDER_SHA256,
    EXPECTED_REGISTRY_SHA256, EXPECTED_SEED_SHA256, JOURNAL_ROOT, RAW_LEDGER_ROOT,
    RAW_POLICY_PATH, TOOLING_BUNDLE_PATH, exclusive_json, load_attempt_specs,
    load_json, verify_final_tooling_bundle, verify_runtime_environment,
)


AUDIT_JSON = E5_DIR / "E5_v2_formal_execution_prelaunch_audit.json"
AUDIT_MD = E5_DIR / "E5_v2_formal_execution_prelaunch_audit.md"
REHEARSAL = E5_DIR / "E5_v2_static_rehearsal_audit.json"


def _unchanged_from_baseline(paths) -> bool:
    return subprocess.run(["git", "diff", "--quiet", BASELINE_COMMIT, "--", *paths],
                          cwd=REPO_ROOT).returncode == 0


def audit() -> dict:
    registry = assert_formal_activation()
    specs = load_attempt_specs()
    first = specs[0]
    assert_formal_attempt(
        order_position=1, trial_id=first["attempt_id"], seed=first["seed"],
        n=first["N"], scenario_id=first["scenario_id"],
        substudy=first["substudy"], task_family=first.get("task_family"),
        completed_attempt_ids=[])
    bundle = verify_final_tooling_bundle()
    runtime_environment = verify_runtime_environment()
    rehearsal = load_json(REHEARSAL)
    old = subprocess.check_output(
        ["git", "show", f"{OLD_E5_SOURCE_COMMIT}:{OLD_E5_REGISTRY_PATH}"],
        cwd=REPO_ROOT)
    journal_records = list(JOURNAL_ROOT.glob("*.json"))
    ledger_records = list(RAW_LEDGER_ROOT.glob("*.json"))
    attempt_directories = [path for path in ATTEMPTS_ROOT.glob("*") if path.is_dir()]
    transactions = E5_DIR / "results/formal_v2/.transactions"
    raw_pending = Path(load_yaml(CONFIG_PATH)["runtime"]["raw_archive_root"]) / ".pending"
    source_names = ("e5_v2_formal_backend.py", "e5_v2_formal_orchestrator.py",
                    "e5_v2_campaign_journal.py", "e5_v2_formal_metrics.py")
    tooling = Path(__file__).parent
    checks = {
        "activated_registry": registry["status"] == "SEALED_FOR_FORMAL_EXECUTION",
        "sealed_registry_sha256": sha256_file(REGISTRY_PATH) == EXPECTED_REGISTRY_SHA256,
        "scientific_payload_unchanged": sealed_scientific_payload_sha256()
            == "96ab0893ee099c1003f6a5aad6896decde97c4b9c8d885d38141b8a4dbae81ed",
        "scientific_protocol_changes_zero": all((
            sha256_file(REGISTRY_PATH) == EXPECTED_REGISTRY_SHA256,
            sha256_file(E5_DIR / "E5_v2_seed_registry.yaml") == EXPECTED_SEED_SHA256,
            sha256_file(E5_DIR / "E5_v2_formal_trial_order.txt") == EXPECTED_ORDER_SHA256,
            sha256_file(ANALYSIS_PATH) == EXPECTED_ANALYSIS_SHA256,
            sha256_file(REPO_ROOT / "lfs_policy/config/lfs_policy.paper_current.yaml")
                == POLICY_SHA256,
        )),
        "registered_attempts_60": len(specs) == 60,
        "consumed_attempts_0": len(journal_records) == 0,
        "journal_records_0": len(journal_records) == 0,
        "attempt_directories_0": len(attempt_directories) == 0,
        "slot_1_exact_identity": (
            first["attempt_id"], first["seed"], first["N"], first["task_family"])
            == ("E5V2-B-S2-N12-R1", 5202036, 12, "UNDER_SPECIFIED"),
        "formal_backend_exists": (tooling / source_names[0]).is_file(),
        "formal_orchestrator_exists": (tooling / source_names[1]).is_file(),
        "journal_implementation_exists": (tooling / source_names[2]).is_file(),
        "metrics_extractor_exists": (tooling / source_names[3]).is_file(),
        "journal_exists_and_empty": JOURNAL_ROOT.is_dir() and not journal_records,
        "raw_storage_policy_frozen": RAW_POLICY_PATH.is_file(),
        "archive_ledger_exists_and_empty": RAW_LEDGER_ROOT.is_dir() and not ledger_records,
        "synthetic_static_rehearsal": rehearsal.get("result") == "PASS",
        "production_method_changes_zero": _unchanged_from_baseline(PRODUCTION_METHOD_PATHS),
        "old_E5_v1_unchanged": (
            hashlib.sha256(old).hexdigest() == OLD_E5_REGISTRY_SHA256
            and subprocess.run(
                ["git", "diff", "--quiet", BASELINE_COMMIT, "--",
                 OLD_E5_REGISTRY_PATH], cwd=REPO_ROOT).returncode == 0),
        "formal_scientific_missions_executed_0": (
            rehearsal.get("registered_commands_physically_submitted") == 0
            and not journal_records and not attempt_directories),
        "accepted_formal_results_0": (
            registry["accepted_formal_results_created"] is False
            and not attempt_directories),
        "final_formal_tooling_bundle_frozen": bool(bundle.get("bundle_sha256")),
        "formal_runtime_environment_pins": runtime_environment.get("status") == "PASS",
        "no_pending_formal_transaction": (
            not transactions.exists() or not any(transactions.iterdir())),
        "no_pending_raw_archive": (
            not raw_pending.exists() or not any(raw_pending.iterdir())),
    }
    return {
        "schema": "E5_v2_formal_execution_prelaunch_audit_v1",
        "result": "PASS" if all(checks.values()) else "FAIL",
        "checks": checks,
        "identities": {
            "sealed_registry_sha256": EXPECTED_REGISTRY_SHA256,
            "scientific_payload_sha256": sealed_scientific_payload_sha256(),
            "seed_registry_sha256": EXPECTED_SEED_SHA256,
            "formal_order_sha256": EXPECTED_ORDER_SHA256,
            "analysis_contract_sha256": EXPECTED_ANALYSIS_SHA256,
            "production_policy_sha256": POLICY_SHA256,
            "old_E5_v1_registry_sha256": OLD_E5_REGISTRY_SHA256,
            "final_formal_execution_tooling_bundle_sha256": bundle["bundle_sha256"],
        },
        "counts": {"registered": len(specs), "consumed": len(journal_records),
                   "journal_records": len(journal_records),
                   "attempt_directories": len(attempt_directories),
                   "archive_ledger_records": len(ledger_records)},
        "slot_1": {key: first.get(key) for key in (
            "campaign_position", "attempt_id", "seed", "substudy", "N",
            "scenario_id", "task_family")},
        "target_state": [
            "E5-v2 FORMAL EXECUTION INFRASTRUCTURE READY",
            "FORMAL EXECUTION NOT STARTED",
            "WAITING FOR FORMAL LAUNCH AUTHORIZATION",
        ],
    }


def render_md(value: dict) -> str:
    checks = "\n".join(
        f"- {name}: {'PASS' if passed else 'FAIL'}"
        for name, passed in value["checks"].items())
    return (
        "# E5-v2 formal execution prelaunch audit\n\n"
        f"Overall result: **{value['result']}**\n\n"
        "This is a tooling/static audit only. No registered scientific command "
        "was submitted and no formal slot was consumed.\n\n"
        "## Checks\n\n" + checks + "\n\n"
        "## Frozen target state\n\n"
        "E5-v2 FORMAL EXECUTION INFRASTRUCTURE READY\n\n"
        "FORMAL EXECUTION NOT STARTED\n\n"
        "WAITING FOR FORMAL LAUNCH AUTHORIZATION\n")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--write", action="store_true")
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    value = audit()
    if args.write:
        if AUDIT_JSON.exists() or AUDIT_MD.exists():
            raise SystemExit("refusing to overwrite prelaunch audit")
        exclusive_json(AUDIT_JSON, value)
        AUDIT_MD.write_text(render_md(value), encoding="utf-8")
    if args.check:
        if load_json(AUDIT_JSON) != value or AUDIT_MD.read_text() != render_md(value):
            raise SystemExit("prelaunch audit is stale")
    return 0 if value["result"] == "PASS" else 2


if __name__ == "__main__":
    raise SystemExit(main())
