#!/usr/bin/env python3
"""Immutable-record campaign journal; its validated prefix is the sole cursor."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List

from e5_v2_formal_common import (
    ATTEMPTS_ROOT, EXPECTED_ORDER_SHA256, JOURNAL_ROOT,
    RAW_LEDGER_ROOT,
    FormalInfrastructureError, canonical_sha256, exclusive_json,
    load_attempt_specs, load_json, sha256_file,
)


class CampaignJournal:
    def __init__(self, root: Path = JOURNAL_ROOT, attempts_root: Path = ATTEMPTS_ROOT,
                 *, synthetic_rehearsal: bool = False):
        self.root, self.attempts_root = Path(root), Path(attempts_root)
        self.synthetic_rehearsal = bool(synthetic_rehearsal)

    def _record_paths(self) -> List[Path]:
        return sorted(path for path in self.root.glob("*.json") if path.is_file())

    def validate(self) -> List[Dict[str, Any]]:
        specs, records, seen, previous = load_attempt_specs(), [], set(), None
        for position, path in enumerate(self._record_paths(), 1):
            expected = specs[position - 1] if position <= len(specs) else None
            if expected is None:
                raise FormalInfrastructureError("journal exceeds sealed 60-slot order")
            record = load_json(path)
            name = f"{position:06d}__{expected['attempt_id']}.json"
            if path.name != name:
                raise FormalInfrastructureError(f"wrong journal order/file: {path.name}")
            for key, value in {
                "campaign_position": position,
                "attempt_id": expected["attempt_id"],
                "seed": expected["seed"],
                "N": expected["N"],
                "scenario_id": expected["scenario_id"],
                "order_sha256": EXPECTED_ORDER_SHA256,
                "previous_record_sha256": previous,
            }.items():
                if record.get(key) != value:
                    raise FormalInfrastructureError(
                        f"journal {path.name} {key} mismatch")
            if record["attempt_id"] in seen:
                raise FormalInfrastructureError("duplicate journal attempt ID")
            claimed = record.get("record_sha256")
            body = {key: value for key, value in record.items()
                    if key != "record_sha256"}
            if claimed != canonical_sha256(body):
                raise FormalInfrastructureError(f"journal hash mismatch: {path}")
            artifact = self.attempts_root / record["artifact_directory"] / "attempt.json"
            if not artifact.is_file() or sha256_file(artifact) != record["attempt_sha256"]:
                raise FormalInfrastructureError(f"missing/mismatched attempt artifact: {artifact}")
            attempt = load_json(artifact)
            if (attempt.get("attempt_id") != record["attempt_id"]
                    or attempt.get("campaign_position") != position
                    or attempt.get("accepted_formal_result") is not (
                        False if self.synthetic_rehearsal else True)
                    or attempt.get("replacement_attempt") is not False):
                raise FormalInfrastructureError(f"invalid attempt artifact: {artifact}")
            compact_inventory = artifact.parent / "compact_inventory.json"
            if (not compact_inventory.is_file()
                    or sha256_file(compact_inventory)
                    != record["compact_inventory_sha256"]):
                raise FormalInfrastructureError("compact inventory missing/mismatched")
            compact = load_json(compact_inventory)
            for item in compact.get("files", []):
                relative = Path(item["path"])
                if relative.is_absolute() or ".." in relative.parts:
                    raise FormalInfrastructureError("unsafe compact inventory path")
                retained = artifact.parent / relative
                if (not retained.is_file() or retained.stat().st_size != item["bytes"]
                        or sha256_file(retained) != item["sha256"]):
                    raise FormalInfrastructureError(
                        f"retained compact evidence mismatch: {retained}")
            raw_record = RAW_LEDGER_ROOT / record["raw_ledger_record"]
            # Custom roots are used only by synthetic tests; their ledger is a
            # sibling of the custom journal directory.
            if self.root != JOURNAL_ROOT:
                raw_record = self.root.parent / "ledger" / record["raw_ledger_record"]
            if (not raw_record.is_file()
                    or sha256_file(raw_record) != record["raw_ledger_record_sha256"]):
                raise FormalInfrastructureError(
                    f"missing/mismatched raw ledger record: {raw_record}")
            seen.add(record["attempt_id"])
            previous, records = claimed, records + [record]
        return records

    def state(self) -> Dict[str, Any]:
        records, specs = self.validate(), load_attempt_specs()
        return {
            "registered_slots": len(specs),
            "consumed_slots": len(records),
            "completed_attempt_ids": [record["attempt_id"] for record in records],
            "next_attempt": None if len(records) == len(specs) else specs[len(records)],
        }

    def append(self, record: Dict[str, Any]) -> Path:
        state = self.state()
        expected = state["next_attempt"]
        if expected is None:
            raise FormalInfrastructureError("sealed campaign already complete")
        for key in ("campaign_position", "attempt_id", "seed", "N", "scenario_id"):
            if record.get(key) != expected.get(key):
                raise FormalInfrastructureError(f"journal append wrong next {key}")
        previous_records = self.validate()
        body = {
            **record,
            "schema": "E5_v2_campaign_journal_record_v1",
            "order_sha256": EXPECTED_ORDER_SHA256,
            "previous_record_sha256": (
                previous_records[-1]["record_sha256"] if previous_records else None),
        }
        final = {**body, "record_sha256": canonical_sha256(body)}
        path = self.root / f"{expected['campaign_position']:06d}__{expected['attempt_id']}.json"
        exclusive_json(path, final)
        self.validate()
        return path
