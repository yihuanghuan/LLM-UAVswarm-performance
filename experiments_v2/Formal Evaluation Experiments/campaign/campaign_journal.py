"""Append-only, hash-chained suite journal and exclusive execution lock."""

from __future__ import annotations

import fcntl
import hashlib
import json
from pathlib import Path
import re
from typing import Any, Dict, List

from campaign_common import CampaignError, canonical_json_bytes, utc_now, write_json_exclusive


ZERO_HASH = "0" * 64
RECORD_NAME = re.compile(r"^(\d{6})-attempt\.json$")


def record_body_hash(record: Dict[str, Any]) -> str:
    body = dict(record)
    body.pop("record_hash", None)
    return hashlib.sha256(canonical_json_bytes(body)).hexdigest()


class CampaignExecutionLock:
    def __init__(self, path: Path):
        self.path = Path(path)
        self.stream = None

    def __enter__(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.stream = self.path.open("a+b")
        try:
            fcntl.flock(self.stream.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            self.stream.close()
            self.stream = None
            raise CampaignError("another campaign dispatcher holds the execution lock") from exc
        return self

    def __exit__(self, exc_type, exc, traceback):
        assert self.stream is not None
        fcntl.flock(self.stream.fileno(), fcntl.LOCK_UN)
        self.stream.close()
        self.stream = None


class CampaignJournal:
    def __init__(self, directory: Path):
        self.directory = Path(directory)

    def record_files(self) -> List[Path]:
        if not self.directory.exists():
            return []
        return sorted(path for path in self.directory.iterdir()
                      if path.is_file() and RECORD_NAME.fullmatch(path.name))

    def read(self) -> List[Dict[str, Any]]:
        records: List[Dict[str, Any]] = []
        previous = ZERO_HASH
        for sequence, path in enumerate(self.record_files(), start=1):
            match = RECORD_NAME.fullmatch(path.name)
            assert match is not None
            if int(match.group(1)) != sequence:
                raise CampaignError(f"journal gap/reorder at {path.name}; expected {sequence:06d}")
            try:
                record = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError) as exc:
                raise CampaignError(f"corrupt journal record: {path}") from exc
            if record.get("sequence") != sequence:
                raise CampaignError(f"journal sequence mismatch: {path}")
            if record.get("previous_record_hash") != previous:
                raise CampaignError(f"journal hash-chain mismatch: {path}")
            expected = record_body_hash(record)
            if record.get("record_hash") != expected:
                raise CampaignError(f"journal record hash mismatch: {path}")
            records.append(record)
            previous = expected
        return records

    def append(
        self, payload: Dict[str, Any], prior_records: List[Dict[str, Any]] | None = None
    ) -> Dict[str, Any]:
        self.directory.mkdir(parents=True, exist_ok=True)
        records = self.read() if prior_records is None else prior_records
        sequence = len(records) + 1
        record = {
            "sequence": sequence,
            "recorded_at_utc": utc_now(),
            "previous_record_hash": records[-1]["record_hash"] if records else ZERO_HASH,
            **payload,
        }
        if "record_hash" in payload or "previous_record_hash" in payload:
            raise CampaignError("caller may not supply journal chain fields")
        record["record_hash"] = record_body_hash(record)
        path = self.directory / f"{sequence:06d}-attempt.json"
        write_json_exclusive(path, record)
        retained = json.loads(path.read_text(encoding="utf-8"))
        if retained != record or record_body_hash(retained) != retained["record_hash"]:
            raise CampaignError(f"new journal record verification failed: {path}")
        return record
