#!/usr/bin/env python3
"""Validate, summarize, and plot experiment 02 results."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import subprocess
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402


REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from lfs_ablation_experiment import METHODS  # noqa: E402


METHOD_LABELS = {
    "direct_waypoint": "Direct waypoint",
    "task_json_no_schema": "Task JSON\n(no schema)",
    "lfs_schema": "LFS + schema",
    "lfs_schema_semantic": "LFS + schema\n+ semantic",
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="分析实验2 LFS消融数据。")
    parser.add_argument(
        "--run-dir",
        default=str(REPO_ROOT / "experiments" / "results" / "experiments_02" / "minimax_m27_100x4"),
    )
    return parser.parse_args()


def _bool(value: Any) -> bool:
    return str(value).strip().lower() == "true"


def _int(value: Any) -> int:
    return int(float(value or 0))


def _mean(values: Iterable[float]) -> float:
    values = list(values)
    return sum(values) / len(values) if values else 0.0


def _ratio(numerator: int, denominator: int) -> float:
    return numerator / denominator if denominator else 0.0


def _write_csv(path: Path, rows: List[Dict[str, Any]]) -> None:
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]), lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def _read_rows(path: Path) -> List[Dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def _git_output(*args: str) -> str:
    return subprocess.check_output(["git", *args], cwd=REPO_ROOT, text=True).strip()


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def validate_rows(rows: List[Dict[str, str]]) -> None:
    keys = [(row["command_id"], row["method"]) for row in rows]
    if len(rows) != 400:
        raise ValueError(f"正式实验必须有400行，实际 {len(rows)}")
    if len(set(keys)) != len(keys):
        duplicates = [key for key, count in Counter(keys).items() if count > 1]
        raise ValueError(f"存在重复 command/method 键: {duplicates[:10]}")
    per_method = Counter(row["method"] for row in rows)
    if set(per_method) != set(METHODS) or any(per_method[method] != 100 for method in METHODS):
        raise ValueError(f"每种方法应为100行，实际 {dict(per_method)}")
    valid_counts = Counter(row["method"] for row in rows if _bool(row["valid_input"]))
    invalid_counts = Counter(row["method"] for row in rows if not _bool(row["valid_input"]))
    if any(valid_counts[method] != 82 or invalid_counts[method] != 18 for method in METHODS):
        raise ValueError(f"有效/无效划分异常: valid={dict(valid_counts)}, invalid={dict(invalid_counts)}")
    infrastructure = [row for row in rows if row["error_type"] == "api_error"]
    if infrastructure:
        raise ValueError(f"存在 {len(infrastructure)} 条 API 基础设施失败，不能生成正式汇总")


def summarize(rows: List[Dict[str, str]]) -> tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    summary = []
    invalid_summary = []
    for method in METHODS:
        method_rows = [row for row in rows if row["method"] == method]
        valid = [row for row in method_rows if _bool(row["valid_input"])]
        invalid = [row for row in method_rows if not _bool(row["valid_input"])]
        summary.append({
            "method": method,
            "n_valid": len(valid),
            "executable_rate": round(_mean(_bool(row["executable"]) for row in valid), 4),
            "mean_retry_count": round(_mean(_int(row["retry_count"]) for row in valid), 4),
            "correction_needed_rate": round(_mean(_int(row["retry_count"]) > 0 for row in valid), 4),
            "invalid_uav_ratio": round(_ratio(
                sum(_int(row["invalid_uav_count"]) for row in valid),
                sum(_int(row["uav_reference_count"]) for row in valid),
            ), 4),
            "invalid_formation_ratio": round(_ratio(
                sum(_int(row["invalid_formation_count"]) for row in valid),
                sum(_int(row["formation_task_count"]) for row in valid),
            ), 4),
            "missing_field_ratio": round(_ratio(
                sum(_int(row["missing_field_count"]) for row in valid),
                sum(_int(row["required_field_slots"]) for row in valid),
            ), 4),
            "compilation_success_rate": round(_mean(_bool(row["compilation_success"]) for row in valid), 4),
            "mean_latency_ms": round(_mean(_int(row["latency_ms"]) for row in valid), 2),
            "mean_prompt_tokens": round(_mean(_int(row["prompt_tokens"]) for row in valid), 2),
            "mean_completion_tokens": round(_mean(_int(row["completion_tokens"]) for row in valid), 2),
        })
        invalid_summary.append({
            "method": method,
            "n_invalid": len(invalid),
            "correct_rejection_rate": round(_mean(_bool(row["correct_rejection"]) for row in invalid), 4),
            "false_executable_rate": round(_mean(_bool(row["false_executable"]) for row in invalid), 4),
            "mean_retry_count": round(_mean(_int(row["retry_count"]) for row in invalid), 4),
        })
    return summary, invalid_summary


def write_table(path: Path, summary: List[Dict[str, Any]], invalid: List[Dict[str, Any]]) -> None:
    invalid_by_method = {row["method"]: row for row in invalid}
    lines = [
        "# Experiment 02: LFS Representation Ablation",
        "",
        "Primary metrics use only the 82 valid commands. Invalid commands are reported separately.",
        "",
        "| Method | Executable rate | Mean retries | Invalid UAV ratio | Invalid formation ratio | Missing field ratio | Compilation success |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for row in summary:
        lines.append(
            f"| {METHOD_LABELS[row['method']].replace(chr(10), ' ')} "
            f"| {row['executable_rate']:.4f} | {row['mean_retry_count']:.4f} "
            f"| {row['invalid_uav_ratio']:.4f} | {row['invalid_formation_ratio']:.4f} "
            f"| {row['missing_field_ratio']:.4f} | {row['compilation_success_rate']:.4f} |"
        )
    lines.extend([
        "",
        "## Invalid / ambiguous commands",
        "",
        "| Method | Correct rejection rate | False executable rate | Mean retries |",
        "| --- | ---: | ---: | ---: |",
    ])
    for method in METHODS:
        row = invalid_by_method[method]
        lines.append(
            f"| {METHOD_LABELS[method].replace(chr(10), ' ')} "
            f"| {row['correct_rejection_rate']:.4f} | {row['false_executable_rate']:.4f} "
            f"| {row['mean_retry_count']:.4f} |"
        )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def plot_error_ratios(run_dir: Path, summary: List[Dict[str, Any]]) -> None:
    metrics = [
        ("missing_field_ratio", "Missing field"),
        ("invalid_uav_ratio", "Invalid UAV"),
        ("invalid_formation_ratio", "Invalid formation"),
    ]
    x_positions = list(range(len(METHODS)))
    width = 0.24
    fig, axis = plt.subplots(figsize=(10.5, 5.8))
    colors = ("#4C78A8", "#F58518", "#E45756")
    for metric_index, (field, label) in enumerate(metrics):
        offset = (metric_index - 1) * width
        values = [next(row[field] for row in summary if row["method"] == method) for method in METHODS]
        axis.bar([x + offset for x in x_positions], values, width=width, label=label, color=colors[metric_index])
    axis.set_xticks(x_positions, [METHOD_LABELS[method] for method in METHODS])
    axis.set_ylabel("Error ratio")
    axis.set_ylim(bottom=0)
    axis.grid(axis="y", alpha=0.25)
    axis.legend(frameon=False, ncol=3, loc="upper center")
    fig.tight_layout()
    for suffix in ("png", "pdf"):
        fig.savefig(run_dir / f"fig_error_ratios.{suffix}", dpi=300, bbox_inches="tight")
    plt.close(fig)


def plot_flow(run_dir: Path) -> None:
    fig, axis = plt.subplots(figsize=(12, 5.8))
    axis.set_xlim(0, 12)
    axis.set_ylim(0, 5)
    axis.axis("off")

    def box(x: float, y: float, text: str, color: str) -> None:
        axis.text(
            x,
            y,
            text,
            ha="center",
            va="center",
            fontsize=10,
            bbox={"boxstyle": "round,pad=0.45", "facecolor": color, "edgecolor": "#333333"},
        )

    def arrow(x1: float, y1: float, x2: float, y2: float) -> None:
        axis.annotate("", xy=(x2, y2), xytext=(x1, y1), arrowprops={"arrowstyle": "->", "lw": 1.5})

    rows = [
        (4.2, "Direct goals", "Native contract", "#FDE2E2"),
        (3.1, "Task JSON", "Geometry compiler", "#FFF0D5"),
        (2.0, "LFS", "Schema → Compiler", "#DDEBFF"),
        (0.9, "LFS", "Schema → Semantic\nvalidator → Compiler", "#DDF4E7"),
    ]
    for y, representation, pipeline, color in rows:
        box(1.2, y, "Natural Language", "#F1F1F1")
        box(4.0, y, representation, color)
        box(7.5, y, pipeline, color)
        box(10.8, y, "UAV Goals", "#EAE2F8")
        arrow(2.2, y, 3.1, y)
        arrow(4.9, y, 5.55, y)
        arrow(9.45, y, 9.8, y)
    axis.set_title("Experiment 02: Natural Language to Executable UAV Goals", fontsize=14, pad=12)
    fig.tight_layout()
    for suffix in ("png", "pdf"):
        fig.savefig(run_dir / f"fig_lfs_compilation_flow.{suffix}", dpi=300, bbox_inches="tight")
    plt.close(fig)


def write_record(run_dir: Path, config: Dict[str, Any], summary: List[Dict[str, Any]]) -> None:
    lines = [
        "# Experiment 02 Completion Record",
        "",
        "## Status",
        "",
        "- Experiment: LFS intermediate representation ablation",
        "- Status: completed successfully",
        f"- Branch: `{_git_output('branch', '--show-current')}`",
        f"- Fixed base: `{config['base_tag']}`",
        f"- Base commit: `{config['base_commit']}`",
        f"- Run ID: `{config['run_id']}`",
        f"- Model: `{config['model']}`",
        f"- Result location: `experiments/results/experiments_02/{config['run_id']}`",
        "- Final pushed commit SHA: recorded in the delivery message after Git creates the commit",
        "",
        "## Dataset and protocol",
        "",
        "The fixed dataset contains 100 unique Chinese commands. Primary metrics use 82 valid commands;",
        "18 invalid or ambiguous commands are evaluated separately for correct rejection and false execution.",
        "Each command was independently evaluated once with all four methods, producing 400 final rows.",
        "All methods used temperature 0, top-p 0.01, JSON response mode, and at most three attempts.",
        "",
        "## Commands",
        "",
        "```bash",
        "source ~/learning/LLM_swarm_ws/llm_env/bin/activate",
        "source /opt/ros/humble/setup.bash",
        "source ~/learning/LLM_swarm_ws/install/setup.bash",
        "python3 experiments/scripts/eval_lfs_ablation.py --run-id " + config["run_id"] + " --method all --workers 4",
        "python3 experiments/scripts/analyze_lfs_ablation.py --run-dir experiments/results/experiments_02/" + config["run_id"],
        "```",
        "",
        "## Primary results",
        "",
        "| Method | Executable | Mean retries | Invalid UAV | Invalid formation | Missing field | Compilation |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for row in summary:
        lines.append(
            f"| {METHOD_LABELS[row['method']].replace(chr(10), ' ')} | {row['executable_rate']:.4f} "
            f"| {row['mean_retry_count']:.4f} | {row['invalid_uav_ratio']:.4f} "
            f"| {row['invalid_formation_ratio']:.4f} | {row['missing_field_ratio']:.4f} "
            f"| {row['compilation_success_rate']:.4f} |"
        )
    lines.extend([
        "",
        "## Validation",
        "",
        "- Final result rows: 400, exactly 100 per method, with no duplicate command/method keys.",
        "- Valid-command rows: 82 per method; invalid-command rows: 18 per method.",
        "- API infrastructure failures: 0.",
        "- Existing experiment data was not overwritten.",
    ])
    (run_dir / "experiment_record.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    args = parse_args()
    run_dir = Path(args.run_dir).resolve()
    sample_path = run_dir / "sample_results.csv"
    config_path = run_dir / "run_config.json"
    rows = _read_rows(sample_path)
    validate_rows(rows)
    summary, invalid_summary = summarize(rows)
    _write_csv(run_dir / "summary_by_method.csv", summary)
    _write_csv(run_dir / "invalid_command_summary.csv", invalid_summary)
    write_table(run_dir / "table_lfs_ablation.md", summary, invalid_summary)
    plot_error_ratios(run_dir, summary)
    plot_flow(run_dir)
    with config_path.open(encoding="utf-8") as handle:
        config = json.load(handle)
    write_record(run_dir, config, summary)

    artifacts = [
        "dataset.json",
        "run_config.json",
        "raw_attempts.jsonl",
        "sample_results.csv",
        "summary_by_method.csv",
        "invalid_command_summary.csv",
        "table_lfs_ablation.md",
        "fig_error_ratios.png",
        "fig_error_ratios.pdf",
        "fig_lfs_compilation_flow.png",
        "fig_lfs_compilation_flow.pdf",
        "experiment_record.md",
    ]
    manifest = {
        "experiment": "experiments_02",
        "analyzed_at_utc": datetime.now(timezone.utc).isoformat(),
        "row_count": len(rows),
        "per_method": {method: 100 for method in METHODS},
        "valid_rows_per_method": 82,
        "invalid_rows_per_method": 18,
        "artifacts": {
            name: {"sha256": _sha256(run_dir / name), "bytes": (run_dir / name).stat().st_size}
            for name in artifacts
        },
    }
    with (run_dir / "analysis_manifest.json").open("w", encoding="utf-8") as handle:
        json.dump(manifest, handle, ensure_ascii=False, indent=2)
        handle.write("\n")
    print(f"已验证并分析400行实验数据，结果写入 {run_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
