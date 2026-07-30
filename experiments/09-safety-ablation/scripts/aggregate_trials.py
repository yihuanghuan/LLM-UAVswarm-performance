#!/usr/bin/env python3
"""Aggregate experiment 09 and run pre-registered paired statistics."""

from __future__ import annotations

import argparse
import math
from pathlib import Path
from typing import Dict, Iterable, List

import numpy as np
import pandas as pd
from scipy.stats import binomtest, rankdata, wilcoxon

from analysis_core import write_dict_rows


CONTINUOUS_METRICS = [
    "nominal_xy_crossings", "nominal_proximity_crossings",
    "predicted_min_distance", "total_path_length",
    "assignment_compute_time_ms", "local_swap_iterations",
    "actual_min_distance", "violation_count", "violation_duration",
    "near_miss_duration", "collision_count", "tracking_rmse",
    "trajectory_deviation", "arrival_time_variance", "mission_duration",
    "recovery_time", "iapf_activation_count", "iapf_active_duration",
    "iapf_active_ratio", "intervention_latency", "mean_position_offset",
    "max_position_offset", "mean_acceleration_offset",
    "max_acceleration_offset", "saturation_count", "stale_neighbor_ratio",
]
BINARY_METRICS = ["mission_success", "safety_success"]
VARIANTS = ["B0", "P", "E", "Full"]


def bootstrap_ci(
    values: Iterable[float], seed: int = 42, statistic=np.mean
) -> tuple[float, float]:
    values = np.asarray(list(values), dtype=float)
    values = values[np.isfinite(values)]
    if not len(values):
        return math.nan, math.nan
    generator = np.random.default_rng(seed)
    samples = generator.choice(values, size=(10000, len(values)), replace=True)
    estimates = statistic(samples, axis=1)
    return tuple(np.quantile(estimates, [0.025, 0.975]).tolist())


def wilson_interval(success: int, total: int) -> tuple[float, float]:
    if total == 0:
        return math.nan, math.nan
    z = 1.959963984540054
    p = success / total
    denominator = 1.0 + z * z / total
    center = (p + z * z / (2 * total)) / denominator
    half = z * math.sqrt(
        p * (1 - p) / total + z * z / (4 * total * total)
    ) / denominator
    return center - half, center + half


def holm_adjust(p_values: Iterable[float]) -> List[float]:
    values = np.asarray(list(p_values), dtype=float)
    adjusted = np.full(len(values), np.nan)
    finite = np.flatnonzero(np.isfinite(values))
    if not len(finite):
        return adjusted.tolist()
    order = finite[np.argsort(values[finite])]
    running = 0.0
    count = len(order)
    for rank, index in enumerate(order):
        running = max(running, min(1.0, (count - rank) * values[index]))
        adjusted[index] = running
    return adjusted.tolist()


def collect(batch_dir: Path) -> pd.DataFrame:
    paths = sorted(batch_dir.glob("raw/**/trial_summary.csv"))
    if not paths:
        raise FileNotFoundError(f"no trial summaries under {batch_dir}")
    return pd.concat([pd.read_csv(path) for path in paths], ignore_index=True)


def validate_pairing(data: pd.DataFrame, expected_seeds: int = 15) -> None:
    formal = data[data["phase"] == "formal"]
    for scenario, group in formal.groupby("scenario"):
        pivot = group.pivot_table(
            index="seed", columns="variant", values="paired_input_digest",
            aggfunc="first")
        if list(pivot.reindex(columns=VARIANTS).columns) != VARIANTS:
            raise ValueError(f"{scenario}: missing variant")
        pivot = pivot.reindex(columns=VARIANTS)
        if len(pivot) != expected_seeds or pivot.isna().any().any():
            raise ValueError(f"{scenario}: incomplete paired matrix")
        if not pivot.nunique(axis=1).eq(1).all():
            raise ValueError(f"{scenario}: paired input digest mismatch")


