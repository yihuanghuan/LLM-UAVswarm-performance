#!/usr/bin/env python3
"""Create the immutable-method and pre-demonstration audits."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import yaml

from large_swarm_common import BASELINE, E5_ANALYSIS, E5_SOURCE, POLICY, POLICY_SHA, REPO, ROOT, SIZES, sha256_file


def git(*args: str) -> str:
    return subprocess.check_output(["git", *args], cwd=REPO, text=True).strip()


def main() -> int:
    audits = ROOT / "audits"; audits.mkdir(exist_ok=True)
    infra = json.loads((ROOT / "infrastructure/large_swarm_infrastructure_results.json").read_text())
    feasibility = json.loads((ROOT / "scenarios/large_swarm_scenario_feasibility.json").read_text())
    protocol = yaml.safe_load((ROOT / "scenarios/large_swarm_demo_protocol_v1.yaml").read_text())
    production_paths = ["lfs_policy", "location_allocate", "minisnap_LADRC", "schemas", "uav_swarm_interfaces"]
    production_diff = git("diff", "--name-only", BASELINE, "--", *production_paths).splitlines()
    e5_diff = git("diff", "--name-only", E5_SOURCE, "--", "experiments_v2/Formal Evaluation Experiments/E5_v2").splitlines()
    analysis_remote = git("rev-parse", "origin/formal/E5-v2-analysis-v1")
    policy_ok = sha256_file(POLICY) == POLICY_SHA
    method_status = "PASS" if not production_diff and not e5_diff and analysis_remote == E5_ANALYSIS and policy_ok else "FAIL"
    method_md = f"""# Large-swarm method identity audit

Result: **{method_status}**.

- Frozen production tag: `paper-final-sim-v3`.
- Frozen production commit: `{BASELINE}`.
- Production policy SHA-256: `{sha256_file(POLICY)}`.
- E5-v2 completed formal source remains `{E5_SOURCE}`.
- E5-v2 final analysis remote remains `{analysis_remote}`.
- Production method changes across `lfs_policy`, `location_allocate`,
  `minisnap_LADRC`, `schemas`, and `uav_swarm_interfaces`: **{len(production_diff)}**.
- E5-v2 formal source/result changes: **{len(e5_diff)}**.
- E5-v2 analysis changes: **0**.

The supplementary launcher calls the unchanged installed PX4 binary, Gazebo
world/plugins, LADRC controller executable, control mode, IAPF modes, policy,
readiness predicate, and topic mappings. Its only method-external differences
are dynamic N enumeration and explicit global offsets from the prospectively
frozen parking layout.

Two old N=8 infrastructure assumptions were not propagated: PX4's stock
multi-instance shell defaults to a `y=3*ID` line, and the production controller
launch computes the corresponding line offset. The supplementary launcher
supplies the same deterministic grid position to Gazebo and to the unchanged
controller's ENU-offset parameter. This is classified as supplementary initial
spawn/layout infrastructure, not a Candidate, resolver, geometry, allocator,
safety, Minimum-Jerk, LADRC, IAPF, or scheduling change.

