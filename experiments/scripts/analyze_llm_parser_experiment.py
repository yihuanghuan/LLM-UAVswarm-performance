#!/usr/bin/env python3
"""Summarize and plot experiment 01 results."""

from __future__ import annotations

import argparse
import csv
import json
import math
from collections import defaultdict
from pathlib import Path
from typing import Any, Dict, Iterable, List, Sequence

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402


METHODS = ("plain_json", "few_shot_json", "lfs_schema", "dense_waypoints")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="汇总并绘制实验 01 结果。")
    parser.add_argument("--run-dir", required=True)
    parser.add_argument("--expected-samples", type=int, default=100)
    parser.add_argument("--allow-incomplete", action="store_true")
    return parser.parse_args()


def load_rows(path: Path) -> List[Dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def number(value: Any) -> float | None:
    try:
        parsed = float(str(value).strip())
    except (TypeError, ValueError):
        return None
    return parsed if math.isfinite(parsed) else None


def truth(value: Any) -> bool:
    return str(value).strip().lower() in {"true", "1", "yes"}


def mean(values: Iterable[float]) -> float:
    items = list(values)
    return sum(items) / len(items) if items else float("nan")


def metric_mean(rows: Sequence[Dict[str, str]], name: str) -> float:
    return mean(value for row in rows if (value := number(row.get(name))) is not None)


def summarize(rows: Sequence[Dict[str, str]]) -> List[Dict[str, Any]]:
    summaries = []
    for method in METHODS:
        method_rows = [row for row in rows if row["method"] == method]
        valid_rows = [row for row in method_rows if row["command_type"] != "invalid/ambiguous"]
        invalid_rows = [row for row in method_rows if row["command_type"] == "invalid/ambiguous"]
        summaries.append({
            "method": method,
            "sample_count": len(method_rows),
            "valid_json_rate": mean(float(truth(row["valid_json"])) for row in method_rows),
            "schema_valid_rate": mean(float(truth(row["schema_valid"])) for row in method_rows),
            "field_accuracy": metric_mean(valid_rows, "field_accuracy"),
            "exact_task_accuracy": metric_mean(valid_rows, "exact_task_accuracy"),
            "rejection_accuracy": metric_mean(invalid_rows, "rejection_accuracy"),
            "uav_set_accuracy": metric_mean(valid_rows, "uav_set_accuracy"),
            "formation_accuracy": metric_mean(valid_rows, "formation_accuracy"),
            "center_error": metric_mean(valid_rows, "center_error"),
            "radius_error": metric_mean(valid_rows, "radius_error"),
            "duration_error": metric_mean(valid_rows, "duration_error"),
            "motion_style_accuracy": metric_mean(valid_rows, "motion_style_accuracy"),
            "safety_factor_error": metric_mean(valid_rows, "safety_factor_error"),
            "trigger_accuracy": metric_mean(valid_rows, "trigger_accuracy"),
            "mean_prompt_tokens": metric_mean(method_rows, "prompt_tokens"),
            "mean_completion_tokens": metric_mean(method_rows, "completion_tokens"),
            "mean_latency_ms": metric_mean(method_rows, "latency_ms"),
            "mean_retry_count": metric_mean(method_rows, "retry_count"),
        })
    return summaries


def format_value(value: Any) -> str:
    if isinstance(value, float):
        return "N/A" if math.isnan(value) else f"{value:.4f}"
    return str(value)


def write_summary(run_dir: Path, summaries: Sequence[Dict[str, Any]]) -> None:
    fields = list(summaries[0])
    with (run_dir / "summary_by_method.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, lineterminator="\n")
        writer.writeheader()
        writer.writerows(summaries)
    table_fields = [
        "method", "valid_json_rate", "schema_valid_rate", "field_accuracy",
        "exact_task_accuracy", "rejection_accuracy", "mean_latency_ms",
    ]
    lines = [
        "# Experiment 01 Summary",
        "",
        "| " + " | ".join(table_fields) + " |",
        "| " + " | ".join("---" for _ in table_fields) + " |",
    ]
    for row in summaries:
        lines.append("| " + " | ".join(format_value(row[field]) for field in table_fields) + " |")
    lines.extend([
        "",
        "- Field and exact-task accuracy exclude invalid/ambiguous samples.",
        "- Rejection accuracy is computed only on invalid/ambiguous samples.",
        "- Latency and token counts include retries.",
    ])
    (run_dir / "table_1.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def save(fig: plt.Figure, run_dir: Path, name: str) -> None:
    for suffix in ("png", "pdf"):
        fig.savefig(run_dir / f"{name}.{suffix}", dpi=180, bbox_inches="tight")
    plt.close(fig)


def plot_tokens(run_dir: Path, summaries: Sequence[Dict[str, Any]]) -> None:
    labels = [row["method"] for row in summaries]
    prompt = [row["mean_prompt_tokens"] for row in summaries]
    completion = [row["mean_completion_tokens"] for row in summaries]
    fig, ax = plt.subplots(figsize=(8.5, 4.8))
    ax.bar(labels, prompt, label="Prompt tokens", color="#4C78A8")
    ax.bar(labels, completion, bottom=prompt, label="Completion tokens", color="#F58518")
    ax.set_ylabel("Mean tokens per command")
    ax.set_title("Token Usage by Parsing Method")
    ax.tick_params(axis="x", rotation=20)
    ax.grid(axis="y", alpha=0.25)
    ax.legend()
    fig.tight_layout()
    save(fig, run_dir, "fig_token_comparison")


def plot_latency(run_dir: Path, rows: Sequence[Dict[str, str]]) -> None:
    types = ["simple", "sequential", "grouped", "style-conditioned", "safety-conditioned", "invalid/ambiguous"]
    fig, axes = plt.subplots(2, 3, figsize=(14, 8), sharey=False)
    for ax, command_type in zip(axes.ravel(), types):
        values = [
            [number(row["latency_ms"]) or 0.0 for row in rows if row["method"] == method and row["command_type"] == command_type]
            for method in METHODS
        ]
        ax.boxplot(values, tick_labels=METHODS, showfliers=True)
        ax.set_title(command_type)
        ax.tick_params(axis="x", rotation=35, labelsize=8)
        ax.set_ylabel("Latency (ms)")
        ax.grid(axis="y", alpha=0.25)
    fig.suptitle("Latency Distribution by Command Type", y=1.01)
    fig.tight_layout()
    save(fig, run_dir, "fig_latency_boxplot")


def plot_errors(run_dir: Path, rows: Sequence[Dict[str, str]]) -> None:
    categories = sorted({row["error_type"] for row in rows if row["error_type"]})
    fig, ax = plt.subplots(figsize=(9, 5))
    bottoms = [0] * len(METHODS)
    palette = plt.get_cmap("tab10")
    for index, category in enumerate(categories):
        counts = [sum(row["method"] == method and row["error_type"] == category for row in rows) for method in METHODS]
        ax.bar(METHODS, counts, bottom=bottoms, label=category, color=palette(index % 10))
        bottoms = [left + right for left, right in zip(bottoms, counts)]
    ax.set_title("Error Type Distribution")
    ax.set_ylabel("Count")
    ax.tick_params(axis="x", rotation=20)
    ax.grid(axis="y", alpha=0.25)
    if categories:
        ax.legend(fontsize="small", bbox_to_anchor=(1.02, 1), loc="upper left")
    fig.tight_layout()
    save(fig, run_dir, "fig_error_distribution")


def plot_complexity(run_dir: Path, rows: Sequence[Dict[str, str]]) -> None:
    valid = [row for row in rows if row["command_type"] != "invalid/ambiguous"]
    fig, ax = plt.subplots(figsize=(8.5, 4.8))
    for method in METHODS:
        x_values, y_values = [], []
        for complexity in range(1, 6):
            group = [row for row in valid if row["method"] == method and int(row["complexity"]) == complexity]
            if group:
                x_values.append(complexity)
                y_values.append(metric_mean(group, "exact_task_accuracy"))
        ax.plot(x_values, y_values, marker="o", label=method)
    ax.set_xticks(range(1, 6))
    ax.set_ylim(-0.03, 1.03)
    ax.set_xlabel("Annotated command complexity")
    ax.set_ylabel("Exact task success rate")
    ax.set_title("Command Complexity vs Parsing Success")
    ax.grid(alpha=0.25)
    ax.legend()
    fig.tight_layout()
    save(fig, run_dir, "fig_complexity_success")


def validate_completeness(rows: Sequence[Dict[str, str]], expected: int) -> List[str]:
    problems = []
    keys = [(row["command_id"], row["method"]) for row in rows]
    if len(keys) != len(set(keys)):
        problems.append("存在重复的 command_id/method")
    for method in METHODS:
        count = sum(row["method"] == method for row in rows)
        if count != expected:
            problems.append(f"{method} 结果数为 {count}，期望 {expected}")
    infrastructure_failures = sum(row.get("error_type") in {"api_error", "quota_exhausted"} for row in rows)
    if rows and infrastructure_failures / len(rows) > 0.05:
        problems.append(f"最终结果基础设施失败率为 {infrastructure_failures / len(rows):.2%}，超过 5%")
    return problems


def validate_raw_attempts(rows: Sequence[Dict[str, str]], raw_path: Path) -> tuple[List[str], int]:
    problems: List[str] = []
    attempts: Dict[tuple[str, str], List[Dict[str, Any]]] = defaultdict(list)
    with raw_path.open(encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            try:
                attempt = json.loads(line)
            except json.JSONDecodeError:
                problems.append(f"raw_attempts.jsonl 第 {line_number} 行不是合法 JSON")
                continue
            attempts[(attempt.get("command_id", ""), attempt.get("method", ""))].append(attempt)
    for row in rows:
        key = (row["command_id"], row["method"])
        history = attempts.get(key, [])
        if not history:
            problems.append(f"{key} 缺少原始尝试记录")
            continue
        last_start = max(index for index, attempt in enumerate(history) if int(attempt.get("attempt", 0)) == 1)
        final_session = history[last_start:]
        expected_attempts = int(float(row["retry_count"])) + 1
        if len(final_session) != expected_attempts:
            problems.append(f"{key} 最终尝试数 {len(final_session)} 与结果 {expected_attempts} 不一致")
        if truth(final_session[-1].get("schema_valid")) != truth(row.get("schema_valid")):
            problems.append(f"{key} 原始记录与结果的 schema_valid 不一致")
    return problems, sum(len(history) for history in attempts.values())


def main() -> int:
    args = parse_args()
    run_dir = Path(args.run_dir)
    rows = load_rows(run_dir / "sample_results.csv")
    problems = validate_completeness(rows, args.expected_samples)
    raw_problems, raw_attempt_count = validate_raw_attempts(rows, run_dir / "raw_attempts.jsonl")
    problems.extend(raw_problems)
    if problems and not args.allow_incomplete:
        raise ValueError("；".join(problems))
    summaries = summarize(rows)
    write_summary(run_dir, summaries)
    plot_tokens(run_dir, summaries)
    plot_latency(run_dir, rows)
    plot_errors(run_dir, rows)
    plot_complexity(run_dir, rows)
    (run_dir / "analysis_manifest.json").write_text(json.dumps({
        "row_count": len(rows),
        "raw_attempt_count": raw_attempt_count,
        "expected_samples_per_method": args.expected_samples,
        "problems": problems,
        "generated_files": [
            "summary_by_method.csv", "table_1.md", "fig_token_comparison.png/pdf",
            "fig_latency_boxplot.png/pdf", "fig_error_distribution.png/pdf",
            "fig_complexity_success.png/pdf",
        ],
    }, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"分析完成：{run_dir}")
    if problems:
        print("警告：" + "；".join(problems))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
