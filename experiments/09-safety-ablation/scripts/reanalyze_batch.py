#!/usr/bin/env python3
"""Recompute derived CSVs for every completed trial in a batch."""

from __future__ import annotations

import argparse
import json
import subprocess
from pathlib import Path

from analysis_core import analyze_trial, write_dict_rows


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("batch_dir", type=Path)
    args = parser.parse_args()
    trial_dirs = sorted(
        path.parent for path in args.batch_dir.glob("raw/**/trial_summary.csv")
        if "_failed_attempt_" not in str(path))
    if not trial_dirs:
        raise FileNotFoundError(f"no completed trials under {args.batch_dir}")
    analysis_commit = subprocess.run(
        ["git", "rev-parse", "HEAD"], check=True, text=True,
        stdout=subprocess.PIPE).stdout.strip()
    for trial_dir in trial_dirs:
        metadata_path = trial_dir / "run_metadata.json"
        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
        metadata["analysis_git_commit"] = analysis_commit
        metadata_path.write_text(
            json.dumps(metadata, indent=2, ensure_ascii=False),
            encoding="utf-8")
        pairs, summary = analyze_trial(trial_dir)
        write_dict_rows(
            trial_dir / "pair_summary.csv",
            [pair.__dict__ for pair in pairs])
        write_dict_rows(trial_dir / "trial_summary.csv", [summary])
    print(f"reanalyzed {len(trial_dirs)} trials")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
