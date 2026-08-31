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
    GRID_PATH, QualificationError, build_candidate_spec, load_yaml, validate_condition,
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