def summarize(data: pd.DataFrame) -> List[Dict[str, object]]:
    rows: List[Dict[str, object]] = []
    for keys, group in data.groupby(["phase", "scenario", "variant"]):
        row: Dict[str, object] = dict(
            zip(["phase", "scenario", "variant"], keys))
        row["trial_count"] = len(group)
        for metric in BINARY_METRICS:
            successes = int(group[metric].astype(bool).sum())
            low, high = wilson_interval(successes, len(group))
            row.update({
                f"{metric}_rate": successes / len(group),
                f"{metric}_ci_low": low, f"{metric}_ci_high": high,
            })
        for metric in CONTINUOUS_METRICS:
            values = pd.to_numeric(group.get(metric), errors="coerce")
            finite = values[np.isfinite(values.to_numpy(dtype=float))]
            low, high = bootstrap_ci(finite)
            row.update({
                f"{metric}_n": len(finite),
                f"{metric}_mean": float(finite.mean()) if len(finite) else math.nan,
                f"{metric}_std": (
                    float(finite.std(ddof=1)) if len(finite) > 1 else math.nan),
                f"{metric}_ci_low": low, f"{metric}_ci_high": high,
            })
        rows.append(row)
    return rows


def exact_sign_flip(values: np.ndarray) -> float:
    values = np.asarray(values, dtype=float)
    values = values[np.isfinite(values)]
    if not len(values) or np.allclose(values, 0.0):
        return 1.0
    observed = abs(float(np.mean(values)))
    if len(values) > 20:
        generator = np.random.default_rng(42)
        signs = generator.choice((-1.0, 1.0), size=(1_000_000, len(values)))
    else:
        indices = np.arange(1 << len(values), dtype=np.uint64)[:, None]
        bits = (indices >> np.arange(len(values), dtype=np.uint64)) & 1
        signs = bits.astype(float) * 2.0 - 1.0
    estimates = np.abs(np.mean(signs * values[None, :], axis=1))
    return float(np.mean(estimates >= observed - 1e-12))


def factorial_tests(data: pd.DataFrame) -> List[Dict[str, object]]:
    rows: List[Dict[str, object]] = []
    formal = data[data["phase"] == "formal"]
    for scenario, scenario_data in formal.groupby("scenario"):
        for metric in CONTINUOUS_METRICS:
            pivot = scenario_data.pivot_table(
                index="seed", columns="variant", values=metric,
                aggfunc="first").reindex(columns=VARIANTS).dropna()
            if pivot.empty:
                continue
            contrasts = {
                "assignment": (
                    (pivot["P"] + pivot["Full"])
                    - (pivot["B0"] + pivot["E"])) / 2.0,
                "avoidance": (
                    (pivot["E"] + pivot["Full"])
                    - (pivot["B0"] + pivot["P"])) / 2.0,
                "interaction": (
                    pivot["Full"] - pivot["P"] - pivot["E"] + pivot["B0"]),
            }
            for effect, series in contrasts.items():
                values = series.to_numpy(dtype=float)
                low, high = bootstrap_ci(values)
                std = float(np.std(values, ddof=1)) if len(values) > 1 else 0.0
                rows.append({
                    "scenario": scenario, "metric": metric, "effect": effect,
                    "n": len(values), "mean_contrast": float(np.mean(values)),
                    "ci_low": low, "ci_high": high,
                    "effect_size_dz": (
                        float(np.mean(values)) / std if std > 0.0 else 0.0),
                    "p_value": exact_sign_flip(values),
                })
    for scenario in {row["scenario"] for row in rows}:
        indices = [i for i, row in enumerate(rows) if row["scenario"] == scenario]
        adjusted = holm_adjust(rows[i]["p_value"] for i in indices)
        for index, value in zip(indices, adjusted):
            rows[index]["p_value_holm"] = value
    return rows


def rank_biserial(differences: np.ndarray) -> float:
    values = differences[np.isfinite(differences)]
    values = values[~np.isclose(values, 0.0)]
    if not len(values):
        return 0.0
    ranks = rankdata(np.abs(values))
    return float(
        (ranks[values > 0].sum() - ranks[values < 0].sum()) / ranks.sum())


def planned_specs() -> Dict[str, List[tuple[str, str, List[str]]]]:
    performance = [
        "actual_min_distance", "mission_duration", "tracking_rmse",
        "mission_success", "safety_success"]
    return {
        "H1": [("B0", "P", [
            "nominal_xy_crossings", "nominal_proximity_crossings",
            "predicted_min_distance"])],
        "H2": [("B0", "E", [
            "actual_min_distance", "mission_success", "safety_success"])],
        "H3": [("E", "Full", [
            "iapf_active_duration", "mean_position_offset",
            "max_position_offset", "mean_acceleration_offset",
            "max_acceleration_offset", "trajectory_deviation"])],
        "H4": [
            ("B0", "Full", performance),
            ("P", "Full", performance),
            ("E", "Full", performance),
        ],
    }


