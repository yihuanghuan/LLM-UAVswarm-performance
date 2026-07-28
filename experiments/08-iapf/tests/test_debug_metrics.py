import pytest

from analysis_core import debug_metrics


def make_row(timestamp, active, position_saturated, acceleration_saturated):
    return {
        "timestamp": timestamp,
        "uav_id": 1,
        "iapf_active": active,
        "raw_repulsion_x": 3 if active else 0,
        "raw_repulsion_y": 4 if active else 0,
        "raw_repulsion_z": 0,
        "position_saturated": position_saturated,
        "acceleration_saturated": acceleration_saturated,
        "modulated_acceleration_x": 1,
        "modulated_acceleration_y": 0,
        "modulated_acceleration_z": 0,
    }


def test_activation_without_saturation():
    result = debug_metrics([
        make_row(0.0, False, False, False),
        make_row(0.1, True, False, False),
        make_row(0.2, True, False, False),
        make_row(0.3, False, False, False),
    ])
    assert result["iapf_activation_time"] == pytest.approx(0.2)
    assert result["mean_repulsion_norm"] == pytest.approx(5.0)
    assert result["position_saturation_ratio"] == 0.0


def test_activation_with_both_saturations():
    result = debug_metrics([
        make_row(0.0, True, True, True),
        make_row(0.1, True, False, True),
    ])
    assert result["position_saturation_ratio"] == 0.5
    assert result["acceleration_saturation_ratio"] == 1.0
