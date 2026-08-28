from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
import subprocess
import sys

import pytest
import e3_runtime_diagnostics as runtime_diagnostics

from e3_formal_adapter import (
    FormalAdapterError, adapter_identity, execution_tooling_identity, run_exact_trial,
)
from e3_trial_registry import (
    ORDER_SHA256, POLICY_SHA256, PROTOCOL_SHA256, REGISTRY_SHA256,
    build_exact_spec, registered_trial_ids,
)
from e3_engineering_smoke import fixture
from e3_formal_backend import build_runtime_spec
from e3_runtime_diagnostics import (
    collect_controller_runtime_evidence, endpoint_snapshot, expected_wrench_topic,
    is_expected_controller_endpoint,
    is_expected_recorder_endpoint, runtime_provenance_gate, validate_command,
)


def context(trial_id, root, **changes):
    identity = adapter_identity()
    order = Path(__file__).resolve().parents[2] / "simulation_trial_order_v1.txt"
    value = {
        "execution_mode": "spec_rehearsal",
        "dataset_class": "synthetic_validation",
        "formal_launch_authorized": False,
        "trial_id": trial_id,
        "global_trial_position": order.read_text().splitlines().index(trial_id) + 1,
        "runner_commit": identity["commit"],
        "runner_source_sha256": identity["source_sha256"],
        "runner_execution_tooling_bundle_schema": identity["execution_tooling_bundle_schema"],
        "runner_execution_tooling_file_sha256": identity["execution_tooling_file_sha256"],
        "runner_execution_tooling_bundle_sha256": identity["execution_tooling_bundle_sha256"],
        "policy_sha256": POLICY_SHA256,
        "protocol_sha256": PROTOCOL_SHA256,
        "registry_sha256": REGISTRY_SHA256,
        "global_trial_order_sha256": ORDER_SHA256,
        "attempt_output_dir": str(root),
    }
    value.update(changes)
    return value


def test_complete_spec_reconstruction_is_deterministic_and_global_registered():
    ids = registered_trial_ids()
    assert len(ids) == len(set(ids)) == 360
    assert [build_exact_spec(value) for value in ids] == [build_exact_spec(value) for value in ids]


def test_spec_rehearsal_retains_nonformal_artifact_without_suite_journal(tmp_path):
    trial = registered_trial_ids()[0]
    descriptor = run_exact_trial(trial, context(trial, tmp_path / "attempt"))
    assert descriptor["accepted_formal_result"] is False
    assert descriptor["dataset_class"] == "synthetic_validation"
    assert descriptor["suite_journal_mutated"] is False
    artifact = Path(descriptor["artifact_path"]).read_text()
    assert '"result_notice":"NOT_FORMAL_RESULT"' in artifact
    assert not list(tmp_path.rglob("*journal*"))


def test_duplicate_attempt_is_refused(tmp_path):
    trial = registered_trial_ids()[0]; ctx = context(trial, tmp_path / "attempt")
    run_exact_trial(trial, ctx)
    with pytest.raises(FormalAdapterError, match="duplicate"):
        run_exact_trial(trial, ctx)


@pytest.mark.parametrize("trial", ["garbage", "E2-CENTER-01__NO_SHIFT__EARLY__S21001"])
def test_unknown_and_wrong_family_refused(trial, tmp_path):
    good = registered_trial_ids()[0]
    with pytest.raises(Exception):
        run_exact_trial(trial, context(good, tmp_path / "attempt", trial_id=trial))


@pytest.mark.parametrize("field,value", [
    ("global_trial_position", 611), ("runner_commit", "0" * 40),
    ("runner_source_sha256", "0" * 64), ("policy_sha256", "0" * 64),
    ("protocol_sha256", "0" * 64), ("registry_sha256", "0" * 64),
    ("global_trial_order_sha256", "0" * 64),
])
def test_provenance_or_position_mismatch_refused(field, value, tmp_path):
    trial = registered_trial_ids()[0]
    with pytest.raises(FormalAdapterError):
        run_exact_trial(trial, context(trial, tmp_path / "attempt", **{field: value}))


