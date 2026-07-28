from __future__ import annotations

import math
import sys
from pathlib import Path

import numpy as np
import pytest


REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = REPO_ROOT / "experiments" / "scripts"
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(SCRIPTS))

from analyze_experiment_07 import (  # noqa: E402
    expected_task_gain,
    first_sustained_time,
    minimum_jerk_progress,
    quaternion_to_roll_pitch,
)
from experiment_07_config import COMMANDS, METHODS, REPEATS, validate  # noqa: E402
from experiment_07_trial import ParseGateError, validate_compiled_result  # noqa: E402
from tools.trajectory_metrics.rosbag_to_csv import flatten_message  # noqa: E402


def compiled_task(style: str = "normal"):
    return {
        "task_sequences": [{
            "task_sequence_id": 1,
            "duration_seconds": 3.0,
            "uav_id": [1],
            "uav_count": 1,
            "motion_profile": style,
            "global_center": [6.0, 3.0, 5.0],
            "parametric_data": {
                "formation_type": "Line",
                "formation_radius": 1.0,
            },
            "iapf_safety_margin_factor": 1.0,
        }]
    }


def test_preregistered_design_is_complete():
    validate()
    assert REPEATS == 5
    assert set(METHODS) == {"fixed_gain", "task_conditioned"}
    assert set(COMMANDS) == {"smooth", "normal", "aggressive"}


def test_parse_gate_accepts_exact_task():
    task = validate_compiled_result(compiled_task("smooth"), "smooth")
    assert task["duration_seconds"] == 3.0


@pytest.mark.parametrize("field", ["duration", "style", "center", "formation"])
def test_parse_gate_rejects_preregistration_drift(field):
    result = compiled_task()
    task = result["task_sequences"][0]
    if field == "duration":
        task["duration_seconds"] = 4.0
    elif field == "style":
        task["motion_profile"] = "smooth"
    elif field == "center":
        task["global_center"] = [5.0, 3.0, 5.0]
    else:
        task["parametric_data"]["formation_type"] = "Circle"
    with pytest.raises(ParseGateError):
        validate_compiled_result(result, "normal")


def test_minimum_jerk_reference_endpoints():
    progress = minimum_jerk_progress(np.array([-1.0, 0.0, 1.5, 3.0, 4.0]), 3.0)
    assert np.allclose(progress[[0, 1]], 0.0)
    assert math.isclose(progress[3], 1.0)
    assert math.isclose(progress[4], 1.0)
    assert math.isclose(progress[2], 0.5)


def test_task_conditioned_gain_matches_controller_formula():
    assert math.isclose(expected_task_gain("smooth", 3.0, 3.0), 0.75)
    assert math.isclose(
        expected_task_gain("aggressive", 7.8, 3.0),
        1.3,
    )


def test_quaternion_conversion_identity_and_roll():
    roll, pitch = quaternion_to_roll_pitch(
        np.array([1.0]), np.array([0.0]), np.array([0.0]), np.array([0.0])
    )
    assert np.allclose(roll, 0.0)
    assert np.allclose(pitch, 0.0)
    half = math.radians(15.0)
    roll, pitch = quaternion_to_roll_pitch(
        np.array([math.cos(half)]),
        np.array([math.sin(half)]),
        np.array([0.0]),
        np.array([0.0]),
    )
    assert np.allclose(roll, 30.0)
    assert np.allclose(pitch, 0.0)


def test_settling_requires_continuous_dwell():
    times = np.arange(0.0, 2.02, 0.02)
    conditions = times >= 0.5
    assert math.isclose(first_sustained_time(times, conditions, 1.0), 0.5)
    conditions[(times > 1.0) & (times < 1.1)] = False
    assert math.isnan(first_sustained_time(times, conditions, 1.0))


def test_controller_and_launch_expose_experiment_switches():
    controller = (
        REPO_ROOT
        / "minisnap_LADRC/ladrc_controller/src/ladrc_position_controller_node.cpp"
    ).read_text(encoding="utf-8")
    launch = (
        REPO_ROOT
        / "minisnap_LADRC/ladrc_controller/launch/swarm_launch.py"
    ).read_text(encoding="utf-8")
    assert 'declare_parameter("enable_ladrc_accel_feedforward", false)' in controller
    assert 'declare_parameter("semantic_gain_mode", "task_conditioned")' in controller
    assert "enable_iapf_accel_feedforward || enable_ladrc_accel_feedforward" in controller
    assert "semantic_gain_mode" in launch
    assert "fixed_gain_multiplier" in launch


def test_rosbag_converter_flattens_px4_numpy_arrays():
    flattened = flatten_message(np.array([1.0, 2.0, 3.0]))
    assert flattened == {"_0": 1.0, "_1": 2.0, "_2": 3.0}
