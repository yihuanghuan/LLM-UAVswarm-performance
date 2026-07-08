#!/usr/bin/env python3
"""根据 odom CSV 计算无人机两两距离和安全阈值统计。"""

from __future__ import annotations

import argparse
import csv
import math
from dataclasses import dataclass
from itertools import combinations
from pathlib import Path
from typing import Dict, Iterable, List, Sequence


REPO_ROOT = Path(__file__).resolve().parents[2]

TIMESERIES_FIELDS = [
    "experiment_id",
    "timestamp",
    "uav_a",
    "uav_b",
    "distance",
]

SUMMARY_FIELDS = [
    "experiment_id",
    "num_uav",
    "min_inter_agent_distance",
    "mean_min_distance",
    "safety_threshold",
    "safety_violation_count",
    "near_miss_duration",
    "closest_pair",
]


@dataclass(frozen=True)
class OdomSample:
    timestamp: float
    uav_id: int
    x: float
    y: float
    z: float


@dataclass(frozen=True)
class DistanceSample:
    timestamp: float
    uav_a: int
    uav_b: int
    distance: float


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="分析 timestamp,uav_id,x,y,z 格式 odom CSV 的机间距离。")
    parser.add_argument(
        "--input",
        required=True,
        help="输入 odom CSV，字段必须包含 timestamp,uav_id,x,y,z。",
    )
    parser.add_argument(
        "--output-dir",
        default=str(REPO_ROOT / "experiments" / "results"),
        help="输出目录。",
    )
    parser.add_argument("--safety-threshold", type=float, default=1.5, help="安全距离阈值。")
    parser.add_argument("--experiment-id", default="exp001", help="实验编号。")
    parser.add_argument(
        "--time-bin",
        type=float,
        default=0.05,
        help="时间同步分箱宽度，单位秒；设为 0 时按原始 timestamp 精确分组。",
    )
    return parser.parse_args()


def parse_float(value: object, field: str, row_number: int) -> float:
    try:
        parsed = float(str(value).strip())
    except (TypeError, ValueError) as exc:
        raise ValueError(f"第 {row_number} 行字段 {field} 不是有效数字: {value}") from exc
    if not math.isfinite(parsed):
        raise ValueError(f"第 {row_number} 行字段 {field} 不是有限数字: {value}")
    return parsed


def read_odom(path: Path) -> List[OdomSample]:
    if not path.is_file():
        raise FileNotFoundError(f"输入文件不存在: {path}")

    with path.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        fieldnames = set(reader.fieldnames or [])
        required = {"timestamp", "uav_id", "x", "y", "z"}
        missing = sorted(required - fieldnames)
        if missing:
            raise ValueError(f"输入 CSV 缺少字段: {', '.join(missing)}")

        samples: List[OdomSample] = []
        for row_number, row in enumerate(reader, start=2):
            samples.append(
                OdomSample(
                    timestamp=parse_float(row.get("timestamp"), "timestamp", row_number),
                    uav_id=int(parse_float(row.get("uav_id"), "uav_id", row_number)),
                    x=parse_float(row.get("x"), "x", row_number),
                    y=parse_float(row.get("y"), "y", row_number),
                    z=parse_float(row.get("z"), "z", row_number),
                )
            )

    if not samples:
        raise ValueError("输入 CSV 没有数据行")
    if len({sample.uav_id for sample in samples}) < 2:
        raise ValueError("至少需要两个 UAV 的 odom 数据")
    return samples


def distance(a: OdomSample, b: OdomSample) -> float:
    return math.sqrt((a.x - b.x) ** 2 + (a.y - b.y) ** 2 + (a.z - b.z) ** 2)


def timestamp_key(timestamp: float, time_bin: float) -> float:
    if time_bin > 0.0:
        return round(timestamp / time_bin) * time_bin
    return timestamp


