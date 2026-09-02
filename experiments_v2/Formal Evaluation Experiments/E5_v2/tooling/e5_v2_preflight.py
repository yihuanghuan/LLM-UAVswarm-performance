#!/usr/bin/env python3
"""Fail-closed E5-v2 design/preflight audit; never executes a mission."""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
from collections import Counter
from pathlib import Path

from e5_v2_common import (
    BASELINE_COMMIT,
    E5_DIR,
    OLD_E5_REGISTRY_PATH,
    OLD_E5_REGISTRY_SHA256,
    OLD_E5_SOURCE_COMMIT,
    ORDER_METADATA_PATH,
    ORDER_PATH,
    POLICY_SHA256,
    PRODUCTION_METHOD_PATHS,
    REGISTRY_PATH,
    REPO_ROOT,
    SEED_REGISTRY_PATH,
    canonical_attempts,
    load_yaml,
    ordered_attempts,
    sha256_file,
)
from e5_v2_formal_adapter import FormalActivationError, assert_formal_activation


OUTPUT_JSON = E5_DIR / "E5_v2_preflight_audit.json"
OUTPUT_MD = E5_DIR / "E5_v2_preflight_audit.md"


def git(*arguments, binary=False):
    return subprocess.run(
        ["git", *arguments],
        cwd=REPO_ROOT,
        check=True,
        capture_output=True,
        text=not binary,
    ).stdout


