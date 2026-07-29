#!/usr/bin/env python3
"""Aggregate trial metrics and run paired statistical tests."""

from __future__ import annotations

import argparse
import csv
import math
from itertools import combinations
from pathlib import Path
from typing import Dict, Iterable, List

import numpy as np
import pandas as pd
from scipy.stats import friedmanchisquare, wilcoxon

from analysis_core import write_dict_rows


METRICS = [
    "minimum_inter_agent_distance", "violation_event_count",
    "risk_exposure_time", "risk_integral", "mean_trajectory_deviation",
    "recovery_time", "iapf_activation_ratio", "path_length_ratio",
    "integrated_squared_acceleration",
]


def bootstrap_ci(values: np.ndarray, seed: int = 42) -> tuple[float, float]:
    if len(values) == 0:
        return math.nan, math.nan
    generator = np.random.default_rng(seed)
    samples = generator.choice(values, size=(10000, len(values)), replace=True)
    means = samples.mean(axis=1)
    return tuple(np.quantile(means, [0.025, 0.975]).tolist())


def wilson_interval(success: int, total: int) -> tuple[float, float]:
    if total == 0:
        return math.nan, math.nan
    z = 1.959963984540054
    proportion = success / total
    denominator = 1.0 + z * z / total
    center = (proportion + z * z / (2 * total)) / denominator
    half = (
        z * math.sqrt(
            proportion * (1 - proportion) / total
            + z * z / (4 * total * total))
        / denominator
    )
    return center - half, center + half


def holm_adjust(p_values: Iterable[float]) -> List[float]:
    values = list(p_values)
    order = np.argsort(values)
    adjusted = np.empty(len(values), dtype=float)
    running = 0.0
    count = len(values)
    for rank, index in enumerate(order):
        running = max(running, min(1.0, (count - rank) * values[index]))
        adjusted[index] = running
    return adjusted.tolist()


def collect(batch_dir: Path) -> pd.DataFrame:
    paths = sorted(batch_dir.glob("raw/**/trial_summary.csv"))
    if not paths:
        raise FileNotFoundError(f"no trial summaries under {batch_dir}")
    frames = [pd.read_csv(path) for path in paths]
    return pd.concat(frames, ignore_index=True)


def summarize(data: pd.DataFrame) -> List[Dict[str, object]]:
    rows: List[Dict[str, object]] = []
    for keys, group in data.groupby(["phase", "scenario", "method"], dropna=False):
        phase, scenario, method = keys
        base = {
            "phase": phase, "scenario": scenario, "method": method,
            "trial_count": len(group),
        }
        success = int(group["mission_success"].astype(bool).sum())
        low, high = wilson_interval(success, len(group))
        base.update({
            "mission_success_rate": success / len(group),
            "mission_success_ci_low": low,
            "mission_success_ci_high": high,
        })
        for metric in METRICS:
            values = pd.to_numeric(group.get(metric), errors="coerce")
            finite = values[np.isfinite(values.to_numpy(dtype=float))].to_numpy()
            ci_low, ci_high = bootstrap_ci(finite)
            base.update({
                f"{metric}_n_valid": len(finite),
                f"{metric}_mean": float(np.mean(finite)) if len(finite) else math.nan,
                f"{metric}_std": (
                    float(np.std(finite, ddof=1)) if len(finite) > 1 else math.nan),
                f"{metric}_median": (
                    float(np.median(finite)) if len(finite) else math.nan),
                f"{metric}_q1": (
                    float(np.quantile(finite, 0.25)) if len(finite) else math.nan),
                f"{metric}_q3": (
                    float(np.quantile(finite, 0.75)) if len(finite) else math.nan),
                f"{metric}_ci_low": ci_low,
                f"{metric}_ci_high": ci_high,
            })
        rows.append(base)
    return rows


def statistical_tests(data: pd.DataFrame) -> List[Dict[str, object]]:
    main = data[(data["phase"] == "main") & data["method"].isin(
        [f"M{value}" for value in range(6)])]
    rows: List[Dict[str, object]] = []
    for scenario, scenario_data in main.groupby("scenario"):
        for metric in METRICS:
            pivot = scenario_data.pivot_table(
                index="seed", columns="method", values=metric, aggfunc="first")
            methods = [f"M{value}" for value in range(6)]
            # pivot_table drops a method column when every value for that
            # method is NaN (recovery_time legitimately has this property in
            # some scenario/method combinations).  Keep the fixed M0--M5
            # schema so the absence is reported as n_valid=0 rather than
            # raising while constructing pairwise tests.
            pivot = pivot.reindex(columns=methods)
            complete = pivot.dropna()
            friedman_stat = math.nan
            friedman_p = math.nan
            if len(complete) >= 2:
                result = friedmanchisquare(
                    *[complete[method].to_numpy() for method in methods])
                friedman_stat = float(result.statistic)
                friedman_p = float(result.pvalue)
            rows.append({
                "scenario": scenario, "metric": metric,
                "test": "friedman", "method_a": "all", "method_b": "all",
                "n_total": len(pivot), "n_valid": len(complete),
                "statistic": friedman_stat, "p_value": friedman_p,
                "p_adjusted": friedman_p,
            })

            pair_rows = []
            for method_a, method_b in combinations(methods, 2):
                paired = pivot[[method_a, method_b]].dropna()
                statistic = math.nan
                p_value = math.nan
                if len(paired) and not np.allclose(
                        paired[method_a], paired[method_b]):
                    result = wilcoxon(
                        paired[method_a], paired[method_b], zero_method="wilcox")
                    statistic = float(result.statistic)
                    p_value = float(result.pvalue)
                elif len(paired):
                    statistic, p_value = 0.0, 1.0
                pair_rows.append({
                    "scenario": scenario, "metric": metric,
                    "test": "wilcoxon", "method_a": method_a,
                    "method_b": method_b, "n_total": len(pivot),
                    "n_valid": len(paired), "statistic": statistic,
                    "p_value": p_value,
                })
            finite_indices = [
                index for index, row in enumerate(pair_rows)
                if math.isfinite(row["p_value"])]
            adjusted = holm_adjust(
                [pair_rows[index]["p_value"] for index in finite_indices])
            for index, value in zip(finite_indices, adjusted):
                pair_rows[index]["p_adjusted"] = value
            for row in pair_rows:
                row.setdefault("p_adjusted", math.nan)
            rows.extend(pair_rows)
    return rows


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("batch_dir", type=Path)
    args = parser.parse_args()
    data = collect(args.batch_dir)
    summary_dir = args.batch_dir / "summaries"
    summary_dir.mkdir(parents=True, exist_ok=True)
    data.to_csv(summary_dir / "trial_summary.csv", index=False)
    write_dict_rows(summary_dir / "method_summary.csv", summarize(data))
    tests = statistical_tests(data)
    if tests:
        write_dict_rows(summary_dir / "statistical_tests.csv", tests)
    print(summary_dir)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
