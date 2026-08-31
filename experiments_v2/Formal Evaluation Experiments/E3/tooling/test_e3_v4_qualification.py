#!/usr/bin/env python3
"""Offline gates for the feedback-off-only E3-v4 qualification harness."""

from __future__ import annotations

import math
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parent))

from e3_formal_backend import build_runtime_spec
from e3_v4_qualification import (
    AMENDMENT_GRID_PATH, QualificationError, GRID_PATH, build_candidate_spec,
    load_yaml, validate_condition,
)
from e3_v4_qualification_metrics import _qualification_identity


class E3V4QualificationTests(unittest.TestCase):
    def setUp(self):
        self.grid = load_yaml(GRID_PATH)
        self.seed = 69707

    def test_feedback_on_is_fail_closed(self):
        for value in ("P0_F1", "P1_F1", "F1", "iapf_dual"):
            with self.assertRaises(QualificationError):
                validate_condition(value)

    def test_runtime_trial_id_recovers_dropped_qualification_metadata(self):
        self.assertEqual(
            _qualification_identity("E3V4Q-B01-G1-4N-1p5__P0_F0__S69707"),
            ("B01-G1-4N-1p5", "P0_F0", "E3-B-01"),
        )
        with self.assertRaises(ValueError):
            _qualification_identity("E3V4Q-B01-G1-4N-1p5__P0_F1__S69707")

    def test_search_orders_are_finite_complete_and_unique(self):
        flattened = []
        for scenario, order in self.grid["search_order"].items():
            self.assertGreater(len(order), 0)
            self.assertEqual(len(order), len(set(order)))
            for candidate_id in order:
                self.assertIn(candidate_id, self.grid["candidates"])
                self.assertEqual(self.grid["candidates"][candidate_id]["scenario_id"], scenario)
            flattened.extend(order)
        self.assertEqual(set(flattened), set(self.grid["candidates"]))

    def test_vector_magnitudes_match_registry(self):
        for candidate in self.grid["candidates"].values():
            magnitude = float(candidate["magnitude_N_per_uav"])
            for vector in candidate["vectors_N"].values():
                norm = math.sqrt(sum(float(value) ** 2 for value in vector))
                self.assertAlmostEqual(norm, magnitude, places=5)

    def test_B02_amendment_is_exact_finite_cartesian_grid(self):
        amendment = load_yaml(AMENDMENT_GRID_PATH)
        expected = {
            f"B02-V1-H{h}-F{force}"
            for h in ("1p0", "1p1", "1p2")
            for force in ("2p0", "3p0", "4p0")
        }
        self.assertEqual(set(amendment["candidates"]), expected)
        self.assertEqual(set(amendment["screening_order"]), expected)
        self.assertEqual(len(amendment["screening_order"]), 9)

    def test_B02_amendment_geometry_and_offline_nominal_gates(self):
        amendment = load_yaml(AMENDMENT_GRID_PATH)
        for geometry in amendment["geometries"].values():
            h = float(geometry["h_m"])
            z_sep = float(geometry["z_separation_m"])
            self.assertLess(h, 1.5)
            self.assertAlmostEqual(math.hypot(h, z_sep), 2.0, places=12)
            for uid in (1, 2, 3, 4):
                initial = geometry["initial_positions_m"][uid]
                target = geometry["ordered_targets_m"][uid]
                self.assertEqual([target[i] - initial[i] for i in range(3)],
                                 [8.0, 0.0, 0.0])
        for candidate_id in amendment["screening_order"]:
            runtimes = [
                build_runtime_spec(build_candidate_spec(candidate_id, condition, self.seed))
                for condition in ("P0_F0", "P1_F0")
            ]
            for runtime in runtimes:
                self.assertEqual(runtime["avoidance_mode"], "off")
                self.assertEqual(runtime["allocator_diagnostics"]["final_assignment"],
                                 [0, 1, 2, 3])
                self.assertEqual(runtime["allocator_metrics"]["hard_violations"], 0)
                self.assertAlmostEqual(runtime["allocator_metrics"]["min_distance"],
                                       2.0, places=12)

    def test_B02_holdout_is_fail_closed_before_selection_freeze(self):
        with self.assertRaisesRegex(QualificationError, "screening selection freeze"):
            build_candidate_spec("B02-V1-H1p0-F2p0", "P0_F0", 76174)

    def test_every_physical_spec_is_feedback_off_and_nominal_gate_is_valid(self):
        for candidate_id, candidate in self.grid["candidates"].items():
            if candidate["disposition"] != "PHYSICAL":
                continue
            runtimes = {}
            for condition in ("P0_F0", "P1_F0"):
                spec = build_candidate_spec(candidate_id, condition, self.seed)
                runtime = build_runtime_spec(spec)
                self.assertEqual(runtime["avoidance_mode"], "off")
                self.assertEqual(runtime["dataset_class"], "calibration_pilot")
                runtimes[condition] = runtime
            scenario = candidate["scenario_id"]
            p0, p1 = runtimes["P0_F0"], runtimes["P1_F0"]
            if scenario.startswith("E3-B"):
                self.assertEqual(p0["allocator_metrics"]["hard_violations"], 0)
                self.assertEqual(p1["allocator_metrics"]["hard_violations"], 0)
                self.assertGreater(p0["allocator_metrics"]["min_distance"], 1.5)
                self.assertAlmostEqual(p0["allocator_metrics"]["min_distance"],
                                       p1["allocator_metrics"]["min_distance"], places=9)
            else:
                self.assertGreater(p0["allocator_metrics"]["hard_violations"], 0)
                self.assertEqual(p1["allocator_metrics"]["hard_violations"], 0)
                self.assertGreater(p1["allocator_metrics"]["min_distance"], 1.5)


if __name__ == "__main__":
    unittest.main()
