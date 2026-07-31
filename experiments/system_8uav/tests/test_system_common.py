import math

from location_allocate.lfs_validator import validate_and_compile_lfs

from run_batch import trial_schedule
from system_common import (
    TASK_NAMES,
    expected_lfs,
    load_task,
    load_yaml,
    stage_groups,
    verify_llm_intent,
)


def test_all_frozen_commands_compile_and_match_intent():
    for task_type in TASK_NAMES:
        task = load_task(task_type)
        compiled = validate_and_compile_lfs(
            expected_lfs(task), list(range(1, 9)))
        matches, error = verify_llm_intent(task, compiled)
        assert matches, error


def test_required_stage_shapes_are_fixed():
    assert [len(stage_groups(load_task(name))) for name in TASK_NAMES] == [
        1, 2, 1, 1, 3]
    assert [len(load_task(name).stages) for name in TASK_NAMES] == [
        1, 2, 2, 1, 5]


def test_dense_terminal_spacing_exceeds_iapf_exit_distance():
    config = load_yaml()
    radius = load_task("task_d_dense").stages[0].radius
    adjacent_spacing = 2.0 * radius * math.sin(math.pi / 8.0)
    assert adjacent_spacing > config["safety"]["iapf_exit_distance"]


def test_formal_schedule_is_ten_complete_reproducible_blocks():
    config = load_yaml()
    first = trial_schedule(config, "formal")
    second = trial_schedule(config, "formal")
    assert first == second
    assert len(first) == 50
    for trial_id in range(1, 11):
        block = [trial.task for trial in first if trial.trial == trial_id]
        assert sorted(block) == sorted(TASK_NAMES)