@pytest.mark.parametrize("field,value", [
    ("runner_execution_tooling_bundle_schema", "wrong"),
    ("runner_execution_tooling_file_sha256", {}),
    ("runner_execution_tooling_bundle_sha256", "0" * 64),
])
def test_execution_tooling_bundle_mismatch_refused(field, value, tmp_path):
    trial = registered_trial_ids()[0]
    with pytest.raises(FormalAdapterError, match="execution-tooling"):
        run_exact_trial(trial, context(trial, tmp_path / "attempt", **{field: value}))


def test_execution_tooling_bundle_covers_complete_runtime_dependency_set():
    identity = execution_tooling_identity()
    assert identity["schema"] == "e3_execution_tooling_bundle_v1"
    assert set(identity["files"]) == {
        "experiments_v2/Formal Evaluation Experiments/E3/tooling/e3_formal_adapter.py",
        "experiments_v2/Formal Evaluation Experiments/E3/tooling/e3_formal_backend.py",
        "experiments_v2/Formal Evaluation Experiments/E3/tooling/e3_physical_trial.py",
        "experiments_v2/Formal Evaluation Experiments/E3/tooling/e3_runtime_diagnostics.py",
        "experiments_v2/Formal Evaluation Experiments/E3/tooling/e3_trial_registry.py",
        "experiments_v2/Formal Evaluation Experiments/E3/tooling/e3_wrench_compat.py",
        "experiments_v2/Formal Evaluation Experiments/harness/e3_wrench_driver.py",
        "experiments-legacy/system_8uav/scripts/wait_swarm_ready.py",
    }
    assert len(identity["bundle_sha256"]) == 64


def test_formal_mode_is_fail_closed_without_final_gate(tmp_path):
    trial = registered_trial_ids()[0]
    with pytest.raises(FormalAdapterError, match="authorization"):
        run_exact_trial(trial, context(
            trial, tmp_path / "attempt", execution_mode="formal",
            dataset_class="formal_evaluation", formal_launch_authorized=False,
            launch_gate_status="READY_FOR_FORMAL_LAUNCH"))
    assert not (tmp_path / "attempt").exists()


def test_failure_injection_is_non_scientific_but_retained(tmp_path):
    trial = registered_trial_ids()[0]
    descriptor = run_exact_trial(trial, context(
        trial, tmp_path / "attempt", failure_injection="infrastructure_failure"))
    assert descriptor["attempt_status"] == "infrastructure_failure"
    assert descriptor["accepted_formal_result"] is False


def test_wrench_compatibility_shim_inherits_all_sealed_behavior():
    for path in ("/opt/ros/humble/local/lib/python3.10/dist-packages",
                 "/opt/ros/humble/lib/python3.10/site-packages"):
        if path not in sys.path:
            sys.path.append(path)
    from e3_wrench_compat import HumbleCompatibleE3WrenchDriver, E3WrenchDriver
    assert HumbleCompatibleE3WrenchDriver._on_clock is E3WrenchDriver._on_clock
    assert HumbleCompatibleE3WrenchDriver._on_arm is E3WrenchDriver._on_arm
    assert HumbleCompatibleE3WrenchDriver._publish is E3WrenchDriver._publish
    assert set(HumbleCompatibleE3WrenchDriver.__dict__) - {
        "__module__", "__doc__", "publishers", "create_subscription"
    } == set()


