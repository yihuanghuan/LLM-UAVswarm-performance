"""Deterministic E5-v2 activation identities and formal bundle helpers."""

from __future__ import annotations

import copy
import hashlib
import subprocess
from pathlib import Path
from typing import Any, Dict, Iterable, List

import yaml

from e5_v2_common import (
    E5_DIR,
    PRODUCTION_METHOD_PATHS,
    REGISTRY_PATH,
    REPO_ROOT,
    canonical_json_bytes,
    load_yaml,
    sha256_bytes,
    sha256_file,
)


ACTIVATION_MANIFEST_PATH = E5_DIR / "E5_v2_human_activation_manifest.yaml"
ACTIVATION_AUDIT_JSON_PATH = E5_DIR / "E5_v2_activation_audit.json"
ACTIVATION_AUDIT_MD_PATH = E5_DIR / "E5_v2_activation_audit.md"
CANDIDATE_COMMIT = "e2b0b3fe4ad93d81ae2477a7bc3e37ce1eb24377"
CANDIDATE_REGISTRY_SHA256 = (
    "7bc6b50de747753e09ca948e806c00961a0539804cff906df75308ff70b76567"
)


def scientific_registry_payload(registry: Dict[str, Any]) -> Dict[str, Any]:
    """Remove only top-level activation administration from a registry."""
    payload = copy.deepcopy(registry)
    payload.pop("status", None)
    payload.pop("activation", None)
    return payload


def scientific_payload_sha256(registry: Dict[str, Any]) -> str:
    """Hash canonical JSON for all non-activation registry content."""
    return sha256_bytes(canonical_json_bytes(scientific_registry_payload(registry)))


def registry_at_commit(commit: str) -> Dict[str, Any]:
    """Load the E5-v2 registry exactly as stored at a commit."""
    relative = REGISTRY_PATH.relative_to(REPO_ROOT).as_posix()
    content = subprocess.check_output(
        ["git", "show", f"{commit}:{relative}"], cwd=REPO_ROOT
    )
    value = yaml.safe_load(content)
    if not isinstance(value, dict):
        raise ValueError("committed registry must be a YAML mapping")
    return value


def _tracked_files(paths: Iterable[str]) -> List[Path]:
    output = subprocess.check_output(
        ["git", "ls-files", "--", *paths], cwd=REPO_ROOT, text=True
    )
    return [REPO_ROOT / value for value in output.splitlines()]


def formal_execution_bundle_files() -> List[Path]:
    """Return the repository files pinned for future formal execution.

    The bundle deliberately excludes engineering smoke tools and their evidence.
    It includes the sealed protocol inputs, the formal gate, and the complete
    tracked frozen production-method trees used by Candidate-to-control runtime.
    """
    experiment_files = [
        E5_DIR / "E5_v2_registry.yaml",
        ACTIVATION_MANIFEST_PATH,
        E5_DIR / "E5_v2_seed_registry.yaml",
        E5_DIR / "E5_v2_formal_trial_order.txt",
        E5_DIR / "E5_v2_analysis_contract.md",
        Path(__file__).with_name("e5_v2_common.py"),
        Path(__file__).with_name("e5_v2_activation_common.py"),
        Path(__file__).with_name("e5_v2_formal_adapter.py"),
    ]
    production_files = _tracked_files(PRODUCTION_METHOD_PATHS)
    files = sorted(set(experiment_files + production_files), key=lambda p: str(p))
    missing = [path for path in files if not path.is_file()]
    if missing:
        raise FileNotFoundError(f"formal bundle file missing: {missing}")
    smoke_names = {"e5_v2_engineering_smoke.py", "e5_v2_wait_ready.py"}
    if any(path.name in smoke_names for path in files):
        raise ValueError("engineering smoke tooling entered formal bundle")
    return files


def formal_execution_bundle() -> Dict[str, Any]:
    """Create a stable path/content digest for the formal source bundle."""
    records = []
    for path in formal_execution_bundle_files():
        records.append({
            "path": path.relative_to(REPO_ROOT).as_posix(),
            "sha256": sha256_file(path),
        })
    return {
        "algorithm": "sha256(canonical-json(sorted repo-relative path+sha256 records))",
        "file_count": len(records),
        "files": records,
        "sha256": hashlib.sha256(canonical_json_bytes(records)).hexdigest(),
        "engineering_smoke_tools_included": False,
    }


def candidate_scientific_payload_sha256() -> str:
    """Return the scientific identity of the human-reviewed candidate commit."""
    return scientific_payload_sha256(registry_at_commit(CANDIDATE_COMMIT))


def sealed_scientific_payload_sha256() -> str:
    """Return the scientific identity of the current sealed registry."""
    return scientific_payload_sha256(load_yaml(REGISTRY_PATH))
