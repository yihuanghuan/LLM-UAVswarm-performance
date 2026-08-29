#!/usr/bin/env python3
"""Read-only final checks plus pristine Campaign-v2 formal-root initialization."""

from __future__ import annotations

import importlib.util
import hashlib
import json
import os
from pathlib import Path
import subprocess

from campaign_v2_common import (FORMAL_EVAL, FORMAL_ROOT, HERE, canonical_sha256,
                                exclusive_json, load_json, load_order, sha256_file,
                                validate_manifest)
from campaign_v2_coordinator import validate_runtime_environment, verify_pins


REPO_ROOT = FORMAL_EVAL.parents[1]
V1_RUNTIME_DEMO = FORMAL_EVAL / "formal_equivalent_demos/tooling/runtime_demo.py"
ANALYSIS_MANIFEST = FORMAL_EVAL / "analysis_freeze/formal_analysis_v1_bundle_manifest.json"
REHEARSAL = HERE / "results/synthetic-validation/campaign-v2-full-610-rehearsal-r3/rehearsal_summary.json"
PROVIDER = HERE / "provider_health_validation.json"


def command(args: list[str], cwd: Path | None = None) -> str:
    return subprocess.check_output(args, cwd=cwd, text=True).strip()


def output_even_if_nonzero(args: list[str], cwd: Path | None = None) -> str:
    result = subprocess.run(args, cwd=cwd, text=True, capture_output=True, check=False)
    return (result.stdout + result.stderr).strip()


def analysis_bundle_check() -> dict:
    manifest = load_json(ANALYSIS_MANIFEST)
    files = {path: sha256_file(REPO_ROOT / path) for path in manifest["files"]}
    actual = hashlib.sha256((json.dumps(files, ensure_ascii=False, allow_nan=False,
                                        sort_keys=True, separators=(",", ":")) + "\n").encode()).hexdigest()
    return {"status": "PASS" if files == manifest["files"] and actual == manifest["formal_analysis_v1_bundle_sha256"] else "FAIL",
            "file_count": len(files), "recomputed_bundle_sha256": actual,
            "expected_bundle_sha256": manifest["formal_analysis_v1_bundle_sha256"]}


def campaign_v1_guard() -> dict:
    spec = importlib.util.spec_from_file_location("campaign_v1_guard", V1_RUNTIME_DEMO)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module.assert_campaign_guard()


def remote_resolution() -> dict:
    branches = {
        "E2": ("formal/E2-formal-adapter-v1", "c361d21360252b4b6d24a615c421825b40ae1c59"),
        "E3": ("formal/E3-protocol-v3-active", "ae694047bf00933658847eef1a5cdc922ae17f6b"),
        "E4A": ("formal/E4A-formal-adapter-v1", "dcb053aded5ac4d4744f4b62f595ebdcb794962c"),
        "E4B": ("formal/E4B-formal-adapter-v1", "ec8895142d753bb7604d10a18f39d0aade64795c"),
        "E5": ("formal/E5-formal-adapter-v1", "31f36ef05224552dc9f5059bdf09f0c3bf82f115"),
        "analysis": ("formal/analysis-v1", "023bf48e521e3a6d2383da4699d8820dcf603da7"),
    }
    details = {}
    for name, (branch, expected) in branches.items():
        line = command(["git", "ls-remote", "origin", f"refs/heads/{branch}"], REPO_ROOT)
        actual = line.split()[0] if line else None
        details[name] = {"branch": branch, "remote_head": actual, "expected_remote_head": expected,
                         "status": "PASS" if actual == expected else "FAIL"}
    return {"status": "PASS" if all(x["status"] == "PASS" for x in details.values()) else "FAIL",
            "branches": details}


