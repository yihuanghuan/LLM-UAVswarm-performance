"""Regression tests for the append-only Epoch 0 -> Epoch 1 transition."""
from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path
import subprocess

import pytest

from campaign_common import CampaignError, load_json, sha256_file, write_json_exclusive
from campaign_interventions import (
    git_blob_hashes, intervention_body_sha256, tooling_bundle,
)
from formal_campaign_launcher import FormalCampaignLauncher
from pinned_adapter_loader import PinnedAdapterLoader
from runner_registry import load_runner_registry, registry_sha256


E3_CHECKOUT = Path(__file__).resolve().parents[4] / "e3_adapter_worktree"
E3_EFFECTIVE_COMMIT = "3d4924a363b84539969c325f93d15e0fff6a2788"
E3_EFFECTIVE_BRANCH = "formal/E3-formal-adapter-case-c-v1"


class FakeLoader:
    def verify_all_checkouts(self):
        return {"status": "PASS"}

    def run_exact_trial(self, family, trial, context):
        output = Path(context["attempt_output_dir"])
        artifact = output / "attempt.json"
        write_json_exclusive(artifact, {
            "record_type": "intervention_test_attempt_v1",
            "dataset_class": "formal_evaluation",
            "accepted_formal_result": True,
            "trial_id": trial,
            "experiment": family,
            "global_position": context["global_trial_position"],
            "attempt_status": "success",
            "replacement_attempt": False,
        })
        return {
            "trial_id": trial, "experiment": family, "attempt_status": "success",
            "artifact_path": str(artifact), "artifact_sha256": sha256_file(artifact),
        }


def _write_json_replace(path: Path, value):
    path.chmod(0o644)
    path.write_text(json.dumps(value, sort_keys=True, indent=2) + "\n", encoding="utf-8")


def _effective_pin(registry):
    pin = deepcopy(registry["runners"]["E3"])
    files = git_blob_hashes(E3_CHECKOUT, E3_EFFECTIVE_COMMIT)
    pin.update({
        "adapter_branch": E3_EFFECTIVE_BRANCH,
        "adapter_commit": E3_EFFECTIVE_COMMIT,
        "adapter_implementation_commit": E3_EFFECTIVE_COMMIT,
        "adapter_source_sha256": files[pin["adapter_entrypoint"]],
    })
    return pin


def _publish_intervention(root, gate, authorization, mutate=None):
    registry = load_runner_registry()
    original_pin = registry["runners"]["E3"]
    effective_pin = _effective_pin(registry)
    original_tooling = tooling_bundle(git_blob_hashes(E3_CHECKOUT, original_pin["adapter_commit"]))
    effective_tooling = tooling_bundle(git_blob_hashes(E3_CHECKOUT, effective_pin["adapter_commit"]))
    changed = {
        path: {"original_sha256": original_tooling["files"][path],
               "effective_sha256": effective_tooling["files"][path]}
        for path in original_tooling["files"]
        if original_tooling["files"][path] != effective_tooling["files"][path]
    }
    record = {
        "record_type": "formal_campaign_intervention_v1",
        "sequence": 1,
        "previous_intervention_sha256": None,
        "trigger_global_position": 2,
        "effective_start_global_position": 3,
        "affected_families": ["E3"],
        "classification": "instrumentation_only",
        "scientific_semantics_changed": False,
        "retained_attempts_modified": False,
        "retained_attempt_rerun": False,
        "authorized": True,
        "effective_from_position_only": 3,
        "publication_status": "PUBLISHED_IMMUTABLE",
        "original_identity": {
            "runner_registry_sha256": registry_sha256(registry),
            "launch_gate_sha256": sha256_file(gate),
            "launcher_run_manifest_sha256": sha256_file(root / "launcher_run_manifest.json"),
            "e3_runner_pin": original_pin,
            "e3_execution_tooling": original_tooling,
        },
        "effective_identity": {
            "e3_runner_pin": effective_pin,
            "e3_execution_tooling": effective_tooling,
        },
        "changed_execution_relevant_files": changed,
        "justification": {"invariant_preserved": True},
        "validation_evidence": {
            "persistent_missing_controller_fails_closed": True,
            "transient_discovery_converges_with_raw_evidence": True,
        },
    }
    if mutate:
        mutate(record)
    record["record_body_sha256"] = intervention_body_sha256(record)
    path = root / "interventions/000001.json"
    write_json_exclusive(path, record)
    write_json_exclusive(authorization, {
        "record_type": "formal_campaign_intervention_authorizations_v1",
        "authorizations": [{
            "sequence": 1, "record_path": "interventions/000001.json",
            "record_sha256": sha256_file(path),
        }],
    })
    return path


