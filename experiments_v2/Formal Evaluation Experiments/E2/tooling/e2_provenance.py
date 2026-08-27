#!/usr/bin/env python3
"""Fail-closed provenance validation for E2 offline tooling."""

from __future__ import annotations

import argparse
import importlib.metadata
import json
from pathlib import Path
import platform
import subprocess
import sys
from typing import Any, Dict, List

from e2_common import (
    BASELINE_COMMIT,
    BASELINE_TAG,
    CANONICAL_POLICY_SHA256,
    CONFIGURATION_ID,
    DATASET_CLASS,
    EXPECTED_BRANCH,
    FORMAL_DIR,
    GLOBAL_REGISTRY_PATH,
    NOT_FORMAL_RESULT,
    ORDER_TXT_PATH,
    ORDER_YAML_PATH,
    POLICY_PATH,
    PREFLIGHT_PATH,
    PROTOCOL_PATH,
    REGISTRY_PATH,
    REPO_ROOT,
    SOURCE_PREFLIGHT_COMMIT,
    WRAPPER_PATH,
    E2ToolingError,
    load_scenario_registry,
    load_yaml,
    registered_trial_ids,
    sha256_file,
    utc_now,
    write_json_exclusive,
)

ALLOWED_BRANCHES = {EXPECTED_BRANCH, "formal/E2-formal-adapter-v1"}


SEALED_PATHS = (
    "experiments_v2/Formal Evaluation Experiments/formal_preflight_v1.yaml",
    "experiments_v2/Formal Evaluation Experiments/protocols/E2_protocol_v1.yaml",
    "experiments_v2/Formal Evaluation Experiments/E2/e2_scenario_registry_v1.yaml",
    "experiments_v2/Formal Evaluation Experiments/e2_e5_scenario_seed_registry_v1.yaml",
    "experiments_v2/Formal Evaluation Experiments/simulation_trial_order_v1.yaml",
    "experiments_v2/Formal Evaluation Experiments/simulation_trial_order_v1.txt",
    "experiments_v2/Formal Evaluation Experiments/harness/e2_commitment_wrapper.py",
    "experiments_v2/Formal Evaluation Experiments/harness/test_e2_commitment_wrapper.py",
    "lfs_policy/config/lfs_policy.paper_current.yaml",
)

PRODUCTION_SOURCE_PATHS = (
    "location_allocate/location_allocate/execution_profile_compiler.py",
    "location_allocate/location_allocate/formation_geometry.py",
    "location_allocate/location_allocate/late_resolution.py",
    "location_allocate/location_allocate/lfs_resolver.py",
    "location_allocate/location_allocate/lfs_types.py",
    "location_allocate/location_allocate/motion_limits.py",
    "location_allocate/location_allocate/paper_lfs_validator.py",
    "location_allocate/location_allocate/policy_adapter.py",
    "location_allocate/location_allocate/prompt_loader.py",
    "location_allocate/location_allocate/reproducibility.py",
    "location_allocate/location_allocate/safety_aware_allocator.py",
    "location_allocate/location_allocate/timing_resolution.py",
    "location_allocate/location_allocate/validation_common.py",
    "location_allocate/prompts/paper_candidate_en_v2_fewshot.json",
    "location_allocate/prompts/paper_candidate_en_v2_system.txt",
    "schemas/paper_candidate_schema_v2.json",
    "lfs_policy/lfs_policy/__init__.py",
    "lfs_policy/lfs_policy/loader.py",
)


class ProvenanceError(E2ToolingError):
    """Raised when any mandatory provenance check fails."""

    def __init__(self, report: Dict[str, Any]):
        failed = [
            item["name"] for item in report.get("checks", [])
            if item.get("status") != "PASS"
        ]
        super().__init__("provenance validation failed: " + ", ".join(failed))
        self.report = report


def _git(repo_root: Path, *args: str, check: bool = True) -> str:
    completed = subprocess.run(
        ["git", *args], cwd=repo_root, text=True,
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False,
    )
    if check and completed.returncode != 0:
        raise E2ToolingError(
            f"git {' '.join(args)} failed: {completed.stderr.strip()}"
        )
    return completed.stdout.strip()


