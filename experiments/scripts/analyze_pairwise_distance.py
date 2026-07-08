#!/usr/bin/env python3
"""Analyze pairwise UAV distances from odometry CSV files.

Supported inputs include CSV files exported from:

* ros2 topic echo --csv /uavN/odom
* tools/trajectory_metrics/rosbag_to_csv.py with /uav*/odom topics

The script writes:

* min_distance.csv
* pairwise_distance_plot.pdf
* safety_violation_summary.csv
"""

from __future__ import annotations

import argparse
import csv
import math
import re
from dataclasses import dataclass
from itertools import combinations
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence, Tuple


POSITION_ALIASES = {
    "x": ("x", "position_x", "pose_position_x", "point_x", "target_pos_x"),
    "y": ("y", "position_y", "pose_position_y", "point_y", "target_pos_y"),
    "z": ("z", "position_z", "pose_position_z", "point_z", "target_pos_z"),
}


@dataclass(frozen=True)
class OdomSample:
    time_s: float
    x: float
    y: float
    z: float


@dataclass(frozen=True)
class DistanceSample:
    time_s: float
    uav_a: int
    uav_b: int
    distance_m: float


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Analyze inter-agent distance metrics from UAV odometry CSV files."
    )
    parser.add_argument(
        "inputs",
        nargs="+",
        help="CSV files or directories containing CSV files.",
    )
    parser.add_argument(
        "--out-dir",
        default="pairwise_distance_analysis",
        help="Directory for CSV/PDF outputs.",
    )
    parser.add_argument(
        "--safety-distance",
        type=float,
        default=1.5,
        help="Distance below which a pair is counted as a safety violation.",
    )
    parser.add_argument(
        "--near-miss-distance",
        type=float,
        default=None,
        help="Distance below which a pair is counted as a near miss. Defaults to 1.5x safety distance.",
    )
    return parser.parse_args()


def normalize_key(key: str) -> str:
    key = key.strip()
    if key.startswith("/"):
        key = key[1:]
    return re.sub(r"[^A-Za-z0-9_]+", "_", key).strip("_").lower()


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


def parse_float(value: object) -> float:
    if value is None:
        return math.nan
    if isinstance(value, (int, float)):
        return float(value)
    text = str(value).strip()
    if not text:
        return math.nan
    try:
        return float(text)
    except ValueError:
        return math.nan


def first_number(row: Dict[str, str], keys: Sequence[str]) -> float:
    for key in keys:
        value = parse_float(row.get(key))
        if math.isfinite(value):
            return value
    return math.nan


def infer_uav_id(path: Path, row: Dict[str, str]) -> Optional[int]:
    for key in ("uav_id", "uav", "id"):
        value = parse_float(row.get(key))
        if math.isfinite(value):
            return int(value)

    topic = row.get("topic", "") or row.get("name", "")
    match = re.search(r"uav[_/-]?(\d+)", topic, flags=re.IGNORECASE)
    if match:
        return int(match.group(1))

    match = re.search(r"uav[_-]?(\d+)", str(path), flags=re.IGNORECASE)
    if match:
        return int(match.group(1))
    return None


def row_time_s(row: Dict[str, str], sample_index: int) -> float:
    bag_time_ns = parse_float(row.get("bag_time_ns"))
    if math.isfinite(bag_time_ns):
        return bag_time_ns * 1e-9

    stamp_sec = parse_float(row.get("header_stamp_sec"))
    stamp_nanosec = parse_float(row.get("header_stamp_nanosec"))
    if math.isfinite(stamp_sec):
        return stamp_sec + (stamp_nanosec if math.isfinite(stamp_nanosec) else 0.0) * 1e-9

    time_s = first_number(row, ("time_s", "time", "stamp", "elapsed_time"))
    if math.isfinite(time_s):
        return time_s

    timestamp = first_number(row, ("timestamp", "timestamp_sample"))
    if math.isfinite(timestamp):
        if timestamp > 1e12:
            return timestamp * 1e-9
        if timestamp > 1e6:
            return timestamp * 1e-6
        return timestamp

    return float(sample_index)


def read_csv_rows(path: Path) -> List[Dict[str, str]]:
    with path.open(newline="") as handle:
        reader = csv.DictReader(handle)
        if not reader.fieldnames:
            return []
        rows: List[Dict[str, str]] = []
        for row in reader:
            rows.append({
                normalize_key(key): value
                for key, value in row.items()
                if key is not None
            })
    return rows


