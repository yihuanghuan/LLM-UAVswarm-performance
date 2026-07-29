import math

import numpy as np
import pandas as pd

from aggregate_trials import (
    METRICS,
    bootstrap_ci,
    statistical_tests,
    wilson_interval,
)


def test_bootstrap_is_deterministic_and_finite():
    first = bootstrap_ci(np.array([1.0, 2.0, 3.0]))
    second = bootstrap_ci(np.array([1.0, 2.0, 3.0]))
    assert first == second
    assert all(math.isfinite(value) for value in first)


def test_wilson_interval_contains_observed_rate():
    low, high = wilson_interval(8, 10)
    assert low < 0.8 < high


def test_statistical_tests_use_only_planned_paired_comparison():
    rows = []
    for seed in (42, 43):
        for method in ("IAPF_OFF", "IAPF_ON"):
            row = {
                "phase": "fallback",
                "family": "fallback",
                "scenario": "staggered_crossing_delay",
                "method": method,
                "seed": seed,
                "mission_success": method == "IAPF_ON",
            }
            row.update({
                metric: float(seed + (method == "IAPF_ON"))
                for metric in METRICS
            })
            if method == "IAPF_ON":
                row["recovery_time"] = math.nan
            rows.append(row)

    tests = statistical_tests(pd.DataFrame(rows))
    missing_pair = next(
        row for row in tests
        if row["metric"] == "recovery_time"
        and row["test"] == "wilcoxon"
        and row["method_a"] == "IAPF_OFF"
        and row["method_b"] == "IAPF_ON"
    )
    assert missing_pair["n_total"] == 2
    assert missing_pair["n_valid"] == 0
    assert math.isnan(missing_pair["p_value"])
    mcnemar = next(row for row in tests if row["test"] == "mcnemar_exact")
    assert mcnemar["fallback_rescue_rate"] == 1.0