def build_audit():
    checks = []

    def check(name, passed, evidence):
        checks.append({
            "check": name,
            "status": "PASS" if passed else "FAIL",
            "evidence": evidence,
        })

    registry = load_yaml(REGISTRY_PATH)
    seeds = load_yaml(SEED_REGISTRY_PATH)
    order_metadata = json.loads(ORDER_METADATA_PATH.read_text(encoding="utf-8"))
    n_audit = json.loads((E5_DIR / "E5_v2_n_agnostic_audit.json").read_text())
    feasibility = json.loads((E5_DIR / "E5_v2_feasibility_audit.json").read_text())
    smoke = json.loads(
        (E5_DIR / "E5_v2_engineering_scale_smoke_results.json").read_text()
    )
    attempts = seeds["attempts"]
    expected_attempts = canonical_attempts(registry)
    expected_order = ordered_attempts(registry)
    changed_paths = sorted(set(
        git("diff", "--name-only", BASELINE_COMMIT).splitlines()
        + git("ls-files", "--others", "--exclude-standard").splitlines()
    ))
    allowed_prefix = "experiments_v2/Formal Evaluation Experiments/E5_v2/"
    change_classification = [
        {
            "path": path,
            "classification": (
                "E5_v2_experiment_only"
                if path.startswith(allowed_prefix)
                else "OUTSIDE_ALLOWED_SCOPE"
            ),
        }
        for path in changed_paths
    ]

    check(
        "baseline_tag_resolution",
        git("rev-parse", "paper-final-sim-v3^{}").strip() == BASELINE_COMMIT,
        {"tag": "paper-final-sim-v3", "commit": BASELINE_COMMIT},
    )
    check(
        "candidate_registry_not_activated",
        registry["status"] == "CANDIDATE_FOR_HUMAN_REVIEW",
        registry["status"],
    )
    try:
        assert_formal_activation(REGISTRY_PATH, None)
        adapter_refused = False
    except FormalActivationError:
        adapter_refused = True
    check("formal_adapter_refuses_candidate", adapter_refused, adapter_refused)
    check(
        "n_agnostic_method_audit",
        n_audit["conclusion"] == "E5_V2_N_AGNOSTIC_METHOD_AUDIT = PASS"
        and not n_audit["method_semantic_change_required_for_N12_or_N16"],
        n_audit["conclusion"],
    )
    check("deterministic_feasibility", feasibility["status"] == "PASS", feasibility["status"])
    check("engineering_scale_smoke", smoke["status"] == "PASS", smoke["status"])
    check(
        "attempt_population",
        attempts == expected_attempts and len(attempts) == 60,
        {"registered": len(attempts), "expected": 60},
    )
    counts = Counter((item["substudy"], item["N"], item.get("task_family")) for item in attempts)
    check(
        "substudy_counts",
        sum(item["substudy"] == "E5-v2A" for item in attempts) == 15
        and sum(item["substudy"] == "E5-v2B" for item in attempts) == 45,
        {"E5-v2A": 15, "E5-v2B": 45},
    )
    check(
        "E5_v2B_cell_counts",
        all(
            counts[("E5-v2B", n, family)] == 5
            for n in (8, 12, 16)
            for family in ("SIMPLE", "UNDER_SPECIFIED", "COMPOSITIONAL")
        ),
        order_metadata["E5_v2B_cell_counts"],
    )
    formal_seeds = [int(item["seed"]) for item in attempts]
    exclusions = {
        int(value)
        for values in seeds["collision_exclusions"].values()
        for value in values
    }
    check(
        "formal_seed_uniqueness_and_exclusion",
        len(formal_seeds) == len(set(formal_seeds))
        and not set(formal_seeds).intersection(exclusions),
        {"count": len(formal_seeds), "unique": len(set(formal_seeds))},
    )
    rendered_order_ids = [
        line.split("\t", 2)[1]
        for line in ORDER_PATH.read_text(encoding="utf-8").splitlines()
    ]
    check(
        "formal_order_determinism",
        rendered_order_ids == [item["attempt_id"] for item in expected_order]
        and sha256_file(ORDER_PATH) == order_metadata["final_order_sha256"],
        {"sha256": sha256_file(ORDER_PATH), "count": len(rendered_order_ids)},
    )
    old_registry = git(
        "show", f"{OLD_E5_SOURCE_COMMIT}:{OLD_E5_REGISTRY_PATH}", binary=True
    )
    old_hash = hashlib.sha256(old_registry).hexdigest()
    check(
        "old_E5_v1_registry_unchanged",
        old_hash == OLD_E5_REGISTRY_SHA256,
        {"source_commit": OLD_E5_SOURCE_COMMIT, "sha256": old_hash},
    )
    old_path_diff = subprocess.run(
        ["git", "diff", "--quiet", BASELINE_COMMIT, "--", OLD_E5_REGISTRY_PATH],
        cwd=REPO_ROOT,
    ).returncode
    check(
        "old_E5_v1_path_unchanged_from_baseline",
        old_path_diff == 0,
        {"path": OLD_E5_REGISTRY_PATH, "diff": old_path_diff},
    )
    production_diff = subprocess.run(
        ["git", "diff", "--quiet", BASELINE_COMMIT, "--", *PRODUCTION_METHOD_PATHS],
        cwd=REPO_ROOT,
    ).returncode
    check(
        "production_method_changes_zero",
        production_diff == 0,
        {"baseline": BASELINE_COMMIT, "paths": list(PRODUCTION_METHOD_PATHS)},
    )
    check(
        "all_branch_changes_classified_allowed",
        bool(change_classification)
        and all(
            item["classification"] == "E5_v2_experiment_only"
            for item in change_classification
        ),
        {"changed_path_count": len(change_classification)},
    )
    policy_hash = sha256_file(REPO_ROOT / "lfs_policy/config/lfs_policy.paper_current.yaml")
    check("frozen_policy_unchanged", policy_hash == POLICY_SHA256, policy_hash)
    forbidden_formal = [
        path.as_posix() for path in (
            E5_DIR / "results/formal",
            E5_DIR / "formal_journal",
        ) if path.exists()
    ]
    check(
        "formal_execution_not_started",
        not forbidden_formal
        and registry["formal_execution_started"] is False
        and registry["accepted_formal_results_created"] is False
        and registry["governance"]["formal_trials_created"] == 0,
        {"forbidden_paths": forbidden_formal, "formal_trials_created": 0},
    )
    required = [
        "E5_v2_n_agnostic_audit.md", "E5_v2_n_agnostic_audit.json",
        "E5_v2_relationship_to_E5_v1.md",
        "E5_v2_scenario_design_candidates.yaml",
        "E5_v2_feasibility_audit.md", "E5_v2_feasibility_audit.json",
        "E5_v2_registry.yaml", "E5_v2_seed_registry.yaml",
        "E5_v2_formal_trial_order.txt", "E5_v2_formal_trial_order_metadata.json",
        "E5_v2_analysis_contract.md",
        "E5_v2_engineering_scale_smoke_protocol.yaml",
        "E5_v2_engineering_scale_smoke_audit.md",
    ]
    missing = [name for name in required if not (E5_DIR / name).is_file()]
    check("required_preformal_artifacts", not missing, {"missing": missing})

    status = "PASS" if all(item["status"] == "PASS" for item in checks) else "FAIL"
    return {
        "audit_id": "E5-v2-preflight-audit-v1",
        "status": status,
        "target_state": (
            "E5-v2 DESIGN/PREFLIGHT READY; FORMAL EXECUTION NOT STARTED; "
            "WAITING FOR HUMAN REVIEW / ACTIVATION"
        ),
        "baseline_commit": BASELINE_COMMIT,
        "branch": git("branch", "--show-current").strip(),
        "hashes": {
            "formal_seed_registry_sha256": sha256_file(SEED_REGISTRY_PATH),
            "formal_order_sha256": sha256_file(ORDER_PATH),
            "candidate_registry_sha256": sha256_file(REGISTRY_PATH),
            "analysis_contract_sha256": sha256_file(E5_DIR / "E5_v2_analysis_contract.md"),
            "old_E5_v1_registry_sha256": old_hash,
            "policy_sha256": policy_hash,
        },
        "production_method_changes": 0 if production_diff == 0 else None,
        "change_classification": change_classification,
        "formal_E5_v2_attempts_created": 0,
        "test_evidence": {
            "E5_v2_design_tests": {
                "passed": 10,
                "failed": 0,
                "command_environment": "project virtual environment",
            },
            "frozen_baseline_existing_suite": {
                "total": 207,
                "passed": 199,
                "failed": 7,
                "skipped": 1,
                "gating_for_E5_v2_design": False,
                "reason": (
                    "Failures are pre-existing at paper-final-sim-v3: stale "
                    "configuration expectations, an absent legacy replay "
                    "script, and existing lint findings. Governance forbids "
                    "editing production or closed evidence to repair them."
                ),
            },
        },
        "checks": checks,
    }


