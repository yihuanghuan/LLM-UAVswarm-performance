"""Tests for experiment 05 trajectory definitions and aggregation."""

from __future__ import annotations

import math
import sys
from pathlib import Path

import numpy as np
import pytest


SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

from analyze_experiment_05 import build_method_summary, build_trial_summary  # noqa: E402
from trajectory_profiles import PROFILES, analytic_metrics, sample_progress  # noqa: E402


@pytest.mark.parametrize("profile", PROFILES)
def test_all_profiles_reach_endpoint(profile: str) -> None:
    values = sample_progress(profile, np.array([0.0, 8.0]), 8.0)
    assert values["position"][0] == pytest.approx(0.0)
    assert values["position"][-1] == pytest.approx(1.0)
    assert values["velocity"][-1] == pytest.approx(0.0)


def test_minimum_jerk_boundary_and_metrics() -> None:
    values = sample_progress("minimum_jerk", np.array([0.0, 8.0]), 8.0)
    assert np.allclose(values["velocity"], 0.0)
    assert np.allclose(values["acceleration"], 0.0)
    metrics = analytic_metrics("minimum_jerk", 10.0, 8.0)
    assert metrics.max_velocity == pytest.approx(15.0 * 10.0 / 64.0)
    assert metrics.max_jerk == pytest.approx(600.0 / 512.0)
    assert metrics.integrated_squared_jerk == pytest.approx(72000.0 / 8.0**5)
    assert metrics.integrated_squared_jerk_valid


def test_piecewise_discontinuities_are_not_reported_as_finite_jerk() -> None:
    step = analytic_metrics("step", 10.0, 8.0)
    linear = analytic_metrics("linear", 10.0, 8.0)
    trapezoidal = analytic_metrics("trapezoidal", 10.0, 8.0)
    assert not step.max_velocity_valid
    assert linear.max_velocity_valid and not linear.max_acceleration_valid
    assert trapezoidal.max_acceleration_valid and not trapezoidal.max_jerk_valid
    assert math.isnan(trapezoidal.integrated_squared_jerk)


def test_trapezoidal_piecewise_solution_is_continuous() -> None:
    epsilon = 1e-8
    times = np.array([2.0 - epsilon, 2.0 + epsilon, 6.0 - epsilon, 6.0 + epsilon])
    values = sample_progress("trapezoidal", times, 8.0)
    assert values["position"][0] == pytest.approx(values["position"][1], abs=1e-7)
    assert values["position"][2] == pytest.approx(values["position"][3], abs=1e-7)
    assert values["velocity"][0] == pytest.approx(values["velocity"][1], abs=1e-7)
    assert values["velocity"][2] == pytest.approx(values["velocity"][3], abs=1e-7)


def test_trial_and_method_summary_preserve_timeouts() -> None:
    rows = []
    for profile in PROFILES:
        for repeat in range(1, 4):
            for uav_id in range(1, 6):
                timed_out = profile == "step" and repeat == 1 and uav_id == 5
                rows.append(
                    {
                        "trial_id": f"{profile}_r{repeat:02d}",
                        "profile": profile,
                        "uav_id": uav_id,
                        "arrival_time_s": math.nan if timed_out else 8.0 + uav_id / 10.0,
                        "arrival_time_error_s": math.nan if timed_out else uav_id / 10.0,
                        "final_position_error_m": 0.1,
                        "tracking_rmse_m": 0.2,
                    }
                )
    trials = build_trial_summary(rows)
    methods = build_method_summary(trials)
    assert len(trials) == 12
    step = next(row for row in methods if row["profile"] == "step")
    assert step["successful_trials"] == 2
    assert step["timeout_rate"] == pytest.approx(1.0 / 3.0)
    minimum_jerk = next(row for row in methods if row["profile"] == "minimum_jerk")
    assert minimum_jerk["synchronization_error_mean_s"] == pytest.approx(0.4)
