#!/usr/bin/env python3
"""Generate analytic profile data for experiment 05."""

from __future__ import annotations

import argparse
import csv
from pathlib import Path
from typing import Dict, Iterable

import numpy as np

from trajectory_profiles import PROFILES, analytic_metrics, sample_progress


REPO_ROOT = Path(__file__).resolve().parents[2]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--output-summary",
        default=str(REPO_ROOT / "experiments/results/trajectory_profile_results.csv"),
    )
    parser.add_argument(
        "--output-timeseries",
        default=str(REPO_ROOT / "experiments/results/trajectory_profile_timeseries.csv"),
    )
    parser.add_argument("--duration", type=float, default=8.0)
    parser.add_argument("--distance", type=float, default=10.0)
    parser.add_argument("--dt", type=float, default=0.02)
    return parser.parse_args()


def write_csv(path: Path, rows: Iterable[Dict[str, object]]) -> None:
    rows = list(rows)
    if not rows:
        raise ValueError("no rows")
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def main() -> int:
    args = parse_args()
    if args.duration <= 0.0 or args.distance <= 0.0:
        raise ValueError("duration and distance must be positive")
    if args.dt <= 0.0 or args.dt >= args.duration:
        raise ValueError("dt must be positive and less than duration")

    count = int(round(args.duration / args.dt))
    times = np.linspace(0.0, args.duration, count + 1)
    summary_rows = []
    timeseries_rows = []
    for profile in PROFILES:
        metrics = analytic_metrics(profile, args.distance, args.duration)
        summary_rows.append(
            {
                "profile": profile,
                "duration": args.duration,
                "distance": args.distance,
                **metrics.__dict__,
                "final_error": 0.0,
            }
        )
        data = sample_progress(profile, times, args.duration)
        for index, time_s in enumerate(times):
            timeseries_rows.append(
                {
                    "profile": profile,
                    "time_s": time_s,
                    "position": args.distance * data["position"][index],
                    "velocity": args.distance * data["velocity"][index],
                    "acceleration": args.distance * data["acceleration"][index],
                    "jerk": args.distance * data["jerk"][index],
                }
            )

    write_csv(Path(args.output_summary), summary_rows)
    write_csv(Path(args.output_timeseries), timeseries_rows)
    print(f"Wrote {args.output_summary}")
    print(f"Wrote {args.output_timeseries}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
