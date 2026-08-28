"""Append-only, campaign-local authorization for post-start tooling interventions."""
from __future__ import annotations

from copy import deepcopy
import hashlib
import json
from pathlib import Path
import subprocess
from typing import Any, Dict, Iterable

from campaign_common import CampaignError, canonical_sha256, load_json, sha256_file
from runner_registry import registry_sha256


INTERVENTION_RECORD_TYPE = "formal_campaign_intervention_v1"
AUTHORIZATION_TYPE = "formal_campaign_intervention_authorizations_v1"
E3_BUNDLE_SCHEMA = "e3_execution_tooling_bundle_v1"
E3_EXECUTION_TOOLING_PATHS = (
    "experiments_v2/Formal Evaluation Experiments/E3/tooling/e3_formal_adapter.py",
    "experiments_v2/Formal Evaluation Experiments/E3/tooling/e3_formal_backend.py",
    "experiments_v2/Formal Evaluation Experiments/E3/tooling/e3_physical_trial.py",
    "experiments_v2/Formal Evaluation Experiments/E3/tooling/e3_runtime_diagnostics.py",
    "experiments_v2/Formal Evaluation Experiments/E3/tooling/e3_trial_registry.py",
    "experiments_v2/Formal Evaluation Experiments/E3/tooling/e3_wrench_compat.py",
    "experiments_v2/Formal Evaluation Experiments/harness/e3_wrench_driver.py",
    "experiments-legacy/system_8uav/scripts/wait_swarm_ready.py",
)
ALLOWED_E3_PIN_CHANGES = {
    "adapter_branch", "adapter_commit", "adapter_implementation_commit",
    "adapter_source_sha256", "adapter_manifest_sha256",
}


def tooling_bundle(file_hashes: Dict[str, str]) -> Dict[str, Any]:
    if tuple(sorted(file_hashes)) != tuple(sorted(E3_EXECUTION_TOOLING_PATHS)):
        raise CampaignError("E3 execution-tooling dependency set mismatch")
    if any(not isinstance(value, str) or len(value) != 64 for value in file_hashes.values()):
        raise CampaignError("E3 execution-tooling file hash malformed")
    payload = {"schema": E3_BUNDLE_SCHEMA, "files": dict(sorted(file_hashes.items()))}
    return {**payload, "bundle_sha256": canonical_sha256(payload)}


def git_blob_hashes(checkout: Path, commit: str,
                    paths: Iterable[str] = E3_EXECUTION_TOOLING_PATHS) -> Dict[str, str]:
    values = {}
    for path in sorted(paths):
        completed = subprocess.run(
            ["git", "show", f"{commit}:{path}"], cwd=checkout,
            check=True, capture_output=True,
        )
        values[path] = hashlib.sha256(completed.stdout).hexdigest()
    return values


def intervention_body_sha256(record: Dict[str, Any]) -> str:
    body = dict(record)
    body.pop("record_body_sha256", None)
    return canonical_sha256(body)


def _validate_bundle(label: str, value: Any, checkout: Path, commit: str) -> None:
    if not isinstance(value, dict):
        raise CampaignError(f"{label} E3 execution-tooling bundle missing")
    expected = tooling_bundle(git_blob_hashes(checkout, commit))
    if value != expected:
        raise CampaignError(f"{label} E3 execution-tooling bundle mismatch")


