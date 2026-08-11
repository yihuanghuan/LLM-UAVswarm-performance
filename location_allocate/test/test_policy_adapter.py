from pathlib import Path

import pytest

from location_allocate.policy_adapter import load_runtime_policy


PAPER_CURRENT = (
    Path(__file__).parents[2]
    / "lfs_policy"
    / "config"
    / "lfs_policy.paper_current.yaml"
)


def test_paper_policy_constructs_all_candidate_runtime_dependencies():
    config, policy = load_runtime_policy(PAPER_CURRENT)

    assert config.configuration_id == "paper-current-v1"
    assert len(config.policy_hash) == 64
    assert policy.scale.nominal_spacing == 2.0
    assert policy.timing.jerk_limit == 10.0
    assert policy.profile.task_adaptation_type == "identity"
    assert policy.resolve_safety(1.0).d_plan == 2.0
    assert policy.resolve_safety(2.0).soft_iapf.exit_distance == pytest.approx(2.3)
    assert policy.allocator_factory(2.4).d_safe == 2.4


def test_paper_safety_factor_has_explicit_policy_boundary():
    _config, policy = load_runtime_policy(PAPER_CURRENT)

    with pytest.raises(ValueError, match="outside configured range"):
        policy.resolve_safety(2.01)


def test_current_qualitative_audit_exposes_safety_clamp():
    config, _policy = load_runtime_policy(PAPER_CURRENT)

    assert any("compact" in warning for warning in config.warnings)
