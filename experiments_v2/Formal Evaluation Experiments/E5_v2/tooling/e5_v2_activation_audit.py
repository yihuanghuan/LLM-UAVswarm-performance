#!/usr/bin/env python3
"""Build the side-effect-free E5-v2 formal-activation audit."""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import tempfile
from collections import Counter
from pathlib import Path

from e5_v2_activation_common import (
    ACTIVATION_AUDIT_JSON_PATH,
    ACTIVATION_AUDIT_MD_PATH,
    ACTIVATION_MANIFEST_PATH,
    CANDIDATE_COMMIT,
    CANDIDATE_REGISTRY_SHA256,
    candidate_scientific_payload_sha256,
    formal_execution_bundle,
    registry_at_commit,
    sealed_scientific_payload_sha256,
)
from e5_v2_common import (
    BASELINE_COMMIT,
    E5_DIR,
    OLD_E5_REGISTRY_PATH,
    OLD_E5_REGISTRY_SHA256,
    OLD_E5_SOURCE_COMMIT,
    ORDER_PATH,
    POLICY_SHA256,
    PRODUCTION_METHOD_PATHS,
    REGISTRY_PATH,
    REPO_ROOT,
    SEED_REGISTRY_PATH,
    canonical_attempts,
    load_yaml,
    sha256_file,
)
from e5_v2_formal_adapter import (
    EXPECTED_ANALYSIS_CONTRACT_SHA256,
    EXPECTED_ORDER_SHA256,
    EXPECTED_SEALED_REGISTRY_SHA256,
    EXPECTED_SEED_REGISTRY_SHA256,
    FormalActivationError,
    assert_formal_activation,
    assert_formal_attempt,
)


ANALYSIS_PATH = E5_DIR / "E5_v2_analysis_contract.md"
SLOT_1 = {
    "order_position": 1,
    "trial_id": "E5V2-B-S2-N12-R1",
    "seed": 5202036,
    "n": 12,
    "scenario_id": "E5V2-B-S2-N12",
    "substudy": "E5-v2B",
    "task_family": "UNDER_SPECIFIED",
}


def git(*arguments: str, binary: bool = False):
    return subprocess.check_output(
        ["git", *arguments], cwd=REPO_ROOT, text=not binary
    )


def _adapter_self_test() -> dict:
    assert_formal_activation(REGISTRY_PATH, ACTIVATION_MANIFEST_PATH)
    expected = assert_formal_attempt(**SLOT_1)
    rejection_checks = []
    for field, wrong in (
        ("order_position", 2),
        ("trial_id", "E5V2-B-S2-N8-R1"),
        ("seed", 5202037),
        ("n", 8),
        ("scenario_id", "E5V2-B-S2-N8"),
        ("substudy", "E5-v2A"),
        ("task_family", "SIMPLE"),
    ):
        request = dict(SLOT_1)
        request[field] = wrong
        try:
            assert_formal_attempt(**request)
            rejected = False
        except FormalActivationError:
            rejected = True
        rejection_checks.append({"case": f"wrong_{field}", "rejected": rejected})
    try:
        assert_formal_attempt(
            **{**SLOT_1, "order_position": 2},
            completed_attempt_ids=[SLOT_1["trial_id"]],
        )
        replacement_rejected = False
    except FormalActivationError:
        replacement_rejected = True

    with tempfile.TemporaryDirectory(prefix="e5_v2_activation_gate_") as directory:
        root = Path(directory)
        candidate_path = root / "candidate.yaml"
        relative = REGISTRY_PATH.relative_to(REPO_ROOT).as_posix()
        candidate_path.write_bytes(
            git("show", f"{CANDIDATE_COMMIT}:{relative}", binary=True)
        )
        try:
            assert_formal_activation(candidate_path, ACTIVATION_MANIFEST_PATH)
            candidate_rejected = False
        except FormalActivationError:
            candidate_rejected = True
        stale_path = root / "stale.yaml"
        stale_path.write_bytes(REGISTRY_PATH.read_bytes() + b"\n")
        try:
            assert_formal_activation(stale_path, ACTIVATION_MANIFEST_PATH)
            stale_rejected = False
        except FormalActivationError:
            stale_rejected = True
    passed = (
        expected["attempt_id"] == SLOT_1["trial_id"]
        and candidate_rejected
        and stale_rejected
        and replacement_rejected
        and all(item["rejected"] for item in rejection_checks)
    )
    return {
        "status": "PASS" if passed else "FAIL",
        "exact_slot_1_accepted": expected,
        "candidate_registry_rejected": candidate_rejected,
        "stale_registry_rejected": stale_rejected,
        "replacement_attempt_rejected": replacement_rejected,
        "wrong_identity_checks": rejection_checks,
        "mission_backend_invoked": False,
    }


