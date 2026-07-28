#!/usr/bin/env python3
"""Analyze one experiment 08 trial directory."""

import argparse
from dataclasses import asdict
from pathlib import Path

from analysis_core import analyze_trial, write_dict_rows


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("trial_dir", type=Path)
    args = parser.parse_args()
    pairs, summary = analyze_trial(args.trial_dir)
    write_dict_rows(
        args.trial_dir / "pair_summary.csv", [asdict(pair) for pair in pairs])
    write_dict_rows(args.trial_dir / "trial_summary.csv", [summary])
    print(args.trial_dir / "trial_summary.csv")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
