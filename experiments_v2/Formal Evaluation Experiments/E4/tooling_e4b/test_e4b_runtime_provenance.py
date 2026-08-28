from e4b_runtime_provenance import collect_controller_runtime_evidence


def _observation(uid, sequence, passed):
    return {
        "sequence": sequence, "node": f"/uav{uid}/ladrc_position_controller",
        "execution_command_topic": f"/uav{uid}/execution_command",
        "node_info": {}, "enable_execution_profiles": {}, "topic_info_verbose": {},
        "node_subscription_present": passed,
        "controller_endpoint_present_in_topic_info": passed,
        "enable_execution_profiles_true": passed, "observation_pass": passed,
    }


def test_bounded_discovery_converges_and_retains_failures(monkeypatch):
    monkeypatch.setattr(
        "e4b_runtime_provenance._controller_observation",
        lambda _repo, _env, uid, sequence: _observation(uid, sequence, sequence == 2),
    )
    report = collect_controller_runtime_evidence(None, {}, [1, 2], max_attempts=4, retry_interval_s=0)
    assert all(item["selected_observation_sequence"] == 2 for item in report.values())
    assert all(item["observation_count"] == 2 for item in report.values())
    assert all(not item["observation_attempts"][0]["observation_pass"] for item in report.values())


def test_persistent_absence_fails_closed(monkeypatch):
    monkeypatch.setattr(
        "e4b_runtime_provenance._controller_observation",
        lambda _repo, _env, uid, sequence: _observation(uid, sequence, False),
    )
    report = collect_controller_runtime_evidence(None, {}, [1], max_attempts=4, retry_interval_s=0)
    assert report["1"]["discovery_converged"] is False
    assert report["1"]["observation_count"] == 4