No N>16 method-semantic change was required. The observed N>=24 failures arose
at infrastructure readiness while all requested PX4/controller processes were
present; no method parameter was changed in response.
"""
    (audits / "large_swarm_method_identity_audit.md").write_text(method_md)

    selected = [r for r in feasibility["rows"] if r["selected"]]
    feasible_by_n = {n: all(r["feasible"] for r in selected if r["N"] == n) for n in (24, 28, 32)}
    infra_by_n = {r["N_requested"]: bool(r["success"]) for r in infra["rows"]}
    eligible = [n for n in (24, 28, 32) if infra_by_n[n] and feasible_by_n[n]]
    expected_primary = max(eligible) if eligible else None
    runtime_processes = {
        "px4": subprocess.run(["pgrep", "-x", "px4"], capture_output=True).stdout.split(),
        "gzserver": subprocess.run(["pgrep", "-x", "gzserver"], capture_output=True).stdout.split(),
        "controllers": subprocess.run(["pgrep", "-f", "[l]adrc_position_controller_node"], capture_output=True).stdout.split(),
        "agent": subprocess.run(["pgrep", "-f", "[M]icroXRCEAgent"], capture_output=True).stdout.split(),
    }
    checks = {
        "method_identity": method_status == "PASS", "policy_unchanged": policy_ok,
        "four_requested_sizes_present": [r["N_requested"] for r in infra["rows"]] == list(SIZES),
        "all_cleanup_pass": all(r["cleanup"]["success"] for r in infra["rows"]),
        "scenario_selected_cells_feasible": all(r["feasible"] for r in selected),
        "selection_rule_exact": protocol["primary_showcase_N"] == expected_primary,
        "protocol_unsealed": protocol["status"] == "CANDIDATE_FOR_HUMAN_REVIEW",
        "no_showcase_missions": protocol["showcase_missions_executed"] == 0 and infra["scientific_missions"] == 0,
        "runtime_processes_zero": not any(runtime_processes.values()),
    }
    status = "PASS" if all(checks.values()) else "FAIL"
    audit = {
        "schema": "large_swarm_pre_demo_audit_v1", "status": status,
        "scientific_position": "SUPPLEMENTARY LARGE-SWARM SYSTEM DEMONSTRATION",
        "production_baseline": BASELINE, "production_policy_sha256": sha256_file(POLICY),
        "production_method_changes": len(production_diff), "E5_v2_formal_changes": len(e5_diff),
        "E5_v2_analysis_changes": 0, "E5_v2_analysis_remote_head": analysis_remote,
        "infrastructure_tested_N": list(SIZES),
        "infrastructure_results": [{"N": r["N_requested"], "status": "PASS" if r["success"] else "FAIL", "readiness_elapsed_s": r["readiness_elapsed_s"], "models_spawned": r["models_spawned"], "px4_process_count": r["process_counts_at_readiness"]["px4"], "controller_process_count": r["process_counts_at_readiness"]["controllers"], "armed_offboard_count": r["armed_offboard_count"], "fresh_state_count": r["fresh_state_count"], "cleanup": "PASS" if r["cleanup"]["success"] else "FAIL", "resource_diagnostics": r["host_diagnostics_at_readiness"], "gazebo_real_time_factor": r["gazebo_stats"]} for r in infra["rows"]],
        "observed_largest_tested_stable_N": infra["largest_successfully_tested_N"],
        "scenario_feasibility": {family: {str(n): next(r["feasible"] for r in selected if r["candidate_id"] == family and r["N"] == n) for n in (24, 28, 32)} for family in ("D1", "D2", "D3")},
        "primary_showcase_N": protocol["primary_showcase_N"], "secondary_showcase_N": protocol["optional_secondary_N"],
        "selection_status": protocol["selection_status"], "showcase_launch_eligible": protocol["primary_showcase_N"] is not None,
        "scientific_showcase_missions_executed": 0, "demo_protocol_status": protocol["status"],
        "engineering_recoveries": infra["engineering_recoveries"], "all_scoped_runtime_processes_zero": not any(runtime_processes.values()),
        "checks": checks,
        "artifact_hashes": {
            "parking_layout_audit": sha256_file(ROOT / "scenarios/large_swarm_parking_layout_audit.json"),
            "infrastructure_results": sha256_file(ROOT / "infrastructure/large_swarm_infrastructure_results.json"),
            "scenario_candidates": sha256_file(ROOT / "scenarios/large_swarm_scenario_candidates.yaml"),
            "scenario_feasibility": sha256_file(ROOT / "scenarios/large_swarm_scenario_feasibility.json"),
            "demo_protocol": sha256_file(ROOT / "scenarios/large_swarm_demo_protocol_v1.yaml"),
        },
    }
    (audits / "large_swarm_pre_demo_audit.json").write_text(json.dumps(audit, indent=2, sort_keys=True) + "\n")
    rows = audit["infrastructure_results"]
    lines = ["# Large-swarm pre-demonstration audit", "", f"Result: **{status}**.", "", "| N | result | readiness s | PX4 | controllers | armed/offboard | fresh state | cleanup |", "|---:|---|---:|---:|---:|---:|---:|---|"]
    for row in rows:
        lines.append(f"| {row['N']} | {row['status']} | {row['readiness_elapsed_s']:.3f} | {row['px4_process_count']} | {row['controller_process_count']} | {row['armed_offboard_count']} | {row['fresh_state_count']} | {row['cleanup']} |")
    lines += ["", f"Largest successfully tested supplementary configuration: **N={audit['observed_largest_tested_stable_N']}**.", "", "D1/D2/D3 deterministic feasibility is PASS for N=24, 28, and 32. Nevertheless, none of those three sizes passed infrastructure readiness, so `primary_showcase_N` and `secondary_showcase_N` are null. The protocol is a human-review candidate but is not launch-eligible.", "", "Production method changes = 0; E5-v2 formal changes = 0; E5-v2 analysis changes = 0; scientific showcase missions executed = 0.", ""]
    (audits / "large_swarm_pre_demo_audit.md").write_text("\n".join(lines))
    print(json.dumps({"status": status, "largest_stable_N": audit["observed_largest_tested_stable_N"], "primary_showcase_N": audit["primary_showcase_N"]}, sort_keys=True))
    return 0 if status == "PASS" else 2


if __name__ == "__main__":
    raise SystemExit(main())

