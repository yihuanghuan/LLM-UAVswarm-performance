#!/usr/bin/env python3
"""Attempt identity, protocol hash gates, and common result envelopes."""

from __future__ import annotations

import hashlib
import json
import platform
from pathlib import Path
import sys
from typing import Any

import numpy as np
import scipy

from analysis_common import (ANALYSIS_VERSION, ProvenanceError, SEMANTICS_VERSION,
                             canonical_sha256, file_inventory, json_load, sha256_file)


TOOL_DIR = Path(__file__).resolve().parent
FREEZE_DIR = TOOL_DIR.parent
FORMAL_ROOT = FREEZE_DIR.parent
REPO_ROOT = FORMAL_ROOT.parents[1]
SEMANTICS_PATH = FREEZE_DIR / "analysis_semantics_v1.yaml"

DEPENDENCIES = {
    "E2": (
        FORMAL_ROOT / "protocols/E2_protocol_v1.yaml",
        FORMAL_ROOT / "E2/e2_scenario_registry_v1.yaml",
        "9ea7234db111b69cccb72315eed26e4abf117955eb20a2d593f2d854ea0b40e3",
        "8215a5d8248c946c480ca4c8cb41e2afac28e6021c9f308a068580da69369bae",
    ),
    "E3": (
        FORMAL_ROOT / "protocols/E3_protocol_v3.yaml",
        FORMAL_ROOT / "E3/e3_factorial_registry_v3.yaml",
        "2eea03e2bb33aa1c10c1ae104b965f909690f00c8caee4446291faf2c9893013",
        "b56344c6cd257e99851523d640d9a89d6def994884877e2303d8fab836e0faf2",
    ),
    "E4A": (
        FORMAL_ROOT / "protocols/E4_protocol_v1.yaml",
        FORMAL_ROOT / "E4/e4_motion_style_registry_v1.yaml",
        "5a7eeb923aebcfb068827c6513a37e856dc8d6f05166a4b84775b33572bd83d0",
        "48779a6667759955dd7dab2d8509f61a5439cca51a4bf98fcb48b6d17c499f95",
    ),
    "E4B": (
        FORMAL_ROOT / "protocols/E4_protocol_v1.yaml",
        FORMAL_ROOT / "E4/e4_motion_style_registry_v1.yaml",
        "5a7eeb923aebcfb068827c6513a37e856dc8d6f05166a4b84775b33572bd83d0",
        "48779a6667759955dd7dab2d8509f61a5439cca51a4bf98fcb48b6d17c499f95",
    ),
    "E5": (
        FORMAL_ROOT / "protocols/E5_protocol_v1.yaml",
        FORMAL_ROOT / "E5/e5_end_to_end_registry_v1.yaml",
        "116002154cd2395b6a9f55d7c1aae6e0a2c42440f0ceaa827a1a8cb02828319c",
        "9bb6bc9b46b5211c50c8f2e29bd434235424beb2bb0fc36ec857a3298d89511e",
    ),
}
POLICY_PATH = REPO_ROOT / "lfs_policy/config/lfs_policy.paper_current.yaml"
POLICY_SHA = "6b47d27f4253d7311e79ea51f6dd1cf0d0182e6df24374a94abae0aa6a135858"


def hash_gate(family: str) -> dict[str, str]:
    protocol, registry, expected_protocol, expected_registry = DEPENDENCIES[family]
    actual_protocol, actual_registry = sha256_file(protocol), sha256_file(registry)
    actual_policy = sha256_file(POLICY_PATH)
    if actual_protocol != expected_protocol or actual_registry != expected_registry:
        raise ProvenanceError(f"{family} authoritative protocol/registry hash mismatch")
    if actual_policy != POLICY_SHA:
        raise ProvenanceError("frozen policy hash mismatch")
    return {"protocol_sha256": actual_protocol, "registry_sha256": actual_registry,
            "policy_sha256": actual_policy}


