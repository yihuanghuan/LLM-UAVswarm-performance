#!/usr/bin/env python3
"""Plot the fixed LFS result against the three experiment-01 baselines."""

from __future__ import annotations

import argparse
import csv
import json
import math
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Dict, Iterable, List, Sequence

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402


METHODS = ("plain_json", "few_shot_json", "lfs_schema", "dense_waypoints")
METHOD_LABELS = {
    "plain_json": "Plain JSON",
    "few_shot_json": "Few-shot JSON",
    "lfs_schema": "LFS + Schema (fixed)",
    "dense_waypoints": "Dense Waypoints",
}
METHOD_COLORS = {
    "plain_json": "#6B7280",
    "few_shot_json": "#4C78A8",
    "lfs_schema": "#2CA02C",
    "dense_waypoints": "#F58518",
}
COMMAND_TYPES = (
    "simple",
    "sequential",
    "grouped",
    "style-conditioned",
    "safety-conditioned",
    "invalid/ambiguous",
)
COMMAND_TYPE_LABELS = (
    "Simple",
    "Sequential",
    "Grouped",
    "Style",
    "Safety",
    "Invalid",
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="用修正后的 LFS 选择性重测结果与三个 experiment-01 baseline 绘图。"
    )
    parser.add_argument("--baseline-csv", required=True)
    parser.add_argument("--fixed-lfs-csv", required=True)
    parser.add_argument("--output-dir", required=True)
    return parser.parse_args()


