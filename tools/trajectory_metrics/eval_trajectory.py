#!/usr/bin/env python3
"""Evaluate trajectory metrics CSV files.

The script accepts CSV files produced by either:

* ros2 topic echo --csv /uavN/trajectory_metrics
* tools/trajectory_metrics/rosbag_to_csv.py

It writes a per-UAV summary CSV plus an aggregate JSON file.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
from pathlib import Path
from statistics import mean
from typing import Dict, Iterable, List


METRIC_FIELDS = [
    "path_length",
    "max_velocity",
    "max_acceleration",
    "max_jerk",
    "integrated_squared_jerk",
    "arrival_time_error",
    "final_position_error",
]

SUMMARY_FIELDS = [
    "source",
    "uav_id",
    "samples",
    "first_elapsed_time",
    "last_elapsed_time",
    "is_finished",
    "is_hover_stable",
    *METRIC_FIELDS,
]

TRAJECTORY_METRICS_CSV_FIELDS = [
    "header_stamp_sec",
    "header_stamp_nanosec",
    "header_frame_id",
    "uav_id",
    "start_pos_x",
    "start_pos_y",
    "start_pos_z",
    "target_pos_x",
    "target_pos_y",
    "target_pos_z",
    "requested_duration",
    "trajectory_duration",
    "motion_style",
    "safety_factor",
    "path_length",
    "max_velocity",
    "max_acceleration",
    "max_jerk",
    "integrated_squared_jerk",
    "elapsed_time",
    "arrival_time_error",
    "final_position_error",
    "is_finished",
    "is_hover_stable",
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Summarize trajectory metrics CSV files."
    )
    parser.add_argument(
        "inputs",
        nargs="+",
        help="CSV files or directories containing CSV files.",
    )
    parser.add_argument(
        "--out-dir",
        default="trajectory_eval",
        help="Directory for summary.csv and summary.json.",
    )
    return parser.parse_args()


def discover_csv_files(inputs: Iterable[str]) -> List[Path]:
    files: List[Path] = []
    for item in inputs:
        path = Path(item)
        if path.is_dir():
            files.extend(sorted(path.rglob("*.csv")))
        elif path.is_file():
            files.append(path)
        else:
            raise FileNotFoundError(f"Input does not exist: {path}")
    if not files:
        raise FileNotFoundError("No CSV files found in inputs")
    return files


def normalize_key(key: str) -> str:
    key = key.strip()
    if key.startswith("/"):
        key = key[1:]
    key = key.replace("/", "_").replace(".", "_")
    aliases = {
        "trajectory_duration": "trajectory_duration",
        "requested_duration": "requested_duration",
        "header_stamp_sec": "header_stamp_sec",
        "header_stamp_nanosec": "header_stamp_nanosec",
        "start_pos_x": "start_pos_x",
        "start_pos_y": "start_pos_y",
        "start_pos_z": "start_pos_z",
        "target_pos_x": "target_pos_x",
        "target_pos_y": "target_pos_y",
        "target_pos_z": "target_pos_z",
    }
    return aliases.get(key, key)


def normalize_row(row: Dict[str, str]) -> Dict[str, str]:
    normalized: Dict[str, str] = {}
    for key, value in row.items():
        if key is None:
            continue
        normalized[normalize_key(key)] = value.strip() if isinstance(value, str) else value
    return normalized


def looks_like_header(row: List[str]) -> bool:
    normalized = {normalize_key(item) for item in row}
    return "uav_id" in normalized and "elapsed_time" in normalized


def parse_float(value: object, default: float = math.nan) -> float:
    if value is None:
        return default
    text = str(value).strip()
    if not text:
        return default
    try:
        return float(text)
    except ValueError:
        return default


def parse_bool(value: object) -> bool:
    return str(value).strip().lower() in {"true", "1", "yes"}


def read_metrics_csv(path: Path) -> List[Dict[str, str]]:
    with path.open(newline="") as handle:
        raw_rows = list(csv.reader(handle))
        if not raw_rows:
            return []

    if looks_like_header(raw_rows[0]):
        headers = [normalize_key(item) for item in raw_rows[0]]
        data_rows = raw_rows[1:]
    else:
        headers = TRAJECTORY_METRICS_CSV_FIELDS
        data_rows = raw_rows

    rows = [
        normalize_row(dict(zip(headers, row)))
        for row in data_rows
        if any(cell.strip() for cell in row)
    ]

    if not rows:
        return []

    missing = [field for field in ["uav_id", "elapsed_time"] if field not in rows[0]]
    missing.extend(field for field in METRIC_FIELDS if field not in rows[0])
    if missing:
        raise ValueError(f"{path} missing required fields: {', '.join(sorted(set(missing)))}")
    return rows


def summarize_file(path: Path) -> List[Dict[str, object]]:
    rows = read_metrics_csv(path)
    grouped: Dict[str, List[Dict[str, str]]] = {}
    for row in rows:
        uav_id = row.get("uav_id", "")
        if uav_id == "":
            continue
        grouped.setdefault(uav_id, []).append(row)

    summaries: List[Dict[str, object]] = []
    for uav_id, uav_rows in sorted(grouped.items(), key=lambda item: int(float(item[0]))):
        first = uav_rows[0]
        final = uav_rows[-1]
        summary: Dict[str, object] = {
            "source": str(path),
            "uav_id": int(float(uav_id)),
            "samples": len(uav_rows),
            "first_elapsed_time": parse_float(first.get("elapsed_time")),
            "last_elapsed_time": parse_float(final.get("elapsed_time")),
            "is_finished": parse_bool(final.get("is_finished")),
            "is_hover_stable": parse_bool(final.get("is_hover_stable")),
        }
        for field in METRIC_FIELDS:
            summary[field] = parse_float(final.get(field))
        summaries.append(summary)
    return summaries


def finite_values(rows: List[Dict[str, object]], field: str) -> List[float]:
    values: List[float] = []
    for row in rows:
        value = row.get(field)
        if isinstance(value, (int, float)) and math.isfinite(float(value)):
            values.append(float(value))
    return values


def build_aggregate(rows: List[Dict[str, object]]) -> Dict[str, object]:
    aggregate: Dict[str, object] = {
        "uav_count": len(rows),
        "stable_count": sum(1 for row in rows if row.get("is_hover_stable")),
        "finished_count": sum(1 for row in rows if row.get("is_finished")),
        "metrics": {},
    }
    metrics: Dict[str, Dict[str, float]] = {}
    for field in METRIC_FIELDS:
        values = finite_values(rows, field)
        if values:
            metrics[field] = {
                "mean": mean(values),
                "min": min(values),
                "max": max(values),
            }
        else:
            metrics[field] = {"mean": math.nan, "min": math.nan, "max": math.nan}
    aggregate["metrics"] = metrics
    return aggregate


def write_summary_csv(path: Path, rows: List[Dict[str, object]]) -> None:
    with path.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=SUMMARY_FIELDS)
        writer.writeheader()
        for row in rows:
            writer.writerow({field: row.get(field, "") for field in SUMMARY_FIELDS})


def main() -> int:
    args = parse_args()
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    summaries: List[Dict[str, object]] = []
    for path in discover_csv_files(args.inputs):
        summaries.extend(summarize_file(path))

    if not summaries:
        raise RuntimeError("No trajectory metric rows found")

    write_summary_csv(out_dir / "summary.csv", summaries)
    with (out_dir / "summary.json").open("w") as handle:
        json.dump(build_aggregate(summaries), handle, indent=2, allow_nan=True)

    print(f"Wrote {out_dir / 'summary.csv'}")
    print(f"Wrote {out_dir / 'summary.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