def planned_tests(data: pd.DataFrame) -> List[Dict[str, object]]:
    formal = data[data["phase"] == "formal"]
    rows: List[Dict[str, object]] = []
    for hypothesis, specs in planned_specs().items():
        for scenario, scenario_data in formal.groupby("scenario"):
            if hypothesis == "H1" and not scenario.startswith("s1_"):
                continue
            for variant_a, variant_b, metrics in specs:
                for metric in metrics:
                    pivot = scenario_data.pivot_table(
                        index="seed", columns="variant", values=metric,
                        aggfunc="first").reindex(
                            columns=[variant_a, variant_b]).dropna()
                    if metric in BINARY_METRICS:
                        a = pivot[variant_a].astype(bool)
                        b = pivot[variant_b].astype(bool)
                        a_only = int((a & ~b).sum())
                        b_only = int((~a & b).sum())
                        discordant = a_only + b_only
                        p_value = (
                            float(binomtest(
                                min(a_only, b_only), discordant, 0.5).pvalue)
                            if discordant else 1.0)
                        rows.append({
                            "hypothesis": hypothesis, "scenario": scenario,
                            "metric": metric, "variant_a": variant_a,
                            "variant_b": variant_b, "test": "mcnemar_exact",
                            "n": len(pivot), "a_only": a_only,
                            "b_only": b_only, "p_value": p_value,
                        })
                        continue
                    differences = (
                        pivot[variant_b].to_numpy(dtype=float)
                        - pivot[variant_a].to_numpy(dtype=float))
                    if not len(differences) or np.allclose(differences, 0.0):
                        statistic, p_value = 0.0, 1.0
                    else:
                        result = wilcoxon(differences, zero_method="wilcox")
                        statistic, p_value = (
                            float(result.statistic), float(result.pvalue))
                    low, high = bootstrap_ci(differences, statistic=np.median)
                    rows.append({
                        "hypothesis": hypothesis, "scenario": scenario,
                        "metric": metric, "variant_a": variant_a,
                        "variant_b": variant_b, "test": "wilcoxon",
                        "n": len(differences),
                        "paired_median_difference": float(np.median(differences)),
                        "ci_low": low, "ci_high": high,
                        "rank_biserial": rank_biserial(differences),
                        "statistic": statistic, "p_value": p_value,
                    })
    for hypothesis in planned_specs():
        indices = [
            index for index, row in enumerate(rows)
            if row["hypothesis"] == hypothesis]
        adjusted = holm_adjust(rows[index]["p_value"] for index in indices)
        for index, value in zip(indices, adjusted):
            rows[index]["p_value_holm"] = value
    return rows


def rescue_events(data: pd.DataFrame) -> List[Dict[str, object]]:
    rows = []
    formal = data[data["phase"] == "formal"]
    for scenario, scenario_data in formal.groupby("scenario"):
        pivot = scenario_data.pivot_table(
            index="seed", columns="variant", values="mission_success",
            aggfunc="first").reindex(columns=VARIANTS).dropna()
        for off, on in [("B0", "E"), ("P", "Full")]:
            rescued = (~pivot[off].astype(bool)) & pivot[on].astype(bool)
            failures = ~pivot[off].astype(bool)
            rows.append({
                "scenario": scenario, "off_variant": off, "on_variant": on,
                "off_failures": int(failures.sum()),
                "rescue_count": int(rescued.sum()),
                "rescue_rate": (
                    float(rescued.sum() / failures.sum())
                    if failures.any() else math.nan),
            })
    return rows


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("batch_dir", type=Path)
    parser.add_argument("--allow-incomplete", action="store_true")
    args = parser.parse_args()
    data = collect(args.batch_dir)
    if not args.allow_incomplete:
        validate_pairing(data)
    summary_dir = args.batch_dir / "summaries"
    summary_dir.mkdir(parents=True, exist_ok=True)
    data.to_csv(summary_dir / "trial_summary.csv", index=False)
    write_dict_rows(summary_dir / "variant_summary.csv", summarize(data))
    write_dict_rows(
        summary_dir / "factorial_effects.csv", factorial_tests(data))
    write_dict_rows(
        summary_dir / "planned_comparisons.csv", planned_tests(data))
    write_dict_rows(summary_dir / "rescue_events.csv", rescue_events(data))
    print(summary_dir)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