def extract_position(row: Dict[str, str]) -> Optional[Tuple[float, float, float]]:
    values = []
    for axis in ("x", "y", "z"):
        value = first_number(row, POSITION_ALIASES[axis])
        if not math.isfinite(value):
            return None
        values.append(value)
    return values[0], values[1], values[2]


def load_odom_samples(files: Sequence[Path]) -> Dict[int, List[OdomSample]]:
    samples: Dict[int, List[OdomSample]] = {}
    for path in files:
        rows = read_csv_rows(path)
        for sample_index, row in enumerate(rows):
            position = extract_position(row)
            if position is None:
                continue
            uav_id = infer_uav_id(path, row)
            if uav_id is None:
                continue
            x, y, z = position
            samples.setdefault(uav_id, []).append(
                OdomSample(row_time_s(row, sample_index), x, y, z)
            )

    for uav_id in list(samples):
        samples[uav_id] = sorted(samples[uav_id], key=lambda item: item.time_s)
        if not samples[uav_id]:
            del samples[uav_id]

    if len(samples) < 2:
        raise RuntimeError(
            "Need odometry CSV data for at least two UAVs. "
            "Ensure filenames or rows include uav{id} or a uav_id column."
        )
    return samples


def distance(a: OdomSample, b: OdomSample) -> float:
    return math.sqrt(
        (a.x - b.x) * (a.x - b.x)
        + (a.y - b.y) * (a.y - b.y)
        + (a.z - b.z) * (a.z - b.z)
    )


def aligned_distances(samples: Dict[int, List[OdomSample]]) -> List[DistanceSample]:
    uav_ids = sorted(samples)
    all_times = sorted({sample.time_s for values in samples.values() for sample in values})
    indices = {uav_id: 0 for uav_id in uav_ids}
    latest: Dict[int, OdomSample] = {}
    distances: List[DistanceSample] = []

    for time_s in all_times:
        for uav_id in uav_ids:
            values = samples[uav_id]
            while indices[uav_id] < len(values) and values[indices[uav_id]].time_s <= time_s:
                latest[uav_id] = values[indices[uav_id]]
                indices[uav_id] += 1

        if len(latest) < len(uav_ids):
            continue

        for uav_a, uav_b in combinations(uav_ids, 2):
            distances.append(
                DistanceSample(
                    time_s,
                    uav_a,
                    uav_b,
                    distance(latest[uav_a], latest[uav_b]),
                )
            )
    return distances


def write_min_distance(distances: Sequence[DistanceSample], out_path: Path) -> None:
    by_time: Dict[float, DistanceSample] = {}
    for item in distances:
        current = by_time.get(item.time_s)
        if current is None or item.distance_m < current.distance_m:
            by_time[item.time_s] = item

    with out_path.open("w", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=["time_s", "uav_a", "uav_b", "min_distance_m"],
        )
        writer.writeheader()
        for time_s in sorted(by_time):
            item = by_time[time_s]
            writer.writerow({
                "time_s": f"{item.time_s:.6f}",
                "uav_a": item.uav_a,
                "uav_b": item.uav_b,
                "min_distance_m": f"{item.distance_m:.6f}",
            })


def estimate_duration(samples: Sequence[DistanceSample]) -> float:
    if len(samples) < 2:
        return 0.0
    duration = 0.0
    for previous, current in zip(samples, samples[1:]):
        duration += max(0.0, current.time_s - previous.time_s)
    return duration


