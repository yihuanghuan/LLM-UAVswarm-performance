#!/usr/bin/env python3
"""Non-mutating replay and invariant tests for E5-v2 analysis_v1."""

from __future__ import annotations

import csv
import hashlib
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
SCRIPT = HERE / "run_e5_v2_analysis.py"


def tree(root: Path) -> dict[str, str]:
    result = {}
    for path in sorted(p for p in root.rglob("*") if p.is_file()):
        result[path.relative_to(root).as_posix()] = hashlib.sha256(path.read_bytes()).hexdigest()
    return result


class AnalysisTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.one_ctx = tempfile.TemporaryDirectory(prefix="e5v2_analysis_replay_a_")
        cls.two_ctx = tempfile.TemporaryDirectory(prefix="e5v2_analysis_replay_b_")
        cls.one, cls.two = Path(cls.one_ctx.name), Path(cls.two_ctx.name)
        for root in [cls.one, cls.two]:
            subprocess.run([sys.executable, str(SCRIPT), "--artifact-root", str(root)], check=True, stdout=subprocess.DEVNULL)

    @classmethod
    def tearDownClass(cls) -> None:
        cls.one_ctx.cleanup(); cls.two_ctx.cleanup()

    def test_byte_identical_replay(self) -> None:
        self.assertEqual(tree(self.one), tree(self.two))

    def test_required_outputs_and_population(self) -> None:
        names = {
            "E5_v2_per_attempt_results.csv", "E5_v2_overall_summary.csv",
            "E5_v2_substudy_summary.csv", "E5_v2_A_scenario_summary.csv",
            "E5_v2_B_N_summary.csv", "E5_v2_B_family_summary.csv",
            "E5_v2_B_cell_summary.csv", "E5_v2_resolved_values.csv",
            "E5_v2_endpoint_availability.csv", "E5_v2_analysis_summary.json",
        }
        self.assertEqual({p.name for p in (self.one / "outputs").iterdir()}, names)
        with (self.one / "outputs/E5_v2_per_attempt_results.csv").open() as f:
            rows = list(csv.DictReader(f))
        self.assertEqual(len(rows), 60)
        self.assertEqual(len({r["attempt_id"] for r in rows}), 60)
        self.assertTrue(all(r["mission_success"] == "True" for r in rows))
        self.assertTrue(all(r["J_hard_available"] == "False" and r["J_hard_value"] == "" for r in rows))
        for endpoint in ["T_validation", "T_state_resolution", "T_geometry", "T_allocator", "T_profile"]:
            self.assertTrue(all(r[endpoint + "_available"] == "False" and r[endpoint] == "" for r in rows))

    def test_wilson_and_strata(self) -> None:
        with (self.one / "outputs/E5_v2_overall_summary.csv").open() as f:
            rows = list(csv.DictReader(f))
        success = next(r for r in rows if r["endpoint"] == "mission_success")
        self.assertEqual((success["numerator"], success["denominator"]), ("60", "60"))
        self.assertAlmostEqual(float(success["wilson_95_low"]), 0.9398281478579098)
        with (self.one / "outputs/E5_v2_B_cell_summary.csv").open() as f:
            cells = [r for r in csv.DictReader(f) if r["endpoint"] == "mission_success"]
        self.assertEqual(len(cells), 9)
        self.assertTrue(all(r["numerator"] == "5" and r["denominator"] == "5" for r in cells))

    def test_resolved_semantics_and_freeze_audit(self) -> None:
        with (self.one / "outputs/E5_v2_resolved_values.csv").open() as f:
            rows = list(csv.DictReader(f))
        self.assertEqual(len(rows), 75)
        self.assertTrue(all(r["all_semantics_ok"] == "True" for r in rows))
        audit = json.loads((self.one / "E5_v2_analysis_freeze_audit.json").read_text())
        self.assertEqual(audit["status"], "PASS")
        self.assertEqual(audit["J_hard_available"], "0/60")
        self.assertEqual(audit["analysis_deterministic_replay"], "PASS")


if __name__ == "__main__":
    unittest.main(verbosity=2)
