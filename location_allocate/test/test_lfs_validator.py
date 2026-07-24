import pytest

from location_allocate.lfs_validator import (
    LFSValidationError,
    canonicalize_lfs_payload,
    validate_and_compile_lfs,
)


AVAILABLE_UAV_IDS = [1, 2, 3, 4, 5]


def formal_lfs_task(**overrides):
    task = {
        "task_id": 1,
        "U": [1, 2, 3],
        "F": "Circle",
        "c": [0.0, 0.0, 3.0],
        "r": 2.0,
        "T": 5.0,
        "m": "normal",
        "s": 1.0,
        "q": "direct",
    }
    task.update(overrides)
    return task


def legacy_task(**overrides):
    task = {
        "task_sequence_id": 1,
        "duration_seconds": 5.0,
        "uav_id": [1, 2, 3],
        "uav_count": 3,
        "trigger_condition": "direct_execution",
        "wait_time": None,
        "iapf_safety_margin_factor": None,
        "motion_profile": "normal",
        "constraints": [
            "minimal_topology_change",
            "no_trajectory_cross",
            "keep_safety_distance",
        ],
        "global_center": [0.0, 0.0, 3.0],
        "generation_mode": "parametric",
        "parametric_data": {
            "formation_type": "Circle",
            "formation_radius": 2.0,
        },
    }
    task.update(overrides)
    return task


def test_valid_formal_lfs_compiles_to_task_sequences():
    payload = {"lfs_version": "1.0", "tasks": [formal_lfs_task()]}

    compiled = validate_and_compile_lfs(payload, AVAILABLE_UAV_IDS)

    assert list(compiled) == ["task_sequences"]
    task = compiled["task_sequences"][0]
    assert task["task_sequence_id"] == 1
    assert task["duration_seconds"] == 5.0
    assert task["uav_id"] == [1, 2, 3]
    assert task["uav_count"] == 3
    assert task["trigger_condition"] == "direct_execution"
    assert task["motion_profile"] == "normal"
    assert task["global_center"] == [0.0, 0.0, 3.0]
    assert task["parametric_data"] == {
        "formation_type": "Circle",
        "formation_radius": 2.0,
    }


def test_invalid_uav_id_raises():
    payload = {"lfs_version": "1.0", "tasks": [formal_lfs_task(U=[1, 9])]}

    with pytest.raises(LFSValidationError, match="UAV ID"):
        validate_and_compile_lfs(payload, AVAILABLE_UAV_IDS)


def test_overlapping_parallel_group_raises():
    payload = {
        "lfs_version": "1.0",
        "tasks": [
            formal_lfs_task(task_id=1, U=[1, 2], parallel_group="same-time"),
            formal_lfs_task(task_id=2, U=[2, 3], parallel_group="same-time"),
        ],
    }

    with pytest.raises(LFSValidationError, match="parallel_group"):
        validate_and_compile_lfs(payload, AVAILABLE_UAV_IDS)


def test_legacy_task_sequences_remain_supported():
    payload = {"task_sequences": [legacy_task()]}

    compiled = validate_and_compile_lfs(payload, AVAILABLE_UAV_IDS)

    assert compiled["task_sequences"][0]["uav_id"] == [1, 2, 3]
    assert compiled["task_sequences"][0]["trigger_condition"] == "direct_execution"
    assert compiled["task_sequences"][0]["parametric_data"]["formation_type"] == "Circle"


def test_missing_required_field_raises():
    task = formal_lfs_task()
    del task["F"]
    payload = {"lfs_version": "1.0", "tasks": [task]}

    with pytest.raises(LFSValidationError, match="schema"):
        validate_and_compile_lfs(payload, AVAILABLE_UAV_IDS)


def test_invalid_motion_style_raises():
    payload = {"lfs_version": "1.0", "tasks": [formal_lfs_task(m="fast")]}

    with pytest.raises(LFSValidationError, match="schema"):
        validate_and_compile_lfs(payload, AVAILABLE_UAV_IDS)


def test_draft_defaults_and_sequential_triggers_are_compiler_owned():
    first = formal_lfs_task(task_id=1)
    second = formal_lfs_task(task_id=2, F="Line", depends_on=[1])
    for task in (first, second):
        task.pop("m")
        task.pop("s")
        task.pop("q")

    canonical = canonicalize_lfs_payload(
        {"lfs_version": "1.0", "tasks": [first, second]},
        "先组成圆形，随后组成直线",
    )

    assert canonical["tasks"][0]["m"] == "normal"
    assert canonical["tasks"][0]["s"] == 1.0
    assert [task["q"] for task in canonical["tasks"]] == ["continuous", "direct"]


def test_parallel_tasks_remain_direct():
    payload = {
        "lfs_version": "1.0",
        "tasks": [
            formal_lfs_task(task_id=1, U=[1, 2], parallel_group="g"),
            formal_lfs_task(task_id=2, U=[3, 4], parallel_group="g"),
        ],
    }

    canonical = canonicalize_lfs_payload(payload)

    assert [task["q"] for task in canonical["tasks"]] == ["direct", "direct"]


def test_lineup_is_canonicalized_to_line():
    payload = {"lfs_version": "1.0", "tasks": [formal_lfs_task(F="Lineup")]}

    compiled = validate_and_compile_lfs(payload, AVAILABLE_UAV_IDS)

    assert compiled["task_sequences"][0]["parametric_data"]["formation_type"] == "Line"


def test_unmentioned_safety_factor_cannot_be_inferred_from_aggressive_style():
    payload = {"lfs_version": "1.0", "tasks": [formal_lfs_task(m="aggressive", s=0.5)]}

    canonical = canonicalize_lfs_payload(payload, "快速激进地组成圆形")

    assert canonical["tasks"][0]["m"] == "aggressive"
    assert canonical["tasks"][0]["s"] == 1.0


def test_style_only_duplicate_task_is_rejected():
    payload = {
        "lfs_version": "1.0",
        "tasks": [
            formal_lfs_task(task_id=1, m="normal"),
            formal_lfs_task(task_id=2, m="aggressive"),
        ],
    }

    with pytest.raises(LFSValidationError, match="style_split_as_task"):
        canonicalize_lfs_payload(payload)
