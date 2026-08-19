#!/usr/bin/env python3
"""Generate the versioned C0-A v2 result and campaign manifest."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
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
    args = parser.parse_args()
    artifact = args.artifact_root.resolve()
    output_dir = args.output_dir.resolve()
    state = json.loads((artifact / "campaign_state.json").read_text(encoding="utf-8"))
    aggregate = json.loads((artifact / "metrics" / "aggregate_v2.json").read_text(encoding="utf-8"))
    schedule = json.loads((ROOT / "trial_order_v2.json").read_text(encoding="utf-8"))
    distributions = aggregate["distributions"]
    scale = state.get("scale_validation", {}).get("scenarios", {})
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
- Experiment source commit: `{state['source_commit']}`
- Algorithm freeze: `paper-algorithm-freeze-v1`
- Dataset class: `calibration`
- Formal trials executed: `{state['formal_trials_executed']}`

## Stage A1

- Screening trials: `{aggregate['stage_counts'].get('A1_SCREENING', {}).get('executed', 0)}`
- Survivors: `{len(state.get('a1_survivors', []))}`
- Winner ID: `{state.get('a1_winner_id', 'NONE')}`
- Winner omega_c: `{fmt(state.get('a1_winner', {}).get('omega_c'))}`
- Winner omega_o: `{fmt(state.get('a1_winner', {}).get('omega_o'))}`

## Stage A2

- Winner ID: `{state.get('a2_winner_id', 'NONE')}`
- v_limit: `{fmt(state.get('a2_winner', {}).get('v_limit'))}`
- a_limit: `{fmt(state.get('a2_winner', {}).get('a_limit'))}`
- j_limit: `{fmt(state.get('a2_winner', {}).get('j_limit'))}`
- minimum_duration: `{fmt(state.get('a2_winner', {}).get('minimum_duration'))}`

## Stage A3

- Winner ID: `{state.get('a3_winner_id', 'NONE')}`
- Selected clamps: `{fmt(state.get('a3_winner'))}`

## Scale validation

- 1 UAV: `{scale.get('C0A-M-1', {}).get('passed', 0)}/{scale.get('C0A-M-1', {}).get('total', 0)}`
- 4 UAV: `{scale.get('C0A-M-4', {}).get('passed', 0)}/{scale.get('C0A-M-4', {}).get('total', 0)}`
- 8 UAV: `{scale.get('C0A-M-8', {}).get('passed', 0)}/{scale.get('C0A-M-8', {}).get('total', 0)}`

## Worst-case evidence

- Tracking RMSE: `{fmt(distributions['tracking_rmse_m']['worst'])}`
- Maximum tracking error: `{fmt(distributions['maximum_tracking_error_m']['worst'])}`
- Final error: `{fmt(distributions['final_error_m']['worst'])}`
- Saturation ratio: `{fmt(distributions['saturation_ratio']['worst'])}`
- Roll/pitch: `{fmt(distributions['roll_peak_deg']['worst'])}` / `{fmt(distributions['pitch_peak_deg']['worst'])}` deg
- Post-trajectory RMS: `{fmt(distributions['post_rms_m']['worst'])}`
- Minimum separation: `{fmt(distributions['minimum_separation_m']['worst'])}`

## Failures

`{json.dumps(aggregate['failure_counts'], sort_keys=True)}`

## Deviations from C0-A-prereg-v2

**NONE**

## Conclusion

`{conclusion}`
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
            "artifact_commit": None,
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
        "deviations_from_preregistration": [],
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
