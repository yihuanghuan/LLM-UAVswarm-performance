#!/usr/bin/env python3
"""按 motion_style 汇总语义条件 LADRC 控制适应日志。"""

from __future__ import annotations

import argparse
import csv
import math
import statistics
from collections import defaultdict
from pathlib import Path
from typing import Dict, Iterable, List


REPO_ROOT = Path(__file__).resolve().parents[2]

METRICS = [
    "gain_multiplier",
    "peak_velocity",
    "peak_acceleration",
    "settling_time",
    "tracking_rmse",
]

RESULT_FIELDS = [
    "motion_style",
    "num_trials",
    "mean_gain_multiplier",
    "std_gain_multiplier",
    "mean_peak_velocity",
    "std_peak_velocity",
    "mean_peak_acceleration",
    "std_peak_acceleration",
    "mean_settling_time",
    "std_settling_time",
    "mean_tracking_rmse",
    "std_tracking_rmse",
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="汇总 semantic-conditioned control adaptation CSV。")
    parser.add_argument(
        "--input",
        default=str(REPO_ROOT / "logs" / "control_adaptation_log.csv"),
        help="输入控制适应日志 CSV。",
    )
    parser.add_argument(
        "--output",
        default=str(REPO_ROOT / "experiments" / "results" / "semantic_control_summary.csv"),
        help="输出 CSV 路径。",
    )
    return parser.parse_args()


def parse_float(value: object) -> float | None:
    try:
        parsed = float(str(value).strip())
    except (TypeError, ValueError):
        return None
    return parsed if math.isfinite(parsed) else None


def read_rows(path: Path) -> List[Dict[str, str]]:
    if not path.is_file():
        raise FileNotFoundError(f"输入文件不存在: {path}")
    with path.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        fields = set(reader.fieldnames or [])
        required = {"motion_style", *METRICS}
        missing = sorted(required - fields)
        if missing:
            raise ValueError(f"控制适应日志缺少字段: {', '.join(missing)}")
        return list(reader)


def mean(values: List[float]) -> float:
    return statistics.fmean(values) if values else 0.0


def std(values: List[float]) -> float:
    return statistics.stdev(values) if len(values) > 1 else 0.0


def format_float(value: float) -> str:
    return f"{value:.6f}"


def summarize(rows: Iterable[Dict[str, str]]) -> List[Dict[str, str]]:
    grouped: Dict[str, List[Dict[str, str]]] = defaultdict(list)
    for row in rows:
        style = (row.get("motion_style") or "unknown").strip() or "unknown"
        grouped[style].append(row)

    summary: List[Dict[str, str]] = []
    for style in sorted(grouped):
        style_rows = grouped[style]
        result = {
            "motion_style": style,
            "num_trials": str(len(style_rows)),
        }
        for metric in METRICS:
            values = [
                value
                for value in (parse_float(row.get(metric)) for row in style_rows)
                if value is not None
            ]
            result[f"mean_{metric}"] = format_float(mean(values))
            result[f"std_{metric}"] = format_float(std(values))
        summary.append(result)
    return summary


def write_results(rows: List[Dict[str, str]], output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=RESULT_FIELDS)
        writer.writeheader()
        writer.writerows(rows)


def main() -> int:
    args = parse_args()
    rows = read_rows(Path(args.input))
    if not rows:
        raise ValueError("控制适应日志没有数据行")
    summary = summarize(rows)
    write_results(summary, Path(args.output))
    print(f"已写入 {len(summary)} 行语义控制汇总: {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
