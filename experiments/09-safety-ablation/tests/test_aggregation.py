import math

import numpy as np
import pandas as pd

from aggregate_trials import (
    bootstrap_ci,
    exact_sign_flip,
    holm_adjust,
    planned_tests,
    rank_biserial,
    validate_pairing,
    wilson_interval,
)


def test_bootstrap_is_deterministic_and_finite():
    first = bootstrap_ci([1.0, 2.0, 3.0])
    second = bootstrap_ci([1.0, 2.0, 3.0])
    assert first == second
    assert all(math.isfinite(value) for value in first)


def test_wilson_interval_contains_observed_rate():
    low, high = wilson_interval(8, 10)
    assert low < 0.8 < high


def test_holm_is_monotone_in_sorted_p_values():
    assert holm_adjust([0.01, 0.04, 0.03]) == [0.03, 0.06, 0.06]


def test_sign_flip_and_rank_biserial_detect_consistent_direction():
    values = np.ones(5)
    assert exact_sign_flip(values) == 2 / 32
    assert rank_biserial(values) == 1.0


def test_pairing_rejects_digest_mismatch():
    rows = []
    for seed in range(15):
        for variant in ("B0", "P", "E", "Full"):
            rows.append({
                "phase": "formal", "scenario": "scene", "seed": seed,
                "variant": variant,
                "paired_input_digest": (
                    "bad" if seed == 0 and variant == "Full" else f"d{seed}"),
            })
    with np.testing.assert_raises(ValueError):
        validate_pairing(pd.DataFrame(rows))


def test_planned_tests_include_exact_mcnemar():
    rows = []
    for seed in (1, 2, 3):
        for index, variant in enumerate(("B0", "P", "E", "Full")):
            rows.append({
                "phase": "formal", "scenario": "s1_crossing_4",
                "variant": variant, "seed": seed,
                "mission_success": variant in ("E", "Full"),
                "safety_success": variant == "Full",
                "actual_min_distance": float(index),
                "mission_duration": float(10 - index),
                "tracking_rmse": float(4 - index),
                "nominal_xy_crossings": float(4 - index),
                "nominal_proximity_crossings": float(4 - index),
                "predicted_min_distance": float(index),
                "iapf_active_duration": float(4 - index),
                "mean_position_offset": float(4 - index),
                "max_position_offset": float(4 - index),
                "mean_acceleration_offset": float(4 - index),
                "max_acceleration_offset": float(4 - index),
                "trajectory_deviation": float(4 - index),
            })
    tests = planned_tests(pd.DataFrame(rows))
    assert any(row["test"] == "mcnemar_exact" for row in tests)
    assert all("p_value_holm" in row for row in tests)
