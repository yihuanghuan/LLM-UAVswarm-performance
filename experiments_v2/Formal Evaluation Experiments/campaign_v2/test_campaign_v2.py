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
                                REHEARSAL_ROOT, canonical_sha256, exclusive_json,
                                family_for_trial, load_order, sha256_file)
from campaign_v2_coordinator import (AUTHORIZATION, FORMAL_LABELS, Coordinator,
                                     Journal, verify_pins)


def disposable(name: str) -> Path:
    path = REHEARSAL_ROOT / f"test-{name}-{uuid.uuid4().hex}"
    return path


def disposable_formal(name: str) -> Path:
    return REHEARSAL_ROOT / "formal-mode-tests" / f"test-{name}-{uuid.uuid4().hex}"


def formal_launcher_payload() -> dict:
    order = load_order()
    return {
        "schema": "campaign_v2_pristine_formal_root_manifest_v1",
        "artifact_class": "formal_campaign_metadata",
        "campaign_id": "E2-E5-final-paper-campaign-v2",
        "campaign_manifest_sha256": sha256_file(HERE / "campaign_v2_manifest.json"),
        "formal_campaign_started": False,
        "retained_formal_attempts": 0,
        "journal_records": 0,
        "accepted_formal_results": 0,
        "next_global_position": 1,
        "next_trial_id": order[0],
        "journal_is_cursor_authority": True,
        "formal_dispatch_authorized_in_this_phase": False,
    }


def initialize_isolated_formal_root(root: Path, monkeypatch,
                                    *, trigger_field: str = "authorize_campaign_v2") -> None:
    root.mkdir(parents=True)
    exclusive_json(root / "launcher_run_manifest.json", formal_launcher_payload())
    exclusive_json(root / "HUMAN_LAUNCH_TRIGGER.json", {
        "schema": "campaign_v2_human_launch_trigger_v1",
        trigger_field: True,
        "campaign_manifest_sha256": sha256_file(HERE / "campaign_v2_manifest.json"),
    })
    monkeypatch.setenv("CAMPAIGN_V2_ISOLATED_FORMAL_TEST", "1")
    monkeypatch.setenv("CAMPAIGN_V2_HUMAN_LAUNCH_TOKEN_SHA256",
                       sha256_file(root / "HUMAN_LAUNCH_TRIGGER.json"))


def retain_formal_prefix(root: Path, count: int,
                         statuses: dict[int, str] | None = None) -> None:
    statuses = statuses or {}
    order = load_order()
    journal = Journal(root)
    records = []
    for position in range(1, count + 1):
        trial = order[position - 1]
        family = family_for_trial(trial)
        status = statuses.get(position, "success")
        adapter_path = root / f"adapter-attempts/{position:06d}/attempt.json"
        exclusive_json(adapter_path, {
            "record_type": "campaign_v2_formal_test_adapter_attempt",
            "dataset_class": "formal_evaluation",
            "accepted_formal_result": True,
            "result_notice": None,
            "execution_mode": "formal",
            "global_trial_position": position,
            "trial_id": trial,
            "experiment": family,
            "attempt_status": status,
        })
        envelope_path = root / f"attempt-artifacts/{position:06d}-attempt.json"
        envelope = {
            "schema": "campaign_v2_attempt_envelope_v1",
            **FORMAL_LABELS,
            "global_position": position,
            "trial_id": trial,
            "experiment": family,
            "attempt_status": status,
            "replacement_attempt": False,
            "adapter_artifact_path": f"adapter-attempts/{position:06d}/attempt.json",
            "adapter_artifact_sha256": sha256_file(adapter_path),
        }
        exclusive_json(envelope_path, envelope)
        record = journal.append({
            "schema": "campaign_v2_suite_journal_record_v1",
            **FORMAL_LABELS,
            "global_position": position,
            "trial_id": trial,
            "experiment": family,
            "attempt_status": status,
            "replacement_attempt": False,
            "artifact_path": f"attempt-artifacts/{position:06d}-attempt.json",
            "artifact_sha256": sha256_file(envelope_path),
        }, records)
        records.append(record)


