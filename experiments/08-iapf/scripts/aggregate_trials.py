#!/usr/bin/env python3
"""Aggregate experiment 08 v2 trials and run planned paired statistics."""

from __future__ import annotations

import argparse
import math
from pathlib import Path
from typing import Dict, List

import numpy as np
import pandas as pd
from scipy.stats import binomtest, wilcoxon

from analysis_core import write_dict_rows


METRICS = [
    "minimum_inter_agent_distance", "violation_event_count",
    "risk_exposure_time", "risk_integral", "mean_trajectory_deviation",
    "recovery_time", "iapf_activation_ratio", "activation_event_count",
    "unnecessary_intervention_rate", "intervention_latency",
    "completion_time", "path_length_ratio", "final_formation_error",
    "mean_repulsion_norm", "max_repulsion_norm",
    "integrated_squared_acceleration",
]


def bootstrap_ci(
    values: np.ndarray, seed: int = 42, statistic=np.median
) -> tuple[float, float]:
    values = np.asarray(values, dtype=float)
    values = values[np.isfinite(values)]
    if len(values) == 0:
        return math.nan, math.nan
    generator = np.random.default_rng(seed)
    samples = generator.choice(values, size=(10000, len(values)), replace=True)
    estimates = statistic(samples, axis=1)
    return tuple(np.quantile(estimates, [0.025, 0.975]).tolist())


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


def collect(batch_dir: Path) -> pd.DataFrame:
    paths = sorted(batch_dir.glob("raw/**/trial_summary.csv"))
    if not paths:
        raise FileNotFoundError(f"no trial summaries under {batch_dir}")
    return pd.concat([pd.read_csv(path) for path in paths], ignore_index=True)


def summarize(data: pd.DataFrame) -> List[Dict[str, object]]:
    rows: List[Dict[str, object]] = []
    group_fields = ["phase", "family", "scenario", "method"]
    for keys, group in data.groupby(group_fields, dropna=False):
        base = dict(zip(group_fields, keys))
        base["trial_count"] = len(group)
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
                f"{metric}_mean": (
                    float(np.mean(finite)) if len(finite) else math.nan),
                f"{metric}_std": (
                    float(np.std(finite, ddof=1))
                    if len(finite) > 1 else math.nan),
                f"{metric}_median": (
                    float(np.median(finite)) if len(finite) else math.nan),
                f"{metric}_q1": (
                    float(np.quantile(finite, 0.25))
                    if len(finite) else math.nan),
                f"{metric}_q3": (
                    float(np.quantile(finite, 0.75))
                    if len(finite) else math.nan),
                f"{metric}_ci_low": ci_low,
                f"{metric}_ci_high": ci_high,
            })
        rows.append(base)
    return rows


def comparison_specs() -> Dict[str, List[tuple[str, str]]]:
    return {
        "nonintrusive": [("IAPF_OFF", "IAPF_ON")],
        "fallback": [("IAPF_OFF", "IAPF_ON")],
        "complement": [
            ("DIST_OFF", "DIST_ON"), ("SAFE_OFF", "SAFE_ON"),
            ("DIST_OFF", "SAFE_OFF"), ("DIST_ON", "SAFE_ON")],
        "stress": [("STRESS_OFF", "STRESS_ON")],
    }


def _paired(
    scenario_data: pd.DataFrame, method_a: str, method_b: str, metric: str
) -> tuple[pd.DataFrame, np.ndarray]:
    pivot = scenario_data.pivot_table(
        index="seed", columns="method", values=metric, aggfunc="first")
    pivot = pivot.reindex(columns=[method_a, method_b])
    paired = pivot.dropna()
    values = (
        paired[method_b].to_numpy(dtype=float)
        - paired[method_a].to_numpy(dtype=float))
    if metric in ("risk_integral", "risk_exposure_time",
                  "violation_event_count"):
        values *= -1.0
    return paired, values


def statistical_tests(data: pd.DataFrame) -> List[Dict[str, object]]:
    """Run only the comparisons declared by the v2 protocol."""
    formal = data[data["phase"] != "pilot"].copy()
    rows: List[Dict[str, object]] = []
    for family, specs in comparison_specs().items():
        family_data = formal[formal["family"] == family]
        for scenario, scenario_data in family_data.groupby("scenario"):
            for method_a, method_b in specs:
                for metric in METRICS:
                    paired, differences = _paired(
                        scenario_data, method_a, method_b, metric)
                    statistic = math.nan
                    p_value = math.nan
                    if len(differences):
                        if np.allclose(differences, 0.0):
                            statistic, p_value = 0.0, 1.0
                        else:
                            result = wilcoxon(differences, zero_method="wilcox")
                            statistic = float(result.statistic)
                            p_value = float(result.pvalue)
                    ci_low, ci_high = bootstrap_ci(differences)
                    rows.append({
                        "family": family, "scenario": scenario,
                        "metric": metric, "test": "wilcoxon",
                        "method_a": method_a, "method_b": method_b,
                        "difference_direction": (
                            "a_minus_b" if metric in (
                                "risk_integral", "risk_exposure_time",
                                "violation_event_count")
                            else "b_minus_a"),
                        "n_total": len(scenario_data["seed"].unique()),
                        "n_valid": len(differences),
                        "paired_median_difference": (
                            float(np.median(differences))
                            if len(differences) else math.nan),
                        "bootstrap_ci_low": ci_low,
                        "bootstrap_ci_high": ci_high,
                        "statistic": statistic, "p_value": p_value,
                    })

                success = scenario_data.pivot_table(
                    index="seed", columns="method",
                    values="mission_success", aggfunc="first").reindex(
                        columns=[method_a, method_b]).dropna()
                a_success = success[method_a].astype(bool)
                b_success = success[method_b].astype(bool)
                a_only = int((a_success & ~b_success).sum())
                b_only = int((~a_success & b_success).sum())
                discordant = a_only + b_only
                p_value = (
                    float(binomtest(
                        min(a_only, b_only), discordant, 0.5,
                        alternative="two-sided").pvalue)
                    if discordant else 1.0)
                off_failures = int((~a_success).sum())
                rescue = int((~a_success & b_success).sum())
                rows.append({
                    "family": family, "scenario": scenario,
                    "metric": "mission_success", "test": "mcnemar_exact",
                    "method_a": method_a, "method_b": method_b,
                    "n_total": len(success), "n_valid": len(success),
                    "a_success_b_failure": a_only,
                    "a_failure_b_success": b_only,
                    "p_value": p_value,
                    "fallback_rescue_rate": (
                        rescue / off_failures if off_failures else math.nan),
                })
    return rows


def ablation_table(data: pd.DataFrame) -> pd.DataFrame:
    scenario = data[
        (data["phase"] != "pilot")
        & (data["scenario"] == "staggered_crossing_delay")
        & data["method"].isin(["IAPF_OFF", "ABL_POSITION", "IAPF_ON"])
    ].copy()
    scenario["ablation_mode"] = scenario["method"].map({
        "IAPF_OFF": "off", "ABL_POSITION": "iapf_position",
        "IAPF_ON": "iapf_dual"})
    return scenario


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
        write_dict_rows(summary_dir / "paired_statistics.csv", tests)
    ablation_table(data).to_csv(
        summary_dir / "position_channel_ablation.csv", index=False)
    print(summary_dir)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
