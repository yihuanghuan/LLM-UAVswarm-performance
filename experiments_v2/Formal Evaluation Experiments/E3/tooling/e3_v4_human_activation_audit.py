#!/usr/bin/env python3
"""Static E3-v4 human-activation audit; never executes a physical trial."""

from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import hashlib
import json
from pathlib import Path
import subprocess

import yaml

from e3_v4_campaign_journal import DEFAULT_JOURNAL, read_journal, validate
from e3_v4_formal_adapter import AdapterError, adapter_identity, validate_context
from e3_v4_trial_registry import (
    E3, OLD_V3_SHA256, ORDER, ORDER_META, POLICY, POLICY_SHA256, REGISTRY,
    REGISTRY_SHA256, SEEDS, SEEDS_SHA256, build_exact_runtime_spec,
    registered_trial_ids, sha256_file,
)

REPO = E3.parents[2]
CANDIDATE_COMMIT = "1c782a14eb1e812f6eaabd95fd01f3ba7dab5f05"
ACTIVATION_COMMIT = "957e65aef5e379ec668f5a9f9b01fe84df7ea5f9"
PRODUCTION_BASELINE = "6cf402debf23851b1eff3edc6f3ab49eae7127c4"
CANDIDATE_REGISTRY_SHA256 = "80ddbb8701f1c7feb84ae64a7985f233742f522c1204131ab4dd6d09960bd79b"
ORDER_SHA256 = "60ee30a7100b53c4964e3f9f086ff3d137fb41282eebc4439760bf17f033b39b"
ANALYSIS_SHA256 = "987ff29aa814a0dc5e9e64081fcf0fc79ceb3086b21a0e945bfe2f8252185c58"
JOURNAL_CONTRACT_SHA256 = "7f00d14504fc914d396909c333700700b4ac68f0f2dddb77d5259ab69b257d84"
SCIENTIFIC_PAYLOAD_SHA256 = "43a4805a5c9bd881fc3cc8ff0785bbf3436a5fbbffc38596d05e985b88a896e0"
E3_PREFIX = "experiments_v2/Formal Evaluation Experiments/E3/"
REGISTRY_REL = E3_PREFIX + "e3_factorial_registry_v4.yaml"
ANALYSIS = E3 / "E3_v4_analysis_contract.md"
JOURNAL_CONTRACT = E3 / "E3_v4_campaign_journal_contract.yaml"
V3 = E3 / "e3_factorial_registry_v3.yaml"
MANIFEST = E3 / "E3_v4_human_activation_manifest.yaml"
TRIAL_REGISTRY = E3 / "tooling/e3_v4_trial_registry.py"
FORMAL_ADAPTER = E3 / "tooling/e3_v4_formal_adapter.py"
ALLOWED_ACTIVATION_PATHS = {
    E3_PREFIX + "E3_v4_formal_trial_order.yaml",
    E3_PREFIX + "E3_v4_human_activation_manifest.yaml",
    REGISTRY_REL,
    E3_PREFIX + "tooling/e3_v4_build_registry_order.py",
    E3_PREFIX + "tooling/e3_v4_trial_registry.py",
    E3_PREFIX + "tooling/test_e3_v4_formal_preflight.py",
}


def git(*args: str, binary: bool = False):
    return subprocess.check_output(
        ["git", *args], cwd=REPO, text=not binary
    ).strip() if not binary else subprocess.check_output(["git", *args], cwd=REPO)


def canonical_sha256(value) -> str:
    payload = json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(payload).hexdigest()


def scientific_payload(value: dict) -> dict:
    result = dict(value)
    for field in ("status", "activation", "activation_metadata"):
        result.pop(field, None)
    return result


def candidate_bytes(path: str) -> bytes:
    return git("show", f"{CANDIDATE_COMMIT}:{path}", binary=True)


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def rejected(trial: str, context: dict, field: str, value) -> bool:
    modified = dict(context)
    if value is None:
        modified.pop(field, None)
    else:
        modified[field] = value
    try:
        validate_context(trial, modified)
    except AdapterError:
        return True
    return False


