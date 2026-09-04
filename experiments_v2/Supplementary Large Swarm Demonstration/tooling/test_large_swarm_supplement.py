#!/usr/bin/env python3
"""Static/non-formal tests for the supplementary large-swarm study."""

from __future__ import annotations

import json
import subprocess
import unittest

import yaml

from large_swarm_common import BASELINE, D_PLAN, E5_ANALYSIS, E5_SOURCE, POLICY, POLICY_SHA, REPO, ROOT, SIZES, layout_audit, parking_layout, sha256_file


class SupplementTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.infra = json.loads((ROOT / "infrastructure/large_swarm_infrastructure_results.json").read_text())
        cls.feasibility = json.loads((ROOT / "scenarios/large_swarm_scenario_feasibility.json").read_text())
        cls.protocol = yaml.safe_load((ROOT / "scenarios/large_swarm_demo_protocol_v1.yaml").read_text())

    def test_dynamic_config_and_layout(self):
        self.assertEqual(tuple(self.infra["tested_sizes"]), SIZES)
        for n in SIZES:
            self.assertEqual(parking_layout(n), parking_layout(n))
            self.assertEqual([x["uav_id"] for x in parking_layout(n)], list(range(1, n + 1)))
        audit = layout_audit()
        self.assertEqual(audit["status"], "PASS")
        self.assertTrue(all(r["workspace_fit"] and r["minimum_pairwise_spacing_m"] > D_PLAN for r in audit["rows"]))

    def test_exact_process_counts_and_cleanup(self):
        for row in self.infra["rows"]:
            n = row["N_requested"]
            self.assertEqual(row["models_spawned"], n)
            self.assertEqual(row["process_counts_at_readiness"]["px4"], n)
            self.assertEqual(row["process_counts_at_readiness"]["controllers"], n)
            self.assertTrue(row["cleanup"]["success"])

    def test_method_and_closed_E5_unchanged(self):
        self.assertEqual(sha256_file(POLICY), POLICY_SHA)
        prod = subprocess.check_output(["git", "diff", "--name-only", BASELINE, "--", "lfs_policy", "location_allocate", "minisnap_LADRC", "schemas", "uav_swarm_interfaces"], cwd=REPO, text=True).strip()
        formal = subprocess.check_output(["git", "diff", "--name-only", E5_SOURCE, "--", "experiments_v2/Formal Evaluation Experiments/E5_v2"], cwd=REPO, text=True).strip()
        self.assertEqual(prod, ""); self.assertEqual(formal, "")
        self.assertEqual(subprocess.check_output(["git", "rev-parse", "origin/formal/E5-v2-analysis-v1"], cwd=REPO, text=True).strip(), E5_ANALYSIS)

    def test_scenarios_and_selection_rule(self):
        selected = [r for r in self.feasibility["rows"] if r["selected"]]
        self.assertEqual({(r["candidate_id"], r["N"]) for r in selected}, {(d, n) for d in ("D1", "D2", "D3") for n in (24, 28, 32)})
        self.assertTrue(all(r["feasible"] for r in selected))
        infra = {r["N_requested"]: r["success"] for r in self.infra["rows"]}
        eligible = [n for n in (24, 28, 32) if infra[n] and all(r["feasible"] for r in selected if r["N"] == n)]
        self.assertEqual(self.protocol["primary_showcase_N"], max(eligible) if eligible else None)
        self.assertEqual(self.protocol["status"], "CANDIDATE_FOR_HUMAN_REVIEW")

    def test_no_scientific_showcase_execution(self):
        self.assertEqual(self.infra["scientific_missions"], 0)
        self.assertEqual(self.infra["accepted_formal_results"], 0)
        self.assertEqual(self.protocol["showcase_missions_executed"], 0)
        self.assertFalse((ROOT / "results/showcase_missions").exists())
        for row in self.infra["rows"]:
            source = json.loads((ROOT / row["evidence_path"]).read_text())
            self.assertFalse(source["accepted_formal_result"])
            self.assertFalse(source["scientific_mission"])
            self.assertEqual(source["llm_calls"], 0)
            self.assertEqual(source["formation_commands"], 0)


if __name__ == "__main__":
    unittest.main(verbosity=2)

