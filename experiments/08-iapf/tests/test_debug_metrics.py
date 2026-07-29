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


def test_event_latency_and_unnecessary_intervention():
    rows = [
        make_row(0.0, False, False, False),
        make_row(0.1, False, False, False),
        make_row(0.2, True, False, False),
        make_row(0.3, False, False, False),
        make_row(0.4, True, False, False),
    ]
    rows[1].update({
        "nearest_neighbor_distance": 1.4,
        "nearest_neighbor_closing_speed": 0.5,
    })
    rows[2].update({
        "nearest_neighbor_distance": 1.3,
        "nearest_neighbor_closing_speed": 0.5,
    })
    rows[4].update({
        "nearest_neighbor_distance": 1.6,
        "nearest_neighbor_closing_speed": -0.2,
    })
    result = debug_metrics(rows)
    assert result["activation_event_count"] == 2
    assert result["unnecessary_intervention_rate"] == 0.5
    assert result["intervention_latency"] == pytest.approx(0.1)
