#!/usr/bin/env python3
"""Tests for the deterministic frozen E3-v4 analysis."""

from __future__ import annotations

import hashlib
import sys
import unittest
from pathlib import Path

import numpy as np

SCRIPT_DIR = Path(__file__).resolve().parent
REPO = SCRIPT_DIR.parents[4]
sys.path.insert(0, str(SCRIPT_DIR))

import run_e3_v4_analysis as analysis  # noqa: E402


class AnalysisMathTests(unittest.TestCase):
    def test_factorial_formulas(self) -> None:
        cells = {"P0_F0": 1.0, "P0_F1": 4.0, "P1_F0": 6.0, "P1_F1": 12.0}
        result = analysis.factorial_contrasts(cells)
        self.assertEqual(result["Delta_P"], ((6 - 1) + (12 - 4)) / 2)
        self.assertEqual(result["Delta_F"], ((4 - 1) + (12 - 6)) / 2)
        self.assertEqual(result["Delta_PF"], (12 - 6) - (4 - 1))

    def test_binary_factorial_encoding(self) -> None:
        result = analysis.factorial_contrasts({"P0_F0": 1, "P0_F1": 0, "P1_F0": 1, "P1_F1": 1})
        self.assertEqual(result, {"Delta_P": 0.5, "Delta_F": -0.5, "Delta_PF": 1})

    def test_bootstrap_seed_first_64_bits(self) -> None:
        text = "E3-v4-analysis-bootstrap-v1|B|j_hard_pair_s|Delta_F"
        expected = int.from_bytes(hashlib.sha256(text.encode()).digest()[:8], "big")
        self.assertEqual(analysis.bootstrap_seed("B", "j_hard_pair_s", "Delta_F"), expected)
        self.assertEqual(expected, 2037804662643476154)

    def test_bootstrap_reproducibility_and_strata(self) -> None:
        values = {"scenario-2": [10.0, 12.0], "scenario-1": [0.0, 1.0, 2.0]}
        first = analysis.stratified_bootstrap_ci(values, 123456789, resamples=500)
        second = analysis.stratified_bootstrap_ci(dict(reversed(list(values.items()))), 123456789, resamples=500)
        self.assertEqual(first, second)

    def test_wilson_interval(self) -> None:
        low, high = analysis.wilson_interval(0, 10)
        self.assertAlmostEqual(low, 0.0, places=15)
        self.assertAlmostEqual(high, 0.2775327998628892, places=12)
        low, high = analysis.wilson_interval(5, 10)
        self.assertAlmostEqual(low, 0.236593090512564, places=12)
        self.assertAlmostEqual(high, 0.7634069094874361, places=12)

    def test_zero_sd_effect_is_na(self) -> None:
        self.assertEqual(float(np.std([2.0, 2.0, 2.0], ddof=1)), 0.0)


class FrozenCampaignTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.analysis_root = SCRIPT_DIR.parent
        cls.gate = analysis.integrity_gate(REPO, cls.analysis_root)
        cls.data = analysis.ingest_campaign(REPO)

    def test_integrity_gate(self) -> None:
        self.assertEqual(self.gate["status"], "PASS")
        self.assertTrue(self.gate["source_worktree_clean"])
        self.assertEqual(self.gate["source_commit"], analysis.SOURCE_COMMIT)

    def test_exact_360_attempt_ingestion(self) -> None:
        self.assertEqual(len(self.data["attempts"]), 360)
        self.assertEqual(len({a["trial_id"] for a in self.data["attempts"]}), 360)
        self.assertEqual(self.data["status_counts"], {"success": 343, "infrastructure_failure": 17})

    def test_exact_74_block_primary_population(self) -> None:
        self.assertEqual(len(self.data["blocks"]), 90)
        self.assertEqual(len(self.data["complete_blocks"]), 74)
        self.assertEqual(len(self.data["blocks"]) - len(self.data["complete_blocks"]), 16)

    def test_four_cell_uniqueness(self) -> None:
        for cells in self.data["blocks"].values():
            self.assertEqual(set(cells), set(analysis.CONDITIONS))
            self.assertEqual(len(cells), 4)

    def test_incomplete_blocks_are_wholly_excluded(self) -> None:
        for key, cells in self.data["complete_blocks"].items():
            self.assertTrue(all(cells[c]["attempt_status"] == "success" for c in analysis.CONDITIONS), key)
        incomplete = set(self.data["blocks"]) - set(self.data["complete_blocks"])
        self.assertEqual(len(incomplete), 16)
        self.assertTrue(all(any(self.data["blocks"][k][c]["attempt_status"] != "success" for c in analysis.CONDITIONS) for k in incomplete))

    def test_binary_paired_comparison_handling(self) -> None:
        rows, _ = analysis.build_binary_results(self.data)
        row = analysis.lookup(rows, result_type="paired_binary_comparison", family="B",
                              endpoint="any_realized_hard_risk", comparison="F1_vs_F0_at_P0")
        self.assertEqual(row["N"], 26)
        self.assertEqual(row["discordant_0_to_1"], 0)
        self.assertEqual(row["discordant_1_to_0"], 11)
        self.assertEqual(row["mcnemar_exact_p_raw"], 0.0009765625)
        self.assertLess(row["estimate"], 0)

    def test_no_qualification_or_e3_v3_data(self) -> None:
        for path, attempt in zip(self.data["attempt_paths"], self.data["attempts"]):
            self.assertIn("results/formal_v4/attempts", path.as_posix())
            self.assertNotIn("qualification", path.as_posix().lower())
            self.assertEqual(attempt["dataset_class"], "formal_evaluation")
            self.assertEqual(attempt["execution_mode"], "formal")
            self.assertNotIn("5310", attempt["trial_id"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