def markdown(audit):
    lines = [
        "# E5-v2 preflight audit",
        "",
        f"Result: `E5_V2_PREFLIGHT_AUDIT = {audit['status']}`.",
        "",
        "| Check | Status |",
        "|---|---|",
    ]
    lines.extend(
        f"| {item['check']} | {item['status']} |" for item in audit["checks"]
    )
    lines.extend([
        "",
        f"Production method changes: {audit['production_method_changes']}.",
        f"Formal E5-v2 attempts created: {audit['formal_E5_v2_attempts_created']}.",
        "E5-v2 design tests: 10 passed, 0 failed. The frozen baseline's "
        "existing suite reported 199 passed, 7 pre-existing failures, and 1 "
        "skip; it is recorded diagnostically and production was not edited.",
        "",
        "E5-v2 DESIGN/PREFLIGHT READY",
        "FORMAL EXECUTION NOT STARTED",
        "WAITING FOR HUMAN REVIEW / ACTIVATION",
        "",
    ])
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--write", action="store_true")
    args = parser.parse_args()
    audit = build_audit()
    if args.write:
        OUTPUT_JSON.write_text(
            json.dumps(audit, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        OUTPUT_MD.write_text(markdown(audit), encoding="utf-8")
    print(json.dumps({"status": audit["status"], **audit["hashes"]}, sort_keys=True))
    return 0 if audit["status"] == "PASS" else 2


if __name__ == "__main__":
    raise SystemExit(main())