def _git_success(repo_root: Path, *args: str) -> bool:
    return subprocess.run(
        ["git", *args], cwd=repo_root,
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False,
    ).returncode == 0


def _source_blob(repo_root: Path, relative_path: str) -> bytes:
    completed = subprocess.run(
        ["git", "show", f"{SOURCE_PREFLIGHT_COMMIT}:{relative_path}"],
        cwd=repo_root, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False,
    )
    if completed.returncode != 0:
        raise E2ToolingError(
            f"cannot read authoritative preflight blob {relative_path}: "
            + completed.stderr.decode("utf-8", errors="replace").strip()
        )
    return completed.stdout


def _changed_paths(repo_root: Path) -> List[str]:
    paths = set()
    for args in (
        ("diff", "--name-only", SOURCE_PREFLIGHT_COMMIT, "HEAD"),
        ("diff", "--name-only"),
        ("diff", "--cached", "--name-only"),
        ("ls-files", "--others", "--exclude-standard"),
    ):
        paths.update(line for line in _git(repo_root, *args).splitlines() if line)
    return sorted(paths)


def _allowed_e2_change(path: str) -> bool:
    tooling = "experiments_v2/Formal Evaluation Experiments/E2/tooling/"
    synthetic = (
        "experiments_v2/Formal Evaluation Experiments/E2/results/"
        "synthetic-validation/"
    )
    formal = "experiments_v2/Formal Evaluation Experiments/E2/results/formal/"
    engineering = (
        "experiments_v2/Formal Evaluation Experiments/E2/results/"
        "engineering-validation/"
    )
    documents = {
        "experiments_v2/Formal Evaluation Experiments/E2/FORMAL_ADAPTER_README.md",
        "experiments_v2/Formal Evaluation Experiments/E2/formal_adapter_readiness_manifest.json",
    }
    return path in documents or path.startswith(tooling) or path.startswith(synthetic) or path.startswith(engineering) or (
        path.startswith(formal) and path.endswith("/.gitignore")
    )


def _runtime_information() -> Dict[str, Any]:
    packages = {}
    for name in ("PyYAML", "numpy", "scipy", "jsonschema"):
        try:
            packages[name] = importlib.metadata.version(name)
        except importlib.metadata.PackageNotFoundError:
            packages[name] = "missing"
    return {
        "python_version": platform.python_version(),
        "python_implementation": platform.python_implementation(),
        "python_executable": str(Path(sys.executable).resolve()),
        "platform": platform.platform(),
        "byteorder": sys.byteorder,
        "packages": packages,
    }


