#!/usr/bin/env python3
"""Run/validate the exact 610-position Campaign-v2 non-formal rehearsal."""

from __future__ import annotations

from collections import Counter
import json
from pathlib import Path

from campaign_v2_common import NONFORMAL_LABELS, ORDER_SHA256, canonical_sha256, exclusive_json, family_for_trial, load_order
from campaign_v2_coordinator import Coordinator


CHECKPOINTS = {0, 1, 2, 7, 11, 120, 121, 480, 481, 585, 586, 609, 610}
FIXTURES = {7: "method_failure", 11: "infrastructure_failure", 131: "timeout", 257: "method_failure"}


def run(run_dir: Path) -> dict:
    coordinator = Coordinator("rehearsal", run_dir)
    restart_checks = []
    initial = coordinator.validate_state()
    if initial["retained_count"] in CHECKPOINTS:
        restart_checks.append(initial)
    while not coordinator.validate_state()["complete"]:
        position = coordinator.validate_state()["next_position"]
        coordinator.dispatch_next(synthetic_terminal_status=FIXTURES.get(position))
        if position in CHECKPOINTS:
            coordinator = Coordinator("rehearsal", run_dir)
            restart_checks.append(coordinator.validate_state())
    records = coordinator.journal.read()
    order = load_order()
    exact = all((record["global_position"], record["trial_id"], record["experiment"]) ==
                (position, order[position - 1], family_for_trial(order[position - 1]))
                for position, record in enumerate(records, 1))
    labels = all(all(record.get(key) == value for key, value in NONFORMAL_LABELS.items()) for record in records)
    summary = {
        "schema": "campaign_v2_full_610_rehearsal_summary_v1", **NONFORMAL_LABELS,
        "status": "PASS" if len(records) == 610 and exact and labels else "FAIL",
        "accounted_positions": len(records), "unique_trial_ids": len({r["trial_id"] for r in records}),
        "exact_global_order": exact, "correct_family_routing": exact, "global_order_sha256": ORDER_SHA256,
        "status_counts": dict(Counter(record["attempt_status"] for record in records)),
        "synthetic_failure_fixtures": FIXTURES, "restart_checkpoint_results": restart_checks,
        "restart_checkpoint_count": len(restart_checks), "physical_execution_performed": False,
        "real_provider_called": False, "formal_root_written": False,
        "journal_tail_sha256": records[-1]["record_sha256"],
    }
    summary["canonical_summary_sha256"] = canonical_sha256(summary)
    output = run_dir / "rehearsal_summary.json"
    if output.exists():
        previous = json.loads(output.read_text())
        if previous != summary:
            raise RuntimeError("existing rehearsal summary differs")
    else:
        exclusive_json(output, summary)
    return summary


if __name__ == "__main__":
    root = Path(__file__).resolve().parent / "results/synthetic-validation/campaign-v2-full-610-rehearsal-r4"
    print(json.dumps(run(root), sort_keys=True, indent=2))