def formal_coordinator(root: Path) -> Coordinator:
    return Coordinator(
        "formal", root,
        _isolated_formal_test_root=root,
        _isolated_runtime_validator=lambda **_kwargs: {"status": "PASS"},
        _isolated_authorization_path=AUTHORIZATION,
    )


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
    run = HERE / "results/synthetic-validation/campaign-v2-full-610-rehearsal-r4"
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
    summary = json.loads((HERE / "results/synthetic-validation/campaign-v2-full-610-rehearsal-r4/rehearsal_summary.json").read_text())
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


def test_formal_t1_pristine_root_resumes_at_position_1(monkeypatch):
    root = disposable_formal("f0")
    try:
        initialize_isolated_formal_root(root, monkeypatch)
        state = formal_coordinator(root).validate_state()
        assert (state["retained_count"], state["next_position"], state["next_trial_id"]) == (
            0, 1, load_order()[0])
    finally:
        shutil.rmtree(root, ignore_errors=True)


@pytest.mark.parametrize("count,expected", [(1, 2), (2, 3)])
def test_formal_t2_t3_valid_prefix_resumes_at_exact_next(monkeypatch, count: int, expected: int):
    root = disposable_formal(f"prefix-{count}")
    try:
        initialize_isolated_formal_root(root, monkeypatch)
        retain_formal_prefix(root, count)
        state = formal_coordinator(root).validate_state()
        assert state["retained_count"] == count
        assert state["next_position"] == expected
        assert state["next_trial_id"] == load_order()[expected - 1]
    finally:
        shutil.rmtree(root, ignore_errors=True)


@pytest.mark.parametrize("status", ["method_failure", "infrastructure_failure"])
def test_formal_t4_t5_retained_failures_advance(monkeypatch, status: str):
    root = disposable_formal(status)
    try:
        initialize_isolated_formal_root(root, monkeypatch)
        retain_formal_prefix(root, 1, {1: status})
        state = formal_coordinator(root).validate_state()
        assert state["retained_count"] == 1
        assert state["next_position"] == 2
        assert state["status_counts"] == {status: 1}
    finally:
        shutil.rmtree(root, ignore_errors=True)


def test_formal_t6_mixed_family_boundary_uses_global_cursor(monkeypatch):
    root = disposable_formal("mixed-family")
    try:
        initialize_isolated_formal_root(root, monkeypatch)
        order = load_order()
        boundary = next(i for i in range(1, len(order))
                        if family_for_trial(order[i - 1]) != family_for_trial(order[i]))
        retain_formal_prefix(root, boundary)
        coordinator = formal_coordinator(root)
        state = coordinator.validate_state()
        assert state["next_position"] == boundary + 1
        assert family_for_trial(state["next_trial_id"]) == family_for_trial(order[boundary])
        with pytest.raises(CampaignV2Error):
            coordinator.reject_family_selector(family_for_trial(order[boundary - 1]))
    finally:
        shutil.rmtree(root, ignore_errors=True)


@pytest.mark.parametrize("count,next_position", [(609, 610), (610, None)])
def test_formal_t7_t8_late_and_complete_campaign(monkeypatch, count: int,
                                                 next_position: int | None):
    root = disposable_formal(f"late-{count}")
    try:
        initialize_isolated_formal_root(root, monkeypatch)
        retain_formal_prefix(root, count)
        coordinator = formal_coordinator(root)
        state = coordinator.validate_state()
        assert state["retained_count"] == count
        assert state["next_position"] == next_position
        assert state["complete"] is (count == 610)
        if count == 610:
            assert state["next_trial_id"] is None
            with pytest.raises(CampaignV2Error, match="campaign rehearsal complete"):
                coordinator.dispatch_next()
    finally:
        shutil.rmtree(root, ignore_errors=True)