def read_rows(path: Path) -> List[Dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def number(value: Any) -> float | None:
    text = str(value).strip().lower()
    if text in {"true", "false"}:
        return float(text == "true")
    try:
        parsed = float(text)
    except (TypeError, ValueError):
        return None
    return parsed if math.isfinite(parsed) else None


def mean(values: Iterable[float]) -> float:
    items = list(values)
    return sum(items) / len(items) if items else float("nan")


def metric_mean(rows: Sequence[Dict[str, str]], metric: str) -> float:
    return mean(value for row in rows if (value := number(row.get(metric))) is not None)


def build_comparison_rows(
    baseline_rows: Sequence[Dict[str, str]],
    fixed_lfs_rows: Sequence[Dict[str, str]],
) -> List[Dict[str, str]]:
    """Replace affected baseline LFS rows while preserving all other observations."""
    baseline_keys = [(row["command_id"], row["method"]) for row in baseline_rows]
    if len(baseline_keys) != len(set(baseline_keys)):
        raise ValueError("baseline 存在重复 command_id/method")
    fixed_ids = [row["command_id"] for row in fixed_lfs_rows]
    if not fixed_lfs_rows or any(row["method"] != "lfs_schema" for row in fixed_lfs_rows):
        raise ValueError("fixed LFS 结果必须只包含 lfs_schema")
    if len(fixed_ids) != len(set(fixed_ids)):
        raise ValueError("fixed LFS 结果存在重复 command_id")

    ids_by_method = {
        method: {row["command_id"] for row in baseline_rows if row["method"] == method}
        for method in METHODS
    }
    reference_ids = ids_by_method[METHODS[0]]
    if not reference_ids or any(ids_by_method[method] != reference_ids for method in METHODS):
        raise ValueError("baseline 四种方法的 command_id 集合不一致")
    missing = sorted(set(fixed_ids) - reference_ids)
    if missing:
        raise ValueError(f"baseline 缺少 fixed LFS 指令: {missing}")

    fixed_by_id = {row["command_id"]: dict(row) for row in fixed_lfs_rows}
    comparison: List[Dict[str, str]] = []
    for baseline in baseline_rows:
        if baseline["method"] == "lfs_schema" and baseline["command_id"] in fixed_by_id:
            row = fixed_by_id[baseline["command_id"]]
            row["result_source"] = "fixed_lfs_rerun"
        else:
            row = dict(baseline)
            row["result_source"] = "original_baseline"
        comparison.append(row)

    for method in METHODS:
        method_ids = {row["command_id"] for row in comparison if row["method"] == method}
        if method_ids != reference_ids:
            raise ValueError(f"合并后 {method} 的 command_id 集合不完整")
    return comparison


def summarize(rows: Sequence[Dict[str, str]]) -> List[Dict[str, Any]]:
    summaries: List[Dict[str, Any]] = []
    for method in METHODS:
        method_rows = [row for row in rows if row["method"] == method]
        valid_rows = [row for row in method_rows if row["command_type"] != "invalid/ambiguous"]
        invalid_rows = [row for row in method_rows if row["command_type"] == "invalid/ambiguous"]
        semantic_scores = [
            number(row["rejection_accuracy"])
            if row["command_type"] == "invalid/ambiguous"
            else number(row["exact_task_accuracy"])
            for row in method_rows
        ]
        summary = {
            "method": method,
            "display_method": METHOD_LABELS[method],
            "sample_count": len(method_rows),
            "valid_json_rate": metric_mean(method_rows, "valid_json"),
            "schema_valid_rate": metric_mean(method_rows, "schema_valid"),
            "overall_semantic_success": mean(
                value for value in semantic_scores if value is not None
            ),
            "field_accuracy": metric_mean(valid_rows, "field_accuracy"),
            "exact_task_accuracy": metric_mean(valid_rows, "exact_task_accuracy"),
            "rejection_accuracy": metric_mean(invalid_rows, "rejection_accuracy"),
            "uav_set_accuracy": metric_mean(valid_rows, "uav_set_accuracy"),
            "formation_accuracy": metric_mean(valid_rows, "formation_accuracy"),
            "motion_style_accuracy": metric_mean(valid_rows, "motion_style_accuracy"),
            "trigger_accuracy": metric_mean(valid_rows, "trigger_accuracy"),
            "center_error": metric_mean(valid_rows, "center_error"),
            "radius_error": metric_mean(valid_rows, "radius_error"),
            "duration_error": metric_mean(valid_rows, "duration_error"),
            "safety_factor_error": metric_mean(valid_rows, "safety_factor_error"),
            "mean_latency_ms": metric_mean(method_rows, "latency_ms"),
            "mean_prompt_tokens": metric_mean(method_rows, "prompt_tokens"),
            "mean_completion_tokens": metric_mean(method_rows, "completion_tokens"),
            "mean_retry_count": metric_mean(method_rows, "retry_count"),
            "error_count": sum(bool(row["error_type"]) for row in method_rows),
        }
        summary["mean_total_tokens"] = (
            summary["mean_prompt_tokens"] + summary["mean_completion_tokens"]
        )
        summaries.append(summary)
    return summaries


def save(fig: plt.Figure, output_dir: Path, name: str) -> None:
    for suffix in ("png", "pdf"):
        fig.savefig(output_dir / f"{name}.{suffix}", dpi=220, bbox_inches="tight")
    plt.close(fig)


def annotate_bars(
    ax: plt.Axes,
    bars: Any,
    *,
    digits: int = 2,
    scale: float = 1.0,
    minimum: float = -1.0,
) -> None:
    for bar in bars:
        height = bar.get_height()
        if height <= minimum:
            continue
        ax.annotate(
            f"{height * scale:.{digits}f}",
            (bar.get_x() + bar.get_width() / 2, height),
            textcoords="offset points",
            xytext=(0, 3),
            ha="center",
            va="bottom",
            fontsize=7,
        )


def plot_accuracy_overview(output_dir: Path, summaries: Sequence[Dict[str, Any]]) -> None:
    metrics = (
        ("valid_json_rate", "JSON valid"),
        ("schema_valid_rate", "Schema valid"),
        ("overall_semantic_success", "Overall success"),
        ("field_accuracy", "Field accuracy"),
        ("exact_task_accuracy", "Exact task"),
        ("rejection_accuracy", "Invalid rejection"),
    )
    x_values = list(range(len(metrics)))
    width = 0.19
    fig, ax = plt.subplots(figsize=(12.5, 5.8))
    for index, summary in enumerate(summaries):
        offsets = [x + (index - 1.5) * width for x in x_values]
        bars = ax.bar(
            offsets,
            [summary[key] for key, _label in metrics],
            width,
            label=summary["display_method"],
            color=METHOD_COLORS[summary["method"]],
        )
        annotate_bars(ax, bars)
    ax.set_xticks(x_values, [label for _key, label in metrics])
    ax.set_ylim(0, 1.13)
    ax.set_ylabel("Rate / accuracy")
    ax.set_title("Parsing Accuracy and Reliability")
    ax.grid(axis="y", alpha=0.22)
    handles, labels = ax.get_legend_handles_labels()
    fig.legend(handles, labels, ncol=2, loc="upper center", bbox_to_anchor=(0.5, 0.99))
    fig.tight_layout(rect=(0, 0, 1, 0.88))
    save(fig, output_dir, "fig_accuracy_overview")


def plot_semantic_dimensions(output_dir: Path, summaries: Sequence[Dict[str, Any]]) -> None:
    accuracy_metrics = (
        ("uav_set_accuracy", "UAV set"),
        ("formation_accuracy", "Formation"),
        ("motion_style_accuracy", "Motion style"),
        ("trigger_accuracy", "Trigger"),
    )
    error_metrics = (
        ("center_error", "Center"),
        ("radius_error", "Radius"),
        ("duration_error", "Duration"),
        ("safety_factor_error", "Safety factor"),
    )
    fig, (left, right) = plt.subplots(1, 2, figsize=(14, 5.3))
    width = 0.19
    for ax, metrics, title, ylabel in (
        (left, accuracy_metrics, "Semantic Field Accuracy", "Accuracy"),
        (right, error_metrics, "Numeric Field Error (lower is better)", "Mean absolute error"),
    ):
        x_values = list(range(len(metrics)))
        for index, summary in enumerate(summaries):
            offsets = [x + (index - 1.5) * width for x in x_values]
            bars = ax.bar(
                offsets,
                [summary[key] for key, _label in metrics],
                width,
                label=summary["display_method"],
                color=METHOD_COLORS[summary["method"]],
            )
            annotate_bars(
                ax,
                bars,
                digits=3,
                minimum=0.0005 if ax is right else -1.0,
            )
        ax.set_xticks(x_values, [label for _key, label in metrics])
        ax.set_title(title)
        ax.set_ylabel(ylabel)
        ax.grid(axis="y", alpha=0.22)
    left.set_ylim(0, 1.13)
    error_max = max(summary[key] for summary in summaries for key, _label in error_metrics)
    right.set_ylim(0, max(0.07, error_max * 1.35))
    handles, labels = left.get_legend_handles_labels()
    fig.legend(handles, labels, ncol=4, loc="lower center", bbox_to_anchor=(0.5, -0.03))
    fig.tight_layout(rect=(0, 0.07, 1, 1))
    save(fig, output_dir, "fig_semantic_dimensions")


def plot_efficiency(output_dir: Path, summaries: Sequence[Dict[str, Any]]) -> None:
    labels = [summary["display_method"] for summary in summaries]
    colors = [METHOD_COLORS[summary["method"]] for summary in summaries]
    x_values = list(range(len(summaries)))
    fig, axes = plt.subplots(1, 3, figsize=(15, 5.2))

    latency = [summary["mean_latency_ms"] / 1000 for summary in summaries]
    bars = axes[0].bar(x_values, latency, color=colors)
    annotate_bars(axes[0], bars, digits=1)
    axes[0].set_ylabel("Mean latency (s)")
    axes[0].set_title("Latency")

    prompt = [summary["mean_prompt_tokens"] for summary in summaries]
    completion = [summary["mean_completion_tokens"] for summary in summaries]
    axes[1].bar(x_values, prompt, label="Prompt", color="#4C78A8")
    token_bars = axes[1].bar(
        x_values, completion, bottom=prompt, label="Completion", color="#F58518"
    )
    for index, bar in enumerate(token_bars):
        axes[1].annotate(
            f"{prompt[index] + completion[index]:.0f}",
            (bar.get_x() + bar.get_width() / 2, prompt[index] + completion[index]),
            textcoords="offset points",
            xytext=(0, 3),
            ha="center",
            fontsize=7,
        )
    axes[1].set_ylabel("Mean tokens / command")
    axes[1].set_title("Token Usage")
    axes[1].legend(fontsize=8)

    retries = [summary["mean_retry_count"] for summary in summaries]
    bars = axes[2].bar(x_values, retries, color=colors)
    annotate_bars(axes[2], bars, digits=2)
    axes[2].set_ylabel("Mean retries / command")
    axes[2].set_title("Retry Overhead")

    for ax in axes:
        ax.set_xticks(x_values, labels, rotation=25, ha="right")
        ax.grid(axis="y", alpha=0.22)
    fig.suptitle("Inference Efficiency", y=1.02)
    fig.tight_layout()
    save(fig, output_dir, "fig_efficiency")


def command_type_scores(rows: Sequence[Dict[str, str]]) -> List[List[float]]:
    scores: List[List[float]] = []
    for method in METHODS:
        method_scores = []
        for command_type in COMMAND_TYPES:
            group = [
                row
                for row in rows
                if row["method"] == method and row["command_type"] == command_type
            ]
            metric = (
                "rejection_accuracy"
                if command_type == "invalid/ambiguous"
                else "exact_task_accuracy"
            )
            method_scores.append(metric_mean(group, metric))
        scores.append(method_scores)
    return scores


def plot_command_types(output_dir: Path, rows: Sequence[Dict[str, str]]) -> None:
    scores = command_type_scores(rows)
    fig, ax = plt.subplots(figsize=(10.5, 5.3))
    image = ax.imshow(scores, cmap="YlGn", vmin=0, vmax=1, aspect="auto")
    ax.set_xticks(range(len(COMMAND_TYPES)), COMMAND_TYPE_LABELS)
    ax.set_yticks(range(len(METHODS)), [METHOD_LABELS[method] for method in METHODS])
    for row_index, row in enumerate(scores):
        for column_index, value in enumerate(row):
            ax.text(
                column_index,
                row_index,
                f"{value:.2f}",
                ha="center",
                va="center",
                color="white" if value >= 0.55 else "black",
                fontweight="bold",
            )
    colorbar = fig.colorbar(image, ax=ax, shrink=0.85)
    colorbar.set_label("Exact-task accuracy (invalid: rejection accuracy)")
    ax.set_title("Success by Command Type")
    fig.tight_layout()
    save(fig, output_dir, "fig_command_type_heatmap")


def plot_complexity(output_dir: Path, rows: Sequence[Dict[str, str]]) -> None:
    valid_rows = [row for row in rows if row["command_type"] != "invalid/ambiguous"]
    complexities = sorted({int(row["complexity"]) for row in valid_rows})
    fig, ax = plt.subplots(figsize=(9, 5.2))
    for method in METHODS:
        values = [
            metric_mean(
                [
                    row
                    for row in valid_rows
                    if row["method"] == method and int(row["complexity"]) == complexity
                ],
                "exact_task_accuracy",
            )
            for complexity in complexities
        ]
        ax.plot(
            complexities,
            values,
            marker="o",
            linewidth=2.2,
            label=METHOD_LABELS[method],
            color=METHOD_COLORS[method],
        )
    ax.set_xticks(complexities)
    ax.set_ylim(-0.03, 1.05)
    ax.set_xlabel("Annotated command complexity")
    ax.set_ylabel("Exact-task accuracy")
    ax.set_title("Accuracy Across Command Complexity")
    ax.grid(alpha=0.25)
    ax.legend(ncol=2)
    fig.tight_layout()
    save(fig, output_dir, "fig_complexity_comparison")


def plot_errors(output_dir: Path, rows: Sequence[Dict[str, str]]) -> None:
    categories = sorted({row["error_type"] for row in rows if row["error_type"]})
    counts = {
        method: Counter(
            row["error_type"]
            for row in rows
            if row["method"] == method and row["error_type"]
        )
        for method in METHODS
    }
    labels = [METHOD_LABELS[method] for method in METHODS]
    x_values = list(range(len(METHODS)))
    bottoms = [0] * len(METHODS)
    fig, ax = plt.subplots(figsize=(10.5, 5.4))
    palette = plt.get_cmap("tab10")
    for index, category in enumerate(categories):
        values = [counts[method][category] for method in METHODS]
        ax.bar(
            x_values,
            values,
            bottom=bottoms,
            label=category.replace("_", " "),
            color=palette(index % 10),
        )
        bottoms = [left + right for left, right in zip(bottoms, values)]
    for x_value, total in zip(x_values, bottoms):
        ax.text(x_value, total + 0.5, str(total), ha="center", fontweight="bold")
    ax.set_xticks(x_values, labels, rotation=15)
    ax.set_ylabel("Commands with an error")
    ax.set_title("Residual Error Distribution")
    ax.grid(axis="y", alpha=0.22)
    ax.legend(fontsize=8, bbox_to_anchor=(1.02, 1), loc="upper left")
    fig.tight_layout()
    save(fig, output_dir, "fig_error_distribution_fixed")


def write_csv(path: Path, rows: Sequence[Dict[str, Any]]) -> None:
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]), lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def write_readme(
    output_dir: Path,
    summaries: Sequence[Dict[str, Any]],
    replacement_count: int,
) -> None:
    by_method = {summary["method"]: summary for summary in summaries}
    lfs = by_method["lfs_schema"]
    few_shot = by_method["few_shot_json"]
    latency_reduction = 1 - lfs["mean_latency_ms"] / few_shot["mean_latency_ms"]
    token_reduction = 1 - lfs["mean_total_tokens"] / few_shot["mean_total_tokens"]
    lines = [
        "# Fixed LFS vs Baseline Comparison",
        "",
        "This comparison keeps all three baseline methods from the original 100-command run.",
        f"For LFS + Schema, {replacement_count} affected commands are replaced by the final selective rerun; "
        f"the other {100 - replacement_count} observations remain from the original run.",
        "",
        "| Method | Overall success | Field accuracy | Exact task | Invalid rejection | Latency (s) | Total tokens | Mean retries | Errors |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for summary in summaries:
        lines.append(
            f"| {summary['display_method']} | {summary['overall_semantic_success']:.4f} | "
            f"{summary['field_accuracy']:.4f} | {summary['exact_task_accuracy']:.4f} | "
            f"{summary['rejection_accuracy']:.4f} | {summary['mean_latency_ms'] / 1000:.2f} | "
            f"{summary['mean_total_tokens']:.2f} | {summary['mean_retry_count']:.2f} | "
            f"{summary['error_count']} |"
        )
    lines.extend(
        [
            "",
            "Key observations:",
            "",
            f"- Fixed LFS reaches {lfs['overall_semantic_success']:.0%} overall semantic success "
            f"and {lfs['exact_task_accuracy']:.0%} exact-task accuracy on valid commands.",
            f"- Relative to Few-shot JSON, fixed LFS uses {latency_reduction:.1%} less mean latency "
            f"and {token_reduction:.1%} fewer mean tokens.",
            f"- Fixed LFS retains {lfs['error_count']} residual errors, both in invalid-command handling; "
            f"its invalid rejection accuracy ({lfs['rejection_accuracy']:.4f}) ties Few-shot JSON "
            "but remains below Plain JSON.",
            "",
            "Metric scopes:",
            "",
            "- Overall success uses exact-task accuracy for 82 valid commands and rejection accuracy for 18 invalid commands.",
            "- Field, exact-task, and semantic-field metrics use only valid commands.",
            "- Invalid rejection uses only invalid/ambiguous commands.",
            "- Latency, tokens, retries, schema validity, and JSON validity use all 100 commands per method.",
            "- The fixed LFS result is a selective replacement comparison, not a new 100-command API rerun.",
        ]
    )
    (output_dir / "README.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    args = parse_args()
    baseline_path = Path(args.baseline_csv)
    fixed_path = Path(args.fixed_lfs_csv)
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    baseline_rows = read_rows(baseline_path)
    fixed_rows = read_rows(fixed_path)
    comparison_rows = build_comparison_rows(baseline_rows, fixed_rows)
    summaries = summarize(comparison_rows)

    write_csv(output_dir / "comparison_sample_results.csv", comparison_rows)
    write_csv(output_dir / "comparison_summary.csv", summaries)
    plot_accuracy_overview(output_dir, summaries)
    plot_semantic_dimensions(output_dir, summaries)
    plot_efficiency(output_dir, summaries)
    plot_command_types(output_dir, comparison_rows)
    plot_complexity(output_dir, comparison_rows)
    plot_errors(output_dir, comparison_rows)
    write_readme(output_dir, summaries, len(fixed_rows))

    generated_files = [
        "comparison_sample_results.csv",
        "comparison_summary.csv",
        "README.md",
        "fig_accuracy_overview.png/pdf",
        "fig_semantic_dimensions.png/pdf",
        "fig_efficiency.png/pdf",
        "fig_command_type_heatmap.png/pdf",
        "fig_complexity_comparison.png/pdf",
        "fig_error_distribution_fixed.png/pdf",
    ]
    (output_dir / "comparison_manifest.json").write_text(
        json.dumps(
            {
                "baseline_csv": str(baseline_path),
                "fixed_lfs_csv": str(fixed_path),
                "baseline_row_count": len(baseline_rows),
                "fixed_lfs_row_count": len(fixed_rows),
                "comparison_row_count": len(comparison_rows),
                "rows_per_method": {
                    method: sum(row["method"] == method for row in comparison_rows)
                    for method in METHODS
                },
                "fixed_command_ids": sorted(row["command_id"] for row in fixed_rows),
                "method_labels": METHOD_LABELS,
                "metric_scope": {
                    "overall_semantic_success": "82 valid exact-task scores + 18 invalid rejection scores",
                    "valid_metrics": "valid commands only",
                    "rejection_accuracy": "invalid/ambiguous commands only",
                    "efficiency": "all commands",
                },
                "selection_note": (
                    "The fixed LFS series replaces only the 20 affected commands; "
                    "it is not a full 100-command rerun."
                ),
                "generated_files": generated_files,
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    print(f"对比图生成完成: {output_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
