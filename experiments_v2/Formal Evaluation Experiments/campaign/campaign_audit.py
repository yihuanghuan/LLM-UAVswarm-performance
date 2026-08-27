#!/usr/bin/env python3
"""Offline auditor for a retained synthetic global campaign run."""

from __future__ import annotations

import argparse
from collections import Counter
import json
from pathlib import Path
from typing import Any, Dict, List

from campaign_common import (
    DATASET_CLASS, FORMAL_RESULTS_DIR, NOT_FORMAL_RESULT, ORDER_TXT_PATH,
    ORDER_TXT_SHA256, family_for_trial, load_json, load_sealed_order,
    sha256_file, utc_now, write_json_exclusive,
)
from campaign_dispatcher import CampaignDispatcher, _formal_cursor_snapshot
from campaign_provenance import validate_provenance
from runner_registry import load_runner_registry, registry_sha256


def audit_run(run_dir: Path, require_complete: bool = True) -> Dict[str, Any]:
    run_dir = Path(run_dir)
    checks: List[Dict[str, Any]] = []

    def check(name: str, ok: bool, details: Any) -> None:
        checks.append({"check": name, "status": "PASS" if ok else "FAIL", "details": details})

    try:
        provenance = validate_provenance(raise_on_failure=False)
        check("current_provenance", provenance["status"] == "PASS", provenance["status"])
        manifest = load_json(run_dir / "campaign_run_manifest.json")
        dispatcher = CampaignDispatcher(
            run_id=run_dir.name,
            adapters={},
            results_root=run_dir.parent,
            provenance_report=provenance,
        )
        state = dispatcher.validate_state()
        records = dispatcher.journal.read()
        order = load_sealed_order()
        check("sealed_order_hash", sha256_file(ORDER_TXT_PATH) == ORDER_TXT_SHA256,
              {"sha256": ORDER_TXT_SHA256, "run_manifest": manifest["sealed_hashes"]["simulation_trial_order_v1_txt_sha256"]})
        check("exact_prefix_or_full_order",
              [item["trial_id"] for item in records] == order[:len(records)],
              {"journal_count": len(records), "sealed_count": len(order)})
        check("complete_610_order", not require_complete or len(records) == 610,
              {"required": require_complete, "count": len(records)})
        check("journal_chain_integrity", True,
              {"records": len(records), "tail_hash": records[-1]["record_hash"] if records else None})
        check("every_attempt_retained", state["retained_count"] == len(records), state)
        ids = [record["trial_id"] for record in records]
        check("no_missing_duplicate_replacement_reorder",
              len(ids) == len(set(ids)) and all(not record["replacement_attempt"] for record in records),
              {"count": len(ids), "unique": len(set(ids)), "replacements": sum(bool(r["replacement_attempt"]) for r in records)})
        routing_errors = [record["global_position"] for record in records
                          if record["experiment"] != family_for_trial(record["trial_id"])]
        check("correct_runner_routing", not routing_errors, {"errors": routing_errors})
        label_errors = [record["global_position"] for record in records
                        if record["dataset_class"] != DATASET_CLASS
                        or record["accepted_formal_result"] is not False
                        or record["result_notice"] != NOT_FORMAL_RESULT]
        check("synthetic_labels", not label_errors, {"errors": label_errors})
        hash_errors = [record["global_position"] for record in records
                       if sha256_file(run_dir / record["artifact_path"]) != record["artifact_sha256"]]
        check("attempt_artifact_hashes", not hash_errors, {"errors": hash_errors})
        current_sources = provenance["campaign_infrastructure_source_hashes"]
        check("campaign_source_provenance_match",
              manifest["campaign_infrastructure_source_hashes"] == current_sources,
              {"recorded_commit": manifest["campaign_infrastructure_commit"]})
        check("runner_registry_provenance_match",
              manifest["runner_registry_sha256"] == registry_sha256(load_runner_registry()),
              {"sha256": manifest["runner_registry_sha256"]})
        formal_unchanged = manifest["formal_cursor_state_before"] == _formal_cursor_snapshot()
        check("formal_cursor_not_consumed",
              manifest.get("formal_cursor_consumed") is False and formal_unchanged,
              {"before": manifest["formal_cursor_state_before"],
               "after": _formal_cursor_snapshot(), "formal_results_path": str(FORMAL_RESULTS_DIR)})
        status_counts = Counter(record["attempt_status"] for record in records)
        check("failure_retention_and_advance",
              bool(status_counts.get("success")) and sum(value for key, value in status_counts.items() if key != "success") > 0,
              dict(status_counts))
    except Exception as exc:
        check("auditor_internal_error", False, {"type": type(exc).__name__, "message": str(exc)})
        records = []
        status_counts = Counter()

    status = "PASS" if all(item["status"] == "PASS" for item in checks) else "FAIL"
    return {
        "audit_type": "E2_E5_global_synthetic_campaign_audit_v1",
        "generated_at_utc": utc_now(),
        "dataset_class": DATASET_CLASS,
        "accepted_formal_result": False,
        "result_notice": NOT_FORMAL_RESULT,
        "status": status,
        "accounted_attempts": len(records),
        "status_counts": dict(status_counts),
        "checks": checks,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("run_dir", type=Path)
    parser.add_argument("--allow-prefix", action="store_true")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    report = audit_run(args.run_dir, require_complete=not args.allow_prefix)
    if args.output:
        write_json_exclusive(args.output, report)
    else:
        print(json.dumps(report, ensure_ascii=False, sort_keys=True, indent=2))
    return 0 if report["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
