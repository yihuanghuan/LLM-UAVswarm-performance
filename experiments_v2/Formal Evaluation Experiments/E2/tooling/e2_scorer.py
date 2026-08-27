#!/usr/bin/env python3
"""Offline scorer for the sealed E2 primary metrics."""

from __future__ import annotations

import argparse
from collections import defaultdict
import json
from pathlib import Path
from typing import Any, Dict, Iterable, List, Tuple

from e2_common import (
    DATASET_CLASS, NOT_FORMAL_RESULT, E2ToolingError, registered_trial_ids,
    utc_now, write_json_exclusive,
)
from e2_journal import AttemptJournal


PRIMARY_FLAGS = (
    "executable_grounding_success",
    "state_consistency_violation",
    "dynamic_infeasibility",
    "correction",
    "rejection",
)


def _cell(records: Iterable[Dict[str, Any]]) -> Dict[str, Any]:
    records = list(records)
    denominator = len(records)
    counts = {
        name: sum(record["metric_flags"][name] is True for record in records)
        for name in PRIMARY_FLAGS
    }
    counts["correction_or_rejection"] = sum(
        record["metric_flags"]["correction"] is True
        or record["metric_flags"]["rejection"] is True
        for record in records
    )
    rates = {
        "executable_grounding_success": counts["executable_grounding_success"] / denominator
        if denominator else None,
        "state_consistency_violation_rate": counts["state_consistency_violation"] / denominator
        if denominator else None,
        "dynamic_infeasibility_rate": counts["dynamic_infeasibility"] / denominator
        if denominator else None,
        "correction_or_rejection_rate": counts["correction_or_rejection"] / denominator
        if denominator else None,
        "correction_rate": counts["correction"] / denominator if denominator else None,
        "rejection_rate": counts["rejection"] / denominator if denominator else None,
    }
    return {"attempt_denominator": denominator, "counts": counts, "rates": rates}


def score_records(
    records: List[Dict[str, Any]], *, journal_snapshot: Dict[str, Any] | None = None,
    require_complete: bool = True,
) -> Dict[str, Any]:
    trial_ids = [str(record.get("identity", {}).get("trial_id")) for record in records]
    if len(trial_ids) != len(set(trial_ids)):
        raise E2ToolingError("scorer refuses duplicate trial IDs")
    if require_complete and set(trial_ids) != set(registered_trial_ids()):
        raise E2ToolingError("scorer input is not the complete 120-attempt E2 population")
    for record in records:
        flags = record.get("metric_flags")
        if not isinstance(flags, dict) or any(
            not isinstance(flags.get(name), bool) for name in PRIMARY_FLAGS
        ):
            raise E2ToolingError(
                f"invalid metric flags for {record.get('identity', {}).get('trial_id')}"
            )
        if flags.get("correction_or_rejection") != (
            flags["correction"] or flags["rejection"]
        ):
            raise E2ToolingError("combined correction/rejection flag is inconsistent")

    grouped: Dict[Tuple[str, str], List[Dict[str, Any]]] = defaultdict(list)
    by_condition: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    by_state: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    for record in records:
        identity = record["identity"]
        condition = identity["commitment_condition"]
        state = identity["state_condition"]
        grouped[(condition, state)].append(record)
        by_condition[condition].append(record)
        by_state[state].append(record)

    failed = [
        record["identity"]["trial_id"] for record in records
        if not record["metric_flags"]["executable_grounding_success"]
    ]
    return {
        "score_type": "E2_primary_metrics_v1",
        "scored_at_utc": utc_now(),
        "dataset_class": DATASET_CLASS,
        "accepted_formal_result": False,
        "result_notice": NOT_FORMAL_RESULT,
        "scientific_interpretation_allowed": False,
        "input_raw_journal": journal_snapshot,
        "registered_attempt_count": 120,
        "observed_attempt_count": len(records),
        "failed_synthetic_attempts": failed,
        "overall": _cell(records),
        "by_commitment_condition": {
            key: _cell(value) for key, value in sorted(by_condition.items())
        },
        "by_state_condition": {
            key: _cell(value) for key, value in sorted(by_state.items())
        },
        "by_commitment_and_state": {
            f"{condition}__{state}": _cell(value)
            for (condition, state), value in sorted(grouped.items())
        },
        "metric_contract": {
            "executable_grounding_success": "valid executable mission produced through the frozen resolver at the registered execution snapshot",
            "state_consistency_violation_rate": "selected executable c/r/T differs from untouched-Candidate resolution at the same registered execution snapshot",
            "dynamic_infeasibility_rate": "an already numerical request required a frozen feasibility change, or resolution terminated at a dynamic/geometry feasibility gate",
            "correction_or_rejection_rate": "downstream numerical correction to an already committed request or terminal rejection",
            "normal_late_resolution_is_correction": False,
        },
    }


def score_run(run_dir: Path) -> Dict[str, Any]:
    journal = AttemptJournal(Path(run_dir) / "raw-journal")
    return score_records(journal.read(), journal_snapshot=journal.snapshot())


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("run_dir", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    score = score_run(args.run_dir)
    if args.output:
        write_json_exclusive(args.output, score)
    else:
        print(json.dumps(score, ensure_ascii=False, sort_keys=True, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
