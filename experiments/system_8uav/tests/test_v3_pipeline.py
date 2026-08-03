import json
import math

from analysis_v3 import (
    final_interval_from_events, final_interval_from_status, stage_timing_rows,
)
from run_batch import initial_schedule
from run_trial import FROZEN_LFS_ROOT, load_frozen_lfs
from system_common import load_task, load_yaml, verify_llm_intent, write_csv


def test_final_confirmed_interval_uses_last_still_valid_interval():
    events = [
        {"timestamp": 2.0, "event": "stable_candidate_enter", "stage_id": 1,
         "mission_id": 7, "uav_id": 1},
        {"timestamp": 3.0, "event": "stable_confirmed", "stage_id": 1,
         "mission_id": 7, "uav_id": 1},
        {"timestamp": 4.0, "event": "stable_confirmed_exit", "stage_id": 1,
         "mission_id": 7, "uav_id": 1},
        {"timestamp": 5.0, "event": "stable_candidate_enter", "stage_id": 1,
         "mission_id": 7, "uav_id": 1},
        {"timestamp": 6.0, "event": "stable_confirmed", "stage_id": 1,
         "mission_id": 7, "uav_id": 1},
    ]
    interval = final_interval_from_events(events, (7, 1), 1, 1.0, 8.0)
    assert interval["confirmed"] == 6.0
    assert interval["candidate"] == 5.0
    assert interval["state"] == 2


def test_status_replay_has_unified_position_acceptance_boundary():
    status = [
        {"timestamp": 1.0, "mission_id": 1, "uav_id": 1,
         "position_error": 0.40, "speed": 0.30},
        {"timestamp": 2.0, "mission_id": 1, "uav_id": 1,
         "position_error": 0.45, "speed": 0.35},
    ]
    interval = final_interval_from_status(status, (1, 1), 0.0, 3.0, {
        "position_enter": 0.40, "speed_enter": 0.30,
        "position_exit": 0.50, "speed_exit": 0.40, "hold_time": 1.0,
    })
    assert interval["state"] == 2
    assert interval["confirmed"] == 2.0


def test_missing_final_confirmed_is_nan_not_zero(tmp_path):
    event_fields = [
        "timestamp", "event", "stage_id", "mission_ids", "uav_ids",
        "mission_id", "uav_id", "success", "failure_reason",
    ]
    events = [
        {"timestamp": 1, "event": "stage_start", "stage_id": 1,
         "mission_ids": json.dumps([1]), "uav_ids": json.dumps([1])},
        {"timestamp": 2, "event": "assignment_complete", "stage_id": 1},
        {"timestamp": 3, "event": "command_dispatch", "stage_id": 1,
         "mission_id": 1, "uav_id": 1},
        {"timestamp": 3.1, "event": "command_acknowledged", "stage_id": 1,
         "mission_id": 1, "uav_id": 1},
        {"timestamp": 3.2, "event": "reference_start", "stage_id": 1,
         "mission_id": 1, "uav_id": 1},
        {"timestamp": 13.2, "event": "reference_finish", "stage_id": 1,
         "mission_id": 1, "uav_id": 1},
        {"timestamp": 43.2, "event": "stage_end", "stage_id": 1,
         "success": False, "failure_reason": "stabilization_timeout"},
    ]
    write_csv(tmp_path / "mission_events.csv", events, event_fields)
    for name, fields in (
        ("status.csv", ["timestamp", "mission_id", "uav_id", "position_error", "speed"]),
        ("odom.csv", ["timestamp", "uav_id"]),
        ("trajectory_metrics.csv", [
            "timestamp", "mission_id", "uav_id", "final_position_error",
            "elapsed_time"]),
        ("control_adaptation.csv", ["timestamp", "mission_id", "uav_id"]),
        ("iapf_debug.csv", ["timestamp", "mission_id", "uav_id"]),
    ):
        write_csv(tmp_path / name, [], fields)
    stages, arrivals, diagnostics = stage_timing_rows(
        tmp_path, {
            "batch_id": "b", "task_type": "task_a_simple",
            "attempt_id": "attempt_0001", "target_execution_index": 1,
        }, load_yaml())
    assert not stages[0]["valid"]
    assert math.isnan(stages[0]["stabilization_delay"])
    assert stages[0]["reference_execution_time"] > 0
    assert arrivals[0]["invalid_reason"] == "missing_final_confirmed"
    assert diagnostics[0]["failure_condition"] == "not_confirmed"


def test_replay_schedule_and_lfs_are_frozen_and_valid():
    rows = initial_schedule(
        load_yaml(), "pilot", ["task_b_sequential", "task_e_mixed"], 5)
    assert len(rows) == 10
    for task_type in ("task_b_sequential", "task_e_mixed"):
        lfs, checksum, path = load_frozen_lfs(task_type, FROZEN_LFS_ROOT)
        assert path.is_file()
        assert len(checksum) == 64
        assert verify_llm_intent(load_task(task_type), lfs) == (True, "")
