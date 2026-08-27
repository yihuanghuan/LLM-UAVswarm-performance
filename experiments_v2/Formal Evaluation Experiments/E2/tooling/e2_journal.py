"""Append-only, hash-chained attempt journal for E2."""

from __future__ import annotations

import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
from typing import Any, Dict, List

from e2_common import E2ToolingError, canonical_json_bytes, json_safe, utc_now


ZERO_HASH = "0" * 64
RECORD_NAME = re.compile(r"^(\d{6})-attempt\.json$")


def _record_body_hash(record: Dict[str, Any]) -> str:
    body = dict(record)
    body.pop("record_hash", None)
    return hashlib.sha256(canonical_json_bytes(body)).hexdigest()


class AttemptJournal:
    """A journal whose write API can create but cannot replace records."""

    def __init__(self, directory: Path):
        self.directory = Path(directory)
        self.directory.mkdir(parents=True, exist_ok=True)
        self._lock_path = self.directory / ".append.lock"

    def _record_files(self) -> List[Path]:
        return sorted(
            path for path in self.directory.iterdir()
            if path.is_file() and RECORD_NAME.fullmatch(path.name)
        )

    def read(self) -> List[Dict[str, Any]]:
        records: List[Dict[str, Any]] = []
        previous_hash = ZERO_HASH
        for expected_sequence, path in enumerate(self._record_files(), start=1):
            match = RECORD_NAME.fullmatch(path.name)
            assert match is not None
            if int(match.group(1)) != expected_sequence:
                raise E2ToolingError(
                    f"journal sequence gap at {path.name}; expected {expected_sequence:06d}"
                )
            try:
                record = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError) as exc:
                raise E2ToolingError(f"corrupt journal record: {path}") from exc
            if record.get("sequence") != expected_sequence:
                raise E2ToolingError(f"record sequence mismatch: {path}")
            if record.get("previous_journal_record_hash") != previous_hash:
                raise E2ToolingError(f"journal hash-chain mismatch: {path}")
            expected_hash = _record_body_hash(record)
            if record.get("record_hash") != expected_hash:
                raise E2ToolingError(f"record hash mismatch: {path}")
            records.append(record)
            previous_hash = expected_hash
        return records

    def append(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        with self._lock_path.open("a+b") as lock_stream:
            fcntl.flock(lock_stream.fileno(), fcntl.LOCK_EX)
            records = self.read()
            sequence = len(records) + 1
            previous_hash = records[-1]["record_hash"] if records else ZERO_HASH
            record = {
                "sequence": sequence,
                "recorded_at_utc": utc_now(),
                "previous_journal_record_hash": previous_hash,
                **json_safe(payload),
            }
            if "record_hash" in payload:
                raise E2ToolingError("caller may not provide record_hash")
            record["record_hash"] = _record_body_hash(record)
            path = self.directory / f"{sequence:06d}-attempt.json"
            raw = canonical_json_bytes(record) + b"\n"
            descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o444)
            try:
                with os.fdopen(descriptor, "wb") as stream:
                    stream.write(raw)
                    stream.flush()
                    os.fsync(stream.fileno())
            except Exception:
                raise
            return record

    def snapshot(self) -> Dict[str, Any]:
        records = self.read()
        digest = hashlib.sha256()
        files = self._record_files()
        for path in files:
            digest.update(path.name.encode("utf-8") + b"\0")
            digest.update(path.read_bytes())
        return {
            "record_count": len(records),
            "head_record_hash": records[-1]["record_hash"] if records else ZERO_HASH,
            "journal_sha256": digest.hexdigest(),
            "serialization": "filename NUL raw-file-bytes in lexical sequence",
        }
