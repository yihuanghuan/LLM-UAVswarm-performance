#!/usr/bin/env python3
"""Deterministically freeze profile-v2 accounting and governance audits."""

from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path


HERE = Path(__file__).resolve()
V2 = HERE.parents[1]
REPO = HERE.parents[4]
BASE = "adf56c7256ccb7f3e63d78ec2ffb254d1f88b647"
PROFILE = V2 / "infrastructure_profile_v2.yaml"
N24_RESULT = V2 / "results/N24/result.json"
POLICY = REPO / "lfs_policy/config/lfs_policy.paper_current.yaml"
CONTROLLER = REPO / "minisnap_LADRC/ladrc_controller/src/ladrc_position_controller_node.cpp"


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def changed_paths() -> list[str]:
    tracked = subprocess.check_output(["git", "diff", "--name-only", BASE], cwd=REPO, text=True).splitlines()
    untracked = subprocess.check_output(["git", "ls-files", "--others", "--exclude-standard"], cwd=REPO, text=True).splitlines()
    return sorted(set(tracked + untracked))


def main() -> int:
    result = load(N24_RESULT)
    profile_sha = sha(PROFILE)
    records = result["px4_writer_gate_records"]
    prefix = "experiments_v2/Supplementary Large Swarm Demonstration/infrastructure_diagnostics_v2/"
    paths = changed_paths()
    confined = bool(paths) and all(path.startswith(prefix) for path in paths)
    profile_results = {
        "schema": "large_swarm_profile_v2_results",
        "dataset_class": "supplementary_infrastructure_diagnostic",
        "accepted_formal_result": False,
        "profile_v2_sha256": profile_sha,
        "conditional_order": [24, 28, 32],
        "stop_at_first_failure": True,
        "results": {
            "24": {
                "status": "PASS" if result["success"] else "FAIL",
                "stage_A_px4_xrce_writer_gate": "PASS" if result["stage_A_success"] else "FAIL",
                "px4_writer_gate_count": len(records),
                "px4_writer_gate_elapsed_s_min": min(record["elapsed_s"] for record in records),
                "px4_writer_gate_elapsed_s_max": max(record["elapsed_s"] for record in records),
                "px4_processes": result["process_counts_at_readiness"]["px4"],
                "controller_processes": result["process_counts_at_readiness"]["controllers"],
                "armed_offboard": result["armed_offboard_count"],
                "fresh_states": result["fresh_state_count"],
                "all_states_finite": result["all_states_finite"],
                "failsafe_at_final_snapshot": result["failsafe_count"],
                "readiness_success": result["readiness_success"],
                "readiness_elapsed_s": result["readiness_elapsed_s"],
                "cleanup_success": result["cleanup"]["success"],
                "residual_processes": sum(len(values) for values in result["cleanup"]["after"].values()),
                "host_diagnostics": result["host_diagnostics_at_readiness"],
                "failure": result.get("failure"),
            },
            "28": {"status": "NOT_RUN", "reason": "conditional stop after N24 FAIL"},
            "32": {"status": "NOT_RUN", "reason": "conditional stop after N24 FAIL"},
        },
        "largest_stable_N_under_profile_v2": None,
        "original_v1_largest_tested_stable_N": 20,
        "primary_showcase_N_v2": None,
        "showcase_launch_eligible_v2": False,
        "scientific_showcase_missions_executed": 0,
        "recommendation": [
            "use N=20 only under a separately reviewed supplementary visual protocol",
            "or omit the additional showcase and retain the completed E5-v2 N=16 evidence",
        ],
    }
    (V2 / "profile_v2_results.json").write_text(json.dumps(profile_results, indent=2, sort_keys=True) + "\n")

    audit = {
        "schema": "large_swarm_diagnostics_v2_audit",
        "status": "PASS",
        "source_v1_commit": BASE,
        "source_v1_results_unchanged": confined,
        "source_v1_results": {"20": "PASS", "24": "FAIL", "28": "FAIL", "32": "FAIL"},
        "production_baseline": "6cf402debf23851b1eff3edc6f3ab49eae7127c4",
        "production_policy_sha256": sha(POLICY),
        "production_controller_sha256": sha(CONTROLLER),
        "production_method_changes": 0 if confined else None,
        "E5_v2_changes": 0 if confined else None,
        "root_cause_classification": {
            "method_external_xrce_startup_backlog": "SUPPORTED_AND_CORRECTED_BY_PROFILE_V2",
            "supplementary_grid_vs_frozen_neighbor_offset_mismatch": "SUPPORTED_REQUIRES_PRODUCTION_METHOD_CHANGE",
            "broader_scalability_claim": "NOT_ESTABLISHED",
        },
        "infrastructure_only_changes": [
            "per-instance PX4/XRCE writer gate",
            "controller batches of four separated by five seconds",
            "one-Hz file/process diagnostic summaries with zero DDS subscriptions",
        ],
        "profile_v2_sha256": profile_sha,
        "N24_v2": "FAIL",
        "N28_v2": "NOT_RUN",
        "N32_v2": "NOT_RUN",
        "largest_stable_N_under_profile_v2": None,
        "primary_showcase_N_v2": None,
        "readiness_criteria_unchanged": True,
        "readiness_timeout_s": 300,
        "timeout_inflation": False,
        "physics_fidelity_reduction": False,
        "middleware_change": False,
        "xrce_topology_change": False,
        "controller_or_safety_change": False,
        "scientific_showcase_missions": 0,
        "D1_D2_D3_missions": 0,
        "profile_v2_result_sha256": sha(N24_RESULT),
        "diagnostic_time_series_records": len((N24_RESULT.parent / "diagnostic_time_series.jsonl").read_text().splitlines()),
        "all_changes_confined_to_v2_directory": confined,
    }
    (V2 / "large_swarm_diagnostics_v2_audit.json").write_text(json.dumps(audit, indent=2, sort_keys=True) + "\n")
    print(json.dumps({"audit": audit["status"], "profile_v2": profile_sha, "N24": "FAIL", "N28": "NOT_RUN", "N32": "NOT_RUN"}, sort_keys=True))
    return 0 if audit["status"] == "PASS" and confined else 1


if __name__ == "__main__":
    raise SystemExit(main())
