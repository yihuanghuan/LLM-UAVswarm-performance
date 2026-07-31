import math
import json

import pytest

from summarize_system_trials import (
    analyze_trial,
    activation_metrics,
    distance_series,
    event_count,
    mask_duration,
    tracking_metrics,
)
from system_common import load_yaml, write_csv, write_json


def test_event_count_and_duration_count_contiguous_events():
    times = [0.0, 0.1, 0.2, 0.3, 0.4]
    mask = [False, True, True, False, True]
    assert event_count(mask) == 2
    assert mask_duration(times, mask) == pytest.approx(0.2)


def test_tracking_error_uses_modulated_reference():
    odom = [
        {"timestamp": "1.0", "uav_id": "1", "x": "2", "y": "0", "z": "3"}
    ]
    iapf = [{
        "timestamp": "1.0", "mission_id": "7", "uav_id": "1",
        "modulated_ref_x": "2", "modulated_ref_y": "0",
        "modulated_ref_z": "3", "nominal_ref_x": "1.9",
        "nominal_ref_y": "0", "nominal_ref_z": "3",
    }]
    control = [{
        "mission_id": "7", "uav_id": "1", "peak_velocity": "2",
        "peak_acceleration": "3", "gain_multiplier": "1.2",
    }]
    result = tracking_metrics(odom, iapf, control)[0]
    assert result["controller_tracking_rmse"] == pytest.approx(0.0)
    assert result["avoidance_deviation"] == pytest.approx(0.1)


def test_synchronized_pairwise_distance_uses_all_uavs():
    odom = [
        {"timestamp": "0.00", "uav_id": "1", "x": "0", "y": "0", "z": "0"},
        {"timestamp": "0.02", "uav_id": "2", "x": "3", "y": "0", "z": "0"},
        {"timestamp": "0.01", "uav_id": "3", "x": "0", "y": "4", "z": "0"},
    ]
    series = distance_series(odom)
    assert series == [(0.0, 3.0)]


def test_iapf_activation_and_stale_ratios():
    rows = [
        {
            "timestamp": str(index * 0.1), "uav_id": "1",
            "iapf_active": str(active), "hysteresis_active": str(active),
            "nearest_neighbor_closing_speed": "0.4",
            "active_neighbor_count": "2", "position_saturated": "false",
            "acceleration_saturated": str(active),
            "valid_neighbor_count": "6", "stale_neighbor_count": "1",
        }
        for index, active in enumerate([False, True, True, False, True])
    ]
    metrics = activation_metrics(rows)
    assert metrics["iapf_activation_count"] == 2
    assert metrics["iapf_active_duration"] == pytest.approx(0.2)
    assert metrics["maximum_active_neighbor_count"] == 2
    assert metrics["stale_neighbor_ratio"] == pytest.approx(1 / 7)
    assert math.isfinite(metrics["mean_closing_speed_at_activation"])


def test_complete_synthetic_trial_is_accepted(tmp_path):
    manifest = {
        "experiment_id": "experiments_10", "batch_id": "synthetic",
        "task_type": "task_a_simple", "trial_id": 1,
        "semantic_success": True, "execution_success": True,
        "safety_success": False, "overall_success": False,
        "failure_reason": "unknown",
    }
    write_json(tmp_path / "manifest.json", manifest)
    odom = []
    iapf = []
    resources = []
    for index in range(51):
        timestamp = index * 0.02
        resources.append({
            "timestamp": timestamp, "cpu_percent": 30,
            "memory_used_bytes": 1000, "memory_percent": 10,
            "real_time_factor": 0.99,
        })
        for uid in range(1, 9):
            angle = 2 * math.pi * (uid - 1) / 8
            point = (4 * math.cos(angle), 4 * math.sin(angle), 5)
            if index % 5 == 0:
                odom.append({
                    "timestamp": timestamp, "uav_id": uid,
                    "x": point[0], "y": point[1], "z": point[2],
                    "speed": 0,
                })
            iapf.append({
                "timestamp": timestamp, "mission_id": 1, "uav_id": uid,
                "iapf_active": False, "hysteresis_active": False,
                "active_neighbor_count": 0, "valid_neighbor_count": 7,
                "stale_neighbor_count": 0, "position_saturated": False,
                "acceleration_saturated": False,
                "nearest_neighbor_closing_speed": 0,
                "modulated_ref_x": point[0], "modulated_ref_y": point[1],
                "modulated_ref_z": point[2], "nominal_ref_x": point[0],
                "nominal_ref_y": point[1], "nominal_ref_z": point[2],
            })
    write_csv(
        tmp_path / "odom.csv", odom,
        ["timestamp", "uav_id", "x", "y", "z", "speed"])
    write_csv(
        tmp_path / "iapf_debug.csv", iapf, sorted({
            key for row in iapf for key in row}))
    write_csv(
        tmp_path / "system_resources.csv", resources, list(resources[0]))
    commands = [{
        "timestamp": 0, "mission_id": 1, "uav_id": uid, "duration": 10,
    } for uid in range(1, 9)]
    status = [{
        "timestamp": 10, "mission_id": 1, "uav_id": uid,
        "is_hover_stable": True,
    } for uid in range(1, 9)]
    write_csv(
        tmp_path / "swarm_commands.csv", commands, list(commands[0]))
    write_csv(tmp_path / "status.csv", status, list(status[0]))
    events = [
        {
            "timestamp": 0, "event": "stage_start", "stage_id": 1,
            "mission_ids": json.dumps([1]),
            "uav_ids": json.dumps(list(range(1, 9))),
            "success": "", "failure_reason": "", "duration_s": "",
        },
        {
            "timestamp": 10, "event": "stage_end", "stage_id": 1,
            "mission_ids": json.dumps([1]),
            "uav_ids": json.dumps(list(range(1, 9))),
            "success": True, "failure_reason": "", "duration_s": 10,
        },
    ]
    write_csv(tmp_path / "mission_events.csv", events, list(events[0]))
    result = analyze_trial(tmp_path, load_yaml())
    assert result["trial"]["overall_success"]
    assert result["trial"]["min_distance"] > 1.0
    assert result["resource"]["control_loop_effective_frequency"] == pytest.approx(
        50.0)
