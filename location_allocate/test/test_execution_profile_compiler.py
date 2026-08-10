import dataclasses
import math

import pytest

from location_allocate.execution_profile_compiler import (
    ExecutionProfilePolicy,
    ProfileCompileError,
    SoftSafetyParameters,
    compile_execution_profiles,
    compile_legacy_baseline_profile,
)
from location_allocate.lfs_types import ExecutableLFS


def policy():
    return ExecutionProfilePolicy(
        base_omega_c=(3.0, 3.0, 3.5),
        base_omega_o=(10.0, 10.0, 15.0),
        style_gains={"smooth": 0.8, "normal": 1.0, "aggressive": 1.2},
        task_reference_speed=2.0,
        task_gain_intercept=0.8,
        task_gain_slope=0.2,
        task_gain_range=(0.7, 1.3),
        total_gain_range=(0.5, 1.8),
        velocity_limit=2.0,
        acceleration_limit=1.5,
        jerk_limit=3.0,
        configuration_id="test-only",
    )


def safety():
    return SoftSafetyParameters(
        enter_distance=1.5,
        exit_distance=1.8,
        repulsion_scale=1.0,
    )


def executable(style="normal", duration=5.0):
    return ExecutableLFS(
        uav_ids=(1, 2),
        formation="Line",
        center=(0.0, 0.0, 1.0),
        radius=2.0,
        duration=duration,
        motion_style=style,
        safety_factor=1.0,
        trigger_semantics="direct",
    )


@pytest.mark.parametrize("style", ["smooth", "normal", "aggressive"])
def test_profile_uses_executable_t_as_its_only_duration(style):
    profiles = compile_execution_profiles(
        executable(style=style, duration=7.25),
        [[0.0, 0.0, 1.0], [0.0, 2.0, 1.0]],
        [[2.0, 0.0, 1.0], [5.0, 2.0, 1.0]],
        policy(),
        safety(),
    )

    assert [profile.duration for profile in profiles] == [7.25, 7.25]
    assert profiles[0].style_gain == policy().style_gains[style]
    assert profiles[0].task_gain != profiles[1].task_gain


def test_profile_policy_has_no_hidden_default_values():
    fields = {field.name for field in dataclasses.fields(ExecutionProfilePolicy)}

    assert "task_gain_intercept" in fields
    assert "task_gain_slope" in fields
    assert all(
        field.default is dataclasses.MISSING
        for field in dataclasses.fields(ExecutionProfilePolicy)
    )


def test_profile_rejects_non_finite_or_inconsistent_values():
    bad_policy = dataclasses.replace(policy(), velocity_limit=float("nan"))
    bad_safety = SoftSafetyParameters(2.0, 1.0, 1.0)

    with pytest.raises(ProfileCompileError, match="finite and positive"):
        compile_execution_profiles(
            executable(), [[0, 0, 0], [0, 1, 0]], [[1, 0, 0], [1, 1, 0]],
            bad_policy, safety()
        )
    with pytest.raises(ProfileCompileError, match="exit distance"):
        compile_execution_profiles(
            executable(), [[0, 0, 0], [0, 1, 0]], [[1, 0, 0], [1, 1, 0]],
            policy(), bad_safety
        )


def test_legacy_profile_ignores_motion_style_and_uses_baseline():
    profile = compile_legacy_baseline_profile(4.0, policy(), safety())

    assert profile.duration == 4.0
    assert profile.style == "legacy-baseline"
    assert profile.omega_c == policy().base_omega_c
    assert profile.style_gain == 1.0
    assert profile.task_gain == 1.0


def test_soft_safety_does_not_expose_hard_violation_threshold():
    assert "hard" not in " ".join(
        field.name for field in dataclasses.fields(SoftSafetyParameters)
    )

