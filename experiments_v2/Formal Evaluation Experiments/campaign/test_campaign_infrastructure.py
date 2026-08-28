"""Synthetic-only tests for sealed global campaign infrastructure."""

from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest

from campaign_audit import audit_run
from campaign_common import (
    CampaignError, RunnerRefusalError, load_sealed_order, write_json_exclusive,
)
from campaign_dispatcher import CampaignDispatcher
from campaign_journal import CampaignExecutionLock
from campaign_provenance import validate_provenance
from mock_runners import build_mock_adapters
from runner_registry import formal_launch_gate, load_runner_registry
from synthetic_rehearsal import deterministic_trace, retained_trace, run_to_completion


class CampaignInfrastructureTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.provenance = validate_provenance()
        cls.order = load_sealed_order()

    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="campaign-test-")
        self.results_root = (
            Path(self.temporary.name) / "campaign" / "results" / "synthetic-validation"
        )

    def tearDown(self):
        self.temporary.cleanup()

    def dispatcher(self, run_id="test", adapters=None):
        return CampaignDispatcher(
            run_id, build_mock_adapters() if adapters is None else adapters,
            self.results_root, self.provenance,
        )

    def test_exact_order_routing_failure_retention_and_restart(self):
        dispatcher = self.dispatcher()
        for _ in range(137):
            dispatcher.dispatch_next()
        self.assertEqual(dispatcher.validate_state()["next_position"], 138)
        dispatcher = self.dispatcher()
        while not dispatcher.validate_state()["complete"]:
            dispatcher.dispatch_next()
        trace = retained_trace(dispatcher)
        self.assertEqual(trace, deterministic_trace(self.order))
        self.assertEqual(len(trace), 610)
        self.assertEqual(len({item["trial_id"] for item in trace}), 610)
        self.assertTrue(any(item["attempt_status"] != "success" for item in trace))
        self.assertEqual(audit_run(dispatcher.run_dir)["status"], "PASS")

    def test_requested_trial_and_selector_refusals(self):
        dispatcher = self.dispatcher()
        for requested in ("NOT-REGISTERED", self.order[1]):
            with self.assertRaises(CampaignError):
                dispatcher.dispatch_next(requested)
        with self.assertRaises(CampaignError):
            dispatcher.reject_selector("next E2")
        dispatcher.dispatch_next()
        with self.assertRaises(CampaignError):
            dispatcher.dispatch_next(self.order[0])
        self.assertEqual(dispatcher.validate_state()["retained_count"], 1)

    def test_unavailable_global_next_fails_without_skip(self):
        adapters = build_mock_adapters()
        adapters.pop("E2")
        dispatcher = self.dispatcher(adapters=adapters)
        with self.assertRaises(CampaignError):
            dispatcher.dispatch_next()
        self.assertEqual(dispatcher.validate_state()["retained_count"], 0)

    def test_invoked_runner_refusal_is_retained_and_advances(self):
        class RefusingAdapter:
            def run_exact_trial(self, trial_id, campaign_context):
                raise RunnerRefusalError("synthetic exact-trial refusal")

        adapters = build_mock_adapters()
        adapters["E2"] = RefusingAdapter()
        dispatcher = self.dispatcher(adapters=adapters)
        record = dispatcher.dispatch_next()
        self.assertEqual(record["attempt_status"], "runner_refusal")
        self.assertEqual(dispatcher.validate_state()["next_position"], 2)
        self.assertEqual(dispatcher.journal.read()[0]["trial_id"], self.order[0])

    def test_orphan_artifact_requires_explicit_recovery(self):
        dispatcher = self.dispatcher()
        write_json_exclusive(dispatcher.artifacts_dir / "000001-attempt.json", {"orphan": True})
        with self.assertRaises(CampaignError):
            dispatcher.validate_state()
        with self.assertRaises(CampaignError):
            self.dispatcher()

    def test_execution_lock_rejects_concurrent_dispatcher(self):
        dispatcher = self.dispatcher()
        with CampaignExecutionLock(dispatcher.execution_lock_path):
            with self.assertRaises(CampaignError):
                dispatcher.dispatch_next()
        self.assertEqual(dispatcher.validate_state()["retained_count"], 0)

    def test_deterministic_replay(self):
        first = run_to_completion("replay-a", self.results_root, (), self.provenance)
        second = run_to_completion("replay-b", self.results_root, (307,), self.provenance)
        self.assertEqual(retained_trace(first), retained_trace(second))

    def test_adapter_registry_is_ready_for_separate_launch_gate(self):
        ready, blockers = formal_launch_gate(load_runner_registry())
        self.assertTrue(ready)
        self.assertEqual(blockers, [])


if __name__ == "__main__":
    unittest.main()
