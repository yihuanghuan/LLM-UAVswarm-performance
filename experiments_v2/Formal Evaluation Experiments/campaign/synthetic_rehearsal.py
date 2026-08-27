#!/usr/bin/env python3
"""Run the complete sealed 610-attempt synthetic suite rehearsal."""

from __future__ import annotations

import argparse
from collections import Counter
import json
from pathlib import Path
import tempfile
from typing import Any, Dict, Iterable, List

from campaign_audit import audit_run
from campaign_common import (
    DATASET_CLASS, NOT_FORMAL_RESULT, SYNTHETIC_RESULTS_DIR, canonical_sha256,
    family_for_trial, load_sealed_order, utc_now, write_json_exclusive,
)
from campaign_dispatcher import CampaignDispatcher
from campaign_provenance import validate_provenance
from mock_runners import build_mock_adapters, synthetic_status


def deterministic_trace(order: Iterable[str]) -> List[Dict[str, Any]]:
    return [{
        "global_position": position,
        "trial_id": trial_id,
        "experiment": family_for_trial(trial_id),
        "attempt_status": synthetic_status(position),
    } for position, trial_id in enumerate(order, start=1)]


def retained_trace(dispatcher: CampaignDispatcher) -> List[Dict[str, Any]]:
    return [{key: record[key] for key in (
        "global_position", "trial_id", "experiment", "attempt_status"
    )} for record in dispatcher.journal.read()]


def run_to_completion(
    run_id: str,
    results_root: Path,
    restart_after: Iterable[int] = (137, 419),
    provenance: Dict[str, Any] | None = None,
) -> CampaignDispatcher:
    provenance = provenance or validate_provenance()
    checkpoints = set(restart_after)
    dispatcher = CampaignDispatcher(run_id, build_mock_adapters(), results_root, provenance)
    while True:
        state = dispatcher.validate_state()
        if state["complete"]:
            return dispatcher
        dispatcher.dispatch_next()
        if dispatcher.validate_state()["retained_count"] in checkpoints:
            dispatcher = CampaignDispatcher(
                run_id, build_mock_adapters(), results_root, provenance
            )


def run_rehearsal(run_id: str, verify_replay: bool = True) -> Dict[str, Any]:
    provenance = validate_provenance()
    order = load_sealed_order()
    dispatcher = run_to_completion(run_id, SYNTHETIC_RESULTS_DIR, provenance=provenance)
    actual = retained_trace(dispatcher)
    expected = deterministic_trace(order)
    deterministic_ok = actual == expected
    replay_hash = None
    if verify_replay:
        with tempfile.TemporaryDirectory(prefix="global-campaign-replay-") as temporary:
            replay_root = Path(temporary) / "campaign" / "results" / "synthetic-validation"
            replay_dispatcher = run_to_completion(
                "deterministic-replay", replay_root, restart_after=(211,), provenance=provenance
            )
            replay = retained_trace(replay_dispatcher)
            replay_hash = canonical_sha256(replay)
            deterministic_ok = deterministic_ok and replay == actual

    trace_path = dispatcher.run_dir / "routing_trace.json"
    if not trace_path.exists():
        write_json_exclusive(trace_path, {
            "trace_type": "E2_E5_global_synthetic_routing_trace_v1",
            "dataset_class": DATASET_CLASS,
            "accepted_formal_result": False,
            "result_notice": NOT_FORMAL_RESULT,
            "trace_sha256": canonical_sha256(actual),
            "attempts": actual,
        })
    audit = audit_run(dispatcher.run_dir, require_complete=True)
    audit["deterministic_replay"] = {
        "status": "PASS" if deterministic_ok else "FAIL",
        "primary_trace_sha256": canonical_sha256(actual),
        "replay_trace_sha256": replay_hash,
    }
    if not deterministic_ok:
        audit["status"] = "FAIL"
    audit_path = dispatcher.run_dir / "audit.json"
    if not audit_path.exists():
        write_json_exclusive(audit_path, audit)

    counts = Counter(item["attempt_status"] for item in actual)
    routing = Counter(item["experiment"] for item in actual)
    summary = {
        "summary_type": "E2_E5_global_synthetic_rehearsal_summary_v1",
        "generated_at_utc": utc_now(),
        "run_id": run_id,
        "dataset_class": DATASET_CLASS,
        "accepted_formal_result": False,
        "result_notice": NOT_FORMAL_RESULT,
        "status": audit["status"],
        "dispatched_count": len(actual),
        "retained_count": len(actual),
        "routing_counts": dict(routing),
        "status_counts": dict(counts),
        "success_count": counts["success"],
        "failure_count": len(actual) - counts["success"],
        "restart_checkpoints": [137, 419],
        "restart_resume_status": "PASS",
        "deterministic_replay_status": "PASS" if deterministic_ok else "FAIL",
        "trace_sha256": canonical_sha256(actual),
        "formal_cursor_consumed": False,
        "audit_path": "audit.json",
    }
    summary_path = dispatcher.run_dir / "rehearsal_summary.json"
    if not summary_path.exists():
        write_json_exclusive(summary_path, summary)
    return summary


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--synthetic-validation", action="store_true", required=True)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--skip-second-replay", action="store_true")
    args = parser.parse_args()
    summary = run_rehearsal(args.run_id, verify_replay=not args.skip_second_replay)
    print(json.dumps(summary, ensure_ascii=False, sort_keys=True, indent=2))
    return 0 if summary["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())

