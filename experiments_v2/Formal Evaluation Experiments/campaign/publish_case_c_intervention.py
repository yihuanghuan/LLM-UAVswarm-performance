#!/usr/bin/env python3
"""Publish the one authorized Case-C record; never dispatch a formal trial."""
from __future__ import annotations

from copy import deepcopy
import hashlib
from pathlib import Path
import subprocess

from campaign_common import (
    CAMPAIGN_DIR, FORMAL_RESULTS_DIR, CampaignError, sha256_file,
    write_json_exclusive,
)
from campaign_interventions import (
    git_blob_hashes, intervention_body_sha256, tooling_bundle,
)
from campaign_journal import CampaignJournal
from runner_registry import load_runner_registry, registry_sha256


E3_CHECKOUT = CAMPAIGN_DIR.parents[2].parent / "e3_adapter_worktree"
E3_EFFECTIVE_BRANCH = "formal/E3-formal-adapter-case-c-v1"
E3_EFFECTIVE_COMMIT = "3d4924a363b84539969c325f93d15e0fff6a2788"
E3_TEST_PATH = "experiments_v2/Formal Evaluation Experiments/E3/tooling/test_e3_formal_adapter.py"
GATE_PATH = CAMPAIGN_DIR / "formal_launch_gate_v1.json"
DIAGNOSTIC_ROOT = CAMPAIGN_DIR.parents[2].parent / "incident_diagnostics"


EVIDENCE = {
    "postfix_smoke": (
        "postfix_engineering_smoke_20260828T030110Z/smoke_manifest.json",
        "de80bbae312c4728a5eba527f7c4f27ec68080e4c69b1c9e7442491ab5becb49",
    ),
    "postfix_runtime_provenance": (
        "postfix_engineering_smoke_20260828T030110Z/raw/runtime_provenance.json",
        "a032f413748671270fb83b5ffd365f2fe3a8ce5b0de8659c3bb3afffd64d4da4",
    ),
    "health_1_cli": (
        "health_check_1_20260828T025325Z/cli_observations.log",
        "a6dee249124045d8b34609f2610fbfcb460030b68de29331ef8ae9a5d9463afe",
    ),
    "health_1_rclpy": (
        "health_check_1_20260828T025325Z/rclpy_graph.jsonl",
        "6d3318570347899eb0329458c23fd33b348b2ceeb42f1e06835d94aac268f9be",
    ),
    "health_2_cli": (
        "health_check_2_20260828T025602Z/cli_observations.log",
        "edc2352b613c9cae38cc0b3c0e06c1a8259582c18e78cd5fb4ad365d6bee937a",
    ),
    "health_2_rclpy": (
        "health_check_2_20260828T025602Z/rclpy_graph.jsonl",
        "bd59f66674b2058d0956063162976e630b27cd457be232777b623dea5e55eb65",
    ),
    "health_2_provenance": (
        "health_check_2_20260828T025602Z/runtime_provenance_revalidation.json",
        "244b4b5ffee9d613b19af5f7d01c958b950c32d8b37022f342e10c3b5fefd12c",
    ),
}


def _blob_sha256(commit: str, path: str) -> str:
    blob = subprocess.run(
        ["git", "show", f"{commit}:{path}"], cwd=E3_CHECKOUT,
        check=True, capture_output=True,
    ).stdout
    return hashlib.sha256(blob).hexdigest()


def _verify_publish_preconditions() -> None:
    records = CampaignJournal(FORMAL_RESULTS_DIR / "suite-journal").read()
    if [(item.get("global_position"), item.get("trial_id")) for item in records] != [
        (1, "E2-RSV-01__SHIFT__LATE__S52105"),
        (2, "E3-C-01__P0_F0__S53107"),
    ]:
        raise CampaignError("formal journal is not the exact retained #1-#2 prefix")
    if list((FORMAL_RESULTS_DIR / "attempt-artifacts").glob("000003*")):
        raise CampaignError("formal #3 artifact already exists")
    if list((FORMAL_RESULTS_DIR / "adapter-attempts").glob("000003*")):
        raise CampaignError("formal #3 adapter output already exists")
    if sha256_file(FORMAL_RESULTS_DIR / "launcher_run_manifest.json") != "dd5ed80049b138d4e97c82ce556ed306efbc6e4b2a369f7616be0ff101f332d1":
        raise CampaignError("immutable launcher manifest hash mismatch")
    retained = FORMAL_RESULTS_DIR / "adapter-attempts/000002/raw/runtime_provenance.json"
    if sha256_file(retained) != "5a225a688c61f81c07ea808987337b236588a456dcbf823eb41a31f408c49181":
        raise CampaignError("retained #2 runtime provenance hash mismatch")
    if subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=E3_CHECKOUT, text=True).strip() != E3_EFFECTIVE_COMMIT:
        raise CampaignError("E3 effective checkout commit mismatch")
    if subprocess.check_output(["git", "branch", "--show-current"], cwd=E3_CHECKOUT, text=True).strip() != E3_EFFECTIVE_BRANCH:
        raise CampaignError("E3 effective checkout branch mismatch")
    if subprocess.check_output(["git", "status", "--porcelain", "--untracked-files=all"], cwd=E3_CHECKOUT, text=True):
        raise CampaignError("E3 effective checkout is dirty")
    for relative, expected in EVIDENCE.values():
        if sha256_file(DIAGNOSTIC_ROOT / relative) != expected:
            raise CampaignError(f"diagnostic evidence hash mismatch: {relative}")