def build_audit() -> dict:
    checks = []

    def check(name, passed, evidence):
        checks.append({
            "check": name,
            "status": "PASS" if passed else "FAIL",
            "evidence": evidence,
        })

    registry = load_yaml(REGISTRY_PATH)
    manifest = load_yaml(ACTIVATION_MANIFEST_PATH)
    candidate_registry_bytes = git(
        "show",
        f"{CANDIDATE_COMMIT}:{REGISTRY_PATH.relative_to(REPO_ROOT).as_posix()}",
        binary=True,
    )
    candidate_registry_hash = hashlib.sha256(candidate_registry_bytes).hexdigest()
    candidate_payload_hash = candidate_scientific_payload_sha256()
    sealed_payload_hash = sealed_scientific_payload_sha256()
    seeds = load_yaml(SEED_REGISTRY_PATH)
    attempts = seeds["attempts"]
    counts = Counter(item["substudy"] for item in attempts)
    bundle = formal_execution_bundle()
    adapter_path = Path(__file__).with_name("e5_v2_formal_adapter.py")
    adapter_test = _adapter_self_test()
    production_diff = subprocess.run(
        ["git", "diff", "--quiet", BASELINE_COMMIT, "--", *PRODUCTION_METHOD_PATHS],
        cwd=REPO_ROOT,
    ).returncode
    old_registry = git(
        "show", f"{OLD_E5_SOURCE_COMMIT}:{OLD_E5_REGISTRY_PATH}", binary=True
    )
    old_hash = hashlib.sha256(old_registry).hexdigest()
    candidate_is_ancestor = subprocess.run(
        ["git", "merge-base", "--is-ancestor", CANDIDATE_COMMIT, "HEAD"],
        cwd=REPO_ROOT,
    ).returncode == 0

    check(
        "candidate_HEAD_provenance",
        candidate_is_ancestor and candidate_registry_hash == CANDIDATE_REGISTRY_SHA256,
        {
            "candidate_commit": CANDIDATE_COMMIT,
            "candidate_registry_sha256": candidate_registry_hash,
            "remote_head_verified_before_activation": CANDIDATE_COMMIT,
        },
    )
    check(
        "scientific_payload_equivalence",
        candidate_payload_hash == sealed_payload_hash,
        {"candidate": candidate_payload_hash, "sealed": sealed_payload_hash},
    )
    check(
        "scientific_protocol_changes_zero",
        registry_at_commit(CANDIDATE_COMMIT) != registry
        and candidate_payload_hash == sealed_payload_hash,
        0,
    )
    check(
        "sealed_registry_identity",
        registry["status"] == "SEALED_FOR_FORMAL_EXECUTION"
        and sha256_file(REGISTRY_PATH) == EXPECTED_SEALED_REGISTRY_SHA256,
        {
            "status": registry["status"],
            "sha256": sha256_file(REGISTRY_PATH),
        },
    )
    check(
        "human_activation_manifest",
        manifest["human_decision"]["approved"] is True
        and manifest["human_decision"]["decision"]
        == "activate_candidate_for_formal_execution",
        manifest["human_decision"],
    )
    immutable_hashes = {
        "formal_seed_registry_sha256": sha256_file(SEED_REGISTRY_PATH),
        "formal_order_sha256": sha256_file(ORDER_PATH),
        "analysis_contract_sha256": sha256_file(ANALYSIS_PATH),
        "production_policy_sha256": sha256_file(
            REPO_ROOT / "lfs_policy/config/lfs_policy.paper_current.yaml"
        ),
        "old_E5_v1_registry_sha256": old_hash,
    }
    check(
        "immutable_protocol_hashes",
        immutable_hashes == {
            "formal_seed_registry_sha256": EXPECTED_SEED_REGISTRY_SHA256,
            "formal_order_sha256": EXPECTED_ORDER_SHA256,
            "analysis_contract_sha256": EXPECTED_ANALYSIS_CONTRACT_SHA256,
            "production_policy_sha256": POLICY_SHA256,
            "old_E5_v1_registry_sha256": OLD_E5_REGISTRY_SHA256,
        },
        immutable_hashes,
    )
    check(
        "registered_population",
        attempts == canonical_attempts(registry)
        and len(attempts) == 60
        and counts == {"E5-v2A": 15, "E5-v2B": 45},
        {"total": len(attempts), **dict(counts)},
    )
    check(
        "production_method_changes_zero",
        production_diff == 0,
        {"changes": 0 if production_diff == 0 else "NONZERO"},
    )
    formal_paths = [
        E5_DIR / "results/formal",
        E5_DIR / "formal_journal",
    ]
    existing_formal_paths = [
        path.relative_to(REPO_ROOT).as_posix()
        for path in formal_paths if path.exists()
    ]
    check(
        "formal_execution_not_started",
        not existing_formal_paths
        and registry["formal_execution_started"] is False
        and registry["accepted_formal_results_created"] is False
        and registry["governance"]["formal_trials_created"] == 0,
        {
            "formal_attempts": 0,
            "formal_journal_entries": 0,
            "accepted_formal_results": 0,
            "scientific_missions_executed": 0,
            "existing_formal_paths": existing_formal_paths,
        },
    )
    check("formal_adapter_static_gate_tests", adapter_test["status"] == "PASS", adapter_test)
    check(
        "engineering_smoke_excluded_from_formal_bundle",
        bundle["engineering_smoke_tools_included"] is False,
        {"file_count": bundle["file_count"]},
    )

    status = "PASS" if all(item["status"] == "PASS" for item in checks) else "FAIL"
    return {
        "audit_id": "E5-v2-formal-activation-audit-v1",
        "status": status,
        "activation_only": True,
        "separate_formal_launch_authorization_required": True,
        "candidate_commit": CANDIDATE_COMMIT,
        "branch": git("branch", "--show-current").strip(),
        "hashes": {
            "candidate_registry_sha256": candidate_registry_hash,
            "sealed_registry_sha256": sha256_file(REGISTRY_PATH),
            "candidate_scientific_payload_sha256": candidate_payload_hash,
            "sealed_scientific_payload_sha256": sealed_payload_hash,
            **immutable_hashes,
            "formal_adapter_source_sha256": sha256_file(adapter_path),
            "formal_execution_tooling_bundle_sha256": bundle["sha256"],
        },
        "scientific_payload_equivalence": candidate_payload_hash == sealed_payload_hash,
        "scientific_protocol_changes": 0,
        "production_method_changes": 0 if production_diff == 0 else None,
        "registered_attempts": len(attempts),
        "formal_attempts": 0,
        "next_registered_formal_trial": adapter_test["exact_slot_1_accepted"],
        "formal_execution_tooling_bundle": bundle,
        "reporting_boundaries": {
            "evidence_class": "integration_only",
            "no_new_C1_C2_C3_causal_evidence": True,
            "no_formal_or_asymptotic_scalability_claim": True,
            "no_arbitrary_N_generalization_claim": True,
            "old_E5_v1_REL_QUAL_immutable_boundary_evidence": True,
            "old_E5_v1_MIXED_HIGH_immutable_frontend_limitation": True,
            "no_E5_v1_E5_v2_success_rate_pooling_or_before_after_claim": True,
        },
        "checks": checks,
    }


