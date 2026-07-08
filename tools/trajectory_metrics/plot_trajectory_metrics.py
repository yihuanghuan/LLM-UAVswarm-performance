#!/usr/bin/env python3
"""Plot trajectory metric summaries."""

from __future__ import annotations

import argparse
import csv
import math
import sys
from pathlib import Path
from typing import Dict, List

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from eval_trajectory import METRIC_FIELDS, normalize_row, parse_float  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate PNG plots from trajectory metrics CSV data."
    )
    parser.add_argument("csv", help="summary.csv or raw trajectory metrics CSV.")
    parser.add_argument(
        "--out-dir",
        default="trajectory_plots",
        help="Directory for generated PNG files.",
    )
    return parser.parse_args()


def read_csv(path: Path) -> List[Dict[str, str]]:
    with path.open(newline="") as handle:
        reader = csv.DictReader(handle)
        return [normalize_row(row) for row in reader]


def final_rows_by_uav(rows: List[Dict[str, str]]) -> List[Dict[str, str]]:
    grouped: Dict[str, Dict[str, str]] = {}
    for row in rows:
        uav_id = row.get("uav_id", "")
        if uav_id:
            grouped[uav_id] = row
    return [
        grouped[key]
        for key in sorted(grouped.keys(), key=lambda item: int(float(item)))
    ]


def plot_bar(rows: List[Dict[str, str]], metric: str, out_dir: Path) -> None:
    labels = [str(int(float(row.get("uav_id", "0")))) for row in rows]
    values = [parse_float(row.get(metric)) for row in rows]
    finite = [value for value in values if math.isfinite(value)]
    if not finite:
        return

    plt.figure(figsize=(max(6.0, len(labels) * 0.7), 4.0))
    plt.bar(labels, values)
    plt.xlabel("UAV ID")
    plt.ylabel(metric)
    plt.title(metric.replace("_", " ").title())
    plt.grid(axis="y", alpha=0.3)
    plt.tight_layout()
    plt.savefig(out_dir / f"{metric}.png", dpi=160)
    plt.close()


def plot_time_series(rows: List[Dict[str, str]], metric: str, out_dir: Path) -> None:
    if "elapsed_time" not in rows[0]:
        return

    grouped: Dict[str, List[Dict[str, str]]] = {}
    for row in rows:
        uav_id = row.get("uav_id", "")
        if uav_id:
            grouped.setdefault(uav_id, []).append(row)

    has_series = any(len(items) > 1 for items in grouped.values())
    if not has_series:
        return

    plt.figure(figsize=(8.0, 4.8))
    plotted = False
    for uav_id, items in sorted(grouped.items(), key=lambda item: int(float(item[0]))):
        points = [
            (parse_float(row.get("elapsed_time")), parse_float(row.get(metric)))
            for row in items
        ]
        points = [
            (elapsed, value)
            for elapsed, value in points
            if math.isfinite(elapsed) and math.isfinite(value)
        ]
        if not points:
            continue
        points.sort(key=lambda item: item[0])
        plt.plot(
            [item[0] for item in points],
            [item[1] for item in points],
            label=f"UAV {int(float(uav_id))}",
        )
        plotted = True

    if not plotted:
        plt.close()
        return
    plt.xlabel("elapsed_time (s)")
    plt.ylabel(metric)
    plt.title(metric.replace("_", " ").title())
    plt.grid(alpha=0.3)
    plt.legend()
    plt.tight_layout()
    plt.savefig(out_dir / f"{metric}_timeseries.png", dpi=160)
    plt.close()


def main() -> int:
    args = parse_args()
    csv_path = Path(args.csv)
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    rows = read_csv(csv_path)
    if not rows:
        raise RuntimeError(f"No rows found in {csv_path}")

    final_rows = final_rows_by_uav(rows)
    if not final_rows:
        raise RuntimeError("No uav_id rows found")

    for metric in METRIC_FIELDS:
        if metric in final_rows[0]:
            plot_bar(final_rows, metric, out_dir)
        if metric in rows[0]:
            plot_time_series(rows, metric, out_dir)

    print(f"Wrote plots to {out_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