def write_summary(
    distances: Sequence[DistanceSample],
    out_path: Path,
    safety_distance: float,
    near_miss_distance: float,
) -> None:
    by_pair: Dict[Tuple[int, int], List[DistanceSample]] = {}
    for item in distances:
        by_pair.setdefault((item.uav_a, item.uav_b), []).append(item)

    fieldnames = [
        "scope",
        "uav_a",
        "uav_b",
        "samples",
        "min_distance_m",
        "safety_distance_m",
        "safety_violation_count",
        "safety_violation_duration_s",
        "near_miss_distance_m",
        "near_miss_count",
        "near_miss_duration_s",
    ]

    rows: List[Dict[str, object]] = []
    total_violations = 0
    total_near_misses = 0
    total_violation_duration = 0.0
    total_near_miss_duration = 0.0
    global_min = math.inf

    for (uav_a, uav_b), values in sorted(by_pair.items()):
        values = sorted(values, key=lambda item: item.time_s)
        min_distance = min(item.distance_m for item in values)
        violations = [item for item in values if item.distance_m < safety_distance]
        near_misses = [item for item in values if item.distance_m < near_miss_distance]
        violation_duration = estimate_duration(violations)
        near_miss_duration = estimate_duration(near_misses)

        total_violations += len(violations)
        total_near_misses += len(near_misses)
        total_violation_duration += violation_duration
        total_near_miss_duration += near_miss_duration
        global_min = min(global_min, min_distance)

        rows.append({
            "scope": "pair",
            "uav_a": uav_a,
            "uav_b": uav_b,
            "samples": len(values),
            "min_distance_m": f"{min_distance:.6f}",
            "safety_distance_m": f"{safety_distance:.6f}",
            "safety_violation_count": len(violations),
            "safety_violation_duration_s": f"{violation_duration:.6f}",
            "near_miss_distance_m": f"{near_miss_distance:.6f}",
            "near_miss_count": len(near_misses),
            "near_miss_duration_s": f"{near_miss_duration:.6f}",
        })

    rows.insert(0, {
        "scope": "all",
        "uav_a": "",
        "uav_b": "",
        "samples": len(distances),
        "min_distance_m": f"{global_min:.6f}",
        "safety_distance_m": f"{safety_distance:.6f}",
        "safety_violation_count": total_violations,
        "safety_violation_duration_s": f"{total_violation_duration:.6f}",
        "near_miss_distance_m": f"{near_miss_distance:.6f}",
        "near_miss_count": total_near_misses,
        "near_miss_duration_s": f"{total_near_miss_duration:.6f}",
    })

    with out_path.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def write_plot(
    distances: Sequence[DistanceSample],
    out_path: Path,
    safety_distance: float,
    near_miss_distance: float,
) -> None:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    by_pair: Dict[Tuple[int, int], List[DistanceSample]] = {}
    for item in distances:
        by_pair.setdefault((item.uav_a, item.uav_b), []).append(item)

    fig, ax = plt.subplots(figsize=(11, 6))
    for (uav_a, uav_b), values in sorted(by_pair.items()):
        values = sorted(values, key=lambda item: item.time_s)
        start = values[0].time_s
        ax.plot(
            [item.time_s - start for item in values],
            [item.distance_m for item in values],
            label=f"UAV{uav_a}-UAV{uav_b}",
            linewidth=1.2,
        )

    ax.axhline(safety_distance, color="red", linestyle="--", linewidth=1.0, label="safety")
    ax.axhline(near_miss_distance, color="orange", linestyle=":", linewidth=1.0, label="near miss")
    ax.set_xlabel("Time (s)")
    ax.set_ylabel("Distance (m)")
    ax.set_title("Pairwise UAV Distance")
    ax.grid(True, alpha=0.25)
    ax.legend(loc="best", fontsize="small", ncol=2)
    fig.tight_layout()
    fig.savefig(out_path)
    plt.close(fig)


def main() -> int:
    args = parse_args()
    safety_distance = args.safety_distance
    near_miss_distance = (
        args.near_miss_distance
        if args.near_miss_distance is not None
        else safety_distance * 1.5
    )
    if safety_distance <= 0.0:
        raise ValueError("--safety-distance must be positive")
    if near_miss_distance < safety_distance:
        raise ValueError("--near-miss-distance must be greater than or equal to --safety-distance")

    files = discover_csv_files(args.inputs)
    samples = load_odom_samples(files)
    distances = aligned_distances(samples)
    if not distances:
        raise RuntimeError("No aligned samples found across UAV odometry CSV files")

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    write_min_distance(distances, out_dir / "min_distance.csv")
    write_summary(
        distances,
        out_dir / "safety_violation_summary.csv",
        safety_distance,
        near_miss_distance,
    )
    write_plot(
        distances,
        out_dir / "pairwise_distance_plot.pdf",
        safety_distance,
        near_miss_distance,
    )

    print(f"Loaded {sum(len(values) for values in samples.values())} samples from {len(samples)} UAVs")
    print(f"Wrote outputs to {out_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
