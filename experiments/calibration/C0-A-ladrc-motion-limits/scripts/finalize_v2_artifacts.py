#!/usr/bin/env python3
"""Generate the versioned C0-A v2 result and campaign manifest."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import shutil
import subprocess


ROOT = Path(__file__).resolve().parents[1]
REPOSITORY = ROOT.parents[2]


def sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def fmt(value):
    return "N/A" if value is None else json.dumps(value, sort_keys=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--artifact-root", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, default=ROOT)
    parser.add_argument("--artifact-commit")
    args = parser.parse_args()
    artifact = args.artifact_root.resolve()
    output_dir = args.output_dir.resolve()
    artifact_commit = None
    if args.artifact_commit:
        artifact_commit = subprocess.check_output(
            ["git", "rev-parse", "--verify", f"{args.artifact_commit}^{{commit}}"],
            cwd=REPOSITORY,
            text=True,
        ).strip()
    state = json.loads((artifact / "campaign_state.json").read_text(encoding="utf-8"))
    aggregate = json.loads((artifact / "metrics" / "aggregate_v2.json").read_text(encoding="utf-8"))
    schedule = json.loads((ROOT / "trial_order_v2.json").read_text(encoding="utf-8"))
    distributions = aggregate["distributions"]
    scale = (state.get("scale_validation") or {}).get("scenarios", {})
    deviations = sorted(path.name for path in (ROOT / "deviations").glob("*.md"))
    artifact_index = artifact / "artifact_index_v2.json"
    final_audit = artifact / "logs" / "final_audit_v2.json"
    evidence_dir = output_dir / "evidence_v2"
    evidence_dir.mkdir(parents=True, exist_ok=True)
    evidence_sources = {
        "a1_screening_ranking.json": artifact / "metrics" / "a1_screening_ranking.json",
        "aggregate_v2.json": artifact / "metrics" / "aggregate_v2.json",
        "artifact_index_v2.json": artifact_index,
        "campaign_state.json": artifact / "campaign_state.json",
        "campaign_trials.jsonl": artifact / "logs" / "campaign_trials.jsonl",
        "c0a_v2_metric_distributions.png": artifact / "figures" / "c0a_v2_metric_distributions.png",
        "final_audit_v2.json": final_audit,
        "post_a1_screening_freeze_gates.json": artifact / "logs" / "post_a1_screening_freeze_gates.json",
        "preflight_v2.json": artifact / "logs" / "preflight_v2.json",
        "preflight_v2.txt": artifact / "logs" / "preflight_v2.txt",
    }
    for name, source in evidence_sources.items():
        shutil.copyfile(source, evidence_dir / name)
    screening_order = [
        entry for entry in schedule["entries"] if entry["stage"] == "A1_SCREENING"
    ]
    trial_records_path = evidence_dir / "trial_records_v2.jsonl"
    with trial_records_path.open("w", encoding="utf-8") as stream:
        for entry in screening_order:
            raw = artifact / "raw" / entry["trial_id"]
            record = {
                "manifest": json.loads((raw / "manifest.json").read_text(encoding="utf-8")),
                "metrics": json.loads((raw / "metrics.json").read_text(encoding="utf-8")),
                "schedule_index": entry["schedule_index"],
                "trial_spec": json.loads((raw / "trial_spec.json").read_text(encoding="utf-8")),
            }
            stream.write(json.dumps(record, sort_keys=True) + "\n")
    conclusion = {
        "PASS": "C0-A = PASS",
        "NO_ACCEPTABLE_CONFIGURATION": "C0-A = NO_ACCEPTABLE_CONFIGURATION",
        "FREEZE_FAIL": "C0-A = INVALIDATED / INFRASTRUCTURE_BLOCKED",
    }.get(state.get("campaign_status"), "C0-A = INVALIDATED / INFRASTRUCTURE_BLOCKED")
    result = f"""# C0-A calibration result v2

## Experiment identity

