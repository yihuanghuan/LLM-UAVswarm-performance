#!/usr/bin/env python3
"""读取 experiments/results 下的 CSV 并生成论文图。"""

from __future__ import annotations

import argparse
import csv
import math
from collections import defaultdict
from pathlib import Path
from typing import Callable, Dict, Iterable, List, Sequence

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402


REPO_ROOT = Path(__file__).resolve().parents[2]

FIGURES = [
    "llm_latency",
    "llm_success_rate",
    "assignment_min_distance",
    "assignment_crossings",
    "trajectory_profiles",
    "semantic_control_summary",
    "iapf_min_distance",
]

ALIASES = {
    "llm": ["llm_latency", "llm_success_rate"],
    "assignment": ["assignment_min_distance", "assignment_crossings"],
    "trajectory": ["trajectory_profiles"],
    "semantic": ["semantic_control_summary"],
    "iapf": ["iapf_min_distance"],
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="生成全部或指定论文图。")
    parser.add_argument("--all", action="store_true", help="生成全部图。")
    parser.add_argument(
        "--which",
        nargs="+",
        choices=FIGURES + sorted(ALIASES),
        help="指定图名或类别，例如 assignment、trajectory_profiles。",
    )
    parser.add_argument(
        "--results-dir",
        default=str(REPO_ROOT / "experiments" / "results"),
        help="结果 CSV 目录。",
    )
    parser.add_argument(
        "--figures-dir",
        default=str(REPO_ROOT / "experiments" / "figures"),
        help="图输出目录。",
    )
    return parser.parse_args()


def read_csv(path: Path) -> List[Dict[str, str]]:
    if not path.is_file():
        print(f"跳过缺失文件: {path}")
        return []
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def parse_float(value: object) -> float | None:
    try:
        parsed = float(str(value).strip())
    except (TypeError, ValueError):
        return None
    return parsed if math.isfinite(parsed) else None


def is_true(value: object) -> bool:
    return str(value).strip().lower() in {"true", "1", "yes", "success", "succeeded"}


def mean(values: Iterable[float]) -> float:
    items = list(values)
    return sum(items) / len(items) if items else 0.0


def grouped_values(rows: Sequence[Dict[str, str]], group_key: str, value_key: str) -> Dict[str, List[float]]:
    grouped: Dict[str, List[float]] = defaultdict(list)
    for row in rows:
        value = parse_float(row.get(value_key))
        if value is None:
            continue
        grouped[row.get(group_key, "unknown") or "unknown"].append(value)
    return grouped


def save_figure(fig: plt.Figure, figures_dir: Path, name: str) -> None:
    figures_dir.mkdir(parents=True, exist_ok=True)
    for suffix in ("png", "pdf"):
        fig.savefig(figures_dir / f"fig_{name}.{suffix}", dpi=180, bbox_inches="tight")
    plt.close(fig)
    print(f"已生成 fig_{name}.png/pdf")


def bar_plot(labels: Sequence[str], values: Sequence[float], title: str, ylabel: str) -> plt.Figure:
    fig, ax = plt.subplots(figsize=(8, 4.8))
    ax.bar(labels, values, color="#4C78A8")
    ax.set_title(title)
    ax.set_ylabel(ylabel)
    ax.grid(axis="y", alpha=0.25)
    ax.tick_params(axis="x", rotation=25)
    fig.tight_layout()
    return fig


def plot_llm_latency(results_dir: Path, figures_dir: Path) -> bool:
    rows = read_csv(results_dir / "llm_parser_results.csv")
    rows = [row for row in rows if parse_float(row.get("latency_ms")) is not None]
    if not rows:
        return False
    labels = [row.get("command_id", "") for row in rows]
    values = [parse_float(row.get("latency_ms")) or 0.0 for row in rows]
    fig = bar_plot(labels, values, "LLM Parsing Latency", "Latency (ms)")
    save_figure(fig, figures_dir, "llm_latency")
    return True


def plot_llm_success_rate(results_dir: Path, figures_dir: Path) -> bool:
    rows = read_csv(results_dir / "llm_parser_results.csv")
    if not rows:
        return False
    grouped: Dict[str, List[bool]] = defaultdict(list)
    for row in rows:
        grouped[row.get("command_type", "unknown") or "unknown"].append(is_true(row.get("compiled_success")))
    labels = sorted(grouped)
    values = [sum(grouped[label]) / len(grouped[label]) for label in labels]
    fig = bar_plot(labels, values, "LLM Compile Success Rate", "Success rate")
    fig.axes[0].set_ylim(0.0, 1.05)
    save_figure(fig, figures_dir, "llm_success_rate")
    return True


def plot_assignment_min_distance(results_dir: Path, figures_dir: Path) -> bool:
    rows = read_csv(results_dir / "assignment_results.csv")
    grouped = grouped_values(rows, "method", "min_distance")
    if not grouped:
        return False
    labels = sorted(grouped)
    values = [mean(grouped[label]) for label in labels]
    fig = bar_plot(labels, values, "Assignment Minimum Distance", "Mean min distance (m)")
    save_figure(fig, figures_dir, "assignment_min_distance")
    return True