def validate_attempt(attempt_dir: Path, family: str) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    attempt_dir = Path(attempt_dir).resolve()
    manifest = json_load(attempt_dir / "demo_manifest.json")
    if manifest.get("family") != family:
        raise ProvenanceError(f"expected {family}, got {manifest.get('family')}")
    required = {
        "dataset_class": "engineering_validation",
        "accepted_formal_result": False,
        "result_notice": "NOT_FORMAL_RESULT",
        "formal_cursor_consumed": False,
    }
    for key, expected in required.items():
        if manifest.get(key) != expected:
            raise ProvenanceError(f"non-formal dataset gate failed: {key}")
    if manifest.get("registered_trial_id") != manifest.get("execution_spec", {}).get("trial_id"):
        raise ProvenanceError("registered trial ID and exact execution spec disagree")
    provenance = manifest.get("runtime_provenance") or {}
    if provenance.get("status") != "PASS" or not manifest.get("same_backend_as_formal_adapter"):
        raise ProvenanceError("deployed runtime provenance did not pass")
    runtime_spec = json_load(attempt_dir / "raw/runtime_spec.json")
    if runtime_spec.get("trial_id") != manifest.get("registered_trial_id"):
        raise ProvenanceError("runtime spec trial identity mismatch")
    expected_spec_prefix = {"E3": "E3_", "E4A": "E4A_", "E4B": "E4B_", "E5": "E5_"}[family]
    if not str(runtime_spec.get("runtime_spec_type", "")).startswith(expected_spec_prefix):
        raise ProvenanceError("runtime spec type mismatch")
    hashes = hash_gate(family)
    installed_policy = provenance.get("installed_policy", {})
    if installed_policy.get("sha256") not in (None, POLICY_SHA):
        raise ProvenanceError("attempt installed policy identity mismatch")
    return manifest, runtime_spec, hashes


def tool_source_hash(path: Path) -> str:
    return sha256_file(path)


def result_envelope(attempt_dir: Path, family: str, extractor_path: Path,
                    manifest: dict[str, Any], dependencies: dict[str, str],
                    *, scored_interval: dict[str, Any] | None,
                    terminal_classification: str, analysis_status: str,
                    metrics: dict[str, Any], source_coverage: dict[str, Any],
                    raw_inventory: dict[str, str] | None = None) -> dict[str, Any]:
    attempt_dir = Path(attempt_dir).resolve()
    if raw_inventory is None:
        raw_inventory = file_inventory(attempt_dir)
    bag_files = {k: v for k, v in raw_inventory.items() if k.startswith("raw/rosbag/")}
    logs = {k: v for k, v in raw_inventory.items() if k.endswith(".log") or ".log." in k}
    semantics_hash = sha256_file(SEMANTICS_PATH)
    common_hash = sha256_file(TOOL_DIR / "analysis_common.py")
    extractor_hash = sha256_file(extractor_path)
    output = {
        "schema": "live_attempt_analysis_result_v1",
        "analysis_version": ANALYSIS_VERSION,
        "analysis_semantics_version": SEMANTICS_VERSION,
        "analysis_semantics_sha256": semantics_hash,
        "dataset_class": "engineering_validation",
        "accepted_formal_result": False,
        "scientific_use": "analysis_tool_validation_only",
        "result_notice": "NOT_FORMAL_RESULT",
        "experiment": family,
        "trial_id": manifest["registered_trial_id"],
        "demo_instance_id": manifest["demo_instance_id"],
        "raw_attempt_identity_sha256": canonical_sha256(raw_inventory),
        "raw_attempt_file_count": len(raw_inventory),
        "rosbag_identity_sha256": canonical_sha256(bag_files) if bag_files else None,
        "log_identity_sha256": canonical_sha256(logs) if logs else None,
        **dependencies,
        "extractor_source_sha256": extractor_hash,
        "common_numerical_utility_sha256": common_hash,
        "numeric_environment": {
            "python": platform.python_version(), "numpy": np.__version__, "scipy": scipy.__version__,
            "platform": platform.platform(), "byteorder": sys.byteorder,
        },
        "scored_interval": scored_interval,
        "source_coverage": source_coverage,
        "analysis_status": analysis_status,
        "terminal_attempt_classification": terminal_classification,
        "infrastructure_status": manifest.get("infrastructure_status"),
        "metrics": metrics,
    }
    output["canonical_result_sha256"] = canonical_sha256(output)
    return output


def terminal_classification(manifest: dict[str, Any]) -> str:
    scientific = manifest.get("scientific_outcome", {})
    backend = scientific.get("backend_terminal_status") or scientific.get("classification")
    if manifest.get("infrastructure_status") != "PASS":
        return "simulation_or_infrastructure_failure"
    return str(backend or "unknown")
