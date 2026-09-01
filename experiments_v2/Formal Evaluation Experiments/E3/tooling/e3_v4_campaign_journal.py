#!/usr/bin/env python3
"""Validate or append one exact E3-v4 standalone campaign journal record."""

from __future__ import annotations

import argparse
import fcntl
import json
import os
from pathlib import Path

from e3_v4_trial_registry import E3, registered_trial_ids, sha256_file

DEFAULT_JOURNAL = E3 / "results/formal_v4/campaign_journal.jsonl"


class JournalError(RuntimeError):
    pass


def read_journal(path: Path) -> list[dict]:
    if not path.exists():
        return []
    records = []
    for number, line in enumerate(path.read_text().splitlines(), start=1):
        try:
            value = json.loads(line)
        except ValueError as exc:
            raise JournalError(f"invalid JSON at journal line {number}") from exc
        records.append(value)
    return records


def validate(records: list[dict]) -> dict:
    order = registered_trial_ids()
    if len(records) > len(order):
        raise JournalError("journal exceeds registered 360 slots")
    for index, record in enumerate(records, start=1):
        expected = order[index - 1]
        if record.get("campaign_position") != index:
            raise JournalError(f"position mismatch at journal line {index}")
        if record.get("trial_id") != expected:
            raise JournalError(f"order mismatch at journal line {index}")
        if record.get("replacement_attempt") is not False:
            raise JournalError(f"replacement marker violation at line {index}")
        if not record.get("attempt_artifact_sha256"):
            raise JournalError(f"attempt hash absent at line {index}")
    return {
        "registered_slot_count": len(order),
        "consumed_slot_count": len(records),
        "next_campaign_position": len(records) + 1 if len(records) < len(order) else None,
        "next_trial_id": order[len(records)] if len(records) < len(order) else None,
        "complete": len(records) == len(order),
    }


def append(path: Path, artifact: Path) -> dict:
    artifact = artifact.resolve()
    if not artifact.is_file():
        raise JournalError("attempt artifact does not exist")
    attempt = json.loads(artifact.read_text())
    if attempt.get("accepted_formal_result") is not True:
        raise JournalError("journal accepts only formal attempt artifacts")
    if attempt.get("replacement_attempt") is not False:
        raise JournalError("replacement formal attempts are forbidden")
    path.parent.mkdir(parents=True, exist_ok=True)
    lock_path = path.with_suffix(path.suffix + ".lock")
    with lock_path.open("a+") as lock:
        fcntl.flock(lock.fileno(), fcntl.LOCK_EX)
        records = read_journal(path)
        state = validate(records)
        if state["next_trial_id"] is None:
            raise JournalError("all registered slots are already consumed")
        if attempt.get("trial_id") != state["next_trial_id"]:
            raise JournalError("attempt is not the exact next registered trial")
        record = {
            "schema": "E3_v4_campaign_journal_record_v1",
            "campaign_position": state["next_campaign_position"],
            "trial_id": attempt["trial_id"],
            "attempt_status": attempt.get("attempt_status"),
            "attempt_artifact_path": str(artifact),
            "attempt_artifact_sha256": sha256_file(artifact),
            "replacement_attempt": False,
            "failed_attempt_retained": attempt.get("attempt_status") != "success",
        }
        descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o644)
        with os.fdopen(descriptor, "a", encoding="utf-8") as stream:
            stream.write(json.dumps(record, sort_keys=True, separators=(",", ":")) + "\n")
            stream.flush()
            os.fsync(stream.fileno())
        return record


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--journal", type=Path, default=DEFAULT_JOURNAL)
    parser.add_argument("--append-artifact", type=Path)
    args = parser.parse_args()
    result = append(args.journal, args.append_artifact) if args.append_artifact else validate(
        read_journal(args.journal)
    )
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
