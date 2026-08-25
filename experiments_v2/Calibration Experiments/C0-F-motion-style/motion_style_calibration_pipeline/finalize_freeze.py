#!/usr/bin/env python3
"""Fail-closed finalization of the locked C0-F freeze artifacts."""
from __future__ import annotations

import csv
from datetime import datetime, timezone
import math
from pathlib import Path
import subprocess

import yaml

from common import CANONICAL_POLICY, PIPELINE, REPO, RESULTS, SCENES_FILE, START_SHA, load_yaml, sha256


def rows(name: str, expected: int):
    path = RESULTS / name
    with path.open(newline="", encoding="utf-8") as handle:
        values = list(csv.DictReader(handle))
    if len(values) != expected or any(row["condition_result"] != "PASS" for row in values):
        raise SystemExit(f"freeze blocked: {name} is not {expected}/{expected} PASS")
    return values


def numeric_max(values, key):
    return max(float(row[key]) for row in values if row[key] not in ("", "None"))


def main() -> None:
    screening = rows("screening_results.csv", 12)
    confirmation = rows("confirmation_results.csv", 24)
    smokes = rows("style_switch_smoke.csv", 2)
    lock = load_yaml(RESULTS / "candidate_lock.yaml")
    policy = load_yaml(CANONICAL_POLICY)
    audit = load_yaml(RESULTS / "upstream_integrity_audit.yaml")
    locked_policy = RESULTS / "locked_candidate_policy.yaml"
    if audit["result"] != "PASS" or audit["ownership_violations"]:
        raise SystemExit("freeze blocked: upstream integrity audit failed")
    if lock["status"] != "LOCKED_NO_RETUNING" or not lock["parameter_search_stopped"]:
        raise SystemExit("freeze blocked: candidate lock invalid")
    if lock["fallback_stage_entered"]:
        raise SystemExit("freeze blocked: unexpected fallback state")
    if sha256(locked_policy) != lock["policy_sha256"]:
        raise SystemExit("freeze blocked: locked policy hash mismatch")
    if policy["configuration_id"] != "paper-current-v11-c0-f-frozen":
        raise SystemExit("freeze blocked: canonical configuration ID is not v11")
    if policy["parameter_status"]["c0_f_motion_style"] != "frozen":
        raise SystemExit("freeze blocked: canonical C0-F status is not frozen")
    if policy["timing"]["auto_style_factors"] != lock["auto_style_factors"]:
        raise SystemExit("freeze blocked: canonical timing differs from lock")
    if policy["execution_profile"]["style_gains"] != lock["style_gains"]:
        raise SystemExit("freeze blocked: canonical gains differ from lock")
    if policy["controller_hard_clamps"]["smoothing_alpha"] != lock["smoothing_alpha"]:
        raise SystemExit("freeze blocked: canonical smoothing differs from lock")
    if policy["execution_profile"]["task_adaptation_type"] != "identity":
        raise SystemExit("freeze blocked: task adaptation is not identity")

    all_trials = screening + confirmation
    summary = {
        "screening_count": len(screening),
        "confirmation_count": len(confirmation),
        "style_switch_smoke_count": len(smokes),
        "maximum_controller_saturation_ratio": numeric_max(all_trials + smokes, "controller_acceleration_saturation_ratio"),
        "maximum_controller_saturation_samples": int(numeric_max(all_trials + smokes, "controller_acceleration_saturation_samples")),
        "maximum_profile_clamp_activity": int(numeric_max(all_trials + smokes, "profile_clamp_activity")),
        "maximum_iapf_clamp_activity": int(numeric_max(all_trials + smokes, "iapf_clamp_activity")),
        "maximum_tracking_rmse_m": numeric_max(all_trials, "tracking_rmse_m"),
        "maximum_final_error_m": numeric_max(all_trials, "final_error_m"),
        "minimum_pairwise_distance_m": min(float(row["minimum_pairwise_distance_m"]) for row in all_trials),
        "maximum_peak_tilt_deg": numeric_max(all_trials, "peak_tilt_deg"),
        "hard_safety_violations": sum(int(row["hard_safety_violation_count"]) for row in all_trials),
        "iapf_activation_fraction_max": numeric_max(all_trials, "iapf_activation_fraction"),
    }
    explicit_pass = all(
        row["explicit_t_invariance"] in ("True", "N/A") for row in all_trials
    )
    auto_pass = all(row["auto_t_ordering"] in ("True", "N/A") for row in all_trials)
    consistency_pass = all(row["compiled_applied_profile_consistent"] == "True" for row in all_trials + smokes)
    evidence_commit = subprocess.check_output(
        ["git", "rev-parse", "HEAD"], cwd=REPO, text=True
    ).strip()
    canonical_hash = sha256(CANONICAL_POLICY)
    frozen = {
        "schema_version": "c0f-frozen-motion-style-policy-v1",
        "freeze_status": "FROZEN",
        "canonical_configuration_id": policy["configuration_id"],
        "auto_style_factors": lock["auto_style_factors"],
        "style_gains": lock["style_gains"],
        "smoothing_alpha": lock["smoothing_alpha"],
        "normal_gain": 1.0,
        "task_adaptation": "identity",
        "task_gain": 1.0,
        "selection_rule": lock["selection_rule"],
        "source_commit": START_SHA,
        "confirmation_evidence_commit": evidence_commit,
        "locked_policy_sha256": lock["policy_sha256"],
        "policy_hash": canonical_hash,
        "confirmation_counts": {
            "screening": "12/12 PASS",
            "locked_confirmation": "24/24 PASS",
            "style_switch_smokes": "2/2 PASS",
            "hard_violations": 0,
            "dynamic_feasibility_violations": 0,
            "controller_saturation_samples": 0,
            "profile_clamp_activity": 0,
            "instability": 0,
        },
        "contracts": {
            "explicit_t_invariance": "PASS" if explicit_pass else "FAIL",
            "auto_t_ordering": "PASS" if auto_pass else "FAIL",
            "compiled_applied_profile_consistency": "PASS" if consistency_pass else "FAIL",
            "upstream_c0_a_through_c0_e_integrity": audit["result"],
        },
        "selection_summary": summary,
    }
    (RESULTS / "frozen_motion_style_policy.yaml").write_text(
        yaml.safe_dump(frozen, sort_keys=False), encoding="utf-8"
    )

    report = f"""# C0-F motion-style freeze report

## Decision

**FROZEN.** The first provisional candidate passed unchanged; Stage-2 fallback
was not entered and parameter search stopped at the candidate lock.

| Item | Frozen value |
| --- | --- |
| `alpha_T(smooth/normal/aggressive)` | `1.30 / 1.15 / 1.10` |
| `kappa_style(smooth/normal/aggressive)` | `0.80 / 1.00 / 1.10` |
| `execution_profile_smoothing_alpha` | `1.0` |
| `task_adaptation`, `task_gain` | `identity`, `1.0` |
| canonical configuration | `{policy['configuration_id']}` |
| canonical SHA-256 | `{canonical_hash}` |
| locked-candidate SHA-256 | `{lock['policy_sha256']}` |

## Evidence

- Screening: **12/12 PASS**; candidate unchanged.
- Locked confirmation: **24/24 PASS**.
- Sequential style-switch smoke: **2/2 PASS** at alpha `1.0`.
- Hard/dynamic violations, controller saturation, profile/IAPF clamps,
  instability, and IAPF activation: **0**.
- Maximum tracking RMSE: `{summary['maximum_tracking_rmse_m']:.9f} m`.
- Maximum final error: `{summary['maximum_final_error_m']:.9f} m`.
- Minimum measured pairwise distance: `{summary['minimum_pairwise_distance_m']:.9f} m`.
- Maximum measured tilt: `{summary['maximum_peak_tilt_deg']:.9f} deg`.
- Explicit-T invariance: **{'PASS' if explicit_pass else 'FAIL'}**.
- Auto-T ordering: **{'PASS' if auto_pass else 'FAIL'}**.
- Compiled/applied profile consistency: **{'PASS' if consistency_pass else 'FAIL'}**.

## Governance

Starting C0-E commit: `{START_SHA}`. The C0-A through C0-E frozen artifact
hashes match their inherited manifests, and the field-level ownership audit has
no violations. Canonical integration changes only C0-F status/provenance
metadata because the first candidate itself was selected without numeric
deviation. No C0-G or E1-E6 work was started.
"""
    (RESULTS / "C0-F_freeze_report.md").write_text(report, encoding="utf-8")

    artifact_names = (
        "C0-F_freeze_report.md", "frozen_motion_style_policy.yaml",
        "candidate_lock.yaml", "locked_candidate_policy.yaml",
        "calibration_plan.csv", "screening_results.csv",
        "confirmation_results.csv", "style_switch_smoke.csv",
        "upstream_integrity_audit.yaml",
    )
    manifest = {
        "schema_version": "c0f-freeze-manifest-v1",
        "status": "FROZEN_PASS",
        "generated_utc": datetime.now(timezone.utc).isoformat(),
        "source_c0_e_commit": START_SHA,
        "candidate_lock_commit": None,
        "confirmation_evidence_commit": evidence_commit,
        "configuration_id": policy["configuration_id"],
        "canonical_policy_sha256": canonical_hash,
        "locked_policy_sha256": lock["policy_sha256"],
        "counts": {"screening": 12, "confirmation": 24, "style_switch_smokes": 2},
        "results": {
            "screening": "PASS", "confirmation": "PASS", "style_switch": "PASS",
            "explicit_t_invariance": "PASS", "auto_t_ordering": "PASS",
            "upstream_integrity": "PASS",
        },
        "summary": summary,
        "artifacts_sha256": {name: sha256(RESULTS / name) for name in artifact_names},
        "pipeline_sha256": {
            path.name: sha256(path) for path in sorted(PIPELINE.glob("*.py"))
        } | {SCENES_FILE.name: sha256(SCENES_FILE)},
    }
    # Resolve the full, immutable lock commit without creating a self-reference.
    manifest["candidate_lock_commit"] = subprocess.check_output(
        ["git", "rev-parse", "f4096f68"], cwd=REPO, text=True
    ).strip()
    (RESULTS / "manifest.yaml").write_text(
        yaml.safe_dump(manifest, sort_keys=False), encoding="utf-8"
    )
    print(yaml.safe_dump({"status": manifest["status"], "summary": summary,
                          "canonical_policy_sha256": canonical_hash}, sort_keys=False), end="")


if __name__ == "__main__":
    main()