def initialize_pristine_formal_root(manifest_sha: str) -> dict:
    FORMAL_ROOT.mkdir(parents=True, exist_ok=True)
    launcher = FORMAL_ROOT / "launcher_run_manifest.json"
    payload = {
        "schema": "campaign_v2_pristine_formal_root_manifest_v1",
        "artifact_class": "formal_campaign_metadata", "campaign_id": "E2-E5-final-paper-campaign-v2",
        "campaign_manifest_sha256": manifest_sha, "formal_campaign_started": False,
        "retained_formal_attempts": 0, "journal_records": 0, "accepted_formal_results": 0,
        "next_global_position": 1, "next_trial_id": load_order()[0],
        "journal_is_cursor_authority": True, "formal_dispatch_authorized_in_this_phase": False,
    }
    if launcher.exists():
        if load_json(launcher) != payload:
            raise RuntimeError("existing Campaign-v2 formal-root metadata mismatch")
    else:
        exclusive_json(launcher, payload)
    forbidden = [FORMAL_ROOT / name for name in ("suite-journal", "attempt-artifacts", "adapter-attempts", "HUMAN_LAUNCH_TRIGGER.json")]
    state = {
        "schema": "campaign_v2_pristine_formal_root_state_v1", "status": "PASS" if not any(p.exists() for p in forbidden) else "FAIL",
        "retained_formal_attempts": 0, "journal_records": 0, "accepted_formal_results": 0,
        "next_global_position": 1, "next_trial_id": load_order()[0],
        "launcher_run_manifest_sha256": sha256_file(launcher),
        "pristine_root_fingerprint_sha256": canonical_sha256({"launcher_run_manifest.json": sha256_file(launcher)}),
        "human_launch_trigger_present": False,
    }
    state_path = FORMAL_ROOT / "pristine_root_state.json"
    if state_path.exists():
        if load_json(state_path) != state:
            raise RuntimeError("pristine formal-root state changed")
    else:
        exclusive_json(state_path, state)
    return state


def main() -> int:
    manifest = validate_manifest()
    manifest_sha = sha256_file(HERE / "campaign_v2_manifest.json")
    runtime = validate_runtime_environment(require_launch_environment=False)
    px4 = Path("/home/yihuang/PX4-Autopilot-formal-v1")
    simulator = {
        "px4_expected_overlay_status": command(["git", "status", "--short"], px4).splitlines(),
        "gazebo_overlay_status": command(["git", "status", "--short"], px4 / "Tools/simulation/gazebo-classic/sitl_gazebo-classic").splitlines(),
        "gazebo_version": output_even_if_nonzero(["gazebo", "--version"]).splitlines()[0],
    }
    simulator["status"] = "PASS" if (
        simulator["px4_expected_overlay_status"] == ["m Tools/simulation/gazebo-classic/sitl_gazebo-classic", " M Tools/simulation/gazebo-classic/sitl_multiple_run.sh"] and
        simulator["gazebo_overlay_status"] == ["M models/iris/iris.sdf.jinja"] and
        "11.10.2" in simulator["gazebo_version"]
    ) else "FAIL"
    checks = {
        "manifest": {"status": "PASS", "sha256": manifest_sha},
        "pins": verify_pins(), "runtime_environment": runtime, "simulator_overlays": simulator,
        "analysis_bundle": analysis_bundle_check(), "remote_resolution": remote_resolution(),
        "rehearsal": load_json(REHEARSAL), "provider": load_json(PROVIDER),
        "campaign_v1": campaign_v1_guard(),
        "formal_root": initialize_pristine_formal_root(manifest_sha),
    }
    statuses = [
        checks["pins"]["status"], checks["runtime_environment"]["status"], checks["simulator_overlays"]["status"],
        checks["analysis_bundle"]["status"], checks["remote_resolution"]["status"],
        checks["rehearsal"]["status"], checks["provider"]["status"], checks["campaign_v1"]["status"],
        checks["formal_root"]["status"],
    ]
    result = {
        "schema": "campaign_v2_final_preflight_evidence_v1", "campaign_id": manifest["campaign_id"],
        "status": "PASS" if all(x == "PASS" for x in statuses) else "FAIL",
        "checks": checks, "formal_attempt_dispatched": False, "formal_provider_call_performed": False,
        "physical_execution_performed": False, "blockers": [],
    }
    if result["status"] != "PASS":
        result["blockers"] = [name for name, value in checks.items() if isinstance(value, dict) and value.get("status") == "FAIL"]
    output = HERE / "campaign_v2_final_preflight_evidence.json"
    output.write_text(json.dumps(result, sort_keys=True, indent=2) + "\n")
    print(json.dumps({"status": result["status"], "blockers": result["blockers"]}, indent=2))
    return 0 if result["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