def validate_intervention_record(
    record_path: Path,
    authorization_path: Path,
    registry: Dict[str, Any],
    gate_path: Path,
    manifest_path: Path,
    e3_checkout: Path,
) -> Dict[str, Any]:
    authorization = load_json(authorization_path)
    if authorization.get("record_type") != AUTHORIZATION_TYPE:
        raise CampaignError("formal intervention authorization type mismatch")
    entries = authorization.get("authorizations")
    if not isinstance(entries, list) or len(entries) != 1:
        raise CampaignError("formal intervention authorization sequence mismatch")
    authorized = entries[0]
    if authorized.get("sequence") != 1 or authorized.get("record_path") != "interventions/000001.json":
        raise CampaignError("formal intervention authorization identity mismatch")
    if not record_path.is_file() or sha256_file(record_path) != authorized.get("record_sha256"):
        raise CampaignError("formal intervention record missing or authorization hash mismatch")
    record = load_json(record_path)
    if record.get("record_body_sha256") != intervention_body_sha256(record):
        raise CampaignError("formal intervention body hash mismatch")
    required = {
        "record_type": INTERVENTION_RECORD_TYPE,
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
    }
    mismatches = [key for key, value in required.items() if record.get(key) != value]
    if mismatches:
        raise CampaignError(f"formal intervention invariant mismatch: {mismatches}")
    original = record.get("original_identity")
    effective = record.get("effective_identity")
    if not isinstance(original, dict) or not isinstance(effective, dict):
        raise CampaignError("formal intervention identity sections missing")
    original_pin = registry["runners"]["E3"]
    if original.get("e3_runner_pin") != original_pin:
        raise CampaignError("formal intervention original E3 pin mismatch")
    if original.get("runner_registry_sha256") != registry_sha256(registry):
        raise CampaignError("formal intervention original registry hash mismatch")
    if original.get("launch_gate_sha256") != sha256_file(gate_path):
        raise CampaignError("formal intervention original launch-gate hash mismatch")
    if original.get("launcher_run_manifest_sha256") != sha256_file(manifest_path):
        raise CampaignError("formal intervention original run-manifest hash mismatch")
    _validate_bundle("original", original.get("e3_execution_tooling"), e3_checkout,
                     original_pin["adapter_commit"])
    effective_pin = effective.get("e3_runner_pin")
    if not isinstance(effective_pin, dict) or set(effective_pin) != set(original_pin):
        raise CampaignError("formal intervention effective E3 pin fields mismatch")
    for frozen in ("protocol_sha256", "registry_sha256", "protocol_path", "registry_path"):
        if effective_pin.get(frozen) != original_pin.get(frozen):
            raise CampaignError(f"formal intervention scientific pin changed: {frozen}")
    changed = {key for key in original_pin if original_pin[key] != effective_pin[key]}
    if not changed or not changed <= ALLOWED_E3_PIN_CHANGES:
        raise CampaignError(f"formal intervention E3 pin change is not instrumentation-only: {sorted(changed)}")
    _validate_bundle("effective", effective.get("e3_execution_tooling"), e3_checkout,
                     effective_pin["adapter_commit"])
    changed_files = record.get("changed_execution_relevant_files")
    if not isinstance(changed_files, dict) or not changed_files:
        raise CampaignError("formal intervention changed-file evidence missing")
    original_files = original["e3_execution_tooling"]["files"]
    effective_files = effective["e3_execution_tooling"]["files"]
    actual_changed = {
        path: {"original_sha256": original_files[path], "effective_sha256": effective_files[path]}
        for path in E3_EXECUTION_TOOLING_PATHS if original_files[path] != effective_files[path]
    }
    if changed_files != actual_changed:
        raise CampaignError("formal intervention changed-file evidence mismatch")
    if record.get("justification", {}).get("invariant_preserved") is not True:
        raise CampaignError("formal intervention invariant-preservation evidence missing")
    validation = record.get("validation_evidence")
    if not isinstance(validation, dict) or validation.get("persistent_missing_controller_fails_closed") is not True or validation.get("transient_discovery_converges_with_raw_evidence") is not True:
        raise CampaignError("formal intervention validation evidence incomplete")
    return record


def resolve_effective_pins(
    run_dir: Path,
    retained_count: int,
    registry: Dict[str, Any],
    gate_path: Path,
    authorization_path: Path,
    e3_checkout: Path,
) -> Dict[str, Any]:
    """Resolve immutable Epoch 0 or the single authorized Epoch 1 transition."""
    run_dir = Path(run_dir)
    record_path = run_dir / "interventions" / "000001.json"
    manifest_path = run_dir / "launcher_run_manifest.json"
    if record_path.exists() and retained_count < 2:
        raise CampaignError("formal intervention published before its trigger history exists")
    if retained_count < 2:
        return {"epoch": 0, "effective_pins": deepcopy(registry["runners"]), "intervention": None}
    if not record_path.is_file():
        raise CampaignError("authorized intervention is required before position #3")
    record = validate_intervention_record(
        record_path, authorization_path, registry, gate_path, manifest_path, e3_checkout,
    )
    pins = deepcopy(registry["runners"])
    pins["E3"] = deepcopy(record["effective_identity"]["e3_runner_pin"])
    return {"epoch": 1, "effective_pins": pins, "intervention": record}
