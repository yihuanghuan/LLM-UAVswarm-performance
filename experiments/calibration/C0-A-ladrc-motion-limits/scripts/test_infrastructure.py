#!/usr/bin/env python3
"""Offline equivalence and fail-closed tests for C0-A instrumentation."""

from __future__ import annotations

import json
from pathlib import Path
import sys
import tempfile
import unittest

import yaml


SCRIPT_DIR = Path(__file__).resolve().parent
ROOT = SCRIPT_DIR.parent
REPOSITORY = ROOT.parents[2]
sys.path.insert(0, str(SCRIPT_DIR))

import render_trial
import trial_driver


class InfrastructureTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.registry = json.loads(
            (ROOT / "configs" / "c0a_prereg_v2.json").read_text(encoding="utf-8")
        )
        cls.schedule = json.loads(
            (ROOT / "trial_order_v2.json").read_text(encoding="utf-8")
        )

    def render_entry(self, stage, state):
        entry = next(item for item in self.schedule["entries"] if item["stage"] == stage)
        temporary = tempfile.TemporaryDirectory()
        path = Path(temporary.name)
        spec = render_trial.render(entry, state, self.registry, path)
        return temporary, path, spec

    def test_single_origin_registered_exactly(self):
        temporary, _, spec = self.render_entry("A1_SCREENING", {})
        self.addCleanup(temporary.cleanup)
        self.assertEqual(spec["world_starts"], [[0.0, 0.0, 3.0]])
        displacement = self.registry["single_uav_cases"][
            f"{spec['entry']['scenario_id']}:{spec['entry']['signed_displacement_id']}"
        ]
        self.assertEqual(
            spec["world_targets"][0],
            [spec["world_starts"][0][axis] + displacement[axis] for axis in range(3)],
        )

    def test_a1_changes_only_owned_candidate_policy_fields(self):
        temporary, path, _ = self.render_entry("A1_SCREENING", {})
        self.addCleanup(temporary.cleanup)
        baseline = yaml.safe_load(render_trial.BASE_POLICY.read_text(encoding="utf-8"))
        candidate = yaml.safe_load((path / "candidate_policy.yaml").read_text(encoding="utf-8"))
        for key in baseline:
            if key in {"configuration_id", "execution_profile", "motion_limits", "timing", "controller_hard_clamps"}:
                continue
            self.assertEqual(candidate[key], baseline[key])
        self.assertEqual(candidate["timing"]["auto_style_factors"], baseline["timing"]["auto_style_factors"])
        self.assertEqual(candidate["timing"]["policy_type"], baseline["timing"]["policy_type"])
        self.assertEqual(
            candidate["execution_profile"]["style_gains"],
            baseline["execution_profile"]["style_gains"],
        )
        for key in ("iapf_enter_min", "iapf_enter_max", "iapf_exit_max", "iapf_repulsion_max", "smoothing_alpha"):
            self.assertEqual(
                candidate["controller_hard_clamps"][key],
                baseline["controller_hard_clamps"][key],
            )

    def test_compiler_outputs_normal_identity_without_auto_t(self):
        temporary, _, spec = self.render_entry("A1_SCREENING", {})
        self.addCleanup(temporary.cleanup)
        for profile in spec["profiles"]:
            self.assertEqual(profile["style"], "normal")
            self.assertEqual(profile["style_gain"], 1.0)
            self.assertEqual(profile["task_gain"], 1.0)
            self.assertAlmostEqual(profile["duration"], spec["explicit_duration_s"], places=10)
            self.assertEqual(profile["omega_c"], spec["resolved_candidate_parameters"]["omega_c"])
            self.assertEqual(profile["omega_o"], spec["resolved_candidate_parameters"]["omega_o"])

    def test_a3_and_scale_use_locked_winners_and_registered_layout(self):
        state = {
            "a1_winner": {
                "omega_c": [1.5, 1.5, 1.75], "omega_o": [5.0, 5.0, 7.5],
                "v_limit": 5.0, "a_limit": 5.0, "j_limit": 10.0,
                "minimum_duration": 0.5,
            },
            "a2_winner": {
                "v_limit": 4.0, "a_limit": 3.0, "j_limit": 8.0,
                "minimum_duration": 0.75,
            },
        }
        temporary, _, a3 = self.render_entry("A3_VALIDATION", state)
        self.addCleanup(temporary.cleanup)
        state["a3_winner"] = {
            key: a3["resolved_candidate_parameters"][key]
            for key in (
                "omega_lower_multiplier", "omega_upper_multiplier",
                "motion_clamp_multiplier",
            )
        }
        scale_entry = next(
            item for item in self.schedule["entries"]
            if item["stage"] == "SCALE_VALIDATION" and item["scenario_id"] == "C0A-M-8"
        )
        second = tempfile.TemporaryDirectory()
        self.addCleanup(second.cleanup)
        scale = render_trial.render(scale_entry, state, self.registry, Path(second.name))
        self.assertEqual(scale["world_starts"], [[-4.0, 3.0 * uid, 3.0] for uid in range(1, 9)])
        self.assertEqual(scale["world_targets"], [[4.0, 3.0 * uid, 3.0] for uid in range(1, 9)])
        self.assertEqual(scale["distance_m"], 8.0)
        self.assertAlmostEqual(
            scale["explicit_duration_s"], 1.25 * scale["t_min_s"], places=12
        )

    def test_instrumentation_does_not_edit_frozen_runtime_sources(self):
        algorithm_manifest = json.loads(
            (REPOSITORY / "experiments" / "calibration" / "algorithm_freeze_manifest.json")
            .read_text(encoding="utf-8")
        )
        instrument_paths = {
            str(path.relative_to(REPOSITORY))
            for path in SCRIPT_DIR.glob("*.py")
        }
        frozen = {
            item["path"]
            for component in algorithm_manifest["algorithm_components"].values()
            for item in component
        }
        self.assertTrue(instrument_paths.isdisjoint(frozen))

    def test_trial_driver_node_constructs_without_reserved_node_attributes(self):
        import rclpy
        from rclpy.qos import ReliabilityPolicy

        temporary, _, spec = self.render_entry("A1_SCREENING", {})
        self.addCleanup(temporary.cleanup)
        rclpy.init()
        try:
            node = trial_driver.TrialDriver(spec)
            self.assertEqual(set(node.command_publishers), {1})
            debug_subscription = node.command_subscriptions[-1]
            self.assertEqual(debug_subscription.topic_name, "/uav1/control_tracking_debug")
            self.assertEqual(
                debug_subscription.qos_profile.reliability,
                ReliabilityPolicy.BEST_EFFORT,
            )
            node.destroy_node()
        finally:
            rclpy.shutdown()


if __name__ == "__main__":
    unittest.main()