def test_rosbag_subscriber_cannot_satisfy_controller_readiness():
    rosbag = SimpleNamespace(
        node_name="rosbag2_recorder", node_namespace="/",
        topic_type="uav_swarm_interfaces/msg/UAVExecutionCommand",
        endpoint_type="SUBSCRIPTION", qos_profile=SimpleNamespace(depth=10),
    )
    controller = SimpleNamespace(
        node_name="ladrc_position_controller", node_namespace="/uav1",
        topic_type="uav_swarm_interfaces/msg/UAVExecutionCommand",
        endpoint_type="SUBSCRIPTION", qos_profile=SimpleNamespace(depth=10),
    )
    wrong_namespace = SimpleNamespace(**{**controller.__dict__, "node_namespace": "/uav2"})
    assert not is_expected_controller_endpoint(rosbag, 1)
    assert is_expected_recorder_endpoint(rosbag)
    assert not is_expected_controller_endpoint(wrong_namespace, 1)
    assert is_expected_controller_endpoint(controller, 1)

    node = SimpleNamespace(
        get_subscriptions_info_by_topic=lambda _topic: [rosbag],
        get_publishers_info_by_topic=lambda _topic: [],
    )
    publisher = SimpleNamespace(get_subscription_count=lambda: 1)
    snapshot = endpoint_snapshot(node, publisher, "/uav1/execution_command", 1)
    assert snapshot["publisher_reported_subscription_count"] == 1
    assert snapshot["controller_endpoint_present"] is False
    assert snapshot["recorder_endpoint_present"] is True


def test_runtime_provenance_and_execution_profile_gate_fail_closed():
    assert runtime_provenance_gate({"status": "PASS", "checks": {"all": True}})
    assert not runtime_provenance_gate({
        "status": "FAIL",
        "checks": {"execution_profiles_enabled_for_every_controller": False},
    })


def _diagnostic_command_result(command, *, node_visible):
    if command[1:3] == ["node", "info"]:
        uid = command[-1].split("/")[1]
        topic = f"/{uid}/execution_command"
        return {
            "command": command, "returncode": 0 if node_visible else 1,
            "stdout": f"{command[-1]}\n  Subscribers:\n    {topic}: type\n"
                if node_visible else "",
            "stderr": "" if node_visible else f"Unable to find node '{command[-1]}'\n",
        }
    if command[1:3] == ["param", "get"]:
        return {"command": command, "returncode": 0,
                "stdout": "Boolean value is: True\n", "stderr": ""}
    if command[1:4] == ["topic", "info", "-v"]:
        uid = command[-1].split("/")[1]
        return {"command": command, "returncode": 0,
                "stdout": ("Subscription count: 1\n"
                           "Node name: ladrc_position_controller\n"
                           f"Node namespace: /{uid}\n"), "stderr": ""}
    raise AssertionError(command)


def test_transient_node_info_miss_retains_raw_evidence_and_converges(monkeypatch):
    node_info_calls = 0

    def fake_run(command, **_kwargs):
        nonlocal node_info_calls
        if command[1:3] == ["node", "info"]:
            node_info_calls += 1
        return _diagnostic_command_result(command, node_visible=node_info_calls > 1)

    monkeypatch.setattr("e3_runtime_diagnostics._run", fake_run)
    evidence = collect_controller_runtime_evidence(
        Path("/repo"), {}, [1], max_attempts=3, retry_interval_s=0.0,
    )["1"]
    assert evidence["discovery_converged"] is True
    assert evidence["selected_observation_sequence"] == 2
    assert evidence["observation_count"] == 2
    assert evidence["observation_attempts"][0]["node_subscription_present"] is False
    assert evidence["observation_attempts"][0]["controller_endpoint_present_in_topic_info"] is True
    assert evidence["observation_attempts"][0]["enable_execution_profiles_true"] is True
    assert evidence["observation_attempts"][1]["observation_pass"] is True