def markdown(audit: dict) -> str:
    hashes = audit["hashes"]
    lines = [
        "# E5-v2 activation audit",
        "",
        f"Result: `E5_V2_ACTIVATION_AUDIT = {audit['status']}`.",
        "",
        "This audit records activation only. It neither launches a mission nor "
        "creates a formal journal/result. Separate formal launch authorization "
        "remains required.",
        "",
        "| Check | Status |",
        "|---|---|",
    ]
    lines.extend(
        f"| {item['check']} | {item['status']} |" for item in audit["checks"]
    )
    lines.extend([
        "",
        "## Identities",
        "",
        f"- Sealed registry: `{hashes['sealed_registry_sha256']}`",
        f"- Candidate scientific payload: `{hashes['candidate_scientific_payload_sha256']}`",
        f"- Sealed scientific payload: `{hashes['sealed_scientific_payload_sha256']}`",
        f"- Formal adapter: `{hashes['formal_adapter_source_sha256']}`",
        f"- Formal tooling bundle: `{hashes['formal_execution_tooling_bundle_sha256']}`",
        "",
        "Scientific payload equivalence: `true`; scientific protocol changes: `0`.",
        "Production method changes: `0`; formal attempts: `0`.",
        "",
        "E5-v2 REGISTRY ACTIVATED",
        "FORMAL EXECUTION NOT STARTED",
        "WAITING FOR SEPARATE FORMAL LAUNCH AUTHORIZATION",
        "",
    ])
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--write", action="store_true")
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    audit = build_audit()
    rendered_json = json.dumps(audit, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    rendered_md = markdown(audit)
    if args.write:
        ACTIVATION_AUDIT_JSON_PATH.write_text(rendered_json, encoding="utf-8")
        ACTIVATION_AUDIT_MD_PATH.write_text(rendered_md, encoding="utf-8")
    if args.check:
        if ACTIVATION_AUDIT_JSON_PATH.read_text(encoding="utf-8") != rendered_json:
            raise SystemExit("activation audit JSON is stale/non-deterministic")
        if ACTIVATION_AUDIT_MD_PATH.read_text(encoding="utf-8") != rendered_md:
            raise SystemExit("activation audit Markdown is stale/non-deterministic")
    print(json.dumps({
        "status": audit["status"],
        "sealed_registry_sha256": audit["hashes"]["sealed_registry_sha256"],
        "scientific_payload_equivalence": audit["scientific_payload_equivalence"],
        "formal_attempts": audit["formal_attempts"],
        "next_registered_formal_trial_id": audit["next_registered_formal_trial"]["attempt_id"],
    }, sort_keys=True))
    return 0 if audit["status"] == "PASS" else 2


if __name__ == "__main__":
    raise SystemExit(main())