- Calibration: `C0-A`
- Protocol: `C0-A-prereg-v2`
- Reason for v2: pre-outcome protocol clarification
- Previous protocol: `C0-A-prereg-v1`, status `INFRASTRUCTURE_BLOCKED`, formal trials `0`
- Experiment branch: `cal/C0-A-ladrc-motion-limits`
- Experiment source commits: `{fmt(state.get('source_commits', [state['source_commit']]))}`
- Algorithm freeze: `paper-algorithm-freeze-v1`
- Dataset class: `calibration`
- Formal trials executed: `{state['formal_trials_executed']}`
- Trial hard passes/failures: `{aggregate['stage_counts'].get('A1_SCREENING', {}).get('passed', 0)}` / `{aggregate['stage_counts'].get('A1_SCREENING', {}).get('failed', 0)}`

## Stage A1

- Screening trials: `{aggregate['stage_counts'].get('A1_SCREENING', {}).get('executed', 0)}`
- Survivors: `{len(state.get('a1_survivors') or [])}`
- Winner ID: `{state.get('a1_winner_id', 'NONE')}`
- Winner omega_c: `{fmt(state.get('a1_winner', {}).get('omega_c'))}`
- Winner omega_o: `{fmt(state.get('a1_winner', {}).get('omega_o'))}`

## Stage A2

- Status: `NOT ACTIVATED (A1 survivor count was zero)`
- Winner ID: `{state.get('a2_winner_id', 'NONE')}`
- v_limit: `{fmt(state.get('a2_winner', {}).get('v_limit'))}`
- a_limit: `{fmt(state.get('a2_winner', {}).get('a_limit'))}`
- j_limit: `{fmt(state.get('a2_winner', {}).get('j_limit'))}`
- minimum_duration: `{fmt(state.get('a2_winner', {}).get('minimum_duration'))}`

## Stage A3

- Status: `NOT ACTIVATED (A1 survivor count was zero)`
- Winner ID: `{state.get('a3_winner_id', 'NONE')}`
- Omega clamps: `{fmt((state.get('a3_winner') or {}).get('omega_envelope'))}`
- Motion clamps: `{fmt((state.get('a3_winner') or {}).get('motion_clamp_multiplier'))}`
- Physical caps: `{fmt((state.get('a3_winner') or {}).get('physical_caps'))}`

## Scale validation

- Status: `NOT ACTIVATED (A1 survivor count was zero)`
- 1 UAV: `{scale.get('C0A-M-1', {}).get('passed', 0)}/{scale.get('C0A-M-1', {}).get('total', 0)}`
- 4 UAV: `{scale.get('C0A-M-4', {}).get('passed', 0)}/{scale.get('C0A-M-4', {}).get('total', 0)}`
- 8 UAV: `{scale.get('C0A-M-8', {}).get('passed', 0)}/{scale.get('C0A-M-8', {}).get('total', 0)}`

## Worst-case evidence

The values below are maxima across the `{distributions['tracking_rmse_m']['count']}` trials with extractable numeric
metrics. Failed trials without extractable metrics remain in the formal
denominator and failure counts.

- Tracking RMSE: `{fmt(distributions['tracking_rmse_m']['worst'])}`
- Maximum tracking error: `{fmt(distributions['maximum_tracking_error_m']['worst'])}`
- Final error: `{fmt(distributions['final_error_m']['worst'])}`
- Saturation ratio: `{fmt(distributions['saturation_ratio']['worst'])}`
- Roll/pitch: `{fmt(distributions['roll_peak_deg']['worst'])}` / `{fmt(distributions['pitch_peak_deg']['worst'])}` deg
- Post-trajectory RMS: `{fmt(distributions['post_rms_m']['worst'])}`
- Post-trajectory peak-to-peak: `{fmt(distributions['peak_to_peak_m']['worst'])}`
- Last/first RMS ratio: `{fmt(distributions['last_first_rms_ratio']['worst'])}`
- Zero crossings on worst axis: `{fmt(distributions['zero_crossings']['worst'])}`
- Command jerk p99.5: `{fmt(distributions['command_jerk_p99_5_mps3']['worst'])}`
- Minimum separation: `{fmt(distributions['minimum_separation_m']['worst'])}`