def plot_assignment_crossings(results_dir: Path, figures_dir: Path) -> bool:
    rows = read_csv(results_dir / "assignment_results.csv")
    if not rows:
        return False
    xy = grouped_values(rows, "method", "xy_crossings")
    prox = grouped_values(rows, "method", "proximity_crossings")
    labels = sorted(set(xy) | set(prox))
    if not labels:
        return False

    x = range(len(labels))
    fig, ax = plt.subplots(figsize=(9, 4.8))
    ax.bar([idx - 0.2 for idx in x], [mean(xy.get(label, [])) for label in labels], width=0.4, label="XY crossings")
    ax.bar([idx + 0.2 for idx in x], [mean(prox.get(label, [])) for label in labels], width=0.4, label="Proximity crossings")
    ax.set_xticks(list(x), labels, rotation=25)
    ax.set_title("Assignment Crossing Metrics")
    ax.set_ylabel("Mean count")
    ax.grid(axis="y", alpha=0.25)
    ax.legend()
    fig.tight_layout()
    save_figure(fig, figures_dir, "assignment_crossings")
    return True


def plot_trajectory_profiles(results_dir: Path, figures_dir: Path) -> bool:
    rows = read_csv(results_dir / "trajectory_profile_timeseries.csv")
    if not rows:
        return False
    grouped: Dict[str, List[Dict[str, str]]] = defaultdict(list)
    for row in rows:
        grouped[row.get("profile", "unknown") or "unknown"].append(row)
    if not grouped:
        return False

    fig, axes = plt.subplots(2, 2, figsize=(10, 7), sharex=True)
    metrics = [
        ("position", "Position (m)"),
        ("velocity", "Velocity (m/s)"),
        ("acceleration", "Acceleration (m/s^2)"),
        ("jerk", "Jerk (m/s^3)"),
    ]
    for ax, (metric, ylabel) in zip(axes.ravel(), metrics):
        for profile in sorted(grouped):
            profile_rows = sorted(grouped[profile], key=lambda item: parse_float(item.get("time_s")) or 0.0)
            times = [parse_float(row.get("time_s")) or 0.0 for row in profile_rows]
            values = [parse_float(row.get(metric)) or 0.0 for row in profile_rows]
            ax.plot(times, values, label=profile, linewidth=1.4)
        ax.set_ylabel(ylabel)
        ax.grid(alpha=0.25)
    axes[1, 0].set_xlabel("Time (s)")
    axes[1, 1].set_xlabel("Time (s)")
    axes[0, 0].set_title("Trajectory Profiles")
    axes[0, 1].legend(fontsize="small")
    fig.tight_layout()
    save_figure(fig, figures_dir, "trajectory_profiles")
    return True


def plot_semantic_control_summary(results_dir: Path, figures_dir: Path) -> bool:
    rows = read_csv(results_dir / "semantic_control_summary.csv")
    rows = [row for row in rows if parse_float(row.get("mean_gain_multiplier")) is not None]
    if not rows:
        return False
    labels = [row.get("motion_style", "unknown") for row in rows]
    values = [parse_float(row.get("mean_gain_multiplier")) or 0.0 for row in rows]
    fig = bar_plot(labels, values, "Semantic Control Gain Summary", "Mean gain multiplier")
    save_figure(fig, figures_dir, "semantic_control_summary")
    return True


def plot_iapf_min_distance(results_dir: Path, figures_dir: Path) -> bool:
    rows = read_csv(results_dir / "iapf_summary.csv")
    rows = [row for row in rows if parse_float(row.get("min_inter_agent_distance")) is not None]
    if not rows:
        return False
    labels = [row.get("method", "unknown") for row in rows]
    values = [parse_float(row.get("min_inter_agent_distance")) or 0.0 for row in rows]
    fig = bar_plot(labels, values, "IAPF Minimum Distance", "Min distance (m)")
    save_figure(fig, figures_dir, "iapf_min_distance")
    return True


PLOTTERS: Dict[str, Callable[[Path, Path], bool]] = {
    "llm_latency": plot_llm_latency,
    "llm_success_rate": plot_llm_success_rate,
    "assignment_min_distance": plot_assignment_min_distance,
    "assignment_crossings": plot_assignment_crossings,
    "trajectory_profiles": plot_trajectory_profiles,
    "semantic_control_summary": plot_semantic_control_summary,
    "iapf_min_distance": plot_iapf_min_distance,
}


def selected_figures(args: argparse.Namespace) -> List[str]:
    if args.all or not args.which:
        return list(FIGURES)
    selected: List[str] = []
    for item in args.which:
        selected.extend(ALIASES.get(item, [item]))
    return [item for item in FIGURES if item in set(selected)]


def main() -> int:
    args = parse_args()
    results_dir = Path(args.results_dir)
    figures_dir = Path(args.figures_dir)
    generated = 0
    for name in selected_figures(args):
        if PLOTTERS[name](results_dir, figures_dir):
            generated += 1
        else:
            print(f"跳过 {name}: 没有可绘制数据")
    if generated == 0:
        raise FileNotFoundError("没有生成任何图，请先运行对应评估脚本生成 CSV")
    print(f"共生成 {generated} 类图。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