@pytest.mark.parametrize("corruption", [
    "journal_without_envelope", "envelope_without_journal", "adapter_without_envelope_or_journal",
    "envelope_hash_mismatch", "adapter_hash_mismatch", "noncontiguous_journal",
    "wrong_trial_id", "partial_temp", "extra_attempt_directory", "foreign_formal_artifact",
])
def test_formal_crash_and_orphan_states_fail_closed(monkeypatch, corruption: str):
    root = disposable_formal(corruption)
    try:
        initialize_isolated_formal_root(root, monkeypatch)
        if corruption == "adapter_without_envelope_or_journal":
            (root / "adapter-attempts/000001").mkdir(parents=True)
        else:
            retain_formal_prefix(root, 1)
            if corruption == "journal_without_envelope":
                (root / "attempt-artifacts/000001-attempt.json").unlink()
            elif corruption == "envelope_without_journal":
                shutil.rmtree(root / "suite-journal")
            elif corruption == "envelope_hash_mismatch":
                path = root / "attempt-artifacts/000001-attempt.json"
                path.chmod(0o644)
                with path.open("a") as stream:
                    stream.write(" ")
            elif corruption == "adapter_hash_mismatch":
                path = root / "adapter-attempts/000001/attempt.json"
                path.chmod(0o644)
                with path.open("a") as stream:
                    stream.write(" ")
            elif corruption == "noncontiguous_journal":
                (root / "suite-journal/000001-attempt.json").rename(
                    root / "suite-journal/000002-attempt.json")
            elif corruption == "wrong_trial_id":
                path = root / "suite-journal/000001-attempt.json"
                record = json.loads(path.read_text())
                record["trial_id"] = load_order()[1]
                record.pop("record_sha256")
                record["record_sha256"] = canonical_sha256(record)
                path.chmod(0o644)
                path.write_text(json.dumps(record, sort_keys=True, indent=2) + "\n")
            elif corruption == "partial_temp":
                (root / "attempt-artifacts/.pending.tmp-test").write_text("partial")
            elif corruption == "extra_attempt_directory":
                (root / "adapter-attempts/000002").mkdir()
            elif corruption == "foreign_formal_artifact":
                (root / "attempt-artifacts/foreign.json").write_text("{}\n")
        with pytest.raises(CampaignV2Error):
            formal_coordinator(root)
    finally:
        shutil.rmtree(root, ignore_errors=True)


def test_formal_authorization_is_campaign_scoped_and_survives_resume(monkeypatch):
    root = disposable_formal("authorization-resume")
    try:
        # The prospective campaign-level spelling is preferred.
        initialize_isolated_formal_root(root, monkeypatch, trigger_field="authorize_campaign_v2")
        retain_formal_prefix(root, 1)
        assert formal_coordinator(root).validate_state()["next_position"] == 2

        # The already documented attempt-1 spelling remains auditable and is
        # interpreted as authorization to start this immutable campaign.
        trigger = root / "HUMAN_LAUNCH_TRIGGER.json"
        trigger.unlink()
        exclusive_json(trigger, {
            "schema": "campaign_v2_human_launch_trigger_v1",
            "authorize_formal_attempt_1": True,
            "campaign_manifest_sha256": sha256_file(HERE / "campaign_v2_manifest.json"),
        })
        monkeypatch.setenv("CAMPAIGN_V2_HUMAN_LAUNCH_TOKEN_SHA256", sha256_file(trigger))
        assert formal_coordinator(root).validate_state()["next_position"] == 2
    finally:
        shutil.rmtree(root, ignore_errors=True)


@pytest.mark.parametrize("failure", ["missing_trigger", "wrong_sha", "wrong_manifest"])
def test_formal_authorization_failures_remain_closed(monkeypatch, failure: str):
    root = disposable_formal(f"auth-{failure}")
    try:
        initialize_isolated_formal_root(root, monkeypatch)
        trigger = root / "HUMAN_LAUNCH_TRIGGER.json"
        if failure == "missing_trigger":
            trigger.unlink()
        elif failure == "wrong_sha":
            monkeypatch.setenv("CAMPAIGN_V2_HUMAN_LAUNCH_TOKEN_SHA256", "0" * 64)
        else:
            trigger.unlink()
            exclusive_json(trigger, {
                "schema": "campaign_v2_human_launch_trigger_v1",
                "authorize_campaign_v2": True,
                "campaign_manifest_sha256": "0" * 64,
            })
            monkeypatch.setenv("CAMPAIGN_V2_HUMAN_LAUNCH_TOKEN_SHA256", sha256_file(trigger))
        with pytest.raises(CampaignV2Error):
            formal_coordinator(root)
    finally:
        shutil.rmtree(root, ignore_errors=True)


def test_isolated_formal_injection_cannot_escape_nonformal_test_root(monkeypatch):
    monkeypatch.setenv("CAMPAIGN_V2_ISOLATED_FORMAL_TEST", "1")
    with pytest.raises(CampaignV2Error, match="escaped"):
        Coordinator("formal", FORMAL_ROOT,
                    _isolated_formal_test_root=FORMAL_ROOT,
                    _isolated_runtime_validator=lambda **_kwargs: {"status": "PASS"})
