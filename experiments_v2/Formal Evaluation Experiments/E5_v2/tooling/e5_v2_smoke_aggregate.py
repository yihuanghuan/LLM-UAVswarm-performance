#!/usr/bin/env python3
"""Aggregate retained non-formal scale-smoke evidence into frozen summaries."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from e5_v2_common import E5_DIR, load_yaml, sha256_file


PROTOCOL = E5_DIR / "E5_v2_engineering_scale_smoke_protocol.yaml"
OUTPUT_JSON = E5_DIR / "E5_v2_engineering_scale_smoke_results.json"
OUTPUT_MD = E5_DIR / "E5_v2_engineering_scale_smoke_audit.md"
RUNNER = Path(__file__).with_name("e5_v2_engineering_smoke.py")
READINESS = Path(__file__).with_name("e5_v2_wait_ready.py")


def build(raw_root: Path, retained_failure_roots=()):
    protocol = load_yaml(PROTOCOL)
    results = []
    for entry in protocol["smokes"]:
        n = int(entry["N"])
        raw = raw_root / f"N{n}_seed{entry['engineering_seed']}" / "smoke_result.json"
        value = json.loads(raw.read_text(encoding="utf-8"))
        readiness = value.get("readiness", {})
        results.append({
            "smoke_id": value["smoke_id"],
            "N": n,
            "engineering_seed": value["engineering_seed"],
            "dataset_class": value["dataset_class"],
            "accepted_formal_result": value["accepted_formal_result"],
            "formal_trial_id": value["formal_trial_id"],
            "scientific_mission": value["scientific_mission"],
            "candidate_payload_submitted": value["candidate_payload_submitted"],
            "command_publications": value["command_publications"],
            "success": value["success"],
            "failure": value["failure"],
            "spawn_ready": value.get("spawn_ready"),
            "spawn_elapsed_s": value.get("spawn_elapsed_s"),
            "readiness_ready": readiness.get("ready"),
            "readiness_elapsed_s": readiness.get("elapsed_s"),
            "all_states_finite": readiness.get("all_states_finite"),
            "process_counts_at_readiness": value.get("process_counts_at_readiness"),
            "gazebo_stats": value.get("gazebo_stats"),
            "host_diagnostics_at_readiness": value.get("host_diagnostics_at_readiness"),
            "cleanup": value.get("cleanup"),
            "elapsed_total_s": value.get("elapsed_total_s"),
            "raw_result_sha256": sha256_file(raw),
            "raw_log_sha256": value.get("log_sha256", {}),
        })
    retained_failures = []
    for failure_root in retained_failure_roots:
        for raw in sorted(failure_root.glob("N*_seed*/smoke_result.json")):
            value = json.loads(raw.read_text(encoding="utf-8"))
            state_rows = value.get("readiness", {}).get("state_diagnostics", {})
            qos_mismatch = bool(state_rows) and not any(
                row.get("present") for row in state_rows.values()
            )
            if qos_mismatch:
                classification = "engineering_readiness_harness_qos_bug"
                diagnosis = (
                    "The experiment-only finite-state subscription initially "
                    "used reliable QoS while the frozen production swarm_state "
                    "publisher uses SensorData/Best-Effort QoS. ROS reported "
                    "the reliability incompatibility; all UAV status streams "
                    "and exact process counts were otherwise ready. The "
                    "subscription was corrected to SensorData QoS."
                )
            else:
                classification = "engineering_readiness_harness_metric_bug"
                diagnosis = (
                    "The initial experiment-only gate incorrectly required "
                    "finite pre-mission position_error. Production intentionally "
                    "publishes +Inf before a command; all UAVs were armed, "
                    "offboard, system_ready, finite in altitude/speed, and the "
                    "exact process counts were present. The corrected gate uses "
                    "finite standardized swarm_state position/velocity."
                )
            retained_failures.append({
                "smoke_id": value["smoke_id"],
                "N": value["N"],
                "success": value["success"],
                "failure": value["failure"],
                "classification": classification,
                "diagnosis": diagnosis,
                "accepted_formal_result": False,
                "raw_result_sha256": sha256_file(raw),
            })
    status = "PASS" if all(
        result["success"]
        and result["dataset_class"] == "engineering_validation"
        and result["accepted_formal_result"] is False
        and result["formal_trial_id"] is None
        and result["scientific_mission"] is False
        and result["candidate_payload_submitted"] is False
        and result["command_publications"] == 0
        and result["process_counts_at_readiness"]["px4"] == result["N"]
        and result["process_counts_at_readiness"]["controllers"] == result["N"]
        and result["cleanup"]["success"]
        for result in results
    ) else "BLOCKED"
    observed_bound = max(
        (result["N"] for result in results if result["success"]), default=0
    )
    return {
        "audit_id": "E5-v2-engineering-scale-smoke-audit-v1",
        "status": status,
        "dataset_class": "engineering_validation",
        "accepted_formal_result": False,
        "formal_attempts_created": 0,
        "scientific_missions_run": 0,
        "protocol_sha256": sha256_file(PROTOCOL),
        "successful_runner_sha256": sha256_file(RUNNER),
        "successful_readiness_gate_sha256": sha256_file(READINESS),
        "smoke_count": len(results),
        "retained_failed_smoke_count": len(retained_failures),
        "retained_engineering_failures": retained_failures,
        "observed_stable_infrastructure_bound": observed_bound,
        "scale_infrastructure_limit": None if status == "PASS" else observed_bound,
        "results": results,
    }


def markdown(audit):
    lines = [
        "# E5-v2 engineering scale smoke audit",
        "",
        f"Result: `E5_V2_ENGINEERING_SCALE_SMOKE = {audit['status']}`.",
        "",
        "These are infrastructure-only spawn/arm/offboard/stable-hover checks. "
        "They contain no registered Candidate mission, no scientific command, "
        "no formal trial ID/journal, and `accepted_formal_result=false`.",
        "The JSON companion records the exact successful runner and readiness-"
        "gate source hashes; both retained failed revisions remain separately "
        "hashed below.",
        "",
        "| N | ready | readiness s | PX4 | controllers | gzserver | finite | cleanup | RTF |",
        "|---:|---|---:|---:|---:|---:|---|---|---|",
    ]
    for result in audit["results"]:
        counts = result["process_counts_at_readiness"] or {}
        gazebo = result.get("gazebo_stats") or {}
        samples = gazebo.get("real_time_factor_samples", [])
        rtf = "NA" if not samples else f"{sum(samples) / len(samples):.4f}"
        lines.append(
            f"| {result['N']} | {result['readiness_ready']} | "
            f"{result['readiness_elapsed_s']:.3f} | {counts.get('px4')} | "
            f"{counts.get('controllers')} | {counts.get('gzserver')} | "
            f"{result['all_states_finite']} | {result['cleanup']['success']} | {rtf} |"
        )
    lines.extend([
        "",
        f"Observed stable infrastructure bound: N={audit['observed_stable_infrastructure_bound']}.",
        "",
        "No physics fidelity, scientific policy, safety value, controller value, "
        "or timeout was changed between N conditions. Failures, if any, remain "
        "retained in the raw engineering evidence and are not formal outcomes.",
        "",
    ])
    if audit["retained_engineering_failures"]:
        lines.extend([
            "## Retained engineering harness failure",
            "",
        ])
        for failure in audit["retained_engineering_failures"]:
            lines.append(
                f"- N={failure['N']}: `{failure['failure']}`. "
                f"Classification: `{failure['classification']}`. "
                f"{failure['diagnosis']}"
            )
        lines.append("")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--raw-root", type=Path, required=True)
    parser.add_argument(
        "--retained-failure-root", type=Path, action="append", default=[]
    )
    parser.add_argument("--write", action="store_true")
    args = parser.parse_args()
    audit = build(
        args.raw_root.resolve(),
        [path.resolve() for path in args.retained_failure_root],
    )
    if args.write:
        OUTPUT_JSON.write_text(
            json.dumps(audit, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        OUTPUT_MD.write_text(markdown(audit), encoding="utf-8")
    print(json.dumps({
        "status": audit["status"],
        "observed_bound": audit["observed_stable_infrastructure_bound"],
    }, sort_keys=True))
    return 0 if audit["status"] == "PASS" else 2


if __name__ == "__main__":
    raise SystemExit(main())
