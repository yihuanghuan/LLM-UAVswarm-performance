from pathlib import Path

import pytest

from location_allocate.execution_profile_compiler import (
    SoftSafetyParameters,
    compile_execution_profiles,
)
from location_allocate.lfs_types import ExecutableLFS
from location_allocate.policy_adapter import load_runtime_policy


PAPER_CURRENT = (
    Path(__file__).parents[2]
    / "lfs_policy"
    / "config"
    / "lfs_policy.paper_current.yaml"
)


def test_paper_policy_constructs_all_candidate_runtime_dependencies():
    config, policy = load_runtime_policy(PAPER_CURRENT)

    assert config.configuration_id == "paper-current-v3"
    assert len(config.policy_hash) == 64
    assert policy.scale.nominal_spacing == 2.0
    assert policy.timing.motion_limits.jerk == 10.0
    assert policy.timing.motion_limits is policy.profile.motion_limits
    assert policy.profile.task_adaptation_type == "identity"
    assert policy.resolve_safety(1.0).d_plan == 2.0
    assert policy.resolve_safety(2.0).soft_iapf.exit_distance == pytest.approx(2.3)
    allocator = policy.allocator_factory(1.0, 2.4)
    assert allocator.d_hard == 1.0
    assert allocator.d_plan == 2.4


def test_paper_safety_factor_has_explicit_policy_boundary():
    _config, policy = load_runtime_policy(PAPER_CURRENT)

    with pytest.raises(ValueError, match="outside configured range"):
        policy.resolve_safety(2.01)


def test_current_qualitative_audit_exposes_safety_clamp():
    config, _policy = load_runtime_policy(PAPER_CURRENT)

    assert any("compact" in warning for warning in config.warnings)


def test_normal_identity_profile_compiles_exact_canonical_ladrc_baseline():
    config, policy = load_runtime_policy(PAPER_CURRENT)
    executable = ExecutableLFS(
        uav_ids=(1,), formation={"type": "Line"}, center=(1.0, 0.0, 1.5),
        radius=1.0, duration=5.0, motion_style="normal",
        safety_factor=1.0, trigger_semantics={"mode": "direct"},
    )
    profile = compile_execution_profiles(
        executable, [(0.0, 0.0, 1.5)], [(1.0, 0.0, 1.5)],
        policy.profile, SoftSafetyParameters(1.5, 1.65, 1.0),
    )[0]

    assert profile.style_gain == 1.0
    assert profile.task_gain == 1.0
    assert profile.omega_c == config.controller.baseline_omega_c
    assert profile.omega_o == config.controller.baseline_omega_o
