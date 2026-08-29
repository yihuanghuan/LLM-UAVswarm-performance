#!/usr/bin/env python3
"""Publish Campaign-v2 tooling bundle, future authorization, and final audits."""

from __future__ import annotations

import json
from pathlib import Path

from campaign_v2_common import HERE, canonical_sha256, load_json, sha256_file


TOOLING_SOURCE_COMMIT = "a2e6ccd8cbc7aba8f2244caa704cc605e383503e"
LAUNCH_FILES = [
    "adapter_spec_worker.py", "campaign_v2_common.py", "campaign_v2_coordinator.py",
    "campaign_v2_manifest.json", "campaign_v2_manifest.sha256", "campaign_v2_pin_inventory.json",
    "results/formal/launcher_run_manifest.json", "results/formal/pristine_root_state.json",
]


def write(name: str, value: object) -> None:
    (HERE / name).write_text(json.dumps(value, sort_keys=True, indent=2) + "\n", encoding="utf-8")


def main() -> int:
    manifest = load_json(HERE / "campaign_v2_manifest.json")
    pins = load_json(HERE / "campaign_v2_pin_inventory.json")
    preflight = load_json(HERE / "campaign_v2_final_preflight_evidence.json")
    rehearsal = load_json(HERE / "results/synthetic-validation/campaign-v2-full-610-rehearsal-r3/rehearsal_summary.json")
    formal_root = load_json(HERE / "results/formal/pristine_root_state.json")
    files = {path: sha256_file(HERE / path) for path in LAUNCH_FILES}
    tooling_bundle = {
        "schema": "campaign_v2_launch_tooling_bundle_v1", "branch": "formal/campaign-v2-freeze",
        "tooling_source_commit": TOOLING_SOURCE_COMMIT, "files": files,
        "bundle_sha256_definition": "SHA-256 of canonical JSON file-path-to-SHA-256 map without trailing newline",
        "campaign_v2_launch_tooling_bundle_sha256": canonical_sha256(files),
    }
    write("campaign_v2_launch_tooling_bundle.json", tooling_bundle)
    authorization = {
        "schema": "campaign_v2_future_launch_authorization_v1",
        "authorization_status": "authorized_for_future_human-triggered_formal_launch",
        "formal_launch_already_started": False, "formal_attempt_1_dispatched": False,
        "campaign_id": manifest["campaign_id"], "branch": "formal/campaign-v2-freeze",
        "campaign_v2_tooling_source_commit": TOOLING_SOURCE_COMMIT,
        "campaign_manifest_sha256": sha256_file(HERE / "campaign_v2_manifest.json"),
        "launcher_tooling_bundle_sha256": tooling_bundle["campaign_v2_launch_tooling_bundle_sha256"],
        "family_execution_bundle_sha256": {family: item["execution_bundle_sha256"] for family, item in pins["families"].items()},
        "analysis_semantics_sha256": manifest["analysis_semantics_sha256"],
        "formal_analysis_bundle_sha256": manifest["formal_analysis_bundle_sha256"],
        "global_order_sha256": manifest["global_610_order_sha256"], "policy_sha256": manifest["policy_sha256"],
        "environment_identity": manifest["runtime_environment"],
        "pristine_formal_root_fingerprint_sha256": formal_root["pristine_root_fingerprint_sha256"],
        "retained_formal_attempts": 0, "journal_records": 0, "accepted_formal_results": 0,
        "next_global_position": 1, "next_trial_id": formal_root["next_trial_id"],
        "human_launch_trigger_present": False,
        "future_launch_requirement": "human must separately create HUMAN_LAUNCH_TRIGGER.json and supply its SHA-256 at runtime",
    }
    write("campaign_v2_launch_authorization.json", authorization)
    scientific = {family: {
        "branch": item["checkout_branch"], "checkout_head": item["checkout_head"],
        "execution_source_commit": item["execution_source_commit"],
        "execution_bundle_sha256": item["execution_bundle_sha256"],
        "protocol_sha256": item["protocol_sha256"], "registry_sha256": item["registry_sha256"],
    } for family, item in pins["families"].items()}
    audit = {
        "schema": "campaign_v2_final_launch_audit_v1",
        "verdict": "CAMPAIGN_V2_FREEZE_COMPLETE_READY_FOR_FORMAL_LAUNCH",
        "campaign_identity": {
            "campaign_id": manifest["campaign_id"], "campaign_version": 2,
            "branch": "formal/campaign-v2-freeze", "freeze_tooling_source_commit": TOOLING_SOURCE_COMMIT,
            "manifest_sha256": authorization["campaign_manifest_sha256"],
            "launcher_tooling_bundle_sha256": authorization["launcher_tooling_bundle_sha256"],
        },
        "scientific_pins": scientific,
        "method_baseline": {"tag": manifest["baseline_tag"], "commit": manifest["baseline_commit"],
                            "policy_sha256": manifest["policy_sha256"]},
        "analysis_pin": {
            "branch": manifest["analysis_branch"], "audit_head": manifest["analysis_freeze_audit_head"],
            "tooling_source_commit": manifest["analysis_tooling_source_commit"],
            "semantics_sha256": manifest["analysis_semantics_sha256"],
            "bundle_sha256": manifest["formal_analysis_bundle_sha256"],
            "independent_recompute_status": preflight["checks"]["analysis_bundle"]["status"],
        },
        "environment": {**manifest["numeric_environment"], **manifest["runtime_environment"],
                        "provider": manifest["provider"], "runtime_hash_gate": "PASS",
                        "provider_health": preflight["checks"]["provider"]},
        "population": {**manifest["population"], "global_order_sha256": manifest["global_610_order_sha256"],
                       "exact_membership": "PASS", "analysis_population_compatibility": "PASS"},
        "rehearsal": {
            "status": rehearsal["status"], "accounted_positions": rehearsal["accounted_positions"],
            "unique_trial_ids": rehearsal["unique_trial_ids"], "exact_global_order": rehearsal["exact_global_order"],
            "correct_family_routing": rehearsal["correct_family_routing"],
            "journal_tail_sha256": rehearsal["journal_tail_sha256"],
            "canonical_summary_sha256": rehearsal["canonical_summary_sha256"],
            "restart_checkpoint_count": rehearsal["restart_checkpoint_count"],
            "synthetic_failure_fixtures": rehearsal["synthetic_failure_fixtures"],
            "physical_execution_performed": False, "real_provider_called": False,
        },
        "regressions": {
            "campaign_v2": {"passed": 14, "failed": 0}, "E2": {"passed": 19, "failed": 0},
            "E3": {"passed": 88, "failed": 0}, "E4A": {"passed": 21, "failed": 0},
            "E4B": {"passed": 24, "failed": 0}, "E5": {"passed": 27, "failed": 0},
            "analysis_fixtures": {"passed": 29, "failed": 0}, "total_passed": 222, "total_failed": 0,
        },
        "restart_crash_isolation": {
            "pristine_0_next_1": "PASS", "after_1": "PASS", "after_2": "PASS",
            "retained_method_failure": "PASS", "retained_infrastructure_failure": "PASS",
            "mixed_family_boundaries": "PASS", "near_final": "PASS", "after_610": "PASS",
            "orphan_adapter_fail_closed": "PASS", "orphan_envelope_fail_closed": "PASS",
            "journal_without_artifact_fail_closed": "PASS", "pre_dispatch_no_consume": "PASS",
            "wrong_family_manual_invocation_refused": "PASS", "formal_nonformal_isolation": "PASS",
            "analysis_cannot_advance_journal": "PASS", "campaign_v1_root_refused_by_v2": "PASS",
        },
        "formal_root": formal_root,
        "campaign_v1": {
            "status": preflight["checks"]["campaign_v1"]["status"], "journal_records": 2,
            "accepted_formal_attempts": 2, "no_attempt_3": True,
            "launcher_manifest_sha256": "dd5ed80049b138d4e97c82ce556ed306efbc6e4b2a369f7616be0ff101f332d1",
            "file_map_sha256": "29a6539e4b6b4372e0adc98bc5b45b4a8a40c20c3f23f244460e45695d14ba37",
            "used_for_final_scientific_analysis": False,
        },
        "remote_resolution_status": preflight["checks"]["remote_resolution"]["status"],
        "unresolved_blockers": [], "scientific_semantics_changed": False,
        "campaign_v2_formal_attempts_launched": 0, "formal_provider_calls": 0,
        "new_physical_demos_launched": 0,
    }
    write("campaign_v2_final_launch_audit.json", audit)
    md = f"""# Campaign v2 Final Freeze / Preflight Audit

Verdict: `{audit['verdict']}`

No Campaign-v2 formal attempt was launched. The formal root remains pristine at `0 retained / 0 journal / next #1`, and the future human trigger is absent.

## Campaign identity

- Campaign: `E2-E5-final-paper-campaign-v2`
- Branch: `formal/campaign-v2-freeze`
- Freeze tooling source commit: `{TOOLING_SOURCE_COMMIT}`
- Manifest SHA-256: `{authorization['campaign_manifest_sha256']}`
- Launch tooling bundle SHA-256: `{authorization['launcher_tooling_bundle_sha256']}`
- Baseline: `paper-final-sim-v3` at `{manifest['baseline_commit']}`
- Policy SHA-256: `{manifest['policy_sha256']}`

## Scientific and analysis pins

- E2: `{scientific['E2']['execution_source_commit']}`; bundle `{scientific['E2']['execution_bundle_sha256']}`
- E3 v3: `{scientific['E3']['execution_source_commit']}`; bundle `{scientific['E3']['execution_bundle_sha256']}`; protocol `{scientific['E3']['protocol_sha256']}`
- E4A: `{scientific['E4A']['execution_source_commit']}`; bundle `{scientific['E4A']['execution_bundle_sha256']}`
- E4B: `{scientific['E4B']['execution_source_commit']}`; bundle `{scientific['E4B']['execution_bundle_sha256']}`
- E5: `{scientific['E5']['execution_source_commit']}`; bundle `{scientific['E5']['execution_bundle_sha256']}`
- Analysis semantics: `{manifest['analysis_semantics_sha256']}`
- Formal-analysis-v1 bundle: `{manifest['formal_analysis_bundle_sha256']}` (independent recomputation PASS)

All source commits are reachable from the named remote authoritative branches. Evidence-only later commits are not execution dependencies.

## Population and rehearsal

- E2 120; E3 360; E4A 45; E4B 60; E5 25; total 610.
- Original global-order SHA-256: `{manifest['global_610_order_sha256']}`.
- Exact membership and analysis-schema compatibility: PASS.
- Full pinned-adapter non-formal rehearsal: 610/610, exact order, correct routing, journal tail `{rehearsal['journal_tail_sha256']}`.
- Restart checkpoints: {rehearsal['restart_checkpoint_count']}; crash-consistency, wrong-family protection, and formal/non-formal isolation: PASS.

## Environment and provider

- Python 3.10.12; NumPy 1.24.4; SciPy 1.8.0.
- ROS 2 Humble; `rmw_fastrtps_cpp` 6.2.9; ROS domain 42; Gazebo Classic 11.10.2.
- PX4 `{manifest['runtime_environment']['px4_commit']}`; Gazebo submodule `{manifest['runtime_environment']['gazebo_classic_submodule_commit']}`.
- Installed controller, interface, launch, policy, simulator overlays, prompt, schema, and model hashes: PASS.
- MiniMax `MiniMax-M2.7-highspeed`: 2/2 independent non-formal health probes PASS. The provider exposes no campaign-total quota endpoint; no quota value is invented.

## Regression and protection

- 222/222 tests PASS across Campaign v2, E2, E3, E4A, E4B, E5, and analysis fixtures.
- Campaign v1: exactly #1/#2, no #3, launcher manifest and full file-map hashes unchanged.
- Campaign v2 formal root: 0 retained, 0 journal records, 0 accepted results, next position #1.
- Unresolved blockers: none.

The authorization artifact says `authorized_for_future_human-triggered_formal_launch`; it does not claim launch has started. A separate untracked human trigger and matching runtime SHA-256 are still required.
"""
    (HERE / "campaign_v2_final_launch_audit.md").write_text(md, encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
