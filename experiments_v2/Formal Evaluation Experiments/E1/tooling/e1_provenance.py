#!/usr/bin/env python3
"""Fail-closed provenance validator for future E1 provider execution."""

from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import platform
import subprocess
import sys
from typing import Any, Dict, List

from e1_common import (
    BASELINE_COMMIT,
    BASELINE_TAG,
    DATASET_PATH,
    DATASET_REGISTRY_PATH,
    E1_DIR,
    FORMAL_DIR,
    FORMAL_PREFIX,
    ORDER_PATH,
    PREFLIGHT_PATH,
    PROTOCOL_PATH,
    REPO_ROOT,
    RUNTIME_MANIFEST_PATH,
    SOURCE_PREFLIGHT_COMMIT,
    E1ToolingError,
    load_dataset,
    load_order,
    load_yaml,
    permutation_bytes,
    sha256_bytes,
    sha256_file,
    utc_now,
)


SEALED_SOURCE_PATHS = (
    "experiments_v2/Formal Evaluation Experiments/README.md",
    "experiments_v2/Formal Evaluation Experiments/formal_preflight_v1.yaml",
    "experiments_v2/Formal Evaluation Experiments/llm_runtime_manifest_v1.yaml",
    "experiments_v2/Formal Evaluation Experiments/E1/e1_candidate_semantic_dataset_v1.jsonl",
    "experiments_v2/Formal Evaluation Experiments/E1/e1_client_environment_lock_v1.sha256",
    "experiments_v2/Formal Evaluation Experiments/E1/e1_client_environment_lock_v1.txt",
    "experiments_v2/Formal Evaluation Experiments/E1/e1_client_environment_lock_v1.yaml",
    "experiments_v2/Formal Evaluation Experiments/E1/e1_dataset_registry_v1.yaml",
    "experiments_v2/Formal Evaluation Experiments/E1/e1_inference_order_v1.yaml",
    "experiments_v2/Formal Evaluation Experiments/E1/e1_protocol_v1.yaml",
)

ALLOWED_BRANCH_PATHS = set(SEALED_SOURCE_PATHS) | {
    "experiments_v2/Formal Evaluation Experiments/E1/e1_tooling_provenance_v1.yaml",
    "experiments_v2/Formal Evaluation Experiments/E1/results/formal/.gitignore",
    "experiments_v2/Formal Evaluation Experiments/E1/results/synthetic-validation/.gitignore",
}


class ProvenanceError(E1ToolingError):
    """One or more frozen provenance checks failed."""

    def __init__(self, report: Dict[str, Any]):
        failed = [
            check["name"] for check in report["checks"]
            if check["status"] != "PASS"
        ]
        super().__init__("provenance validation failed: " + ", ".join(failed))
        self.report = report


