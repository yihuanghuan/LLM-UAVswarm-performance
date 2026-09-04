#!/usr/bin/env python3
"""Non-scientific governance and deterministic infrastructure tests."""

from __future__ import annotations

import csv
import hashlib
import json
import subprocess
import unittest
from pathlib import Path

import yaml


HERE = Path(__file__).resolve()
V2 = HERE.parents[1]
REPO = HERE.parents[4]
BASE = "adf56c7256ccb7f3e63d78ec2ffb254d1f88b647"
POLICY = REPO / "lfs_policy/config/lfs_policy.paper_current.yaml"
POLICY_SHA = "6b47d27f4253d7311e79ea51f6dd1cf0d0182e6df24374a94abae0aa6a135858"


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


class DiagnosticsV2Tests(unittest.TestCase):
    def test_changes_confined_to_new_study(self):
        result = subprocess.run(["git", "diff", "--name-only", BASE], cwd=REPO, capture_output=True, text=True, check=True)
        untracked = subprocess.run(["git", "ls-files", "--others", "--exclude-standard"], cwd=REPO, capture_output=True, text=True, check=True)
        prefix = "experiments_v2/Supplementary Large Swarm Demonstration/infrastructure_diagnostics_v2/"
        paths = result.stdout.splitlines() + untracked.stdout.splitlines()
        self.assertTrue(paths)
        self.assertTrue(all(path.startswith(prefix) for path in paths))

    def test_frozen_policy(self):
        self.assertEqual(sha(POLICY), POLICY_SHA)
        tag = subprocess.check_output(["git", "rev-list", "-n", "1", "paper-final-sim-v3"], cwd=REPO, text=True).strip()
        self.assertEqual(tag, "6cf402debf23851b1eff3edc6f3ab49eae7127c4")

    def test_profile_is_one_prospective_configuration(self):
        profile = yaml.safe_load((V2 / "infrastructure_profile_v2.yaml").read_text())
        self.assertEqual(profile["status"], "FROZEN_BEFORE_PROFILE_V2_EXECUTION")
        self.assertEqual(profile["test_order"], [24, 28, 32])
        self.assertTrue(profile["stop_at_first_failure"])
        self.assertEqual(profile["fixed_runtime"]["readiness_timeout_s"], 300)
        self.assertEqual(profile["fixed_runtime"]["readiness_hold_s"], 5)
        self.assertTrue(profile["unchanged"]["gazebo_physics_fidelity"])
        self.assertTrue(profile["unchanged"]["readiness_predicate"])
        self.assertTrue(profile["unchanged"]["controller_parameters"])

    def test_full_neighbor_set_not_batch_subset(self):
        source = (HERE.with_name("large_swarm_controller_batch_launch.py")).read_text()
        self.assertIn('"neighbor_uav_ids": swarm_ids', source)
        self.assertIn("for other in swarm_ids", source)
        self.assertNotIn('"neighbor_uav_ids": launch_ids', source)

    def test_no_scientific_command_path(self):
        source = HERE.with_name("run_profile_v2.py").read_text()
        self.assertIn('"scientific_mission": False', source)
        self.assertIn('"llm_calls": 0', source)
        self.assertIn('"candidate_commands": 0', source)
        self.assertIn('"formation_commands": 0', source)
        for prohibited in ("Candidate", "run_physical_trial", "swarm_command"):
            self.assertNotIn(prohibited, source)

    def test_v1_diagnostics_are_complete(self):
        expected = {24: 24, 28: 28, 32: 32}
        for n, count in expected.items():
            with (V2 / f"per_uav_N{n}_diagnostics.csv").open(newline="") as stream:
                rows = list(csv.DictReader(stream))
            self.assertEqual(len(rows), count)
            self.assertEqual([int(row["uav_id"]) for row in rows], list(range(1, n + 1)))

    def test_root_cause_audit_classifications(self):
        audit = json.loads((V2 / "large_swarm_root_cause_audit.json").read_text())
        self.assertEqual(audit["hypotheses"]["H2"]["classification"], "SUPPORTED")
        self.assertEqual(audit["hypotheses"]["H4"]["classification"], "SUPPORTED")
        self.assertTrue(audit["method_semantic_assumption_found"])
        self.assertFalse(audit["broader_method_scalability_limitation_inferred"])

    def test_profile_v2_result_and_conditional_stop(self):
        result = json.loads((V2 / "results/N24/result.json").read_text())
        self.assertFalse(result["success"])
        self.assertTrue(result["stage_A_success"])
        self.assertEqual(len(result["px4_writer_gate_records"]), 24)
        self.assertTrue(all(record["success"] for record in result["px4_writer_gate_records"]))
        self.assertEqual(result["fresh_state_count"], 24)
        self.assertTrue(result["all_states_finite"])
        self.assertEqual(result["readiness_elapsed_s"], 300.00010287901387)
        self.assertTrue(result["cleanup"]["success"])
        self.assertFalse((V2 / "results/N28").exists())
        self.assertFalse((V2 / "results/N32").exists())

    def test_profile_identity_and_non_scientific_result(self):
        result = json.loads((V2 / "results/N24/result.json").read_text())
        self.assertEqual(result["profile_sha256"], sha(V2 / "infrastructure_profile_v2.yaml"))
        self.assertEqual(result["dataset_class"], "supplementary_infrastructure_diagnostic")
        self.assertFalse(result["accepted_formal_result"])
        self.assertFalse(result["scientific_mission"])
        self.assertEqual(result["llm_calls"], 0)
        self.assertEqual(result["candidate_commands"], 0)
        self.assertEqual(result["formation_commands"], 0)

    def test_final_audit_and_no_showcase_protocol_v2(self):
        audit = json.loads((V2 / "large_swarm_diagnostics_v2_audit.json").read_text())
        self.assertEqual(audit["status"], "PASS")
        self.assertEqual(audit["production_method_changes"], 0)
        self.assertEqual(audit["E5_v2_changes"], 0)
        self.assertEqual(audit["D1_D2_D3_missions"], 0)
        self.assertFalse(audit["timeout_inflation"])
        self.assertFalse(audit["physics_fidelity_reduction"])
        self.assertFalse((V2.parents[0] / "scenarios/large_swarm_demo_protocol_v2.yaml").exists())


if __name__ == "__main__":
    unittest.main(verbosity=2)
