"""Formal infrastructure tests. No registered scientific command is executed."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest


HERE = Path(__file__).resolve()
E5_DIR = HERE.parents[1]
TOOLING = E5_DIR / "tooling"
REPO = HERE.parents[4]
sys.path.insert(0, str(TOOLING))

from e5_v2_campaign_journal import CampaignJournal  # noqa: E402
from e5_v2_common import (  # noqa: E402
    BASELINE_COMMIT, OLD_E5_REGISTRY_PATH, OLD_E5_REGISTRY_SHA256,
    OLD_E5_SOURCE_COMMIT, PRODUCTION_METHOD_PATHS, flatten_conditions,
    load_yaml, sha256_file,
)
from e5_v2_formal_adapter import FormalActivationError, assert_formal_attempt  # noqa: E402
from e5_v2_formal_common import (  # noqa: E402
    ATTEMPTS_ROOT, JOURNAL_ROOT, RAW_LEDGER_ROOT, FormalInfrastructureError,
    build_launch_plan, exclusive_json, load_attempt_specs, runtime_submission,
    verify_final_tooling_bundle, verify_runtime_environment,
)
from e5_v2_formal_metrics import extract_metrics, synthetic_fixture  # noqa: E402
from e5_v2_raw_storage import (  # noqa: E402
    EvidenceIntegrityError, RawArchiveLedger, assert_no_pending_raw, pre_raw_failure,
    raw_evidence_loss, verify_and_publish_raw,
)
from e5_v2_static_rehearsal import run_rehearsal  # noqa: E402


def _attempt_artifact(root: Path, spec: dict, status="scientific_failure"):
    directory = root / f"{spec['campaign_position']:06d}__{spec['attempt_id']}"
    directory.mkdir(parents=True)
    exclusive_json(directory / "attempt.json", {
        "campaign_position": spec["campaign_position"],
        "attempt_id": spec["attempt_id"], "accepted_formal_result": False,
        "replacement_attempt": False, "attempt_status": status,
    })
    exclusive_json(directory / "compact_inventory.json", {
        "schema": "synthetic_rehearsal_compact_inventory"})
    return directory


def _append(journal, ledger, attempts, spec, status="scientific_failure"):
    artifact = _attempt_artifact(attempts, spec, status)
    raw_path = ledger.append(pre_raw_failure(spec, "synthetic"))
    return journal.append({
        "campaign_position": spec["campaign_position"],
        "attempt_id": spec["attempt_id"], "seed": spec["seed"], "N": spec["N"],
        "scenario_id": spec["scenario_id"], "substudy": spec["substudy"],
        "task_family": spec.get("task_family"), "attempt_status": status,
        "artifact_directory": artifact.name,
        "attempt_sha256": sha256_file(artifact / "attempt.json"),
        "compact_inventory_sha256": sha256_file(
            artifact / "compact_inventory.json"),
        "raw_ledger_record": raw_path.name,
        "raw_ledger_record_sha256": sha256_file(raw_path),
    })


def test_sealed_slot1_and_all_60_specs_compile_exactly():
    specs = load_attempt_specs()
    assert len(specs) == 60
    assert (specs[0]["attempt_id"], specs[0]["seed"], specs[0]["N"],
            specs[0]["task_family"]) == (
                "E5V2-B-S2-N12-R1", 5202036, 12, "UNDER_SPECIFIED")
    commands = {item["scenario_id"]: item["exact_command"]
                for item in flatten_conditions(load_yaml(E5_DIR / "E5_v2_registry.yaml"))}
    completed = []
    for position, spec in enumerate(specs, 1):
        assert spec["campaign_position"] == position
        assert spec["exact_command"] == commands[spec["scenario_id"]]
        assert_formal_attempt(
            order_position=position, trial_id=spec["attempt_id"], seed=spec["seed"],
            n=spec["N"], scenario_id=spec["scenario_id"],
            substudy=spec["substudy"], task_family=spec.get("task_family"),
            completed_attempt_ids=completed)
        completed.append(spec["attempt_id"])


@pytest.mark.parametrize("n", [8, 12, 16])
def test_dynamic_launch_configuration_and_topic_rule(n, tmp_path):
    spec = next(item for item in load_attempt_specs() if item["N"] == n)
    plan = build_launch_plan(spec, tmp_path)
    assert plan["uav_ids"] == list(range(1, n + 1))
    assert plan["sitl"][plan["sitl"].index("-n") + 1] == str(n)
    assert f"uav_ids:=[{','.join(map(str, range(1, n + 1)))}]" in plan["controllers"]
    assert plan["topic_count"] == 1 + 10 * n
    assert "control_mode:=ladrc_acceleration" in plan["controllers"]
    assert "avoidance_mode:=iapf_dual" in plan["controllers"]
    assert "iapf_escape_mode:=id_order" in plan["controllers"]


def test_candidate_gt_never_enters_runtime_or_fallback_source():
    submission = runtime_submission(load_attempt_specs()[0])
    assert not any("ground_truth" in key for key in submission)
    assert "candidate" not in submission and "mission_json" not in submission
    trial_source = (TOOLING / "e5_v2_formal_trial.py").read_text(encoding="utf-8")
    assert "parse_candidate_mission(submission[\"exact_command\"]" in trial_source
    assert '"fallback_used": False' in trial_source
    assert "execute_runtime_payload(node, candidate)" in trial_source


def test_formal_runtime_environment_and_provider_are_pinned():
    result = verify_runtime_environment()
    assert result["status"] == "PASS"
    assert result["openai"] == "2.34.0"
    assert result["httpx"] == "0.28.1"


def test_journal_prefix_failed_consumption_duplicate_order_and_hash(tmp_path):
    attempts, journal_root, ledger_root = (tmp_path / "attempts", tmp_path / "journal",
                                           tmp_path / "ledger")
    journal = CampaignJournal(journal_root, attempts, synthetic_rehearsal=True)
    ledger = RawArchiveLedger(ledger_root)
    specs = load_attempt_specs()
    first_path = _append(journal, ledger, attempts, specs[0], "infrastructure_failure")
    state = journal.state()
    assert state["consumed_slots"] == 1
    assert state["next_attempt"]["attempt_id"] == specs[1]["attempt_id"]
    with pytest.raises(FormalInfrastructureError, match="wrong next"):
        journal.append({"campaign_position": 3, "attempt_id": specs[2]["attempt_id"]})
    record = json.loads(first_path.read_text())
    record["attempt_id"] = "duplicate-or-wrong"
    first_path.chmod(0o644)
    first_path.write_text(json.dumps(record), encoding="utf-8")
    with pytest.raises(FormalInfrastructureError):
        journal.validate()


def test_adapter_refuses_replacement_attempt():
    first = load_attempt_specs()[0]
    with pytest.raises(FormalActivationError):
        assert_formal_attempt(
            order_position=1, trial_id=first["attempt_id"], seed=first["seed"],
            n=first["N"], scenario_id=first["scenario_id"],
            substudy=first["substudy"], task_family=first.get("task_family"),
            completed_attempt_ids=[first["attempt_id"]])


def test_raw_storage_dispositions_and_archive_verification(tmp_path):
    spec = load_attempt_specs()[0]
    pre = pre_raw_failure(spec, "synthetic startup failure")
    assert pre["raw_acquisition_started"] is False
    assert pre["disposition"] == "PRE_RAW_ACQUISITION_INFRASTRUCTURE_FAILURE"
    pending = tmp_path / "pending"
    (pending / "rosbag").mkdir(parents=True)
    (pending / "rosbag/metadata.yaml").write_text("synthetic: true\n")
    (pending / "rosbag/evidence.db3").write_bytes(b"fixture")
    verified = verify_and_publish_raw(spec, pending, tmp_path / "archive")
    assert verified["disposition"] == "RAW_ARCHIVE_VERIFIED"
    assert verified["archive_verification"] == "PASS"
    assert verified["total_bytes"] > 0
    broken = tmp_path / "broken"
    broken.mkdir()
    with pytest.raises(EvidenceIntegrityError):
        verify_and_publish_raw(spec, broken, tmp_path / "archive2")
    assert raw_evidence_loss(spec, "synthetic")["campaign_stop"] is True
    (tmp_path / "archive/.pending/orphan").mkdir(parents=True)
    with pytest.raises(EvidenceIntegrityError, match="RAW_ARCHIVE_PENDING"):
        assert_no_pending_raw(tmp_path / "archive")


def test_metric_NA_never_zero_and_synthetic_schema():
    spec = load_attempt_specs()[0]
    stages = {"infrastructure_readiness": {"success": False},
              "candidate_validation": {"success": False},
              "resolver": {"success": False}, "planning": {"success": False},
              "mission_completion": {"success": False},
              "scientific_terminal_reached": False}
    metrics = extract_metrics(spec, stages, {"candidate": None},
                              "PRE_RAW_ACQUISITION_INFRASTRUCTURE_FAILURE")
    for key in ("actual_d_min", "tracking_rmse", "final_error", "completion_time"):
        assert metrics[key]["available"] is False
        assert metrics[key]["value"] is None
    fixture = synthetic_fixture(spec["N"])
    fixture["candidate"] = spec["candidate_semantic_ground_truth"]
    stages.update({"infrastructure_readiness": {"success": True},
                   "candidate_validation": {"success": True},
                   "resolver": {"success": True}, "planning": {"success": True},
                   "mission_completion": {"success": True},
                   "scientific_terminal_reached": True, "hard_failure": False})
    assert extract_metrics(spec, stages, fixture,
                           "RAW_ARCHIVE_VERIFIED")["mission_success"]["value"] is True


def test_final_bundle_exact_hashes_and_excludes_smoke():
    bundle = verify_final_tooling_bundle()
    names = {Path(item["path"]).name for item in bundle["files"]}
    assert "e5_v2_formal_backend.py" in names
    assert "e5_v2_formal_orchestrator.py" in names
    assert "e5_v2_engineering_smoke.py" not in names
    assert "e5_v2_wait_ready.py" not in names


def test_rehearsal_leaves_real_formal_state_empty_or_preserves_recovered_prefix():
    existing = CampaignJournal().state()
    if existing["consumed_slots"]:
        assert existing["consumed_slots"] == 1
        assert existing["completed_attempt_ids"] == ["E5V2-B-S2-N12-R1"]
        assert existing["next_attempt"]["campaign_position"] == 2
        return
    result = run_rehearsal()
    assert result["result"] == "PASS"
    assert result["registered_commands_physically_submitted"] == 0
    assert not list(JOURNAL_ROOT.glob("*.json"))
    assert not list(RAW_LEDGER_ROOT.glob("*.json"))
    assert not [path for path in ATTEMPTS_ROOT.glob("*") if path.is_dir()]


def test_old_registry_and_production_method_untouched():
    old = subprocess.check_output(
        ["git", "show", f"{OLD_E5_SOURCE_COMMIT}:{OLD_E5_REGISTRY_PATH}"], cwd=REPO)
    import hashlib
    assert hashlib.sha256(old).hexdigest() == OLD_E5_REGISTRY_SHA256
    assert subprocess.run(["git", "diff", "--quiet", BASELINE_COMMIT, "--",
                           *PRODUCTION_METHOD_PATHS], cwd=REPO).returncode == 0