def test_ros_cli_timeout_is_retained_as_failed_observation(monkeypatch):
    def timeout(*_args, **_kwargs):
        raise subprocess.TimeoutExpired(
            ["ros2", "param", "get", "/uav1/ladrc_position_controller",
             "enable_execution_profiles"],
            timeout=20,
            output="partial stdout",
            stderr="partial stderr",
        )

    monkeypatch.setattr(runtime_diagnostics.subprocess, "run", timeout)
    result = runtime_diagnostics._run(
        ["ros2", "param", "get", "/uav1/ladrc_position_controller",
         "enable_execution_profiles"],
        env={}, cwd=Path("/repo"),
    )
    assert result["returncode"] == 124
    assert result["timed_out"] is True
    assert result["stdout"] == "partial stdout"
    assert result["stderr"] == "partial stderr"


def test_persistent_missing_controller_exhausts_bounds_and_fails_closed(monkeypatch):
    monkeypatch.setattr(
        "e3_runtime_diagnostics._run",
        lambda command, **_kwargs: _diagnostic_command_result(command, node_visible=False),
    )
    evidence = collect_controller_runtime_evidence(
        Path("/repo"), {}, [1], max_attempts=3, retry_interval_s=0.0,
    )["1"]
    assert evidence["discovery_converged"] is False
    assert evidence["node_subscription_present"] is False
    assert evidence["controller_endpoint_present_in_topic_info"] is True
    assert evidence["enable_execution_profiles_true"] is True
    assert evidence["observation_count"] == 3
    assert all(not item["observation_pass"] for item in evidence["observation_attempts"])
    checks = {
        "every_controller_node_subscribes": evidence["node_subscription_present"],
        "every_controller_endpoint_visible_separately_from_rosbag":
            evidence["controller_endpoint_present_in_topic_info"],
        "execution_profiles_enabled_for_every_controller":
            evidence["enable_execution_profiles_true"],
    }
    assert not runtime_provenance_gate({"status": "FAIL", "checks": checks})


def test_nonregistered_fixture_class_and_dataset_propagate():
    runtime = build_runtime_spec(fixture())
    assert runtime["fixture_class"] == "non_registered_engineering_fixture"
    assert runtime["dataset_class"] == "engineering_validation"


def test_registered_runtime_defaults_remain_registered():
    runtime = build_runtime_spec(build_exact_spec(registered_trial_ids()[0]))
    assert runtime["fixture_class"] == "registered_formal_spec"
    assert runtime["dataset_class"] == "formal_evaluation"
    assert all(
        isinstance(coordinate, float)
        for vector in runtime["initial_positions_m"] + runtime["ordered_targets_m"]
        for coordinate in vector
    )


def test_exact_e3_wrench_topic_mapping():
    assert expected_wrench_topic(1) == "/e3_force/mavlink_2/wrench"
    assert expected_wrench_topic(2) == "/e3_force/mavlink_3/wrench"


def test_command_guard_and_single_publish_no_retry_are_explicit():
    source = Path(__file__).with_name("e3_physical_trial.py").read_text()
    assert source.count(".publish(command)") == 1
    assert "get_subscription_count() for p" not in source
    assert "controller_endpoint_present" in source
    assert "command_publish_count_by_uav" in source


def test_validation_rejects_wrong_uav_and_bad_profile():
    profile = SimpleNamespace(
        duration=3.0, style="normal", configuration_id="frozen",
        omega_c=[1.0, 1.0, 1.0], omega_o=[5.0, 5.0, 5.0],
        velocity_limit=5.0, acceleration_limit=5.0, jerk_limit=10.0,
        iapf_enter_distance=1.6, iapf_exit_distance=1.7,
        iapf_repulsion_scale=1.0, style_gain=1.0, task_gain=1.0,
    )
    command = SimpleNamespace(
        uav_id=2, mission_id=3,
        target_pos=SimpleNamespace(x=0.0, y=3.0, z=3.0), profile=profile,
    )
    assert not validate_command(command, 1)["frozen_controller_metadata_guard_pass"]
    profile.configuration_id = ""
    assert not validate_command(command, 2)["frozen_controller_metadata_guard_pass"]