def grouped_by_timestamp(samples: Sequence[OdomSample], time_bin: float) -> Dict[float, Dict[int, OdomSample]]:
    grouped: Dict[float, Dict[int, OdomSample]] = {}
    for sample in samples:
        grouped.setdefault(timestamp_key(sample.timestamp, time_bin), {})[sample.uav_id] = sample
    return grouped


def compute_distances(samples: Sequence[OdomSample], time_bin: float) -> List[DistanceSample]:
    distances: List[DistanceSample] = []
    for timestamp, by_uav in sorted(grouped_by_timestamp(samples, time_bin).items()):
        if len(by_uav) < 2:
            continue
        for uav_a, uav_b in combinations(sorted(by_uav), 2):
            distances.append(
                DistanceSample(
                    timestamp=timestamp,
                    uav_a=uav_a,
                    uav_b=uav_b,
                    distance=distance(by_uav[uav_a], by_uav[uav_b]),
                )
            )
    if not distances:
        raise ValueError("没有找到同一 timestamp 下的两机样本，无法计算两两距离")
    return distances


def timestamp_minima(distances: Sequence[DistanceSample]) -> List[DistanceSample]:
    by_time: Dict[float, DistanceSample] = {}
    for sample in distances:
        current = by_time.get(sample.timestamp)
        if current is None or sample.distance < current.distance:
            by_time[sample.timestamp] = sample
    return [by_time[timestamp] for timestamp in sorted(by_time)]


def estimate_violation_duration(minima: Sequence[DistanceSample], threshold: float) -> float:
    if len(minima) < 2:
        return 0.0
    duration = 0.0
    for current, following in zip(minima, minima[1:]):
        if current.distance < threshold:
            duration += max(0.0, following.timestamp - current.timestamp)
    return duration


def write_timeseries(path: Path, experiment_id: str, distances: Iterable[DistanceSample]) -> None:
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=TIMESERIES_FIELDS)
        writer.writeheader()
        for sample in distances:
            writer.writerow({
                "experiment_id": experiment_id,
                "timestamp": f"{sample.timestamp:.6f}",
                "uav_a": sample.uav_a,
                "uav_b": sample.uav_b,
                "distance": f"{sample.distance:.6f}",
            })


def write_summary(
    path: Path,
    experiment_id: str,
    num_uav: int,
    distances: Sequence[DistanceSample],
    safety_threshold: float,
) -> None:
    minima = timestamp_minima(distances)
    closest = min(distances, key=lambda item: item.distance)
    violation_count = sum(1 for item in distances if item.distance < safety_threshold)
    mean_min_distance = sum(item.distance for item in minima) / len(minima)

    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=SUMMARY_FIELDS)
        writer.writeheader()
        writer.writerow({
            "experiment_id": experiment_id,
            "num_uav": num_uav,
            "min_inter_agent_distance": f"{closest.distance:.6f}",
            "mean_min_distance": f"{mean_min_distance:.6f}",
            "safety_threshold": f"{safety_threshold:.6f}",
            "safety_violation_count": violation_count,
            "near_miss_duration": f"{estimate_violation_duration(minima, safety_threshold):.6f}",
            "closest_pair": f"{closest.uav_a}-{closest.uav_b}",
        })


def main() -> int:
    args = parse_args()
    if args.safety_threshold <= 0.0:
        raise ValueError("--safety-threshold 必须大于 0")
    if args.time_bin < 0.0:
        raise ValueError("--time-bin 不能小于 0")

    samples = read_odom(Path(args.input))
    distances = compute_distances(samples, args.time_bin)
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    write_timeseries(output_dir / "pairwise_distance_timeseries.csv", args.experiment_id, distances)
    write_summary(
        output_dir / "pairwise_distance_summary.csv",
        args.experiment_id,
        len({sample.uav_id for sample in samples}),
        distances,
        args.safety_threshold,
    )
    print(f"已写入两两距离时序和汇总结果: {output_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
