import math
import sys
from pathlib import Path


SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

from analyze_tracking_performance import (  # noqa: E402
    analyze_uav_rows,
    first_sustained_time,
    summarize_methods,
    summarize_trials,
)


def row(time_s, actual_x, speed, reference_x, target_x=1.0):
    return {
        "elapsed_time": str(time_s),
        "requested_duration": "2.0",
        "uav_id": "1",
        "start_pos_x": "0", "start_pos_y": "0", "start_pos_z": "0",
        "target_pos_x": str(target_x), "target_pos_y": "0", "target_pos_z": "0",
        "reference_pos_x": str(reference_x),
        "reference_pos_y": "0", "reference_pos_z": "0",
        "actual_pos_x": str(actual_x), "actual_pos_y": "0", "actual_pos_z": "0",
        "actual_velocity_x": str(speed),
        "actual_velocity_y": "0", "actual_velocity_z": "0",
        "tracking_error": str(abs(reference_x - actual_x)),
    }


def metadata(trial_id="trial_1"):
    return {
        "trial_id": trial_id,
        "scenario": "single_uav",
        "method": "minimum_jerk_ladrc",
        "repeat": 1,
    }


def test_first_sustained_time_requires_full_dwell():
    times = [index / 10.0 for index in range(21)]
    interrupted = [False] + [True] * 9 + [False] + [True] * 10
    sustained = [False] + [True] * 20
    assert math.isnan(first_sustained_time(times, interrupted, 1.0))
    assert first_sustained_time(times, sustained, 1.0) == 0.1


def test_first_sustained_time_rejects_missing_sample_gap():
    assert math.isnan(first_sustained_time([0.0, 0.2, 0.8, 1.2], [True] * 4, 1.0))


def test_uav_metrics_use_command_window_and_projected_overshoot():
    rows = [
        row(0.0, 0.0, 0.5, 0.0),
        row(1.0, 0.4, 0.5, 0.5),
        row(2.0, 1.1, 0.2, 1.0),
        *[row(2.0 + index / 10.0, 1.1 - index / 100.0, 0.2, 1.0)
          for index in range(1, 11)],
        row(3.1, 1.0, 0.1, 1.0),
    ]
    summary, samples = analyze_uav_rows(rows, metadata())
    expected = math.sqrt((0.0**2 + 0.1**2 + 0.1**2) / 3.0)
    assert math.isclose(summary["tracking_rmse_m"], expected)
    assert math.isclose(summary["max_tracking_error_m"], 0.1)
    assert summary["arrival_time_s"] == 2.0
    assert math.isclose(summary["settling_time_s"], 2.0)
    assert math.isclose(summary["overshoot_m"], 0.1)
    assert len(samples) == len(rows)


def test_trial_and_method_arrival_variance():
    base = {
        **metadata(),
        "samples": 10,
        "requested_duration_s": 2.0,
        "tracking_rmse_m": 0.2,
        "max_tracking_error_m": 0.4,
        "settling_time_s": 2.2,
        "overshoot_m": 0.1,
        "max_actual_velocity_mps": 1.0,
        "max_actual_acceleration_mps2": 2.0,
        "final_position_error_m": 0.05,
    }
    rows = [
        {**base, "uav_id": 1, "arrival_time_s": 2.0},
        {**base, "uav_id": 2, "arrival_time_s": 4.0},
    ]
    trial = summarize_trials(rows)[0]
    method = summarize_methods(rows)[0]
    assert trial["arrival_time_variance_s2"] == 1.0
    assert trial["all_arrived"] is True
    assert method["arrival_success_rate"] == 1.0


def test_missing_arrival_is_preserved_as_failure():
    base = {
        **metadata(),
        "uav_id": 1,
        "samples": 10,
        "requested_duration_s": 2.0,
        "tracking_rmse_m": 0.2,
        "max_tracking_error_m": 0.4,
        "arrival_time_s": math.nan,
        "settling_time_s": math.nan,
        "overshoot_m": 0.0,
        "max_actual_velocity_mps": 1.0,
        "max_actual_acceleration_mps2": 2.0,
        "final_position_error_m": 0.5,
    }
    assert summarize_trials([base])[0]["all_settled"] is False
    assert summarize_methods([base])[0]["settling_success_rate"] == 0.0
