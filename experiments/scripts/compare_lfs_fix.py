#!/usr/bin/env python3
"""Compare the selective LFS accuracy rerun against experiment 01 baseline."""

from __future__ import annotations

import argparse
import csv
from collections import defaultdict
from pathlib import Path
from typing import Any, Dict, Iterable, List, Sequence


METRICS = [
    "schema_valid",
    "field_accuracy",
    "exact_task_accuracy",
    "uav_set_accuracy",
    "formation_accuracy",
    "motion_style_accuracy",
    "trigger_accuracy",
    "safety_factor_error",
    "latency_ms",
    "prompt_tokens",
    "completion_tokens",
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="比较 LFS 修正前后的选择性重测结果。")
    parser.add_argument("--baseline-csv", required=True)
    parser.add_argument("--rerun-csv", required=True)
    parser.add_argument("--output-dir", required=True)
    return parser.parse_args()


def read_rows(path: Path) -> List[Dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def numeric(value: Any) -> float | None:
    try:
        return float(str(value).strip())
    except (TypeError, ValueError):
        return None


def mean(values: Iterable[float]) -> float:
    items = list(values)
    return sum(items) / len(items) if items else 0.0


def metric_mean(rows: Sequence[Dict[str, str]], metric: str) -> float:
    return mean(value for row in rows if (value := numeric(row.get(metric))) is not None)


def main() -> int:
    args = parse_args()
    baseline_rows = [row for row in read_rows(Path(args.baseline_csv)) if row["method"] == "lfs_schema"]
    rerun_rows = read_rows(Path(args.rerun_csv))
    if not rerun_rows or any(row["method"] != "lfs_schema" for row in rerun_rows):
        raise ValueError("重测结果必须只包含 lfs_schema")
    if len({row["command_id"] for row in rerun_rows}) != len(rerun_rows):
        raise ValueError("重测结果存在重复 command_id")

    baseline_by_id = {row["command_id"]: row for row in baseline_rows}
    missing = sorted({row["command_id"] for row in rerun_rows} - set(baseline_by_id))
    if missing:
        raise ValueError(f"基线中缺少重测样本: {missing}")

    comparison: List[Dict[str, Any]] = []
    for rerun in sorted(rerun_rows, key=lambda row: row["command_id"]):
        baseline = baseline_by_id[rerun["command_id"]]
        row: Dict[str, Any] = {
            "command_id": rerun["command_id"],
            "command_type": rerun["command_type"],
            "before_error_type": baseline["error_type"],
            "after_error_type": rerun["error_type"],
        }
        for metric in METRICS:
            row[f"before_{metric}"] = baseline[metric]
            row[f"after_{metric}"] = rerun[metric]
        comparison.append(row)

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    fields = list(comparison[0])
    with (output_dir / "lfs_fix_comparison.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, lineterminator="\n")
        writer.writeheader()
        writer.writerows(comparison)

    grouped: Dict[str, List[Dict[str, str]]] = defaultdict(list)
    for row in rerun_rows:
        grouped[row["command_type"]].append(row)
    lines = [
        "# LFS Fix Selective Rerun",
        "",
        f"Retested commands: {len(rerun_rows)}",
        "",
        "| Scope | Count | Before field accuracy | After field accuracy | Before exact | After exact | Before trigger | After trigger |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    scopes = [("all", rerun_rows)] + sorted(grouped.items())
    for scope, after_rows in scopes:
        ids = {row["command_id"] for row in after_rows}
        before_rows = [baseline_by_id[sample_id] for sample_id in ids]
        lines.append(
            f"| {scope} | {len(after_rows)} | {metric_mean(before_rows, 'field_accuracy'):.4f} | "
            f"{metric_mean(after_rows, 'field_accuracy'):.4f} | "
            f"{metric_mean(before_rows, 'exact_task_accuracy'):.4f} | "
            f"{metric_mean(after_rows, 'exact_task_accuracy'):.4f} | "
            f"{metric_mean(before_rows, 'trigger_accuracy'):.4f} | "
            f"{metric_mean(after_rows, 'trigger_accuracy'):.4f} |"
        )
    lines.extend([
        "",
        "The rerun contains only commands affected by deterministic LFS canonicalization, "
        "transition derivation, enum normalization, safety grounding, and LFS few-shot changes.",
        "The original 400-row experiment remains unchanged.",
    ])
    (output_dir / "lfs_fix_summary.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"比较完成: {output_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