def build_record():
    _verify_publish_preconditions()
    registry = load_runner_registry()
    original_pin = registry["runners"]["E3"]
    original_tooling = tooling_bundle(git_blob_hashes(
        E3_CHECKOUT, original_pin["adapter_commit"],
    ))
    effective_tooling = tooling_bundle(git_blob_hashes(
        E3_CHECKOUT, E3_EFFECTIVE_COMMIT,
    ))
    effective_pin = deepcopy(original_pin)
    effective_pin.update({
        "adapter_branch": E3_EFFECTIVE_BRANCH,
        "adapter_commit": E3_EFFECTIVE_COMMIT,
        "adapter_implementation_commit": E3_EFFECTIVE_COMMIT,
        "adapter_source_sha256": effective_tooling["files"][original_pin["adapter_entrypoint"]],
    })
    changed = {
        path: {
            "original_sha256": original_tooling["files"][path],
            "effective_sha256": effective_tooling["files"][path],
        }
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
            "launch_gate_sha256": sha256_file(GATE_PATH),
            "launcher_run_manifest_sha256": sha256_file(
                FORMAL_RESULTS_DIR / "launcher_run_manifest.json"
            ),
            "e3_runner_pin": original_pin,
            "e3_execution_tooling": original_tooling,
        },
        "effective_identity": {
            "e3_runner_pin": effective_pin,
            "e3_execution_tooling": effective_tooling,
        },
        "changed_execution_relevant_files": changed,
        "changed_validation_files": {
            E3_TEST_PATH: {
                "original_sha256": _blob_sha256(original_pin["adapter_commit"], E3_TEST_PATH),
                "effective_sha256": _blob_sha256(E3_EFFECTIVE_COMMIT, E3_TEST_PATH),
            },
        },
        "justification": {
            "incident_classification": "systematic_one_shot_ros_cli_graph_discovery_false_negative",
            "invariant_preserved": True,
            "invariant": "every required controller exists, subscribes to its execution_command topic, and has enable_execution_profiles=True",
            "observation_change_only": "bounded four-attempt discovery stabilization with one-second spacing; joint evidence required; every raw observation retained",
            "scientific_runtime_change": None,
        },
        "validation_evidence": {
            "transient_discovery_converges_with_raw_evidence": True,
            "persistent_missing_controller_fails_closed": True,
            "e3_unit_regression": "28 passed",
            "postfix_engineering_smoke": {
                "status": "PASS", "accepted_formal_result": False,
                "path": f"incident_diagnostics/{EVIDENCE['postfix_smoke'][0]}",
                "sha256": EVIDENCE["postfix_smoke"][1],
            },
            "postfix_runtime_provenance": {
                "status": "PASS", "uav1_observations": [False, True],
                "uav2_observations": [False, True],
                "path": f"incident_diagnostics/{EVIDENCE['postfix_runtime_provenance'][0]}",
                "sha256": EVIDENCE["postfix_runtime_provenance"][1],
            },
            "independent_health_checks": [
                {"sequence": 1, "cli_sha256": EVIDENCE["health_1_cli"][1],
                 "persistent_rclpy_sha256": EVIDENCE["health_1_rclpy"][1]},
                {"sequence": 2, "cli_sha256": EVIDENCE["health_2_cli"][1],
                 "persistent_rclpy_sha256": EVIDENCE["health_2_rclpy"][1],
                 "runtime_provenance_sha256": EVIDENCE["health_2_provenance"][1]},
            ],
            "retained_attempt_2_runtime_provenance_sha256":
                "5a225a688c61f81c07ea808987337b236588a456dcbf823eb41a31f408c49181",
            "formal_attempts_created_by_validation": 0,
        },
        "epoch_contract": {
            "epoch_0_positions": [1, 2],
            "epoch_0_uses_original_registry_pins": True,
            "epoch_1_first_position": 3,
            "epoch_1_only_changes_e3_instrumentation_identity": True,
            "journal_remains_cursor_authority": True,
            "launch_gate_remains_immutable_metadata": True,
        },
    }
    record["record_body_sha256"] = intervention_body_sha256(record)
    return record


def main() -> int:
    destination = FORMAL_RESULTS_DIR / "interventions/000001.json"
    write_json_exclusive(destination, build_record())
    print(f"published={destination}")
    print(f"sha256={sha256_file(destination)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