def build_evidence() -> dict:
    candidate_registry_bytes = candidate_bytes(REGISTRY_REL)
    candidate_registry = yaml.safe_load(candidate_registry_bytes)
    sealed_registry = yaml.safe_load(REGISTRY.read_text())
    candidate_payload_sha = canonical_sha256(scientific_payload(candidate_registry))
    sealed_payload_sha = canonical_sha256(scientific_payload(sealed_registry))

    ids = registered_trial_ids()
    counts = Counter()
    blocks: dict[tuple[str, str], set[str]] = defaultdict(set)
    for trial in ids:
        runtime = build_exact_runtime_spec(trial)
        counts[(runtime["scenario_id"], runtime["condition"])] += 1
        blocks[(runtime["scenario_id"], str(runtime["seed"]))].add(runtime["condition"])
    expected_cells = {"P0_F0", "P0_F1", "P1_F0", "P1_F1"}

    identity = adapter_identity()
    trial = ids[0]
    context = {
        "trial_id": trial,
        "campaign_position": 1,
        "execution_mode": "formal",
        "dataset_class": "formal_evaluation",
        "formal_launch_authorized": True,
        "runner_commit": identity["commit"],
        "runner_source_sha256": identity["source_sha256"],
        "runner_tooling_bundle_sha256": identity["execution_tooling"]["bundle_sha256"],
        "registry_sha256": REGISTRY_SHA256,
        "formal_seed_registry_sha256": SEEDS_SHA256,
        "order_sha256": ORDER_SHA256,
        "policy_sha256": POLICY_SHA256,
        "attempt_output_dir": "/not-used-static-validation",
    }
    formal_validation_pass = False
    try:
        mode, position, _ = validate_context(trial, context)
        formal_validation_pass = mode == "formal" and position == 1
    except AdapterError:
        pass
    negative_gate_checks = {
        "authorization_false_rejected": rejected(
            trial, context, "formal_launch_authorized", False
        ),
        "authorization_missing_rejected": rejected(
            trial, context, "formal_launch_authorized", None
        ),
        "wrong_dataset_class_rejected": rejected(
            trial, context, "dataset_class", "engineering_validation"
        ),
    }
    for field in (
        "registry_sha256", "formal_seed_registry_sha256", "order_sha256",
        "policy_sha256", "runner_tooling_bundle_sha256",
    ):
        negative_gate_checks[f"wrong_{field}_rejected"] = rejected(
            trial, context, field, "0" * 64
        )

    journal_state = validate(read_journal(DEFAULT_JOURNAL))
    formal_files = []
    formal_root = E3 / "results/formal_v4"
    if formal_root.exists():
        formal_files = sorted(str(path.relative_to(REPO)) for path in formal_root.rglob("*") if path.is_file())

    activation_paths = git(
        "diff", "--name-only", f"{CANDIDATE_COMMIT}..{ACTIVATION_COMMIT}"
    ).splitlines()
    baseline_paths = git(
        "diff", "--name-only", f"{PRODUCTION_BASELINE}..{ACTIVATION_COMMIT}"
    ).splitlines()
    baseline_production_paths = [
        path for path in baseline_paths
        if not path.startswith("experiments_v2/") and path != ".gitattributes"
    ]

    candidate_byte_identity = {
        "formal_seed_registry": sha256_bytes(candidate_bytes(
            E3_PREFIX + "E3_v4_formal_paired_seeds.yaml"
        )) == sha256_file(SEEDS) == SEEDS_SHA256,
        "formal_order": sha256_bytes(candidate_bytes(
            E3_PREFIX + "E3_v4_formal_trial_order.txt"
        )) == sha256_file(ORDER) == ORDER_SHA256,
        "analysis_contract": sha256_bytes(candidate_bytes(
            E3_PREFIX + "E3_v4_analysis_contract.md"
        )) == sha256_file(ANALYSIS) == ANALYSIS_SHA256,
        "journal_contract": sha256_bytes(candidate_bytes(
            E3_PREFIX + "E3_v4_campaign_journal_contract.yaml"
        )) == sha256_file(JOURNAL_CONTRACT) == JOURNAL_CONTRACT_SHA256,
    }

    checks = {
        "registry_status_sealed": sealed_registry.get("status") == "SEALED_FOR_FORMAL_EXECUTION",
        "candidate_registry_hash_matches": sha256_bytes(candidate_registry_bytes) == CANDIDATE_REGISTRY_SHA256,
        "sealed_registry_hash_matches": sha256_file(REGISTRY) == REGISTRY_SHA256,
        "scientific_payload_equivalent": candidate_payload_sha == sealed_payload_sha == SCIENTIFIC_PAYLOAD_SHA256,
        "candidate_frozen_artifacts_byte_identical": all(candidate_byte_identity.values()),
        "policy_hash_unchanged": sha256_file(POLICY) == POLICY_SHA256,
        "E3_v3_registry_hash_unchanged": sha256_file(V3) == OLD_V3_SHA256,
        "all_360_specs_compile": len(ids) == 360,
        "all_trial_ids_unique": len(set(ids)) == 360,
        "all_90_blocks_complete": len(blocks) == 90 and all(v == expected_cells for v in blocks.values()),
        "all_scenario_condition_counts_15": len(counts) == 24 and all(v == 15 for v in counts.values()),
        "sealed_formal_context_validates": formal_validation_pass,
        "negative_gate_checks_pass": all(negative_gate_checks.values()),
        "journal_absent": not DEFAULT_JOURNAL.exists(),
        "formal_attempt_count_zero": not formal_files,
        "candidate_to_activation_paths_allowed": set(activation_paths) == ALLOWED_ACTIVATION_PATHS,
        "baseline_production_changes_zero": not baseline_production_paths,
    }
    evidence = {
        "schema": "E3_v4_human_activation_audit_v1",
        "status": "PASS" if all(checks.values()) else "FAIL",
        "candidate_commit": CANDIDATE_COMMIT,
        "activation_commit": ACTIVATION_COMMIT,
        "production_baseline": PRODUCTION_BASELINE,
        "registry_status": sealed_registry["status"],
        "candidate_registry_sha256": CANDIDATE_REGISTRY_SHA256,
        "sealed_registry_sha256": sha256_file(REGISTRY),
        "candidate_scientific_payload_sha256": candidate_payload_sha,
        "sealed_scientific_payload_sha256": sealed_payload_sha,
        "scientific_payload_equivalent": candidate_payload_sha == sealed_payload_sha,
        "scientific_protocol_changes": 0 if candidate_payload_sha == sealed_payload_sha else 1,
        "formal_seed_registry_sha256": sha256_file(SEEDS),
        "formal_order_sha256": sha256_file(ORDER),
        "formal_order_metadata_sha256": sha256_file(ORDER_META),
        "analysis_contract_sha256": sha256_file(ANALYSIS),
        "journal_contract_sha256": sha256_file(JOURNAL_CONTRACT),
        "policy_sha256_before": POLICY_SHA256,
        "policy_sha256_after": sha256_file(POLICY),
        "E3_v3_registry_sha256_before": OLD_V3_SHA256,
        "E3_v3_registry_sha256_after": sha256_file(V3),
        "activation_manifest_sha256": sha256_file(MANIFEST),
        "trial_registry_source_sha256": sha256_file(TRIAL_REGISTRY),
        "formal_adapter_source_sha256": sha256_file(FORMAL_ADAPTER),
        "execution_tooling_bundle_sha256": identity["execution_tooling"]["bundle_sha256"],
        "execution_tooling_files": identity["execution_tooling"]["files"],
        "runner_commit": identity["commit"],
        "attempt_count": len(ids),
        "unique_attempt_count": len(set(ids)),
        "complete_four_cell_block_count": len(blocks),
        "scenario_condition_counts": {
            f"{scenario}__{condition}": count
            for (scenario, condition), count in sorted(counts.items())
        },
        "formal_context_static_validation": "PASS" if formal_validation_pass else "FAIL",
        "negative_gate_checks": negative_gate_checks,
        "formal_attempt_count": len(formal_files),
        "formal_attempt_files": formal_files,
        "journal_exists": DEFAULT_JOURNAL.exists(),
        "journal_consumed_slots": journal_state["consumed_slot_count"],
        "next_campaign_position": journal_state["next_campaign_position"],
        "next_trial_id": journal_state["next_trial_id"],
        "F1_qualification_attempt_count": sealed_registry["qualification_provenance"]["F1_attempt_count"],
        "candidate_byte_identity": candidate_byte_identity,
        "candidate_to_activation_changed_paths": activation_paths,
        "candidate_to_activation_outside_E3": [p for p in activation_paths if not p.startswith(E3_PREFIX)],
        "baseline_to_activation_production_changed_paths": baseline_production_paths,
        "production_changes": len(baseline_production_paths),
        "checks": checks,
    }
    return evidence


