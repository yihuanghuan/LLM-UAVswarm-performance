from pathlib import Path
import subprocess

from e5_runtime_provenance import _run, collect_controller_runtime_evidence


def _observation(uid, sequence, passed):
    return {
        "sequence": sequence, "node": f"/uav{uid}/ladrc_position_controller",
        "execution_command_topic": f"/uav{uid}/execution_command",
        "node_info": {}, "enable_execution_profiles": {}, "topic_info_verbose": {},
        "node_subscription_present": passed,
        "controller_endpoint_present_in_topic_info": passed,
        "enable_execution_profiles_true": passed, "observation_pass": passed,
    }


def test_eight_uav_bounded_discovery(monkeypatch):
    monkeypatch.setattr(
        "e5_runtime_provenance._controller_observation",
        lambda _repo, _env, uid, sequence: _observation(uid, sequence, sequence >= (uid % 4) + 1),
    )
    report = collect_controller_runtime_evidence(None, {}, range(1, 9), max_attempts=4, retry_interval_s=0)
    assert len(report) == 8
    assert all(item["discovery_converged"] for item in report.values())
    assert max(item["selected_observation_sequence"] for item in report.values()) == 4


def test_persistent_absence_fails_closed(monkeypatch):
    monkeypatch.setattr(
        "e5_runtime_provenance._controller_observation",
        lambda _repo, _env, uid, sequence: _observation(uid, sequence, False),
    )
    report = collect_controller_runtime_evidence(None, {}, [8], max_attempts=4, retry_interval_s=0)
    assert report["8"]["discovery_converged"] is False
    assert report["8"]["observation_count"] == 4


def test_run_normal_behavior_unchanged(monkeypatch):
    command = ["ros2", "node", "list"]
    monkeypatch.setattr(
        subprocess, "run",
        lambda *args, **kwargs: subprocess.CompletedProcess(command, 0, "/node\n", ""),
    )
    result = _run(command, env={}, cwd=Path("."))
    assert result["returncode"] == 0
    assert result["stdout"] == "/node\n"
    assert result["stderr"] == ""
    assert result["timed_out"] is False


def test_run_timeout_returns_failed_observation(monkeypatch):
    command = ["ros2", "param", "get", "/node", "parameter"]
    def timeout(*args, **kwargs):
        raise subprocess.TimeoutExpired(command, 20, output=b"partial", stderr=b"late")
    monkeypatch.setattr(subprocess, "run", timeout)
    result = _run(command, env={}, cwd=Path("."))
    assert result["returncode"] != 0
    assert result["stdout"] == "partial"
    assert result["stderr"] == "late"
    assert result["timed_out"] is True


def test_timeout_allows_next_discovery_observation(monkeypatch):
    calls = 0
    def observe(command, **kwargs):
        nonlocal calls
        calls += 1
        if calls == 2:
            raise subprocess.TimeoutExpired(command, 20)
        if command[1:3] == ["node", "info"]:
            stdout = "/uav1/execution_command\n"
        elif command[1:3] == ["param", "get"]:
            stdout = "Boolean value is: True\n"
        else:
            stdout = "Node name: ladrc_position_controller\nNode namespace: /uav1\n"
        return subprocess.CompletedProcess(command, 0, stdout, "")
    monkeypatch.setattr(subprocess, "run", observe)
    report = collect_controller_runtime_evidence(
        Path("."), {}, [1], max_attempts=2, retry_interval_s=0,
    )["1"]
    assert report["discovery_converged"] is True
    assert report["selected_observation_sequence"] == 2
    assert report["observation_count"] == 2
    assert report["observation_attempts"][0]["enable_execution_profiles"]["timed_out"] is True


def test_persistent_timeouts_fail_closed(monkeypatch):
    def timeout(command, **kwargs):
        raise subprocess.TimeoutExpired(command, 20)
    monkeypatch.setattr(subprocess, "run", timeout)
    report = collect_controller_runtime_evidence(
        Path("."), {}, [1], max_attempts=4, retry_interval_s=0,
    )["1"]
    assert report["discovery_converged"] is False
    assert report["observation_count"] == 4
    assert all(
        observation["node_info"]["timed_out"] is True
        for observation in report["observation_attempts"]
    )
