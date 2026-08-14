from pathlib import Path

import pytest
import yaml

from lfs_policy import PolicyLoadError, load_paper_policy, load_policy


LEGACY = Path(__file__).parents[1] / "config" / "lfs_policy.legacy.yaml"
TEMPLATE = Path(__file__).parents[2] / "location_allocate" / "config" / "lfs_policy.template.yaml"
PAPER = Path(__file__).parents[1] / "config" / "lfs_policy.paper_current.yaml"


def write_policy(tmp_path, mutate):
    data = yaml.safe_load(PAPER.read_text(encoding="utf-8"))
    mutate(data)
    path = tmp_path / "policy.yaml"
    path.write_text(yaml.safe_dump(data), encoding="utf-8")
    return path


def test_legacy_policy_loads_and_exposes_controller_parameters():
    policy = load_policy(LEGACY)

    assert policy.configuration_id == "legacy-main-v1"
    assert policy.state.require_velocity is True
    assert policy.state.allow_receive_time_fallback is False
    assert policy.controller.ros_parameters()["enable_execution_profiles"] is True
    assert policy.provenance["legacy_baseline"] == "historical runtime defaults"


def test_template_is_not_a_production_policy():
    with pytest.raises(PolicyLoadError):
        load_policy(TEMPLATE)


def test_paper_current_has_hash_status_and_explicit_clamp_warning():
    policy = load_paper_policy(PAPER)

    assert policy.configuration_id == "paper-current-v3"
    assert policy.status == "paper_current"
    assert len(policy.policy_hash) == 64
    assert policy.parameter_status["architecture_rules"] == "paper-frozen"
    assert "safety-clamped" in policy.warnings[0]
    parameters = policy.controller.ros_parameters()
    assert [parameters[f"omega_c_{axis}"] for axis in "xyz"] == [
        1.5, 1.5, 1.75
    ]
    assert [parameters[f"omega_o_{axis}"] for axis in "xyz"] == [
        5.0, 5.0, 7.5
    ]


def test_paper_runtime_rejects_legacy_policy():
    with pytest.raises(PolicyLoadError, match="paper_current"):
        load_paper_policy(LEGACY)


@pytest.mark.parametrize(
    "mutate, message",
    [
        (lambda data: data.pop("configuration_id"), "missing key"),
        (lambda data: data["motion_limits"].update(jerk=None), "null"),
        (lambda data: data["motion_limits"].update(jerk=float("nan")), "finite"),
        (lambda data: data["safety"].update(iapf_exit_base=1.1), "hysteresis"),
        (lambda data: data["controller_hard_clamps"].update(iapf_enter_max=1.6), "cover"),
        (
            lambda data: data["controller_hard_clamps"].update(
                velocity_max=4.0
            ),
            "cover motion limits",
        ),
        (
            lambda data: data["execution_profile"].update(
                baseline_omega_c=[1.5, 1.5, 1.8]
            ),
            "baseline_omega_c",
        ),
    ],
)
def test_invalid_production_policy_fails_fast(tmp_path, mutate, message):
    path = write_policy(tmp_path, mutate)

    with pytest.raises(PolicyLoadError, match=message):
        load_policy(path)