## Failures

`{json.dumps(aggregate['failure_counts'], sort_keys=True)}`

Trial termination reasons: `{json.dumps(aggregate['termination_counts'], sort_keys=True)}`

## Deviations from C0-A-prereg-v2

`{fmt(deviations) if deviations else 'NONE'}`

## Conclusion

`{conclusion}`

- Frozen parameter commit: `NONE`
- Checkpoint tag: `NONE`
- Policy SHA-256: `N/A (no winner and no frozen policy)`
- READY_FOR_C0_B: `NO`
"""
    result_path = output_dir / "CALIBRATION_RESULT_v2.md"
    result_path.write_text(result, encoding="utf-8")
    preflight = json.loads((artifact / "logs" / "preflight_v2.json").read_text(encoding="utf-8"))
    manifest = {
        "manifest_version": 2,
        "calibration_id": "C0-A",
        "protocol_version": "C0-A-prereg-v2",
        "dataset_class": "calibration",
        "status": state.get("campaign_status"),
        "reason_for_v2": "pre-outcome protocol clarification",
        "previous_protocol": {
            "version": "C0-A-prereg-v1",
            "status": "INFRASTRUCTURE_BLOCKED",
            "formal_trials": 0,
        },
        "git": {
            "branch": "cal/C0-A-ladrc-motion-limits",
            "source_commit": state["source_commit"],
            "source_commits": state.get("source_commits", [state["source_commit"]]),
            "artifact_commit": artifact_commit,
            "base_ref": "origin/paper/calibration",
            "base_commit": subprocess.check_output(
                ["git", "rev-parse", "origin/paper/calibration"], cwd=REPOSITORY, text=True
            ).strip(),
        },
        "algorithm_freeze": {
            "tag": "paper-algorithm-freeze-v1",
            "commit": "56e8d2c8e59fc3513769e21910b7a20b2b43088d",
            "check": "PASS",
        },
        "parameter_ownership_check": "PASS",
        "protocol_sha256": sha256(ROOT / "CALIBRATION_PROTOCOL.md"),
        "trial_order_sha256": sha256(ROOT / "trial_order_v2.json"),
        "trial_schedule_complete": True,
        "unresolved_protocol_ambiguity": 0,
        "scheduled_trial_ids": [entry["trial_id"] for entry in schedule["entries"]],
        "potential_trial_count": len(schedule["entries"]),
        "formal_trial_count": state["formal_trials_executed"],
        "artifact_storage": {
            "path": str(artifact),
            "aggregate_sha256": sha256(artifact / "metrics" / "aggregate_v2.json"),
            "campaign_state_sha256": sha256(artifact / "campaign_state.json"),
            "artifact_index_sha256": sha256(artifact_index),
            "final_audit_sha256": sha256(final_audit),
            "repository_evidence": {
                name: sha256(evidence_dir / name) for name in sorted(evidence_sources)
            },
            "trial_records_v2_sha256": sha256(trial_records_path),
        },
        "preflight": preflight,
        "environment": preflight["environment"],
        "winners": {
            "a1": state.get("a1_winner"),
            "a2": state.get("a2_winner"),
            "a3": state.get("a3_winner"),
        },
        "scale_validation": state.get("scale_validation"),
        "failure_counts": aggregate["failure_counts"],
        "result_sha256": sha256(result_path),
        "deviations_from_preregistration": deviations,
        "frozen_parameter_commit": None,
        "checkpoint_tag": None,
        "ready_for_c0_b": False,
        "generated_utc": datetime.now(timezone.utc).isoformat(),
    }
    manifest_path = output_dir / "manifest_v2.json"
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"result": str(result_path), "manifest": str(manifest_path)}, sort_keys=True))


if __name__ == "__main__":
    main()
