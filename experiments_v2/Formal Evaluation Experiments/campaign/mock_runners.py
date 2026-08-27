"""Deterministic synthetic adapters; these never invoke scientific runners."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict

from campaign_common import (
    ATTEMPT_STATUSES, DATASET_CLASS, NOT_FORMAL_RESULT, CampaignError,
    family_for_trial, sha256_file, write_json_exclusive,
)


def synthetic_status(position: int) -> str:
    """Stable mixed-outcome policy for infrastructure rehearsal only."""
    if position % 29 == 0:
        return "runner_refusal"
    if position % 23 == 0:
        return "timeout"
    if position % 17 == 0:
        return "infrastructure_failure"
    if position % 11 == 0:
        return "method_failure"
    return "success"


class MockRunnerAdapter:
    """Strict exact-trial adapter used only by the 610-attempt rehearsal."""

    def __init__(self, family: str):
        self.family = family

    def run_exact_trial(self, trial_id: str, campaign_context: Dict[str, Any]) -> Dict[str, Any]:
        position = int(campaign_context["global_position"])
        if campaign_context.get("exact_trial_id") != trial_id:
            raise CampaignError("adapter context exact_trial_id mismatch")
        if family_for_trial(trial_id) != self.family:
            raise CampaignError(f"{self.family} adapter refused foreign trial {trial_id}")
        status = synthetic_status(position)
        if status not in ATTEMPT_STATUSES:
            raise CampaignError(f"invalid synthetic status: {status}")
        artifact_path = Path(campaign_context["artifact_path"])
        artifact = {
            "record_type": "global_campaign_synthetic_attempt_v1",
            "dataset_class": DATASET_CLASS,
            "accepted_formal_result": False,
            "result_notice": NOT_FORMAL_RESULT,
            "global_position": position,
            "trial_id": trial_id,
            "experiment": self.family,
            "attempt_status": status,
            "replacement_attempt": False,
            "synthetic_adapter_policy": "deterministic-mixed-outcomes-v1",
            "runner": campaign_context["runner_provenance"],
            "sealed_provenance": campaign_context["sealed_provenance"],
        }
        write_json_exclusive(artifact_path, artifact)
        return {
            "trial_id": trial_id,
            "experiment": self.family,
            "attempt_status": status,
            "artifact_path": artifact_path.relative_to(campaign_context["run_dir"]).as_posix(),
            "artifact_sha256": sha256_file(artifact_path),
            "runner_provenance": campaign_context["runner_provenance"],
        }


def build_mock_adapters() -> Dict[str, MockRunnerAdapter]:
    return {family: MockRunnerAdapter(family) for family in ("E2", "E3", "E4A", "E4B", "E5")}

