from e5_runtime_provenance import collect_controller_runtime_evidence


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
