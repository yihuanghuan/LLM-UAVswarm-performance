from e4a_runtime_provenance import collect_controller_runtime_evidence


def test_bounded_discovery_retains_failures_then_converges(monkeypatch):
    calls = {1: 0, 2: 0}

    def observe(_repo, _env, uid, sequence):
        calls[uid] += 1
        passed = uid == 1 or sequence == 3
        return {
            "sequence": sequence, "node": f"/uav{uid}/ladrc_position_controller",
            "execution_command_topic": f"/uav{uid}/execution_command",
            "node_info": {}, "enable_execution_profiles": {}, "topic_info_verbose": {},
            "node_subscription_present": passed,
            "controller_endpoint_present_in_topic_info": passed,
            "enable_execution_profiles_true": passed, "observation_pass": passed,
        }

    monkeypatch.setattr("e4a_runtime_provenance._controller_observation", observe)
    report = collect_controller_runtime_evidence(
        None, {}, [1, 2], max_attempts=4, retry_interval_s=0,
    )
    assert report["1"]["selected_observation_sequence"] == 1
    assert report["2"]["selected_observation_sequence"] == 3
    assert report["2"]["observation_count"] == 3
    assert [item["observation_pass"] for item in report["2"]["observation_attempts"]] == [False, False, True]


def test_persistent_absence_fails_closed(monkeypatch):
    def observe(_repo, _env, uid, sequence):
        return {
            "sequence": sequence, "node": f"/uav{uid}/ladrc_position_controller",
            "execution_command_topic": f"/uav{uid}/execution_command",
            "node_info": {}, "enable_execution_profiles": {}, "topic_info_verbose": {},
            "node_subscription_present": False,
            "controller_endpoint_present_in_topic_info": False,
            "enable_execution_profiles_true": False, "observation_pass": False,
        }

    monkeypatch.setattr("e4a_runtime_provenance._controller_observation", observe)
    report = collect_controller_runtime_evidence(
        None, {}, [1], max_attempts=4, retry_interval_s=0,
    )
    assert report["1"]["discovery_converged"] is False
    assert report["1"]["observation_count"] == 4
