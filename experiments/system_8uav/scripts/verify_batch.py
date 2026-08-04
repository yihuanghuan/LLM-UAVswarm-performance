#!/usr/bin/env python3
"""Verify experiment-10 batch data integrity after summarization.

Checks that the tracked manifests/ archive, the raw per-attempt manifests,
and the summary CSVs all agree on the final verdicts.
"""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
from typing import Dict, List

from system_common import (
    CONFIG_PATH, REPO_ROOT, bool_value, load_yaml,
)

VERDICT_FIELDS = [
    "semantic_success", "execution_success", "safety_success",
    "overall_success", "failure_reason", "analysis_complete",
]


def find_outcomes(batch: Path) -> Path:
    for name in (
        "formal_batch_outcomes.json", "diagnostic_batch_outcomes.json",
            "pilot_batch_outcomes.json"):
        path = batch / name
        if path.is_file():
            return path
    raise FileNotFoundError(f"no batch outcomes found in {batch}")


def verify_batch(batch: Path, summaries: Path) -> List[str]:
    """Return a sorted list of consistency violation descriptions.

    An empty list means the batch is internally consistent.
    """
    outcomes = json.loads(
        find_outcomes(batch).read_text(encoding="utf-8"))
    violations: List[str] = []
    archive_root = batch / "manifests"
    manifests: Dict[str, dict] = {}

    for outcome in outcomes:
        attempt_id = outcome["attempt_id"]
        raw_path = Path(outcome["path"]) / "manifest.json"
        archive_path = archive_root / f"{attempt_id}.json"
        if not raw_path.is_file():
            violations.append(f"{attempt_id}: raw manifest missing {raw_path}")
            continue
        raw = json.loads(raw_path.read_text(encoding="utf-8"))
        if not archive_path.is_file():
            violations.append(f"{attempt_id}: archived manifest missing")
            continue
        archived = json.loads(archive_path.read_text(encoding="utf-8"))
        for field in VERDICT_FIELDS:
            if raw.get(field) != archived.get(field):
                violations.append(
                    f"{attempt_id}: archive {field}={archived.get(field)!r} "
                    f"!= raw {field}={raw.get(field)!r}")
        if (bool_value(raw.get("entered_execution"))
                and not bool_value(raw.get("analysis_complete"))):
            violations.append(
                f"{attempt_id}: entered execution but analysis_complete is "
                f"{raw.get('analysis_complete')!r}")
        manifests[attempt_id] = raw

    csv_path = summaries / "attempt_summary.csv"
    if csv_path.is_file():
        with csv_path.open(newline="", encoding="utf-8") as handle:
            for row in csv.DictReader(handle):
                raw = manifests.get(row.get("attempt_id", ""))
                if raw is None:
                    continue
                for field in ("execution_success", "safety_success",
                              "overall_success"):
                    if (str(raw.get(field, "")).strip().lower()
                            != str(row.get(field, "")).strip().lower()):
                        violations.append(
                            f"{row.get('attempt_id')}: attempt_summary.csv "
                            f"{field}={row.get(field)!r} != manifest "
                            f"{raw.get(field)!r}")

    safety_csv = summaries / "safety_summary.csv"
    if safety_csv.is_file():
        by_trial = {
            (raw.get("task_type"), str(raw.get("trial_id"))): raw
            for raw in manifests.values()
        }
        with safety_csv.open(newline="", encoding="utf-8") as handle:
            for row in csv.DictReader(handle):
                raw = by_trial.get(
                    (row.get("task_type"), str(row.get("trial_id"))))
                if raw is None:
                    continue
                if (str(raw.get("safety_success", "")).strip().lower()
                        != str(row.get("safety_success", "")).strip().lower()):
                    violations.append(
                        f"{row.get('task_type')}/trial {row.get('trial_id')}: "
                        f"safety_summary.csv safety_success mismatch")

    checksums = {
        manifest.get("config_checksum")
        for manifest in manifests.values()
        if manifest.get("config_checksum")
    }
    if len(checksums) > 1:
        violations.append(
            f"distinct config checksums across attempts: {sorted(checksums)}")

    return sorted(set(violations))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--batch-id", required=True)
    parser.add_argument("--config", default=str(CONFIG_PATH))
    parser.add_argument("--results-root")
    parser.add_argument("--summaries-dir")
    args = parser.parse_args()
    config = load_yaml(Path(args.config).resolve())
    root = Path(args.results_root).resolve() if args.results_root else (
        REPO_ROOT / config["paths"]["results_root"]).resolve()
    batch = root / args.batch_id
    summaries = (Path(args.summaries_dir).resolve()
                 if args.summaries_dir else batch / "summaries")
    violations = verify_batch(batch, summaries)
    if violations:
        for violation in violations:
            print(f"consistency violation: {violation}")
        print(f"FAILED: {len(violations)} consistency violations",
              file=sys.stderr)
        return 1
    print(f"OK: {batch} manifest archive and summaries are consistent")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
