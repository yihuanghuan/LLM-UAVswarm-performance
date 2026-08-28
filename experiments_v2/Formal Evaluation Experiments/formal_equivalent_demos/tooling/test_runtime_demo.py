import json

import runtime_demo


def test_e5_method_rejection_retains_zero_dispatch_and_termination(tmp_path, monkeypatch):
    raw = tmp_path / "raw"
    (raw / "ros_home").mkdir(parents=True)
    (raw / "llm_raw_responses.append.jsonl").write_text("{}\n")
    (raw / "validated_candidate.json").write_text("{}\n")
    (raw / "ros_home/candidate_resolution_trace.jsonl").write_text("{}\n")
    (raw / "readiness.log").write_text("ready\n")
    (raw / "language_result.json").write_text(json.dumps({
        "attempt_status": "method_failure",
        "failure_stage": "resolution",
        "mission_termination": "frozen_method_rejection",
        "error": "GeometryError: workspace limit",
    }))
    counts = {"/clock": 1}
    for uid in range(1, 9):
        counts.update({
            f"/uav{uid}/swarm_state": 1,
            f"/uav{uid}/control_tracking_debug": 1,
            f"/uav{uid}/iapf_debug": 1,
            f"/uav{uid}/status": 1,
            f"/px4_{uid}/fmu/out/vehicle_status": 1,
        })
    monkeypatch.setattr(runtime_demo, "bag_counts", lambda _raw: counts)
    audit = runtime_demo.raw_audit("E5", {"uav_ids": list(range(1, 9))}, raw)
    assert audit["complete"] is True
    retained = {item["required_raw_field"]: item for item in audit["requirements"]}
    assert "zero-dispatch" in retained["dispatch_events"]["authoritative_source"]
    assert "pre-dispatch" in retained["task_completion_events"]["authoritative_source"]
