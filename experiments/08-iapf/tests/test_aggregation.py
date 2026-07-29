import math

import numpy as np
import pandas as pd

from aggregate_trials import (
    METRICS,
    bootstrap_ci,
    holm_adjust,
    statistical_tests,
    wilson_interval,
)


def test_bootstrap_is_deterministic_and_finite():
    first = bootstrap_ci(np.array([1.0, 2.0, 3.0]))
    second = bootstrap_ci(np.array([1.0, 2.0, 3.0]))
    assert first == second
    assert all(math.isfinite(value) for value in first)


def test_holm_adjustment_is_monotonic_in_sorted_order():
    adjusted = holm_adjust([0.01, 0.04, 0.03])
    assert adjusted[0] <= adjusted[2] <= adjusted[1]
    assert all(0.0 <= value <= 1.0 for value in adjusted)


def test_wilson_interval_contains_observed_rate():
    low, high = wilson_interval(8, 10)
    assert low < 0.8 < high


def test_statistical_tests_report_all_nan_method_as_no_valid_pairs():
    rows = []
    for seed in (42, 43):
        for method_index in range(6):
            row = {
                "phase": "main",
                "scenario": "head_on",
                "method": f"M{method_index}",
                "seed": seed,
            }
            row.update({
                metric: float(seed + method_index)
                for metric in METRICS
            })
            if method_index == 1:
                row["recovery_time"] = math.nan
            rows.append(row)

    tests = statistical_tests(pd.DataFrame(rows))
    missing_pair = next(
        row for row in tests
        if row["metric"] == "recovery_time"
        and row["test"] == "wilcoxon"
        and row["method_a"] == "M0"
        and row["method_b"] == "M1"
    )
    assert missing_pair["n_total"] == 2
    assert missing_pair["n_valid"] == 0
    assert math.isnan(missing_pair["p_value"])
