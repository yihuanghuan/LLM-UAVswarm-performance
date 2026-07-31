import json

from location_allocate.no_location import purify_json_content
from run_batch import assign_attempt_ids, initial_schedule
from summarize_v2 import timing_rows
from system_common import load_yaml, write_csv


def test_limited_repair_only_removes_wrappers():
    payload = '{"lfs_version":"1.0","tasks":[]}'
    cleaned, repaired = purify_json_content(f"```json\n{payload}\n```")
    assert cleaned == payload
    assert repaired
    unchanged, repaired = purify_json_content(payload)
    assert unchanged == payload
    assert not repaired


def test_formal_plan_has_ten_seeded_randomized_blocks():
    config = load_yaml()
    rows = initial_schedule(config, "formal", [
        "task_a_simple", "task_b_sequential", "task_c_grouped",
        "task_d_dense", "task_e_mixed",
    ])
    assert len(rows) == 50
    assert {row["randomization_seed"] for row in rows} == {1010}
    assigned = assign_attempt_ids(rows)
    assert assigned[0]["attempt_id"] == "attempt_0001"
    assert assigned[-1]["run_order"] == 50


def test_timing_rejects_arrival_before_dispatch(tmp_path):
    fields = [
        "timestamp", "event", "stage_id", "mission_ids", "uav_ids",
        "mission_id", "uav_id",
    ]
    events = [
        {"timestamp": 1, "event": "stage_start", "stage_id": 1,
         "mission_ids": json.dumps([1]), "uav_ids": json.dumps([1])},
        {"timestamp": 2, "event": "assignment_complete", "stage_id": 1},
        {"timestamp": 3, "event": "command_dispatch", "stage_id": 1,
         "mission_id": 1, "uav_id": 1},
        {"timestamp": 3.1, "event": "reference_start", "stage_id": 1,
         "mission_id": 1, "uav_id": 1},
        {"timestamp": 4, "event": "reference_finish", "stage_id": 1,
         "mission_id": 1, "uav_id": 1},
        {"timestamp": 2.5, "event": "stable_candidate_enter", "stage_id": 1,
         "mission_id": 1, "uav_id": 1},
        {"timestamp": 2.8, "event": "stable_confirmed", "stage_id": 1,
         "mission_id": 1, "uav_id": 1},
        {"timestamp": 5, "event": "stage_end", "stage_id": 1},
    ]
    write_csv(tmp_path / "mission_events.csv", events, fields)
    write_csv(tmp_path / "swarm_commands.csv", [], [
        "timestamp", "mission_id", "uav_id"])
    write_csv(tmp_path / "trajectory_metrics.csv", [], [
        "timestamp", "mission_id", "uav_id", "final_position_error",
        "elapsed_time"])
    stages, arrivals = timing_rows(tmp_path, {
        "batch_id": "b", "task_type": "task_a_simple",
        "attempt_id": "attempt_0001", "target_execution_index": 1,
    })
    assert not stages[0]["valid"]
    assert "arrival_before_dispatch" in arrivals[0]["invalid_reason"]


def test_replacement_ids_are_never_reused():
    rows = assign_attempt_ids([
        {"task_type": "task_a_simple", "target_execution_index": 1,
         "replacement_for": ""},
        {"task_type": "task_a_simple", "target_execution_index": 1,
         "replacement_for": "attempt_0001"},
    ])
    assert len({row["attempt_id"] for row in rows}) == 2
