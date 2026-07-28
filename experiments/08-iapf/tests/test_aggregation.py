import math

import numpy as np

from aggregate_trials import bootstrap_ci, holm_adjust, wilson_interval


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
