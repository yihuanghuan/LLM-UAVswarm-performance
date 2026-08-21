#!/usr/bin/env python3
"""汇总不同 IAPF 配置下的安全、轨迹和任务指标。"""

from __future__ import annotations

import argparse
import csv
import math
import statistics
from pathlib import Path
from typing import Dict, Iterable, List, Sequence


REPO_ROOT = Path(__file__).resolve().parents[2]

METHODS = [
    "no_iapf",
    "iapf_position_only",
    "iapf_position_accel",
    "safety_assignment_plus_iapf",
]

RESULT_FIELDS = [
    "method",
    "num_trials",
    "min_inter_agent_distance",
    "mean_min_distance",
    "safety_violation_count",
    "near_miss_duration",
    "mean_integrated_squared_jerk",
    "mean_final_error",
    "mission_success_rate",
    "mean_completion_time",
]

METHOD_KEYS = ["method", "iapf_method", "experiment_id", "condition"]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="汇总 IAPF 对比实验 CSV。")
    parser.add_argument(
        "--pairwise",
        default=str(REPO_ROOT / "experiments" / "results" / "pairwise_distance_summary.csv"),
        help="pairwise_distance_summary.csv 路径。",
    )
    parser.add_argument(
        "--trajectory",
        default=str(REPO_ROOT / "experiments" / "results" / "trajectory_profile_results.csv"),
        help="轨迹指标 CSV 路径。",
    )
    parser.add_argument(
        "--mission",
        default=str(REPO_ROOT / "experiments" / "results" / "mission_summary.csv"),
        help="任务结果 CSV 路径。",
    )
    parser.add_argument(
        "--output",
        default=str(REPO_ROOT / "experiments" / "results" / "iapf_summary.csv"),
        help="输出 CSV 路径。",
    )
    return parser.parse_args()


def read_optional_csv(path: Path) -> List[Dict[str, str]]:
    if not path.is_file():
        return []
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def parse_float(value: object) -> float | None:
    try:
        parsed = float(str(value).strip())
    except (TypeError, ValueError):
        return None
    return parsed if math.isfinite(parsed) else None


def parse_bool(value: object) -> bool | None:
    if value is None:
        return None
    text = str(value).strip().lower()
    if text in {"1", "true", "yes", "success", "succeeded", "completed"}:
        return True
    if text in {"0", "false", "no", "failed", "failure"}:
        return False
    return None


def row_method(row: Dict[str, str]) -> str | None:
    for key in METHOD_KEYS:
        value = row.get(key)
        if value:
            return value.strip()
    return None


def rows_for_method(rows: Sequence[Dict[str, str]], method: str) -> List[Dict[str, str]]:
    return [row for row in rows if row_method(row) == method]


def values(rows: Iterable[Dict[str, str]], *keys: str) -> List[float]:
    parsed: List[float] = []
    for row in rows:
        for key in keys:
            value = parse_float(row.get(key))
            if value is not None:
                parsed.append(value)
                break
    return parsed


def min_or_blank(items: List[float]) -> str:
    return f"{min(items):.6f}" if items else ""


def mean_or_blank(items: List[float]) -> str:
    return f"{statistics.fmean(items):.6f}" if items else ""


def sum_or_blank(items: List[float]) -> str:
    return f"{sum(items):.6f}" if items else ""


def sum_count_or_blank(items: List[float]) -> str:
    return str(int(round(sum(items)))) if items else ""


def success_rate(rows: Sequence[Dict[str, str]]) -> str:
    outcomes: List[bool] = []
    for row in rows:
        for key in ("mission_success", "success", "completed", "is_success"):
            parsed = parse_bool(row.get(key))
            if parsed is not None:
                outcomes.append(parsed)
                break
    if not outcomes:
        return ""
    return f"{sum(1 for item in outcomes if item) / len(outcomes):.6f}"


def summarize_method(
    method: str,
    pairwise_rows: Sequence[Dict[str, str]],
    trajectory_rows: Sequence[Dict[str, str]],
    mission_rows: Sequence[Dict[str, str]],
) -> Dict[str, str]:
    pairwise = rows_for_method(pairwise_rows, method)
    trajectory = rows_for_method(trajectory_rows, method)
    mission = rows_for_method(mission_rows, method)
    trial_count = max(len(pairwise), len(trajectory), len(mission))

    return {
        "method": method,
        "num_trials": str(trial_count),
        "min_inter_agent_distance": min_or_blank(
            values(pairwise, "min_inter_agent_distance", "min_distance", "min_distance_m")
        ),
        "mean_min_distance": mean_or_blank(values(pairwise, "mean_min_distance", "mean_distance")),
        "safety_violation_count": sum_count_or_blank(values(pairwise, "safety_violation_count")),
        "near_miss_duration": sum_or_blank(
            values(pairwise, "near_miss_duration", "near_miss_duration_s")
        ),
        "mean_integrated_squared_jerk": mean_or_blank(
            values(trajectory, "integrated_squared_jerk", "mean_integrated_squared_jerk")
        ),
        "mean_final_error": mean_or_blank(
            values(trajectory, "final_error", "final_position_error", "mean_final_error")
        ),
        "mission_success_rate": success_rate(mission),
        "mean_completion_time": mean_or_blank(
            values(mission, "completion_time", "completion_time_s", "mission_time", "duration")
        ),
    }


def write_results(rows: List[Dict[str, str]], output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=RESULT_FIELDS)
        writer.writeheader()
        writer.writerows(rows)


def main() -> int:
    args = parse_args()
    pairwise_rows = read_optional_csv(Path(args.pairwise))
    trajectory_rows = read_optional_csv(Path(args.trajectory))
    mission_rows = read_optional_csv(Path(args.mission))

    if not pairwise_rows and not trajectory_rows and not mission_rows:
        raise FileNotFoundError("未找到任何 IAPF 输入 CSV，请至少提供 pairwise、trajectory 或 mission 之一")

    rows = [
        summarize_method(method, pairwise_rows, trajectory_rows, mission_rows)
        for method in METHODS
    ]
    write_results(rows, Path(args.output))
    print(f"已写入 IAPF 汇总: {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
