import csv
import json

from analysis_core import analyze_trial


def write_csv(path, fields, rows):
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def test_complete_synthetic_trial(tmp_path):
    metadata = {
        "experiment_id": "synthetic", "batch_id": "test", "phase": "main",
        "scenario": "head_on", "method": "M3", "trial": 1, "seed": 42,
        "safety_thresholds": {
            "d_collision": 0.7, "d_violation": 1.0,
            "r_iapf": 1.5, "d_assignment": 2.0,
        },
        "analysis": {
            "sample_hz": 20.0, "max_odom_gap": 0.1,
            "final_position_tolerance": 0.3, "stall_distance": 0.5,
            "stall_speed": 0.15, "stall_duration": 2.0,
        },
        "outcome": {
            "hover_stable": True, "timed_out": False,
            "px4_failsafe": False, "node_crash": False,
            "failure_reason": "none",
        },
    }
    (tmp_path / "run_metadata.json").write_text(json.dumps(metadata))
    write_csv(
        tmp_path / "assignment.csv",
        ["uav_id", "target_x", "target_y", "target_z"],
        [
            {"uav_id": 1, "target_x": 1, "target_y": 0, "target_z": 2},
            {"uav_id": 2, "target_x": -1, "target_y": 0, "target_z": 2},
        ])
    odom = []
    debug = []
    for index in range(21):
        timestamp = index * 0.05
        progress = index / 20
        for uav_id, start, end in ((1, -1, 1), (2, 1, -1)):
            x = start + (end - start) * progress
            odom.append({
                "timestamp": timestamp, "uav_id": uav_id,
                "x": x, "y": 0, "z": 2})
            debug.append({
                "timestamp": timestamp, "uav_id": uav_id,
                "iapf_active": 0.3 <= timestamp <= 0.7,
                "raw_repulsion_x": 1, "raw_repulsion_y": 0,
                "raw_repulsion_z": 0, "position_saturated": False,
                "acceleration_saturated": False,
                "nominal_ref_x": x, "nominal_ref_y": 0, "nominal_ref_z": 2,
                "modulated_acceleration_x": 0,
                "modulated_acceleration_y": 0,
                "modulated_acceleration_z": 0,
            })
    write_csv(tmp_path / "odom.csv", list(odom[0]), odom)
    write_csv(tmp_path / "iapf_debug.csv", list(debug[0]), debug)
    write_csv(
        tmp_path / "mission_events.csv",
        ["timestamp", "event", "uav_id"],
        [
            {"timestamp": 0.9, "event": "hover_stable", "uav_id": 1},
            {"timestamp": 0.95, "event": "hover_stable", "uav_id": 2},
        ])

    pairs, summary = analyze_trial(tmp_path)

    assert pairs[0].collision_event_count == 1
    assert summary["failure_reason"] == "collision"
    assert summary["mission_success"] is False
    assert summary["recovery_time"] > 0
