from pathlib import Path

import pytest
import yaml

from lfs_policy import PolicyLoadError, load_policy


MIGRATION = Path(__file__).parents[1] / "config" / "lfs_policy.migration.yaml"
TEMPLATE = Path(__file__).parents[2] / "location_allocate" / "config" / "lfs_policy.template.yaml"


def write_policy(tmp_path, mutate):
    data = yaml.safe_load(MIGRATION.read_text(encoding="utf-8"))
    mutate(data)
    path = tmp_path / "policy.yaml"
    path.write_text(yaml.safe_dump(data), encoding="utf-8")
    return path


def test_migration_policy_loads_and_exposes_controller_parameters():
    policy = load_policy(MIGRATION)

    assert policy.configuration_id == "migration-main-v1"
    assert policy.state.require_velocity is True
    assert policy.state.allow_receive_time_fallback is False
    assert policy.controller.ros_parameters()["enable_execution_profiles"] is True
    assert policy.provenance["d_hard"].endswith("iapf_violation_distance")


def test_template_is_not_a_production_policy():
    with pytest.raises(PolicyLoadError):
        load_policy(TEMPLATE)


@pytest.mark.parametrize(
    "mutate, message",
    [
        (lambda data: data.pop("configuration_id"), "missing key"),
        (lambda data: data["timing"].update(jerk_limit=None), "null"),
        (lambda data: data["timing"].update(jerk_limit=float("nan")), "finite"),
        (lambda data: data["safety"].update(iapf_exit_margin=0.1), "hysteresis"),
        (lambda data: data["controller_hard_clamps"].update(iapf_enter_max=1.6), "cover"),
    ],
)
def test_invalid_production_policy_fails_fast(tmp_path, mutate, message):
    path = write_policy(tmp_path, mutate)

    with pytest.raises(PolicyLoadError, match=message):
        load_policy(path)
