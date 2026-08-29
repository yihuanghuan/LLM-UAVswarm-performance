"""Campaign-v2 population, journal, crash, and isolation regressions."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import shutil
import sys
import uuid

import pytest

from campaign_v2_common import (CampaignV2Error, FORMAL_EVAL, FORMAL_ROOT, HERE,
                                REHEARSAL_ROOT, canonical_sha256, family_for_trial,
                                load_order, sha256_file)
from campaign_v2_coordinator import Coordinator, Journal, verify_pins


def disposable(name: str) -> Path:
    path = REHEARSAL_ROOT / f"test-{name}-{uuid.uuid4().hex}"
    return path


def load_attempt(run: Path, position: int) -> dict:
    return json.loads((run / f"adapter-attempts/{position:06d}/attempt.json").read_text())


def test_exact_population_and_original_order():
    order = load_order()
    generator = FORMAL_EVAL / "harness/generate_simulation_trial_order_v1.py"
    spec = importlib.util.spec_from_file_location("sealed_generator", generator)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    assert set(order) == set(module.canonical_ids())
    assert len(order) == len(set(order)) == 610


def test_analysis_population_compatibility():
    tool_dir = FORMAL_EVAL / "analysis_freeze/tooling"
    sys.path.insert(0, str(tool_dir))
    try:
        import population_analysis as population
        order = load_order()
        by_family = {family: {trial for trial in order if family_for_trial(trial) == family}
                     for family in ("E2", "E3", "E4A", "E4B", "E5")}
        assert by_family["E3"] == population.expected_e3_trials()
        assert by_family["E4A"] == population.expected_e4a_trials()
        assert by_family["E4B"] == population.expected_e4b_trials()
        assert by_family["E5"] == population.expected_e5_trials()
        assert len(by_family["E2"]) == 120
    finally:
        sys.path.remove(str(tool_dir))


def test_preserved_e2_scorer():
    scorer = Path("/home/yihuang/learning/LLM_swarm_ws/e2_adapter_worktree") / (
        "experiments_v2/Formal Evaluation Experiments/E2/tooling/e2_scorer.py")
    assert sha256_file(scorer) == "7b7725a6cba5fc3ba89636db5a87d2f26a65bfc8c85e764dfd16dfa7f4cfc48a"


def test_final_scientific_spec_corrections_are_active():
    run = HERE / "results/synthetic-validation/campaign-v2-full-610-rehearsal-r3"
    order = load_order()
    by_id = {trial: i for i, trial in enumerate(order, 1)}
    a01 = load_attempt(run, by_id["E3-A-01__P0_F0__S53101"])["execution_spec"]
    a02 = load_attempt(run, by_id["E3-A-02__P0_F0__S53101"])["execution_spec"]
    c01 = load_attempt(run, by_id["E3-C-01__P1_F1__S53101"])["execution_spec"]
    c02 = load_attempt(run, by_id["E3-C-02__P1_F1__S53101"])["execution_spec"]
    targets = {"1": [-3, 4, 3], "2": [3, 4, 3], "3": [-2, 12, 3], "4": [0, 12, 3]}
    assert a01["ordered_targets_m"] == targets
    assert c01["ordered_targets_m"] == targets
    assert a02["duration_s"] == c02["duration_s"] == 9.5
    assert a01["spec_type"] == c02["spec_type"] == "E3_exact_execution_spec_v3"
    e4b = load_attempt(run, by_id["E4B-INFEASIBLE-EXPLICIT-T__normal__S54201"])["execution_spec"]
    assert e4b["requested_T"]["value_s"] < e4b["T_min_s"]
    assert e4b["expected_T_exec_s"] >= e4b["T_min_s"]


def test_full_rehearsal_and_restart_checkpoints():
    summary = json.loads((HERE / "results/synthetic-validation/campaign-v2-full-610-rehearsal-r3/rehearsal_summary.json").read_text())
    assert summary["status"] == "PASS"
    assert summary["accounted_positions"] == summary["unique_trial_ids"] == 610
    retained = {item["retained_count"] for item in summary["restart_checkpoint_results"]}
    assert {1, 2, 7, 11, 120, 121, 480, 481, 585, 586, 609, 610} <= retained
    assert summary["restart_checkpoint_results"][-1]["complete"] is True


def test_pristine_and_two_attempt_restart():
    root = disposable("restart")
    try:
        c = Coordinator("rehearsal", root)
        assert c.validate_state()["next_position"] == 1
        c.dispatch_next()
        assert Coordinator("rehearsal", root).validate_state()["next_position"] == 2
        Coordinator("rehearsal", root).dispatch_next()
        assert Coordinator("rehearsal", root).validate_state()["next_position"] == 3
    finally:
        shutil.rmtree(root, ignore_errors=True)


def test_retained_failure_advances_and_pre_dispatch_does_not():
    root = disposable("failure")
    try:
        c = Coordinator("rehearsal", root)
        assert c.validate_state()["next_position"] == 1
        # A refusal before calling dispatch leaves the journal untouched.
        with pytest.raises(CampaignV2Error):
            c.dispatch_next(requested_trial_id=load_order()[1])
        assert c.validate_state()["next_position"] == 1
        c.dispatch_next(synthetic_terminal_status="method_failure")
        assert Coordinator("rehearsal", root).validate_state()["next_position"] == 2
        Coordinator("rehearsal", root).dispatch_next(synthetic_terminal_status="infrastructure_failure")
        assert Coordinator("rehearsal", root).validate_state()["next_position"] == 3
    finally:
        shutil.rmtree(root, ignore_errors=True)


@pytest.mark.parametrize("window", ["orphan_adapter", "orphan_envelope", "journal_without_artifact"])
def test_crash_windows_fail_closed(window: str):
    root = disposable(window)
    try:
        c = Coordinator("rehearsal", root)
        if window == "orphan_adapter":
            (root / "adapter-attempts/000001").mkdir(parents=True)
        elif window == "orphan_envelope":
            (root / "attempt-artifacts").mkdir(parents=True)
            (root / "attempt-artifacts/000001-attempt.json").write_text("{}\n")
        else:
            Journal(root).append({
                "schema": "campaign_v2_suite_journal_record_v1", "global_position": 1,
                "trial_id": load_order()[0], "experiment": "E2", "attempt_status": "success",
                "artifact_path": "attempt-artifacts/000001-attempt.json", "artifact_sha256": "0" * 64,
            }, [])
        with pytest.raises(CampaignV2Error):
            Coordinator("rehearsal", root)
    finally:
        shutil.rmtree(root, ignore_errors=True)


def test_wrong_family_and_nonformal_isolation(monkeypatch):
    root = disposable("isolation")
    try:
        c = Coordinator("rehearsal", root)
        with pytest.raises(CampaignV2Error):
            c.reject_family_selector("E3")
        with pytest.raises(CampaignV2Error):
            Coordinator("rehearsal", FORMAL_ROOT)
        monkeypatch.delenv("CAMPAIGN_V2_HUMAN_LAUNCH_TOKEN_SHA256", raising=False)
        with pytest.raises(CampaignV2Error):
            Coordinator("formal", FORMAL_ROOT)
    finally:
        shutil.rmtree(root, ignore_errors=True)


def test_all_execution_worktrees_clean_and_hash_gated():
    assert verify_pins()["status"] == "PASS"


def test_launch_tooling_bundle_and_future_authorization_are_hash_pinned():
    bundle = json.loads((HERE / "campaign_v2_launch_tooling_bundle.json").read_text())
    files = {path: sha256_file(HERE / path) for path in bundle["files"]}
    assert files == bundle["files"]
    assert canonical_sha256(files) == bundle["campaign_v2_launch_tooling_bundle_sha256"]
    auth = json.loads((HERE / "campaign_v2_launch_authorization.json").read_text())
    assert auth["launcher_tooling_bundle_sha256"] == bundle["campaign_v2_launch_tooling_bundle_sha256"]
    assert auth["formal_launch_already_started"] is False
    assert auth["human_launch_trigger_present"] is False


def test_formal_root_pristine_and_human_trigger_still_required(monkeypatch):
    state = json.loads((FORMAL_ROOT / "pristine_root_state.json").read_text())
    assert (state["retained_formal_attempts"], state["journal_records"],
            state["accepted_formal_results"], state["next_global_position"]) == (0, 0, 0, 1)
    assert not (FORMAL_ROOT / "HUMAN_LAUNCH_TRIGGER.json").exists()
    monkeypatch.setenv("RMW_IMPLEMENTATION", "rmw_fastrtps_cpp")
    monkeypatch.setenv("ROS_DOMAIN_ID", "42")
    monkeypatch.setenv("CAMPAIGN_V2_HUMAN_LAUNCH_TOKEN_SHA256", "0" * 64)
    with pytest.raises(CampaignV2Error, match="missing future human launch-trigger"):
        Coordinator("formal", FORMAL_ROOT)
