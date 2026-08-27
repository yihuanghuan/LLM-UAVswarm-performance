#!/usr/bin/env python3
"""Fail-closed provenance validation for suite-level campaign dispatch."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import subprocess
from typing import Any, Dict, List

from campaign_common import (
    BASELINE_COMMIT, BASELINE_TAG, CAMPAIGN_DIR, CAMPAIGN_MANIFEST_PATH,
    CANONICAL_POLICY_SHA256, DATASET_CLASS, FORMAL_DIR, GLOBAL_REGISTRY_PATH,
    GLOBAL_REGISTRY_SHA256, NOT_FORMAL_RESULT, ORDER_TXT_PATH, ORDER_TXT_SHA256,
    ORDER_YAML_PATH, ORDER_YAML_SHA256, POLICY_PATH, PREFLIGHT_PATH,
    PREFLIGHT_SHA256, REPO_ROOT, SOURCE_PREFLIGHT_COMMIT, CampaignError,
    load_json, load_sealed_order, load_yaml, sha256_file, source_hashes, utc_now,
    write_json_exclusive,
)
from runner_registry import formal_launch_gate, load_runner_registry, registry_sha256


SEALED_RELATIVE_PATHS = (
    "experiments_v2/Formal Evaluation Experiments/formal_preflight_v1.yaml",
    "experiments_v2/Formal Evaluation Experiments/e2_e5_scenario_seed_registry_v1.yaml",
    "experiments_v2/Formal Evaluation Experiments/simulation_trial_order_v1.yaml",
    "experiments_v2/Formal Evaluation Experiments/simulation_trial_order_v1.txt",
)
E2_RUNNER_COMMIT = "22110f3515662d88a9e8482368fad843fff6968a"
E2_RUNNER_PATH = "experiments_v2/Formal Evaluation Experiments/E2/tooling/e2_runner.py"
E2_RUNNER_SHA256 = "39d3fa0a34b623c46468b62c12da74ace443d360e8f4a84ee20fef9edfa479ac"


def _git(*args: str, binary: bool = False) -> str | bytes:
    result = subprocess.run(
        ["git", *args], cwd=REPO_ROOT, check=True, capture_output=True,
        text=not binary,
    )
    return result.stdout


def _check(checks: List[Dict[str, Any]], name: str, ok: bool, details: Any) -> None:
    checks.append({"check": name, "status": "PASS" if ok else "FAIL", "details": details})


def _changed_paths() -> List[str]:
    tracked = str(_git("diff", "--name-only", SOURCE_PREFLIGHT_COMMIT)).splitlines()
    untracked = str(_git("ls-files", "--others", "--exclude-standard")).splitlines()
    return sorted(set(tracked + untracked))


def validate_provenance(raise_on_failure: bool = True) -> Dict[str, Any]:
    checks: List[Dict[str, Any]] = []
    try:
        head = str(_git("rev-parse", "HEAD")).strip()
        source = str(_git("rev-parse", SOURCE_PREFLIGHT_COMMIT)).strip()
        ancestor = subprocess.run(
            ["git", "merge-base", "--is-ancestor", SOURCE_PREFLIGHT_COMMIT, "HEAD"],
            cwd=REPO_ROOT,
        ).returncode == 0
        _check(checks, "exact_preflight_source_and_ancestry",
               source == SOURCE_PREFLIGHT_COMMIT and ancestor,
               {"expected_source": SOURCE_PREFLIGHT_COMMIT, "resolved_source": source,
                "campaign_infrastructure_commit": head, "source_is_ancestor": ancestor})

        baseline = str(_git("rev-parse", f"{BASELINE_TAG}^{{}}")).strip()
        _check(checks, "sealed_baseline_tag_resolution", baseline == BASELINE_COMMIT,
               {"tag": BASELINE_TAG, "resolved": baseline, "expected": BASELINE_COMMIT})

        sealed_details: Dict[str, Any] = {}
        sealed_ok = True
        for relative in SEALED_RELATIVE_PATHS:
            current = (REPO_ROOT / relative).read_bytes()
            approved = _git("show", f"{SOURCE_PREFLIGHT_COMMIT}:{relative}", binary=True)
            identical = current == approved
            sealed_ok = sealed_ok and identical
            sealed_details[relative] = {
                "sha256": hashlib.sha256(current).hexdigest(), "byte_identical": identical
            }
        _check(checks, "sealed_inputs_byte_identical_to_preflight_commit", sealed_ok, sealed_details)

        order = load_sealed_order()
        _check(checks, "sealed_610_permutation", len(order) == 610,
               {"count": len(order), "unique": len(set(order)), "sha256": sha256_file(ORDER_TXT_PATH)})

        preflight = load_yaml(PREFLIGHT_PATH)
        policy_hash = sha256_file(POLICY_PATH)
        gate_ok = (
            preflight.get("status") == "SEALED"
            and preflight.get("final_review_completed") is True
            and preflight.get("baseline_tag") == BASELINE_TAG
            and preflight.get("baseline_commit") == BASELINE_COMMIT
            and preflight.get("canonical_policy_sha256") == CANONICAL_POLICY_SHA256
            and policy_hash == CANONICAL_POLICY_SHA256
        )
        _check(checks, "sealed_preflight_policy_gate", gate_ok,
               {"preflight_status": preflight.get("status"), "policy_sha256": policy_hash})

        pinned_hashes = {
            "formal_preflight_v1.yaml": (sha256_file(PREFLIGHT_PATH), PREFLIGHT_SHA256),
            "global_seed_registry": (sha256_file(GLOBAL_REGISTRY_PATH), GLOBAL_REGISTRY_SHA256),
            "simulation_trial_order_v1.yaml": (sha256_file(ORDER_YAML_PATH), ORDER_YAML_SHA256),
            "simulation_trial_order_v1.txt": (sha256_file(ORDER_TXT_PATH), ORDER_TXT_SHA256),
        }
        _check(checks, "pinned_sealed_artifact_hashes",
               all(actual == expected for actual, expected in pinned_hashes.values()),
               {key: {"actual": value[0], "expected": value[1]}
                for key, value in pinned_hashes.items()})

        registry = load_runner_registry()
        e2_source = _git("show", f"{E2_RUNNER_COMMIT}:{E2_RUNNER_PATH}", binary=True)
        e2_hash = hashlib.sha256(e2_source).hexdigest()
        e2 = registry["runners"]["E2"]
        e2_ok = (e2["runner_commit"] == E2_RUNNER_COMMIT
                 and e2["runner_source_sha256"] == E2_RUNNER_SHA256 == e2_hash)
        _check(checks, "pinned_E2_stage_B_reference", e2_ok,
               {"commit": E2_RUNNER_COMMIT, "source_sha256": e2_hash,
                "validation_scope": e2.get("validation_scope")})

        launch_ready, blockers = formal_launch_gate(registry)
        _check(checks, "formal_launch_fail_closed_NOT_READY",
               not launch_ready and registry.get("formal_campaign_status") == "NOT_READY",
               {"formal_launch_allowed": launch_ready, "blockers": blockers})

        machine_manifest = load_json(CAMPAIGN_MANIFEST_PATH)
        labels_ok = (machine_manifest.get("dataset_class") == DATASET_CLASS
                     and machine_manifest.get("accepted_formal_result") is False
                     and machine_manifest.get("result_notice") == NOT_FORMAL_RESULT
                     and machine_manifest.get("current_formal_campaign_status") == "NOT_READY")
        _check(checks, "synthetic_only_machine_manifest", labels_ok, machine_manifest)

        changed = _changed_paths()
        prefix = CAMPAIGN_DIR.relative_to(REPO_ROOT).as_posix() + "/"
        prohibited = [path for path in changed if not path.startswith(prefix)]
        _check(checks, "changes_confined_to_global_campaign_infrastructure", not prohibited,
               {"changed_count": len(changed), "prohibited_paths": prohibited})
    except Exception as exc:
        _check(checks, "provenance_validator_internal_error", False,
               {"type": type(exc).__name__, "message": str(exc)})
        head = "UNKNOWN"
        registry = {}

    campaign_sources = [path for path in CAMPAIGN_DIR.iterdir()
                        if path.is_file() and path.suffix in {".py", ".json", ".md"}]
    report = {
        "manifest_type": "E2_E5_global_campaign_provenance_v1",
        "generated_at_utc": utc_now(),
        "dataset_class": DATASET_CLASS,
        "accepted_formal_result": False,
        "result_notice": NOT_FORMAL_RESULT,
        "status": "PASS" if all(item["status"] == "PASS" for item in checks) else "FAIL",
        "campaign_infrastructure_commit": head,
        "campaign_infrastructure_source_hashes": source_hashes(campaign_sources),
        "runner_registry_sha256": registry_sha256(registry) if registry else None,
        "sealed_hashes": {
            "preflight_sha256": PREFLIGHT_SHA256,
            "canonical_policy_sha256": CANONICAL_POLICY_SHA256,
            "global_seed_registry_sha256": GLOBAL_REGISTRY_SHA256,
            "simulation_trial_order_yaml_sha256": ORDER_YAML_SHA256,
            "simulation_trial_order_txt_sha256": ORDER_TXT_SHA256,
        },
        "checks": checks,
    }
    if report["status"] != "PASS" and raise_on_failure:
        raise CampaignError(json.dumps(report, ensure_ascii=False, sort_keys=True))
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    report = validate_provenance(raise_on_failure=False)
    if args.output:
        write_json_exclusive(args.output, report)
    else:
        print(json.dumps(report, ensure_ascii=False, sort_keys=True, indent=2))
    return 0 if report["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())

