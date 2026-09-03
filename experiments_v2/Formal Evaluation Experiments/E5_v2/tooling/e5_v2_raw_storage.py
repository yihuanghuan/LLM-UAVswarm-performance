#!/usr/bin/env python3
"""Frozen E5-v2 external raw archive and immutable-ledger transactions."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Dict, List

from e5_v2_formal_common import (
    RAW_LEDGER_ROOT, EvidenceIntegrityError, FormalInfrastructureError,
    canonical_sha256, exclusive_json, inventory, load_json, sha256_file,
)


DISPOSITIONS = {
    "PRE_RAW_ACQUISITION_INFRASTRUCTURE_FAILURE",
    "RAW_ARCHIVE_VERIFIED", "RAW_EVIDENCE_LOSS", "RAW_ARCHIVE_PENDING",
}


class RawArchiveLedger:
    def __init__(self, root: Path = RAW_LEDGER_ROOT):
        self.root = Path(root)

    def _paths(self) -> List[Path]:
        return sorted(path for path in self.root.glob("*.json") if path.is_file())

    def validate(self, *, verify_archives: bool = False) -> List[Dict[str, Any]]:
        records, previous, seen = [], None, set()
        for position, path in enumerate(self._paths(), 1):
            record = load_json(path)
            if path.name != f"{position:06d}__{record.get('attempt_id')}.json":
                raise FormalInfrastructureError("raw ledger order/file mismatch")
            if record.get("campaign_position") != position:
                raise FormalInfrastructureError("raw ledger position mismatch")
            if record.get("attempt_id") in seen:
                raise FormalInfrastructureError("duplicate raw ledger attempt ID")
            if record.get("disposition") not in DISPOSITIONS - {"RAW_ARCHIVE_PENDING"}:
                raise FormalInfrastructureError("non-terminal raw ledger disposition")
            if record.get("previous_record_sha256") != previous:
                raise FormalInfrastructureError("raw ledger chain mismatch")
            body = {key: value for key, value in record.items()
                    if key != "record_sha256"}
            if record.get("record_sha256") != canonical_sha256(body):
                raise FormalInfrastructureError("raw ledger record hash mismatch")
            if verify_archives and record.get("archive_reference"):
                archive = Path(record["archive_reference"])
                for item in record.get("file_inventory", []):
                    relative = Path(item["path"])
                    if relative.is_absolute() or ".." in relative.parts:
                        raise EvidenceIntegrityError("unsafe raw inventory path")
                    retained = archive / relative
                    if (not retained.is_file()
                            or retained.stat().st_size != item["bytes"]
                            or sha256_file(retained) != item["sha256"]):
                        raise EvidenceIntegrityError(
                            f"retained raw archive mismatch: {retained}")
            previous = record["record_sha256"]
            seen.add(record["attempt_id"])
            records.append(record)
        return records

    def append(self, record: Dict[str, Any]) -> Path:
        records = self.validate()
        position = len(records) + 1
        if record.get("campaign_position") != position:
            raise FormalInfrastructureError("raw ledger append is not next position")
        body = {
            **record,
            "schema": "E5_v2_raw_archive_ledger_record_v1",
            "previous_record_sha256": records[-1]["record_sha256"] if records else None,
        }
        final = {**body, "record_sha256": canonical_sha256(body)}
        path = self.root / f"{position:06d}__{record['attempt_id']}.json"
        exclusive_json(path, final)
        self.validate()
        return path


def pre_raw_failure(spec: Dict[str, Any], reason: str,
                    pending: Path | None = None,
                    archive_root: Path | None = None) -> Dict[str, Any]:
    record = {
        "campaign_position": spec["campaign_position"],
        "attempt_id": spec["attempt_id"],
        "disposition": "PRE_RAW_ACQUISITION_INFRASTRUCTURE_FAILURE",
        "raw_acquisition_started": False,
        "archive_reference": None,
        "file_inventory": [],
        "total_bytes": 0,
        "reason": reason,
        "archive_verification": "NOT_APPLICABLE",
        "campaign_stop": False,
    }
    pending = Path(pending) if pending is not None else None
    if pending is not None and pending.exists():
        if archive_root is None:
            raise FormalInfrastructureError("archive root required for pre-raw diagnostic")
        target = Path(archive_root) / "pre_raw_diagnostics" / (
            f"{spec['campaign_position']:06d}__{spec['attempt_id']}")
        if target.exists():
            raise FormalInfrastructureError("pre-raw diagnostic target already exists")
        target.parent.mkdir(parents=True, exist_ok=True)
        os.rename(pending, target)
        records = inventory(target)
        record.update({
            "archive_reference": str(target), "file_inventory": records,
            "inventory_sha256": canonical_sha256(records),
            "total_bytes": sum(item["bytes"] for item in records),
            "archive_verification": "DIAGNOSTIC_ONLY",
        })
        for path in sorted(target.rglob("*"), reverse=True):
            path.chmod(0o555 if path.is_dir() else 0o444)
        target.chmod(0o555)
    return record


def raw_evidence_loss(spec: Dict[str, Any], reason: str,
                      pending: Path | None = None,
                      archive_root: Path | None = None,
                      existing_archive: Path | None = None) -> Dict[str, Any]:
    record = {
        "campaign_position": spec["campaign_position"],
        "attempt_id": spec["attempt_id"],
        "disposition": "RAW_EVIDENCE_LOSS",
        "raw_acquisition_started": True,
        "archive_reference": None,
        "file_inventory": [],
        "total_bytes": 0,
        "reason": reason,
        "archive_verification": "FAILED",
        "campaign_stop": True,
    }
    source = Path(existing_archive) if existing_archive is not None else (
        Path(pending) if pending is not None else None)
    if ((source is None or not source.exists()) and archive_root is not None):
        possibly_published = Path(archive_root) / "attempts" / (
            f"{spec['campaign_position']:06d}__{spec['attempt_id']}")
        if possibly_published.exists():
            source = possibly_published
    if source is not None and source.exists() and archive_root is not None:
        target = Path(archive_root) / "evidence_loss" / (
            f"{spec['campaign_position']:06d}__{spec['attempt_id']}")
        if target.exists():
            raise EvidenceIntegrityError("evidence-loss archive target already exists")
        target.parent.mkdir(parents=True, exist_ok=True)
        os.rename(source, target)
        try:
            records = inventory(target)
            record.update({
                "archive_reference": str(target), "file_inventory": records,
                "inventory_sha256": canonical_sha256(records),
                "total_bytes": sum(item["bytes"] for item in records),
            })
        except Exception as exc:
            record["archive_inventory_error"] = str(exc)
            record["archive_reference"] = str(target)
        for path in sorted(target.rglob("*"), reverse=True):
            try:
                path.chmod(0o555 if path.is_dir() else 0o444)
            except OSError:
                pass
        try:
            target.chmod(0o555)
        except OSError:
            pass
    return record


def verify_and_publish_raw(spec: Dict[str, Any], pending: Path,
                           archive_root: Path) -> Dict[str, Any]:
    """Verify twice and atomically publish pending raw evidence externally."""
    pending, archive_root = Path(pending), Path(archive_root)
    try:
        first = inventory(pending)
        names = {item["path"] for item in first}
        has_metadata = any(name.endswith("metadata.yaml") for name in names)
        has_payload = any(name.endswith((".db3", ".mcap")) for name in names)
        if not first or not has_metadata or not has_payload:
            raise EvidenceIntegrityError("raw bag metadata/payload missing")
        if inventory(pending) != first:
            raise EvidenceIntegrityError("raw inventory changed during verification")
        target = archive_root / "attempts" / (
            f"{spec['campaign_position']:06d}__{spec['attempt_id']}")
        if target.exists():
            raise EvidenceIntegrityError(f"raw archive target already exists: {target}")
        target.parent.mkdir(parents=True, exist_ok=True)
        os.rename(pending, target)
        second = inventory(target)
        if second != first:
            raise EvidenceIntegrityError("published raw archive verification mismatch")
        directory = os.open(target.parent, os.O_RDONLY)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
        for path in sorted(target.rglob("*"), reverse=True):
            path.chmod(0o555 if path.is_dir() else 0o444)
        target.chmod(0o555)
        aggregate = canonical_sha256(second)
        return {
            "campaign_position": spec["campaign_position"],
            "attempt_id": spec["attempt_id"],
            "disposition": "RAW_ARCHIVE_VERIFIED",
            "raw_acquisition_started": True,
            "archive_reference": str(target),
            "file_inventory": second,
            "inventory_sha256": aggregate,
            "total_bytes": sum(item["bytes"] for item in second),
            "reason": None,
            "archive_verification": "PASS",
            "verification_passes": 3,
            "campaign_stop": False,
        }
    except Exception as exc:
        if isinstance(exc, EvidenceIntegrityError):
            raise
        raise EvidenceIntegrityError(str(exc)) from exc


def assert_no_pending_raw(archive_root: Path) -> None:
    pending = Path(archive_root) / ".pending"
    leftovers = list(pending.iterdir()) if pending.is_dir() else []
    if leftovers:
        raise EvidenceIntegrityError(
            f"unresolved RAW_ARCHIVE_PENDING entries: {[path.name for path in leftovers]}")
