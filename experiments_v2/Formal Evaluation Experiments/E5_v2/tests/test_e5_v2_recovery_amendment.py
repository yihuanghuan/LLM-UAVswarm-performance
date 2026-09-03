"""Non-formal regression tests for the E5-v2 slot-1 recovery amendment."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest


HERE = Path(__file__).resolve()
E5_DIR = HERE.parents[1]
TOOLING = E5_DIR / "tooling"
REPO = HERE.parents[4]
sys.path.insert(0, str(TOOLING))

import e5_v2_formal_common as common  # noqa: E402
import e5_v2_recover_preserved_attempt as recovery  # noqa: E402
from e5_v2_campaign_journal import CampaignJournal  # noqa: E402
from e5_v2_common import (  # noqa: E402
    BASELINE_COMMIT, OLD_E5_REGISTRY_PATH, OLD_E5_REGISTRY_SHA256,
    OLD_E5_SOURCE_COMMIT, PRODUCTION_METHOD_PATHS, sha256_file,
)
from e5_v2_formal_common import (  # noqa: E402
    EvidenceIntegrityError, FormalInfrastructureError,
    RecoverableTransactionError, canonical_sha256, inventory,
    load_attempt_specs,
)
from e5_v2_formal_metrics import (  # noqa: E402
    J_HARD_UNAVAILABLE_REASON, extract_metrics, synthetic_fixture,
)
from e5_v2_formal_orchestrator import read_verified_evidence_or_block  # noqa: E402
from e5_v2_raw_storage import (  # noqa: E402
    raw_evidence_loss, verify_existing_raw_archive,
)


def _successful_stages():
    return {
        "infrastructure_readiness": {"success": True},
        "candidate_validation": {"success": True},
        "resolver": {"success": True}, "planning": {"success": True},
        "geometry": {"success": True},
        "execution_profile_compilation": {"success": True},
        "mission_dispatch": {"success": True, "any_command_dispatched": True},
        "controller_px4": {"success": True, "reached": True, "reason": None},
        "mission_completion": {"success": True},
        "scientific_terminal_reached": True, "hard_failure": False,
    }


def _preserved_source_context():
    context = recovery.default_context()
    if context.transaction_root.is_dir():
        return context
    recovered = (
        E5_DIR / "results/formal_v2/recovered_transaction_evidence" /
        context.transaction_root.name)
    return recovery.RecoveryContext(
        transaction_root=recovered, raw_archive=context.raw_archive)


def test_j_hard_is_always_unavailable_and_has_no_proxy():
    spec = load_attempt_specs()[0]
    for evidence in ({"candidate": None}, synthetic_fixture(spec["N"])):
        evidence["candidate"] = spec["candidate_semantic_ground_truth"]
        metrics = extract_metrics(
            spec, _successful_stages(), evidence, "RAW_ARCHIVE_VERIFIED")
        assert metrics["J_hard"] == {
            "available": False, "value": None,
            "reason": J_HARD_UNAVAILABLE_REASON,
        }
    source = (TOOLING / "e5_v2_formal_metrics.py").read_text(encoding="utf-8")
    assert '"J_hard": unavailable(J_HARD_UNAVAILABLE_REASON)' in source
    assert '"J_hard": (available(int(not d_min_ok))' not in source


def test_mission_success_independently_uses_frozen_d_min_threshold():
    spec = load_attempt_specs()[0]
    safe = synthetic_fixture(spec["N"])
    safe["candidate"] = spec["candidate_semantic_ground_truth"]
    assert extract_metrics(
        spec, _successful_stages(), safe,
        "RAW_ARCHIVE_VERIFIED")["mission_success"]["value"] is True
    unsafe = synthetic_fixture(spec["N"])
    unsafe["candidate"] = spec["candidate_semantic_ground_truth"]
    unsafe["positions"][2] = [
        [row[0], unsafe["positions"][1][index][1] + 1.49, row[2], row[3]]
        for index, row in enumerate(unsafe["positions"][2])
    ]
    result = extract_metrics(
        spec, _successful_stages(), unsafe, "RAW_ARCHIVE_VERIFIED")
    assert result["actual_d_min"]["value"] < 1.50
    assert result["mission_success"]["value"] is False
    assert result["J_hard"]["available"] is False


def test_ros_python_modules_import_via_amended_environment():
    wrapper = TOOLING / "e5_v2_formal_environment.sh"
    completed = subprocess.run(
        [str(wrapper), "-c",
         "import rosbag2_py,rclpy,rosidl_runtime_py; print('PASS')"],
        cwd=REPO, capture_output=True, text=True, check=True)
    assert completed.stdout.strip() == "PASS"


def test_verified_archive_survives_metric_reader_failure(tmp_path):
    spec = load_attempt_specs()[0]
    archive = tmp_path / "archive"
    (archive / "rosbag").mkdir(parents=True)
    (archive / "rosbag/metadata.yaml").write_text("fixture: true\n")
    (archive / "rosbag/evidence.db3").write_bytes(b"fixture")
    records = inventory(archive)
    disposition = {
        "archive_reference": str(archive), "file_inventory": records,
        "disposition": "RAW_ARCHIVE_VERIFIED",
    }

    def fail_reader(*_args):
        raise ModuleNotFoundError("synthetic metric reader environment failure")

    before = canonical_sha256(inventory(archive))
    with pytest.raises(RecoverableTransactionError):
        read_verified_evidence_or_block(spec, disposition, None, reader=fail_reader)
    assert archive.is_dir()
    assert canonical_sha256(inventory(archive)) == before
    assert not (tmp_path / "evidence_loss").exists()


def test_raw_evidence_loss_reserved_for_unverifiable_evidence(tmp_path):
    spec = load_attempt_specs()[0]
    with pytest.raises(EvidenceIntegrityError):
        verify_existing_raw_archive(spec, tmp_path / "missing")
    loss = raw_evidence_loss(
        spec, "genuinely missing", existing_archive=tmp_path / "missing")
    assert loss["disposition"] == "RAW_EVIDENCE_LOSS"
    assert loss["campaign_stop"] is True


def test_recovery_source_has_no_physical_backend_path():
    source = (TOOLING / "e5_v2_recover_preserved_attempt.py").read_text(
        encoding="utf-8")
    forbidden = (
        "run_physical_trial", "start_process(", "MicroXRCEAgent",
        "ros2 bag record", "parse_candidate_mission", "execute_runtime_payload",
    )
    assert not any(token in source for token in forbidden)


def test_recovery_refuses_wrong_raw_and_transaction_hash(tmp_path, monkeypatch):
    monkeypatch.setattr(recovery, "_verify_bundle", lambda _path: {
        "bundle_sha256": "synthetic"})
    source = _preserved_source_context()
    context = recovery.RecoveryContext(
        transaction_root=source.transaction_root, raw_archive=source.raw_archive,
        attempts_root=tmp_path / "attempts", journal_root=tmp_path / "journal",
        ledger_root=tmp_path / "ledger",
        recovered_transactions_root=tmp_path / "recovered",
        recovery_bundle_path=tmp_path / "bundle.json", make_read_only=False,
        synthetic_rehearsal=True)
    with pytest.raises(EvidenceIntegrityError, match="transaction inventory"):
        recovery.verify_recovery_gate(context, expected_transaction_sha="0" * 64)
    with pytest.raises(EvidenceIntegrityError, match="raw inventory"):
        recovery.verify_recovery_gate(context, expected_raw_sha="0" * 64)


def test_recovery_refuses_wrong_slot_identity(monkeypatch):
    original = recovery.load_attempt_specs
    specs = original()
    specs[0] = {**specs[0], "seed": 1}
    monkeypatch.setattr(recovery, "load_attempt_specs", lambda: specs)
    with pytest.raises(FormalInfrastructureError, match="slot-1 seed mismatch"):
        recovery.verify_recovery_gate(recovery.default_context())


def _synthetic_metrics(spec):
    evidence = synthetic_fixture(spec["N"])
    evidence["candidate"] = spec["candidate_semantic_ground_truth"]
    return extract_metrics(spec, _successful_stages(), evidence, "RAW_ARCHIVE_VERIFIED")


def test_recovery_exactly_once_publication_and_prefix(tmp_path, monkeypatch):
    source = _preserved_source_context()
    transaction = tmp_path / source.transaction_root.name
    raw = tmp_path / "raw"
    shutil.copytree(source.transaction_root, transaction)
    transaction.chmod(0o755)
    shutil.copytree(source.raw_archive, raw)
    state = tmp_path / "state"
    context = recovery.RecoveryContext(
        transaction_root=transaction, raw_archive=raw,
        attempts_root=state / "attempts", journal_root=state / "journal",
        ledger_root=state / "ledger",
        recovered_transactions_root=state / "recovered",
        recovery_bundle_path=tmp_path / "synthetic-bundle.json",
        make_read_only=False, synthetic_rehearsal=True,
    )
    monkeypatch.setattr(recovery, "_verify_bundle", lambda _path: {
        "bundle_sha256": "1" * 64})
    monkeypatch.setattr(recovery, "verify_ros_python_environment", lambda: {
        "status": "PASS"})
    monkeypatch.setattr(
        recovery, "_read_confirmed_evidence",
        lambda gate, _context: ([], _successful_stages(),
                                _synthetic_metrics(gate["spec"])))
    result = recovery.publish_recovery(context)
    assert result["published"] is True and result["physical_rerun"] is False
    journal = CampaignJournal(
        context.journal_root, context.attempts_root, synthetic_rehearsal=True)
    assert journal.state()["completed_attempt_ids"] == [recovery.SLOT1_ATTEMPT_ID]
    assert journal.state()["next_attempt"]["campaign_position"] == 2
    assert len(list(context.ledger_root.glob("*.json"))) == 1
    assert len([path for path in context.attempts_root.glob("*") if path.is_dir()]) == 1
    assert not context.transaction_root.exists()
    with pytest.raises(FormalInfrastructureError):
        recovery.publish_recovery(context)


def test_recovery_refuses_nonempty_prefix(tmp_path, monkeypatch):
    source = _preserved_source_context()
    transaction = tmp_path / source.transaction_root.name
    raw = tmp_path / "raw"
    shutil.copytree(source.transaction_root, transaction)
    transaction.chmod(0o755)
    shutil.copytree(source.raw_archive, raw)
    journal = tmp_path / "state/journal"
    journal.mkdir(parents=True)
    (journal / "000001__E5V2-B-S2-N12-R1.json").write_text("{}\n")
    context = recovery.RecoveryContext(
        transaction_root=transaction, raw_archive=raw,
        attempts_root=tmp_path / "state/attempts", journal_root=journal,
        ledger_root=tmp_path / "state/ledger",
        recovered_transactions_root=tmp_path / "state/recovered",
        recovery_bundle_path=tmp_path / "bundle.json", make_read_only=False,
        synthetic_rehearsal=True,
    )
    monkeypatch.setattr(recovery, "_verify_bundle", lambda _path: {
        "bundle_sha256": "synthetic"})
    with pytest.raises(FormalInfrastructureError):
        recovery.verify_recovery_gate(context)


def test_future_resume_gate_requires_exact_slot1_prefix_and_position2(
        tmp_path, monkeypatch):
    bundle = tmp_path / "bundle.json"
    bundle.write_text(json.dumps({"bundle_sha256": "2" * 64}))
    auth = tmp_path / "resume.yaml"
    auth.write_text("placeholder\n")
    authorization = {
        "schema": "E5_v2_formal_resume_authorization_v1", "authorized": True,
        "registry_sha256": common.EXPECTED_REGISTRY_SHA256,
        "formal_execution_tooling_bundle_sha256": "2" * 64,
        "start_position": 2, "completed_prefix_length": 1,
        "completed_slot_attempt_id": recovery.SLOT1_ATTEMPT_ID,
        "completed_slot_seed": recovery.SLOT1_SEED,
        "slot1_physical_execution_count": 1,
        "slot1_transactionally_recovered": True,
        "slot1_rerun_permitted": False, "continuous_exact_order": True,
    }
    original_load_yaml = common.load_yaml
    monkeypatch.setattr(common, "TOOLING_BUNDLE_V2_PATH", bundle)
    monkeypatch.setattr(
        common, "load_yaml",
        lambda path: authorization if Path(path) == auth else original_load_yaml(path))
    monkeypatch.setenv("E5_V2_FORMAL_RESUME_TOKEN_SHA256", sha256_file(auth))
    assert common.validate_external_launch_authorization(
        auth, [recovery.SLOT1_ATTEMPT_ID])["start_position"] == 2
    with pytest.raises(FormalInfrastructureError):
        common.validate_external_launch_authorization(auth, [])
    wrong = dict(authorization, start_position=1)
    monkeypatch.setattr(
        common, "load_yaml",
        lambda path: wrong if Path(path) == auth else original_load_yaml(path))
    with pytest.raises(FormalInfrastructureError):
        common.validate_external_launch_authorization(
            auth, [recovery.SLOT1_ATTEMPT_ID])


def test_frozen_identities_old_registry_and_production_method_unchanged():
    common.verify_frozen_identities()
    old = subprocess.check_output(
        ["git", "show", f"{OLD_E5_SOURCE_COMMIT}:{OLD_E5_REGISTRY_PATH}"],
        cwd=REPO)
    import hashlib
    assert hashlib.sha256(old).hexdigest() == OLD_E5_REGISTRY_SHA256
    assert subprocess.run([
        "git", "diff", "--quiet", BASELINE_COMMIT, "--",
        *PRODUCTION_METHOD_PATHS], cwd=REPO).returncode == 0
