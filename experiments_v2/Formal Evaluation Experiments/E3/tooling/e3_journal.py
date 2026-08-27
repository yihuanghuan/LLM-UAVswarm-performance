"""Immutable artifacts and append-only hash-chained E3 synthetic journal."""

from __future__ import annotations

import fcntl
import hashlib
import json
import os
from pathlib import Path
from typing import Any, Dict, List

from e3_trial_registry import E3Error, canonical_bytes

ZERO = "0" * 64


def _atomic_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    data = json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2).encode() + b"\n"
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o444)
    with os.fdopen(fd, "wb") as stream:
        stream.write(data); stream.flush(); os.fsync(stream.fileno())
    directory_fd = os.open(path.parent, os.O_RDONLY)
    try: os.fsync(directory_fd)
    finally: os.close(directory_fd)


def write_artifact(path: Path, value: Any) -> None:
    _atomic_json(path, value)


class E3Journal:
    def __init__(self, path: Path):
        self.path = Path(path); self.path.mkdir(parents=True, exist_ok=True)
        self.lock = self.path / ".append.lock"

    def read(self) -> List[Dict[str, Any]]:
        records, previous = [], ZERO
        files = sorted(self.path.glob("*-attempt.json"))
        for sequence, path in enumerate(files, 1):
            if path.name != f"{sequence:06d}-attempt.json": raise E3Error("journal gap")
            record = json.loads(path.read_text())
            body = dict(record); recorded = body.pop("record_hash", None)
            digest = hashlib.sha256(canonical_bytes(body)).hexdigest()
            if record.get("sequence") != sequence or record.get("previous_record_hash") != previous or recorded != digest:
                raise E3Error(f"journal chain failure: {path}")
            records.append(record); previous = digest
        return records

    def append(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        with self.lock.open("a+b") as lock:
            fcntl.flock(lock.fileno(), fcntl.LOCK_EX)
            records = self.read(); sequence = len(records) + 1
            record = {"sequence": sequence, "previous_record_hash": records[-1]["record_hash"] if records else ZERO, **payload}
            record["record_hash"] = hashlib.sha256(canonical_bytes(record)).hexdigest()
            _atomic_json(self.path / f"{sequence:06d}-attempt.json", record)
            return record

