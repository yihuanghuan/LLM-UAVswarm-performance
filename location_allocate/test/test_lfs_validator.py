import pytest

from location_allocate.lfs_validator import (
    LFSValidationError,
    early_validate_candidate_mission,
    validate_and_compile_lfs,
    validate_schema,
)
from location_allocate.mission_compiler import (
    MissionCompileError,
    QRelationPolicy,
    compile_candidate_mission,
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


def candidate_task(**overrides):
    task = {
        "task_id": 1,
        "U": [1, 2, 3],
        "F": {"type": "Circle"},
        "c": {"mode": "maintain_current_centroid"},
        "r": {"mode": "qualitative", "value": "normal"},
        "T": {"mode": "auto"},
        "m": "normal",
        "s": 1.0,
        "q": {"mode": "direct"},
    }
    task.update(overrides)
    return task


def relation_policy():
    return QRelationPolicy(
        completion_event_by_q={
            "direct": "stable",
            "hover-and-wait": "stable",
            "continuous": "trajectory_complete",
        },
        wait_condition_by_q={
            "direct": None,
            "hover-and-wait": "hover_stable",
            "continuous": None,
        },
    )


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


@pytest.mark.parametrize("formation", ["Lineup", "Free"])
def test_legacy_schema_keeps_historical_formation_vocabulary(formation):
    payload = {"task_sequences": [legacy_task()]}
    payload["task_sequences"][0]["parametric_data"]["formation_type"] = formation

    validate_schema(payload)


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


def test_candidate_mission_early_validation_and_graph_compilation():
    payload = {
        "lfs_version": "2.1",
        "mission": {
            "nodes": [
                {"type": "task", "task": candidate_task()},
                {
                    "type": "parallel",
                    "completion_mode": "independent",
                    "tasks": [
                        candidate_task(
                            task_id=2, U=[1, 2], F={"type": "Line"}
                        ),
                        candidate_task(task_id=3, U=[3, 4, 5]),
                    ],
                },
            ]
        }
    }

    validated = early_validate_candidate_mission(payload, available_uav_ids=AVAILABLE_UAV_IDS)
    compiled = compile_candidate_mission(validated, relation_policy())

    assert len(compiled.nodes) == 2
    assert compiled.nodes[1].completion_mode == "independent"
    assert compiled.nodes[1].tasks[0].task["T"] == {"mode": "auto"}


def test_candidate_auto_center_and_scale_are_schema_valid():
    payload = {
        "lfs_version": "2.1",
        "mission": {"nodes": [{
            "type": "task",
            "task": candidate_task(c={"mode": "auto"}, r={"mode": "auto"}),
        }]}
    }

    assert early_validate_candidate_mission(
        payload, available_uav_ids=AVAILABLE_UAV_IDS
    ) == payload


def test_paper_wait_is_only_canonical_q_and_wait_node_is_rejected():
    canonical = {"lfs_version": "2.1", "mission": {"nodes": [{
        "type": "task",
        "task": candidate_task(q={"mode": "hover-and-wait", "duration": 2.0}),
    }]}}
    wait_node = {"lfs_version": "2.1", "mission": {"nodes": [
        {"type": "wait", "condition": "elapsed", "duration": 2.0}
    ]}}

    assert early_validate_candidate_mission(
        canonical, available_uav_ids=AVAILABLE_UAV_IDS
    ) == canonical
    compiled = compile_candidate_mission(canonical, relation_policy())
    assert compiled.nodes[0].wait.condition == "hover_stable"
    assert compiled.nodes[0].wait.duration == 2.0
    with pytest.raises(LFSValidationError, match="schema"):
        early_validate_candidate_mission(
            wait_node, available_uav_ids=AVAILABLE_UAV_IDS
        )


def test_candidate_parallel_overlap_is_rejected_early():
    payload = {
        "lfs_version": "2.1",
        "mission": {
            "nodes": [{
                "type": "parallel",
                "completion_mode": "independent",
                "tasks": [
                    candidate_task(task_id=1, U=[1, 2]),
                    candidate_task(task_id=2, U=[2, 3]),
                ],
            }]
        }
    }

    with pytest.raises(LFSValidationError, match="overlapping UAV"):
        early_validate_candidate_mission(payload, available_uav_ids=AVAILABLE_UAV_IDS)


def test_candidate_non_finite_and_weak_safety_are_rejected():
    infinite = {
        "lfs_version": "2.1", "mission": {"nodes": [{
            "type": "task",
            "task": candidate_task(
                c={"mode": "absolute", "value": [0.0, float("inf"), 1.0]}
            ),
        }]}
    }
    weak_safety = {
        "lfs_version": "2.1", "mission": {"nodes": [{
            "type": "task", "task": candidate_task(s=0.5)
        }]}
    }

    with pytest.raises(LFSValidationError):
        early_validate_candidate_mission(infinite, available_uav_ids=AVAILABLE_UAV_IDS)
    with pytest.raises(LFSValidationError):
        early_validate_candidate_mission(weak_safety, available_uav_ids=AVAILABLE_UAV_IDS)


def test_candidate_requires_explicit_q_graph_policy():
    payload = {
        "lfs_version": "2.1",
        "mission": {"nodes": [{
            "type": "task", "task": candidate_task(q={"mode": "direct"})
        }]}
    }
    validated = early_validate_candidate_mission(payload, available_uav_ids=AVAILABLE_UAV_IDS)
    missing_policy = QRelationPolicy({}, {})

    with pytest.raises(MissionCompileError, match="no configured graph mapping"):
        compile_candidate_mission(validated, missing_policy)


def test_candidate_cannot_be_eagerly_flattened_to_legacy_tasks():
    payload = {
        "mission": {"nodes": [{
            "type": "task", "task": candidate_task()
        }]}
    }

    with pytest.raises(LFSValidationError, match="cannot be flattened eagerly"):
        validate_and_compile_lfs(payload)


@pytest.mark.parametrize(
    "formation,uav_ids",
    [
        ({"type": "Line"}, [1]),
        ({"type": "Circle"}, [1, 2]),
        ({"type": "Sphere"}, [1]),
        ({"type": "Triangle"}, [1, 2, 3, 4]),
        ({"type": "Polygon", "sides": 5}, [1, 2, 3, 4]),
    ],
)
def test_static_validator_rejects_invalid_formation_cardinality(
        formation, uav_ids):
    payload = {"lfs_version": "2.1", "mission": {"nodes": [{
        "type": "task",
        "task": candidate_task(F=formation, U=uav_ids),
    }]}}

    with pytest.raises(LFSValidationError, match="cardinality"):
        early_validate_candidate_mission(
            payload, available_uav_ids=AVAILABLE_UAV_IDS
        )


def test_static_validator_rejects_unavailable_uav_and_duplicate_task_id():
    unavailable = {"lfs_version": "2.1", "mission": {"nodes": [{
        "type": "task", "task": candidate_task(U=[1, 2, 9]),
    }]}}
    duplicate = {"lfs_version": "2.1", "mission": {"nodes": [
        {"type": "task", "task": candidate_task()},
        {"type": "task", "task": candidate_task()},
    ]}}

    with pytest.raises(LFSValidationError, match="unavailable UAV"):
        early_validate_candidate_mission(
            unavailable, available_uav_ids=AVAILABLE_UAV_IDS
        )
    with pytest.raises(LFSValidationError, match="duplicate task_id"):
        early_validate_candidate_mission(
            duplicate, available_uav_ids=AVAILABLE_UAV_IDS
        )


def test_static_validator_requires_availability_and_continuous_successor():
    direct = {"lfs_version": "2.1", "mission": {"nodes": [{
        "type": "task", "task": candidate_task(),
    }]}}
    continuous = {"lfs_version": "2.1", "mission": {"nodes": [{
        "type": "task",
        "task": candidate_task(q={"mode": "continuous"}),
    }]}}

    with pytest.raises(LFSValidationError, match="requires available UAV"):
        early_validate_candidate_mission(direct)
    with pytest.raises(LFSValidationError, match="requires a successor"):
        early_validate_candidate_mission(
            continuous, available_uav_ids=AVAILABLE_UAV_IDS
        )