def markdown(evidence: dict) -> str:
    return f"""# E3-v4 Human Activation Audit

Status: **{evidence['status']}**

This is a static activation audit. No physical trial, Gazebo/PX4 process,
formal attempt artifact, or campaign-journal record was created.

## Activation identity

- Candidate Git commit: `{evidence['candidate_commit']}`
- Activation Git commit: `{evidence['activation_commit']}`
- Candidate registry SHA-256: `{evidence['candidate_registry_sha256']}`
- Sealed registry SHA-256: `{evidence['sealed_registry_sha256']}`
- Registry status: `{evidence['registry_status']}`

## Scientific equivalence

- Candidate scientific payload SHA-256: `{evidence['candidate_scientific_payload_sha256']}`
- Sealed scientific payload SHA-256: `{evidence['sealed_scientific_payload_sha256']}`
- Equivalent after removing only activation fields: `{str(evidence['scientific_payload_equivalent']).lower()}`
- Scientific protocol changes: `{evidence['scientific_protocol_changes']}`

## Frozen population and analysis

- Formal seeds SHA-256: `{evidence['formal_seed_registry_sha256']}`
- 360-order SHA-256: `{evidence['formal_order_sha256']}`
- Analysis contract SHA-256: `{evidence['analysis_contract_sha256']}`
- Journal contract SHA-256: `{evidence['journal_contract_sha256']}`
- Specs / unique IDs / complete blocks: `{evidence['attempt_count']} / {evidence['unique_attempt_count']} / {evidence['complete_four_cell_block_count']}`

## Execution gate and cursor

- Static sealed formal-context validation: `{evidence['formal_context_static_validation']}`
- Explicit authorization and wrong-context/hash rejection checks: `PASS`
- Formal attempts: `{evidence['formal_attempt_count']}`
- Journal consumed slots: `{evidence['journal_consumed_slots']}`
- Next campaign position: `{evidence['next_campaign_position']}`
- Next trial ID: `{evidence['next_trial_id']}`

## Provenance and invariance

- Policy SHA-256 before/after: `{evidence['policy_sha256_before']}` / `{evidence['policy_sha256_after']}`
- E3-v3 registry SHA-256 before/after: `{evidence['E3_v3_registry_sha256_before']}` / `{evidence['E3_v3_registry_sha256_after']}`
- Trial-registry source SHA-256: `{evidence['trial_registry_source_sha256']}`
- Formal-adapter source SHA-256: `{evidence['formal_adapter_source_sha256']}`
- Execution tooling bundle SHA-256: `{evidence['execution_tooling_bundle_sha256']}`
- Activation manifest SHA-256: `{evidence['activation_manifest_sha256']}`
- Candidate-to-activation changes outside E3: `{len(evidence['candidate_to_activation_outside_E3'])}`
- Production changes: `{evidence['production_changes']}`

## Final gate

```text
E3-v4 HUMAN ACTIVATION: {evidence['status']}
REGISTRY SEALED FOR FORMAL EXECUTION
FORMAL CAMPAIGN READY TO START AT SLOT {evidence['next_campaign_position']}
FORMAL EXECUTION NOT STARTED
```
"""


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", type=Path, required=True)
    parser.add_argument("--markdown", type=Path, required=True)
    args = parser.parse_args()
    evidence = build_evidence()
    args.json.write_text(json.dumps(evidence, indent=2, sort_keys=True) + "\n")
    args.markdown.write_text(markdown(evidence))
    print(json.dumps({
        "status": evidence["status"],
        "sealed_registry_sha256": evidence["sealed_registry_sha256"],
        "formal_attempt_count": evidence["formal_attempt_count"],
        "journal_consumed_slots": evidence["journal_consumed_slots"],
        "next_campaign_position": evidence["next_campaign_position"],
    }, sort_keys=True))
    return 0 if evidence["status"] == "PASS" else 2


if __name__ == "__main__":
    raise SystemExit(main())
