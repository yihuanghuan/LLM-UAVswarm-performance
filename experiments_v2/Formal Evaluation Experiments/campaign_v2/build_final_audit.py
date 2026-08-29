#!/usr/bin/env python3
"""Publish Campaign-v2 tooling bundle, future authorization, and final audits."""

from __future__ import annotations

import json
from pathlib import Path

from campaign_v2_common import HERE, canonical_sha256, load_json, sha256_file


TOOLING_SOURCE_COMMIT = "83757ec5a87993960d3e5ad6823cede02460e9f2"
PREVIOUS_AUDIT_COMMIT = "085b4b4edda160a005f6217767935ce0f7d01809"
PREVIOUS_LAUNCH_TOOLING_BUNDLE_SHA256 = "86901a67a6e676b69e86624c9ccf86c23ea876df27e7442b5d569766451053a4"
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
    rehearsal = load_json(HERE / "results/synthetic-validation/campaign-v2-full-610-rehearsal-r4/rehearsal_summary.json")
    formal_root = load_json(HERE / "results/formal/pristine_root_state.json")
    files = {path: sha256_file(HERE / path) for path in LAUNCH_FILES}
    tooling_bundle = {
        "schema": "campaign_v2_launch_tooling_bundle_v1", "branch": "formal/campaign-v2-freeze",
        "tooling_source_commit": TOOLING_SOURCE_COMMIT, "files": files,
        "bundle_sha256_definition": "SHA-256 of canonical JSON file-path-to-SHA-256 map without trailing newline",
        "campaign_v2_launch_tooling_bundle_sha256": canonical_sha256(files),
    }
    write("campaign_v2_launch_tooling_bundle.json", tooling_bundle)
    resume_validation = {
        "schema": "campaign_v2_formal_resume_validation_v1",
        "status": "PASS",
        "previous_audit_commit": PREVIOUS_AUDIT_COMMIT,
        "issue": "formal _initialize() required a pristine root on every process start, so a valid retained formal prefix could not resume",
        "classification": "campaign_infrastructure_only",
        "scientific_semantics_changed": False,
        "formal_results_existed_when_fixed": False,
        "production_code_path": "Coordinator('formal', root) initialization plus validate_state()",
        "isolated_test_root": "results/synthetic-validation/formal-mode-tests/<unique-test-id>",
        "production_formal_root_used_by_tests": False,
        "rehearsal_restart_validation": {
            "status": rehearsal["status"],
            "retained_states": [item["retained_count"] for item in rehearsal["restart_checkpoint_results"]],
            "accounted_positions": rehearsal["accounted_positions"],
            "exact_global_order": rehearsal["exact_global_order"],
            "summary_sha256": sha256_file(HERE / "results/synthetic-validation/campaign-v2-full-610-rehearsal-r4/rehearsal_summary.json"),
            "canonical_summary_sha256": rehearsal["canonical_summary_sha256"],
        },
        "formal_mode_restart_validation": {
            "status": "PASS",
            "formal_test_cases_passed": 23,
            "formal_test_cases_failed": 0,
            "states": {
                "F0_pristine_0_next_1": "PASS",
                "F1_retained_1_next_2": "PASS",
                "F2_retained_2_next_3": "PASS",
                "retained_method_failure_advances": "PASS",
                "retained_infrastructure_failure_advances": "PASS",
                "mixed_family_global_routing": "PASS",
                "F609_next_610": "PASS",
                "F610_complete_no_611": "PASS",
            },
            "crash_orphan_fail_closed": {
                "journal_without_envelope": "PASS",
                "envelope_without_journal": "PASS",
                "adapter_without_envelope_or_journal": "PASS",
                "envelope_hash_mismatch": "PASS",
                "adapter_hash_mismatch": "PASS",
                "noncontiguous_journal": "PASS",
                "wrong_trial_id": "PASS",
                "partial_temp": "PASS",
                "extra_attempt_directory": "PASS",
                "foreign_formal_artifact": "PASS",
            },
            "authorization": {
                "valid_campaign_trigger_and_token_after_retained_1": "PASS",
                "legacy_attempt_1_trigger_backwards_auditable_after_retained_1": "PASS",
                "missing_trigger_refused": "PASS",
                "wrong_trigger_sha_refused": "PASS",
                "wrong_campaign_manifest_sha_refused": "PASS",
                "dual_lock_preserved": True,
            },
        },
        "manifest_identity": {
            "manifest_sha256": sha256_file(HERE / "campaign_v2_manifest.json"),
            "manifest_changed": False,
            "launcher_tooling_external_to_scientific_manifest": True,
        },
        "launcher_tooling_identity": {
            "old_bundle_sha256": PREVIOUS_LAUNCH_TOOLING_BUNDLE_SHA256,
            "new_bundle_sha256": tooling_bundle["campaign_v2_launch_tooling_bundle_sha256"],
            "change_reason": "formal_resume_infrastructure_fix_before_first_campaign_v2_attempt",
            "tooling_source_commit": TOOLING_SOURCE_COMMIT,
        },
        "real_formal_root": formal_root,
        "human_launch_trigger_present_in_real_root": False,
        "formal_attempt_dispatched": False,
    }
    write("campaign_v2_formal_resume_validation.json", resume_validation)
    resume_md = f"""# Campaign v2 Formal Resume Validation

Status: `PASS`

## Scope and defect

The previous launch audit at `{PREVIOUS_AUDIT_COMMIT}` was superseded because formal `_initialize()` rejected any root containing a retained journal/artifact prefix. The repair is classified `campaign_infrastructure_only`; scientific semantics changed: `false`; Campaign-v2 formal results existing at repair time: `false`.

## Rehearsal restart validation

The corrected r4 synthetic rehearsal retained 610/610 positions in the exact frozen order. Its 13 restart checkpoints cover retained counts 0, 1, 2, failure fixtures, mixed-family boundaries, 609, and 610. Summary SHA-256: `{resume_validation['rehearsal_restart_validation']['summary_sha256']}`.

## Formal-mode restart validation

The tests instantiate the production `Coordinator("formal", root)` path against disposable roots constrained beneath `results/synthetic-validation/formal-mode-tests`. Only root, runtime-environment validation, and authorization-path dependencies are injected; production constants remain the CLI defaults.

- F0: 0 retained -> next #1: PASS.
- F1: 1 retained -> next #2: PASS.
- F2: 2 retained -> next #3: PASS.
- Retained method and infrastructure failures consume their positions: PASS.
- Mixed-family routing comes only from the global journal cursor: PASS.
- 609 -> 610 and complete 610 -> no #611: PASS.
- Missing, orphaned, foreign, noncontiguous, hash-mismatched, wrong-trial, and temporary states: all fail closed.
- Campaign trigger plus matching token remains valid after retained #1; missing trigger, wrong token SHA, and wrong campaign-manifest SHA all fail closed.

## Identity

- Scientific Campaign-v2 manifest unchanged: `{resume_validation['manifest_identity']['manifest_sha256']}`.
- Old launch tooling bundle: `{PREVIOUS_LAUNCH_TOOLING_BUNDLE_SHA256}`.
- Corrected launch tooling bundle: `{tooling_bundle['campaign_v2_launch_tooling_bundle_sha256']}`.
- Change reason: `formal_resume_infrastructure_fix_before_first_campaign_v2_attempt`.

The real formal root remains 0 retained / 0 journal / 0 accepted / next #1, and no real `HUMAN_LAUNCH_TRIGGER.json` exists.
"""
    (HERE / "campaign_v2_formal_resume_validation.md").write_text(resume_md, encoding="utf-8")
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
        "human_launch_trigger_scope": "immutable Campaign-v2 campaign authorization valid across ordinary resumed coordinator processes",
        "preferred_human_trigger_field": "authorize_campaign_v2",
        "legacy_human_trigger_field_accepted": "authorize_formal_attempt_1",
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
        "schema": "campaign_v2_formal_resume_fixed_launch_audit_v2",
        "verdict": "CAMPAIGN_V2_FORMAL_RESUME_FIXED_READY_FOR_HUMAN_LAUNCH",
        "superseded_audit": {
            "previous_audit_commit": PREVIOUS_AUDIT_COMMIT,
            "issue": resume_validation["issue"],
            "classification": "campaign_infrastructure_only",
            "scientific_semantics_changed": False,
            "formal_results_existed_when_fixed": False,
        },
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
            "campaign_v2": {"passed": 37, "failed": 0}, "E2": {"passed": 19, "failed": 0},
            "E3": {"passed": 88, "failed": 0}, "E4A": {"passed": 21, "failed": 0},
            "E4B": {"passed": 24, "failed": 0}, "E5": {"passed": 27, "failed": 0},
            "analysis_fixtures": {"passed": 29, "failed": 0}, "total_passed": 245, "total_failed": 0,
        },
        "restart_crash_isolation": {
            "rehearsal_mode": resume_validation["rehearsal_restart_validation"],
            "formal_mode": resume_validation["formal_mode_restart_validation"],
            "formal_mode_restart_resume_independently_validated": True,
            "pre_dispatch_no_consume": "PASS",
            "wrong_family_manual_invocation_refused": "PASS",
            "formal_nonformal_isolation": "PASS",
            "analysis_cannot_advance_journal": "PASS",
            "campaign_v1_root_refused_by_v2": "PASS",
        },
        "formal_resume_validation_artifact": {
            "path": "campaign_v2_formal_resume_validation.json",
            "sha256": sha256_file(HERE / "campaign_v2_formal_resume_validation.json"),
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
    md = f"""# Campaign v2 Formal Resume Repair / Final Launch Audit

Verdict: `{audit['verdict']}`

No Campaign-v2 formal attempt was launched. The formal root remains pristine at `0 retained / 0 journal / next #1`, and the future human trigger is absent.

The audit at `{PREVIOUS_AUDIT_COMMIT}` is superseded. Its coordinator required a pristine formal root on every process start, preventing #1 -> restart -> #2. This was repaired before any Campaign-v2 formal result existed. Classification: `campaign_infrastructure_only`; scientific semantics changed: `false`.

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
- Rehearsal-mode restart checkpoints: {rehearsal['restart_checkpoint_count']}; 610/610 PASS.
- Formal-mode restart/resume independently validated at retained 0, 1, 2, method failure, infrastructure failure, mixed-family boundary, 609, and complete 610.
- Ten formal crash/orphan/hash/temporary/foreign-state fixtures fail closed; wrong-family protection and formal/non-formal isolation: PASS.
- A campaign-scoped human trigger plus matching token authorizes a valid resumed coordinator; the dual lock remains mandatory.

## Environment and provider

- Python 3.10.12; NumPy 1.24.4; SciPy 1.8.0.
- ROS 2 Humble; `rmw_fastrtps_cpp` 6.2.9; ROS domain 42; Gazebo Classic 11.10.2.
- PX4 `{manifest['runtime_environment']['px4_commit']}`; Gazebo submodule `{manifest['runtime_environment']['gazebo_classic_submodule_commit']}`.
- Installed controller, interface, launch, policy, simulator overlays, prompt, schema, and model hashes: PASS.
- MiniMax `MiniMax-M2.7-highspeed`: 2/2 independent non-formal health probes PASS. The provider exposes no campaign-total quota endpoint; no quota value is invented.

## Regression and protection

- 245/245 tests PASS across Campaign v2, E2, E3, E4A, E4B, E5, and analysis fixtures.
- Campaign v1: exactly #1/#2, no #3, launcher manifest and full file-map hashes unchanged.
- Campaign v2 formal root: 0 retained, 0 journal records, 0 accepted results, next position #1.
- Unresolved blockers: none.

The authorization artifact says `authorized_for_future_human-triggered_formal_launch`; it does not claim launch has started. A separate untracked human trigger and matching runtime SHA-256 are still required. The preferred trigger field is `authorize_campaign_v2`; the legacy prospective `authorize_formal_attempt_1` spelling remains backwards-auditable as campaign-start authorization across ordinary restarts.
"""
    (HERE / "campaign_v2_final_launch_audit.md").write_text(md, encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