def _git(repo_root: Path, *args: str, check: bool = True) -> str:
    completed = subprocess.run(
        ["git", *args],
        cwd=repo_root,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    if check and completed.returncode != 0:
        raise E1ToolingError(
            f"git {' '.join(args)} failed: {completed.stderr.strip()}"
        )
    return completed.stdout.strip()


def _source_blob(repo_root: Path, relative_path: str) -> bytes:
    completed = subprocess.run(
        ["git", "show", f"{SOURCE_PREFLIGHT_COMMIT}:{relative_path}"],
        cwd=repo_root,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    if completed.returncode != 0:
        raise E1ToolingError(
            f"cannot read approved blob {relative_path}: "
            f"{completed.stderr.decode('utf-8', errors='replace').strip()}"
        )
    return completed.stdout


def _changed_paths(repo_root: Path) -> List[str]:
    paths = set()
    for arguments in (
        ("diff", "--name-only", BASELINE_COMMIT, "HEAD"),
        ("diff", "--name-only"),
        ("diff", "--cached", "--name-only"),
        ("ls-files", "--others", "--exclude-standard"),
    ):
        output = _git(repo_root, *arguments)
        paths.update(line for line in output.splitlines() if line)
    return sorted(paths)


def _locked_freeze(lock_path: Path) -> List[str]:
    lines = lock_path.read_text(encoding="utf-8").splitlines()
    try:
        start = lines.index("# pip_freeze_begin") + 1
        end = lines.index("# pip_freeze_end")
    except ValueError as exc:
        raise E1ToolingError("client lock lacks pip freeze delimiters") from exc
    return lines[start:end]


def validate_provenance(
    repo_root: Path = REPO_ROOT,
    *,
    require_clean: bool = True,
    verify_environment: bool = True,
) -> Dict[str, Any]:
    """Validate every frozen E1 input and return a machine-readable report."""
    repo_root = Path(repo_root).resolve()
    checks: List[Dict[str, Any]] = []

    def record(name: str, passed: bool, evidence: Any) -> None:
        checks.append({
            "name": name,
            "status": "PASS" if passed else "FAIL",
            "evidence": evidence,
        })

    try:
        tag_type = _git(repo_root, "cat-file", "-t", f"refs/tags/{BASELINE_TAG}")
        tag_commit = _git(repo_root, "rev-parse", f"{BASELINE_TAG}^{{commit}}")
        record(
            "immutable_baseline_tag_and_commit",
            tag_type == "tag" and tag_commit == BASELINE_COMMIT,
            {"tag_type": tag_type, "resolved_commit": tag_commit},
        )

        ancestor = subprocess.run(
            ["git", "merge-base", "--is-ancestor", BASELINE_COMMIT, "HEAD"],
            cwd=repo_root,
            check=False,
        ).returncode == 0
        record(
            "branch_descends_from_runtime_baseline",
            ancestor,
            {"head": _git(repo_root, "rev-parse", "HEAD")},
        )

        source_type = _git(repo_root, "cat-file", "-t", SOURCE_PREFLIGHT_COMMIT)
        record(
            "source_final_preflight_commit",
            source_type == "commit",
            {"commit": SOURCE_PREFLIGHT_COMMIT, "object_type": source_type},
        )

        sealed_evidence = {}
        sealed_ok = True
        for relative in SEALED_SOURCE_PATHS:
            current = (repo_root / relative).read_bytes()
            approved = _source_blob(repo_root, relative)
            current_hash = sha256_bytes(current)
            approved_hash = sha256_bytes(approved)
            match = current == approved
            sealed_ok = sealed_ok and match
            sealed_evidence[relative] = {
                "sha256": current_hash,
                "approved_sha256": approved_hash,
                "byte_identical": match,
            }
        record(
            "approved_e1_assets_byte_identical",
            sealed_ok,
            sealed_evidence,
        )

        preflight = load_yaml(repo_root / PREFLIGHT_PATH.relative_to(REPO_ROOT))
        preflight_ok = (
            preflight.get("status") == "SEALED"
            and preflight.get("baseline_tag") == BASELINE_TAG
            and preflight.get("baseline_commit") == BASELINE_COMMIT
            and preflight.get("E1_execution_gate", {}).get("execution_allowed")
            is True
            and preflight.get("human_approval", {}).get("status") == "APPROVED"
        )
        record("human_approved_final_preflight_gate", preflight_ok, {
            "status": preflight.get("status"),
            "execution_allowed": preflight.get("E1_execution_gate", {}).get(
                "execution_allowed"
            ),
            "approval": preflight.get("human_approval", {}).get("status"),
        })

        policy_relative = "lfs_policy/config/lfs_policy.paper_current.yaml"
        policy_hash = sha256_file(repo_root / policy_relative)
        expected_policy_hash = preflight.get("canonical_policy_sha256")
        record(
            "canonical_policy_sha256",
            policy_hash == expected_policy_hash,
            {"path": policy_relative, "sha256": policy_hash},
        )

        registry = load_yaml(repo_root / DATASET_REGISTRY_PATH.relative_to(REPO_ROOT))
        dataset_hash = sha256_file(repo_root / DATASET_PATH.relative_to(REPO_ROOT))
        dataset = load_dataset(repo_root / DATASET_PATH.relative_to(REPO_ROOT))
        ids = [str(record_["id"]) for record_ in dataset]
        valid_count = sum(record_.get("valid") is True for record_ in dataset)
        invalid_count = sum(record_.get("valid") is False for record_ in dataset)
        dataset_ok = (
            dataset_hash == registry.get("dataset_sha256")
            and len(dataset) == registry.get("command_count") == 120
            and valid_count == registry.get("valid_count") == 96
            and invalid_count == registry.get("invalid_count") == 24
            and ids == [f"E1-{index:04d}" for index in range(1, 121)]
        )
        record("sealed_dataset", dataset_ok, {
            "sha256": dataset_hash,
            "commands": len(dataset),
            "valid": valid_count,
            "invalid": invalid_count,
        })

        order_doc = load_yaml(repo_root / ORDER_PATH.relative_to(REPO_ROOT))
        protocol = load_yaml(repo_root / PROTOCOL_PATH.relative_to(REPO_ROOT))
        order = load_order(repo_root / ORDER_PATH.relative_to(REPO_ROOT))
        order_hash = hashlib.sha256(permutation_bytes(order)).hexdigest()
        expected_order_hash = order_doc.get("permutation_sha256")
        order_ok = (
            len(order) == order_doc.get("command_count") == 120
            and len(set(order)) == 120
            and set(order) == set(ids)
            and order_hash == expected_order_hash
            and order_hash == protocol.get("inference_order_permutation_sha256")
        )
        record("sealed_inference_permutation", order_ok, {
            "sha256": order_hash,
            "command_count": len(order),
        })

        runtime = load_yaml(repo_root / RUNTIME_MANIFEST_PATH.relative_to(REPO_ROOT))
        prompt = runtime["prompt"]
        schema = runtime["schema"]
        implementation = runtime["implementation"]
        system_path = repo_root / prompt["system_prompt_path"]
        few_shot_path = repo_root / prompt["few_shot_path"]
        system_bytes = system_path.read_bytes()
        few_shot_bytes = few_shot_path.read_bytes()
        prompt_evidence = {
            "system_prompt_sha256": sha256_bytes(system_bytes),
            "few_shot_sha256": sha256_bytes(few_shot_bytes),
            "combined_prompt_sha256": sha256_bytes(
                system_bytes + b"\n--PAPER-FEWSHOT--\n" + few_shot_bytes
            ),
        }
        prompt_ok = (
            prompt_evidence["system_prompt_sha256"]
            == prompt["system_prompt_sha256"]
            and prompt_evidence["few_shot_sha256"]
            == prompt["few_shot_sha256"]
            and prompt_evidence["combined_prompt_sha256"]
            == prompt["combined_prompt_sha256"]
        )
        record("frozen_prompt_and_few_shot_hashes", prompt_ok, prompt_evidence)

        code_evidence = {
            "candidate_schema_sha256": sha256_file(repo_root / schema["path"]),
            "candidate_parser_sha256": sha256_file(
                repo_root / implementation["parser_path"]
            ),
            "prompt_loader_sha256": sha256_file(
                repo_root / implementation["prompt_loader_path"]
            ),
        }
        code_ok = (
            code_evidence["candidate_schema_sha256"] == schema["sha256"]
            and code_evidence["candidate_parser_sha256"]
            == implementation["parser_sha256"]
            and code_evidence["prompt_loader_sha256"]
            == implementation["prompt_loader_sha256"]
        )
        record("frozen_schema_parser_and_loader_hashes", code_ok, code_evidence)

        lock_manifest_path = E1_DIR / "e1_client_environment_lock_v1.sha256"
        lock_manifest_path = repo_root / lock_manifest_path.relative_to(REPO_ROOT)
        declared_lock_hashes = {}
        for line in lock_manifest_path.read_text(encoding="utf-8").splitlines():
            digest, relative = line.split("  ", 1)
            declared_lock_hashes[relative] = digest
        lock_evidence = {
            relative: sha256_file(repo_root / relative)
            for relative in declared_lock_hashes
        }
        lock_ok = all(
            lock_evidence[path] == digest
            for path, digest in declared_lock_hashes.items()
        )
        record("sealed_client_environment_lock_hashes", lock_ok, lock_evidence)

        if verify_environment:
            lock_metadata_path = E1_DIR / "e1_client_environment_lock_v1.yaml"
            lock_metadata = load_yaml(
                repo_root / lock_metadata_path.relative_to(REPO_ROOT)
            )
            expected_runtime = lock_metadata["runtime"]
            package_groups = lock_metadata["direct_and_runtime_relevant_packages"]
            expected_packages = {
                name: str(version)
                for group in package_groups.values()
                if isinstance(group, dict)
                for name, version in group.items()
            }
            actual_packages = {}
            packages_ok = True
            for name, expected_version in expected_packages.items():
                try:
                    actual_version = importlib.metadata.version(name)
                except importlib.metadata.PackageNotFoundError:
                    actual_version = "missing"
                actual_packages[name] = actual_version
                packages_ok = packages_ok and actual_version == expected_version
            pip_version = importlib.metadata.version("pip")
            actual_freeze = subprocess.run(
                [sys.executable, "-m", "pip", "freeze"],
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=True,
            ).stdout.splitlines()
            lock_text_path = E1_DIR / "e1_client_environment_lock_v1.txt"
            expected_freeze = _locked_freeze(
                repo_root / lock_text_path.relative_to(REPO_ROOT)
            )
            environment_evidence = {
                "python_version": platform.python_version(),
                "pip_version": pip_version,
                "sys_prefix": str(Path(sys.prefix).resolve()),
                "packages": actual_packages,
                "complete_pip_freeze_matches": actual_freeze == expected_freeze,
            }
            environment_ok = (
                platform.python_version()
                == str(expected_runtime["python_exact_version"])
                and pip_version == str(expected_runtime["pip_exact_version"])
                and Path(sys.prefix).resolve()
                == Path(expected_runtime["virtual_environment"]).resolve()
                and packages_ok
                and actual_freeze == expected_freeze
            )
            record("active_client_environment_lock", environment_ok, environment_evidence)
            record(
                "real_provider_credential_present",
                bool(os.getenv("LLM_API_KEY")),
                {
                    "variable_name": "LLM_API_KEY",
                    "present": bool(os.getenv("LLM_API_KEY")),
                    "secret_value_read_or_recorded": False,
                },
            )

        package_root = repo_root / "location_allocate"
        if str(package_root) not in sys.path:
            sys.path.insert(0, str(package_root))
        from location_allocate import paper_candidate_parser as parser

        decoding = runtime["decoding"]
        provider = runtime["provider"]
        parser_path_ok = Path(parser.__file__).resolve() == (
            repo_root / implementation["parser_path"]
        ).resolve()
        model_ok = (
            parser_path_ok
            and parser.MODEL_NAME == provider["exact_model_name"]
            and parser.BASE_URL == provider["base_url"]
            and parser.TEMPERATURE == decoding["temperature"]
            and parser.TOP_P == decoding["top_p"]
            and runtime["retry_and_failure_policy"]["maximum_attempts"] == 3
            and runtime["retry_and_failure_policy"][
                "delay_between_failed_attempts_seconds"
            ] == 2
            and runtime["retry_and_failure_policy"][
                "timeout_per_attempt_seconds"
            ] == 60
            and decoding["max_tokens"] == 4000
            and decoding["response_format"] == {"type": "json_object"}
        )
        record("frozen_model_decoding_and_retry_configuration", model_ok, {
            "parser_path": str(Path(parser.__file__).resolve()),
            "model": parser.MODEL_NAME,
            "base_url": parser.BASE_URL,
            "temperature": parser.TEMPERATURE,
            "top_p": parser.TOP_P,
            "max_tokens": decoding["max_tokens"],
            "response_format": decoding["response_format"],
            "maximum_attempts": runtime["retry_and_failure_policy"][
                "maximum_attempts"
            ],
        })

        changed = _changed_paths(repo_root)
        scope_ok = all(path.startswith(FORMAL_PREFIX) for path in changed)
        record("production_runtime_tree_unchanged", scope_ok, {
            "changed_from_baseline": changed,
            "allowed_prefix": FORMAL_PREFIX,
        })
        exact_scope_ok = all(
            path in ALLOWED_BRANCH_PATHS
            or path.startswith(
                "experiments_v2/Formal Evaluation Experiments/E1/tooling/"
            )
            for path in changed
        )
        record("e1_branch_change_scope", exact_scope_ok, {
            "changed_from_baseline": changed,
            "sealed_source_paths": list(SEALED_SOURCE_PATHS),
            "tooling_prefix": (
                "experiments_v2/Formal Evaluation Experiments/E1/tooling/"
            ),
        })

        if require_clean:
            dirty = _git(repo_root, "status", "--porcelain=v1", "--untracked-files=all")
            record("clean_worktree", not dirty, {
                "dirty": bool(dirty),
                "entries": dirty.splitlines(),
            })
    except Exception as exc:
        if isinstance(exc, ProvenanceError):
            raise
        record("validator_internal_error", False, {
            "type": type(exc).__name__,
            "message": str(exc),
        })

    report = {
        "report_type": "E1_pre_run_provenance_validation_v1",
        "validated_at_utc": utc_now(),
        "source_final_preflight_commit": SOURCE_PREFLIGHT_COMMIT,
        "runtime_baseline_tag": BASELINE_TAG,
        "runtime_baseline_commit": BASELINE_COMMIT,
        "repo_root": str(repo_root),
        "status": "PASS" if all(
            check["status"] == "PASS" for check in checks
        ) else "FAIL",
        "checks": checks,
    }
    if report["status"] != "PASS":
        raise ProvenanceError(report)
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--allow-dirty-for-mock-validation",
        action="store_true",
        help="test-only: do not require a clean worktree",
    )
    parser.add_argument(
        "--skip-active-environment-check",
        action="store_true",
        help="test-only: validate lock artifacts but not the running interpreter",
    )
    args = parser.parse_args()
    try:
        report = validate_provenance(
            require_clean=not args.allow_dirty_for_mock_validation,
            verify_environment=not args.skip_active_environment_check,
        )
    except ProvenanceError as exc:
        print(json.dumps(exc.report, indent=2, ensure_ascii=False))
        return 1
    print(json.dumps(report, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
