"""Atomic append-only, hash-chained event journal for E1 attempts."""

from __future__ import annotations

import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import secrets
from typing import Any, Callable, Dict, List, Optional

from e1_common import E1ToolingError, utc_now


ZERO_HASH = "0" * 64
EVENT_NAME = re.compile(r"^(\d{6})-[a-z0-9_-]+\.json$")


def _canonical_json(value: Any) -> bytes:
    return (
        json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        + "\n"
    ).encode("utf-8")


class EventJournal:
    """A journal whose public write path can create but never replace events."""

    def __init__(
        self,
        directory: Path,
        after_append: Optional[Callable[[Dict[str, Any]], None]] = None,
    ) -> None:
        self.directory = Path(directory)
        self.directory.mkdir(parents=True, exist_ok=True)
        self._lock_path = self.directory / ".append.lock"
        self._after_append = after_append

    def read(self) -> List[Dict[str, Any]]:
        events: List[Dict[str, Any]] = []
        previous_hash = ZERO_HASH
        files = sorted(
            path for path in self.directory.iterdir()
            if path.is_file() and EVENT_NAME.match(path.name)
        )
        for expected_sequence, path in enumerate(files, start=1):
            match = EVENT_NAME.match(path.name)
            assert match is not None
            filename_sequence = int(match.group(1))
            if filename_sequence != expected_sequence:
                raise E1ToolingError(
                    f"journal sequence gap at {path.name}; expected "
                    f"{expected_sequence:06d}"
                )
            raw = path.read_bytes()
            try:
                event = json.loads(raw)
            except json.JSONDecodeError as exc:
                raise E1ToolingError(f"corrupt journal event: {path}") from exc
            if event.get("sequence") != expected_sequence:
                raise E1ToolingError(f"event sequence mismatch: {path}")
            if event.get("previous_event_sha256") != previous_hash:
                raise E1ToolingError(f"journal hash-chain mismatch: {path}")
            actual_hash = hashlib.sha256(raw).hexdigest()
            event["_event_sha256"] = actual_hash
            event["_event_path"] = str(path)
            events.append(event)
            previous_hash = actual_hash
        return events

    def append(self, event_type: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        if not re.fullmatch(r"[a-z0-9_]+", event_type):
            raise E1ToolingError(f"invalid event type: {event_type!r}")
        with self._lock_path.open("a+b") as lock_stream:
            fcntl.flock(lock_stream.fileno(), fcntl.LOCK_EX)
            existing = self.read()
            sequence = len(existing) + 1
            previous_hash = (
                existing[-1]["_event_sha256"] if existing else ZERO_HASH
            )
            event = {
                "sequence": sequence,
                "event_type": event_type,
                "recorded_at_utc": utc_now(),
                "previous_event_sha256": previous_hash,
                "payload": payload,
            }
            raw = _canonical_json(event)
            suffix = event_type
            command_id = payload.get("command_id")
            if isinstance(command_id, str):
                suffix += "-" + command_id.lower()
            attempt = payload.get("attempt_index")
            if isinstance(attempt, int):
                suffix += f"-a{attempt:02d}"
            final_path = self.directory / f"{sequence:06d}-{suffix}.json"
            temp_path = self.directory / (
                f".pending-{os.getpid()}-{secrets.token_hex(8)}"
            )
            try:
                with temp_path.open("xb") as stream:
                    stream.write(raw)
                    stream.flush()
                    os.fsync(stream.fileno())
                os.link(temp_path, final_path)
                directory_fd = os.open(self.directory, os.O_RDONLY)
                try:
                    os.fsync(directory_fd)
                finally:
                    os.close(directory_fd)
            finally:
                if temp_path.exists():
                    temp_path.unlink()
            fcntl.flock(lock_stream.fileno(), fcntl.LOCK_UN)
        written = dict(event)
        written["_event_sha256"] = hashlib.sha256(raw).hexdigest()
        written["_event_path"] = str(final_path)
        if self._after_append is not None:
            self._after_append(written)
        return written


def events_by_type(events: List[Dict[str, Any]], event_type: str):
    return [event for event in events if event.get("event_type") == event_type]