def validate_provenance(
    repo_root: Path = REPO_ROOT,
    *,
    expected_policy_sha256: str = CANONICAL_POLICY_SHA256,
    raise_on_failure: bool = True,
) -> Dict[str, Any]:
    """Validate sealed assets and production sources against the final seal."""
    repo_root = Path(repo_root).resolve()
    checks: List[Dict[str, Any]] = []

    def record(name: str, passed: bool, evidence: Any) -> None:
        checks.append({
            "name": name,
            "status": "PASS" if passed else "FAIL",
            "evidence": evidence,
        })

    try:
        head = _git(repo_root, "rev-parse", "HEAD")
        branch = _git(repo_root, "symbolic-ref", "--short", "HEAD")
        source_ancestor = _git_success(
            repo_root, "merge-base", "--is-ancestor", SOURCE_PREFLIGHT_COMMIT, "HEAD"
        )
        record(
            "authoritative_preflight_ancestry_and_branch",
            source_ancestor and branch in ALLOWED_BRANCHES,
            {"head": head, "branch": branch, "source_commit": SOURCE_PREFLIGHT_COMMIT},
        )

        tag_type = _git(repo_root, "cat-file", "-t", f"refs/tags/{BASELINE_TAG}")
        tag_commit = _git(repo_root, "rev-parse", f"{BASELINE_TAG}^{{commit}}")
        record(
            "frozen_baseline_tag_and_commit",
            tag_type == "tag" and tag_commit == BASELINE_COMMIT,
            {"tag": BASELINE_TAG, "tag_type": tag_type, "commit": tag_commit},
        )

        source_type = _git(repo_root, "cat-file", "-t", SOURCE_PREFLIGHT_COMMIT)
        baseline_ancestor = _git_success(
            repo_root, "merge-base", "--is-ancestor", BASELINE_COMMIT,
            SOURCE_PREFLIGHT_COMMIT,
        )
        record(
            "authoritative_preflight_commit_available",
            source_type == "commit" and baseline_ancestor,
            {"object_type": source_type, "baseline_is_ancestor": baseline_ancestor},
        )

        sealed_hashes: Dict[str, Any] = {}
        sealed_ok = True
        for relative in SEALED_PATHS:
            current = (repo_root / relative).read_bytes()
            approved = _source_blob(repo_root, relative)
            current_hash = __import__("hashlib").sha256(current).hexdigest()
            approved_hash = __import__("hashlib").sha256(approved).hexdigest()
            identical = current == approved
            sealed_ok = sealed_ok and identical
            sealed_hashes[relative] = {
                "sha256": current_hash,
                "approved_sha256": approved_hash,
                "byte_identical": identical,
            }
        record("sealed_protocol_inputs_byte_identical", sealed_ok, sealed_hashes)

        production_hashes: Dict[str, Any] = {}
        production_ok = True
        for relative in PRODUCTION_SOURCE_PATHS:
            current = (repo_root / relative).read_bytes()
            approved = _source_blob(repo_root, relative)
            current_hash = __import__("hashlib").sha256(current).hexdigest()
            approved_hash = __import__("hashlib").sha256(approved).hexdigest()
            identical = current == approved
            production_ok = production_ok and identical
            production_hashes[relative] = {
                "sha256": current_hash,
                "approved_sha256": approved_hash,
                "byte_identical": identical,
            }
        record("frozen_production_sources_byte_identical", production_ok, production_hashes)

        preflight = load_yaml(repo_root / PREFLIGHT_PATH.relative_to(REPO_ROOT))
        protocol = load_yaml(repo_root / PROTOCOL_PATH.relative_to(REPO_ROOT))
        registry = load_scenario_registry(repo_root / REGISTRY_PATH.relative_to(REPO_ROOT))
        global_registry = load_yaml(
            repo_root / GLOBAL_REGISTRY_PATH.relative_to(REPO_ROOT)
        )
        gate_ok = (
            preflight.get("status") == "SEALED"
            and preflight.get("final_review_completed") is True
            and preflight.get("baseline_tag") == BASELINE_TAG
            and preflight.get("baseline_commit") == BASELINE_COMMIT
            and preflight.get("configuration_id") == CONFIGURATION_ID
            and preflight.get("canonical_policy_sha256") == CANONICAL_POLICY_SHA256
            and protocol.get("status") == "SEALED"
            and registry.get("status") == "SEALED"
            and global_registry.get("status") == "SEALED"
        )
        record("final_sealed_E2_gate", gate_ok, {
            "preflight_status": preflight.get("status"),
            "final_review_completed": preflight.get("final_review_completed"),
            "protocol_status": protocol.get("status"),
            "registry_status": registry.get("status"),
            "global_registry_status": global_registry.get("status"),
        })

        policy_path = repo_root / POLICY_PATH.relative_to(REPO_ROOT)
        policy_hash = sha256_file(policy_path)
        policy_doc = load_yaml(policy_path)
        policy_ok = (
            policy_hash == expected_policy_sha256 == CANONICAL_POLICY_SHA256
            and policy_doc.get("configuration_id") == CONFIGURATION_ID
            and policy_doc.get("policy_status") == "paper_frozen"
        )
        record("frozen_configuration_and_policy_hash", policy_ok, {
            "configuration_id": policy_doc.get("configuration_id"),
            "policy_status": policy_doc.get("policy_status"),
            "sha256": policy_hash,
            "expected_sha256": expected_policy_sha256,
        })

        order_yaml = load_yaml(repo_root / ORDER_YAML_PATH.relative_to(REPO_ROOT))
        order_hash = sha256_file(repo_root / ORDER_TXT_PATH.relative_to(REPO_ROOT))
        declared_order_hash = global_registry["global_seed_policy"][
            "deterministic_trial_order_sha256"
        ]
        order_ok = (
            order_yaml.get("status") == "SEALED"
            and order_hash == order_yaml.get("permutation_sha256")
            and order_hash == declared_order_hash
            and len(
                (repo_root / ORDER_TXT_PATH.relative_to(REPO_ROOT))
                .read_text(encoding="utf-8").splitlines()
            ) == order_yaml.get("canonical_population_count") == 610
        )
        record("sealed_global_trial_order", order_ok, {
            "sha256": order_hash,
            "yaml_sha256": order_yaml.get("permutation_sha256"),
            "global_registry_sha256": declared_order_hash,
            "population_count": order_yaml.get("canonical_population_count"),
        })

        trial_ids = registered_trial_ids(
            repo_root / ORDER_TXT_PATH.relative_to(REPO_ROOT), registry, global_registry
        )
        record("registered_E2_population", len(trial_ids) == 120, {
            "trial_count": len(trial_ids), "unique_trial_count": len(set(trial_ids))
        })

        changed = _changed_paths(repo_root)
        prohibited = [path for path in changed if not _allowed_e2_change(path)]
        record("branch_changes_confined_to_E2_tooling_and_synthetic_results", not prohibited, {
            "changed_paths": changed, "prohibited_paths": prohibited
        })
    except Exception as exc:
        record("provenance_validator_internal_error", False, {
            "type": type(exc).__name__, "message": str(exc)
        })

    status = "PASS" if all(item["status"] == "PASS" for item in checks) else "FAIL"
    report = {
        "manifest_type": "E2_provenance_manifest_v1",
        "generated_at_utc": utc_now(),
        "dataset_class": DATASET_CLASS,
        "accepted_formal_result": False,
        "result_notice": NOT_FORMAL_RESULT,
        "status": status,
        "baseline_tag": BASELINE_TAG,
        "baseline_commit": BASELINE_COMMIT,
        "source_preflight_commit": SOURCE_PREFLIGHT_COMMIT,
        "configuration_id": CONFIGURATION_ID,
        "canonical_policy_sha256": CANONICAL_POLICY_SHA256,
        "artifact_hashes": {
            "E2_protocol_sha256": sha256_file(repo_root / PROTOCOL_PATH.relative_to(REPO_ROOT)),
            "E2_registry_sha256": sha256_file(repo_root / REGISTRY_PATH.relative_to(REPO_ROOT)),
            "global_registry_sha256": sha256_file(repo_root / GLOBAL_REGISTRY_PATH.relative_to(REPO_ROOT)),
            "simulation_trial_order_yaml_sha256": sha256_file(repo_root / ORDER_YAML_PATH.relative_to(REPO_ROOT)),
            "simulation_trial_order_sha256": sha256_file(repo_root / ORDER_TXT_PATH.relative_to(REPO_ROOT)),
            "wrapper_sha256": sha256_file(repo_root / WRAPPER_PATH.relative_to(REPO_ROOT)),
        },
        "production_source_hashes": {
            relative: sha256_file(repo_root / relative)
            for relative in PRODUCTION_SOURCE_PATHS
            if (repo_root / relative).is_file()
        },
        "runtime": _runtime_information(),
        "checks": checks,
    }
    if status != "PASS" and raise_on_failure:
        raise ProvenanceError(report)
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    try:
        report = validate_provenance()
    except ProvenanceError as exc:
        report = exc.report
    if args.output:
        write_json_exclusive(args.output, report)
    else:
        print(json.dumps(report, ensure_ascii=False, sort_keys=True, indent=2))
    return 0 if report["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
