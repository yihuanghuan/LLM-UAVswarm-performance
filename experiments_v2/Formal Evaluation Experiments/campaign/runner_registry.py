"""Pinned runner registry and formal-launch gate."""

from __future__ import annotations

from typing import Any, Dict, List, Tuple

from campaign_common import CampaignError, FAMILIES, RUNNER_REGISTRY_PATH, canonical_sha256, load_json


def load_runner_registry() -> Dict[str, Any]:
    registry = load_json(RUNNER_REGISTRY_PATH)
    if tuple(registry.get("required_families", ())) != FAMILIES:
        raise CampaignError("runner registry required_families mismatch")
    runners = registry.get("runners")
    if not isinstance(runners, dict) or set(runners) != set(FAMILIES):
        raise CampaignError("runner registry must contain exactly E2/E3/E4A/E4B/E5")
    for family, entry in runners.items():
        if entry.get("experiment") != family:
            raise CampaignError(f"runner registry experiment mismatch for {family}")
        status = entry.get("validation_status")
        if status not in {"READY", "NOT_READY"}:
            raise CampaignError(f"invalid validation status for {family}: {status}")
        pinned = (entry.get("runner_branch"), entry.get("runner_commit"),
                  entry.get("runner_entrypoint"), entry.get("runner_source_sha256"))
        if status == "READY" and not all(pinned):
            raise CampaignError(f"READY runner lacks complete pinning: {family}")
        if status == "NOT_READY" and any(pinned):
            raise CampaignError(f"NOT_READY runner contains fabricated partial pinning: {family}")
    return registry


def formal_launch_gate(registry: Dict[str, Any] | None = None) -> Tuple[bool, List[str]]:
    registry = registry or load_runner_registry()
    blockers = [f"{family} validated runner is NOT_READY" for family in FAMILIES
                if registry["runners"][family]["validation_status"] != "READY"]
    if registry.get("formal_campaign_status") != "READY":
        blockers.append("CURRENT FORMAL CAMPAIGN STATUS is NOT_READY")
    return not blockers, blockers


def registry_sha256(registry: Dict[str, Any] | None = None) -> str:
    return canonical_sha256(registry or load_runner_registry())