@pytest.fixture
def campaign(tmp_path):
    root = tmp_path / "formal"
    gate = tmp_path / "gate.json"
    authorization = tmp_path / "authorizations.json"
    source = Path(__file__).with_name("formal_launch_gate_v1.json")
    write_json_exclusive(gate, load_json(source))

    def launcher():
        return FormalCampaignLauncher(
            "formal", run_root=root, loader=FakeLoader(), gate_path=gate,
            intervention_authorizations_path=authorization, e3_checkout=E3_CHECKOUT,
        )
    return root, gate, authorization, launcher


def test_epoch0_history_remains_on_original_pins(campaign):
    root, _gate, _authorization, launcher = campaign
    first = launcher()
    first.dispatch_next()
    restarted = launcher()
    assert restarted.epoch == 0
    assert restarted.validate_state()["next_position"] == 2
    envelope = load_json(root / "attempt-artifacts/000001-attempt.json")
    assert envelope["adapter_pin"] == load_runner_registry()["runners"]["E2"]


def test_transition_restart_preserves_history_and_next_is_three(campaign):
    root, gate, authorization, launcher = campaign
    running = launcher()
    running.dispatch_next()
    running.dispatch_next()
    before = [sha256_file(path) for path in sorted((root / "suite-journal").glob("*.json"))]
    _publish_intervention(root, gate, authorization)
    restarted = launcher()
    assert restarted.epoch == 1
    assert restarted.validate_state()["next_position"] == 3
    assert [sha256_file(path) for path in sorted((root / "suite-journal").glob("*.json"))] == before
    assert not (root / "attempt-artifacts/000003-attempt.json").exists()


def test_missing_intervention_fails_after_trigger(campaign):
    _root, _gate, _authorization, launcher = campaign
    running = launcher(); running.dispatch_next(); running.dispatch_next()
    with pytest.raises(CampaignError, match="required before position #3"):
        launcher()


def test_tampered_intervention_record_fails_authorization_hash(campaign):
    root, gate, authorization, launcher = campaign
    running = launcher(); running.dispatch_next(); running.dispatch_next()
    path = _publish_intervention(root, gate, authorization)
    value = load_json(path); value["classification"] = "tampered"; _write_json_replace(path, value)
    with pytest.raises(CampaignError, match="authorization hash mismatch"):
        launcher()


@pytest.mark.parametrize("mutate,match", [
    (lambda r: r.__setitem__("effective_start_global_position", 4), "invariant mismatch"),
    (lambda r: r["effective_identity"]["e3_runner_pin"].__setitem__("protocol_sha256", "0" * 64), "scientific pin changed"),
])
def test_wrong_effective_position_and_scientific_drift_fail_closed(campaign, mutate, match):
    _root, gate, authorization, launcher = campaign
    running = launcher(); running.dispatch_next(); running.dispatch_next()
    _publish_intervention(_root, gate, authorization, mutate)
    with pytest.raises(CampaignError, match=match):
        launcher()


def test_dirty_effective_e3_checkout_fails(tmp_path):
    clone = tmp_path / "e3"
    subprocess.run([
        "git", "clone", "--shared", "--branch", E3_EFFECTIVE_BRANCH,
        str(E3_CHECKOUT), str(clone),
    ], check=True, capture_output=True)
    registry = load_runner_registry(); pin = _effective_pin(registry)
    tooling = tooling_bundle(git_blob_hashes(E3_CHECKOUT, E3_EFFECTIVE_COMMIT))
    dirty_path = clone / "experiments_v2/Formal Evaluation Experiments/E3/tooling/e3_runtime_diagnostics.py"
    dirty_path.write_text(dirty_path.read_text() + "\n", encoding="utf-8")
    loader = PinnedAdapterLoader(
        registry, checkout_roots={"E3": clone},
        effective_pins={**registry["runners"], "E3": pin},
        execution_tooling={"E3": tooling},
    )
    with pytest.raises(CampaignError, match="checkout is dirty"):
        loader._load("E3")
