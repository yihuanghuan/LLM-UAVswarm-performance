#!/usr/bin/env python3
"""Archive one completed E3-v4 rosbag outside Git and freeze compact provenance."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import fcntl
import hashlib
import json
import os
from pathlib import Path
import shutil
from typing import Any

TOOLING = Path(__file__).resolve().parent
E3 = TOOLING.parent
REPO = E3.parents[2]
DEFAULT_CAMPAIGN_JOURNAL = E3 / "results/formal_v4/campaign_journal.jsonl"
DEFAULT_ARCHIVE_LEDGER = E3 / "results/formal_v4/raw_archive_ledger.jsonl"
ARCHIVE_ENV = "E3_V4_RAW_ARCHIVE_ROOT"
PAYLOAD_SUFFIXES = {".db3", ".mcap"}


class RawArchiveError(RuntimeError):
    pass


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def canonical_sha256(value: Any) -> str:
    payload = json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(payload).hexdigest()


def fsync_directory(path: Path) -> None:
    descriptor = os.open(path, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def durable_json(path: Path, value: Any) -> None:
    if path.exists():
        raise RawArchiveError(f"refusing to overwrite retained artifact: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + f".tmp-{os.getpid()}")
    descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o444)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            json.dump(value, stream, indent=2, sort_keys=True)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
        fsync_directory(path.parent)
    finally:
        if temporary.exists():
            temporary.unlink()


def resolve_archive_root(explicit: Path | None) -> Path:
    raw = str(explicit) if explicit is not None else os.environ.get(ARCHIVE_ENV)
    if not raw:
        raise RawArchiveError(
            f"archive root missing; set {ARCHIVE_ENV} or pass --archive-root"
        )
    root = Path(raw).expanduser().resolve()
    if root == REPO or REPO in root.parents:
        raise RawArchiveError("archive root must be outside the Git repository")
    return root


def read_json_lines(path: Path) -> list[dict]:
    if not path.is_file():
        raise RawArchiveError(f"required ledger absent: {path}")
    records = []
    for number, line in enumerate(path.read_text().splitlines(), start=1):
        try:
            records.append(json.loads(line))
        except ValueError as exc:
            raise RawArchiveError(f"invalid JSON at {path}:{number}") from exc
    return records


def journaled_attempt(attempt: dict, attempt_sha: str, journal: Path) -> None:
    matches = [
        record for record in read_json_lines(journal)
        if record.get("campaign_position") == attempt.get("campaign_position")
        and record.get("trial_id") == attempt.get("trial_id")
    ]
    if len(matches) != 1:
        raise RawArchiveError("attempt is not uniquely present in campaign journal")
    record = matches[0]
    if record.get("attempt_artifact_sha256") != attempt_sha:
        raise RawArchiveError("campaign-journal attempt SHA-256 mismatch")
    if attempt.get("accepted_formal_result") is not True:
        raise RawArchiveError("archive accepts only a formal attempt artifact")
    if attempt.get("replacement_attempt") is not False:
        raise RawArchiveError("replacement attempts are forbidden")


def copy_and_verify(source_root: Path, archive_root: Path, final: Path) -> list[dict]:
    source_files = sorted(path for path in source_root.rglob("*") if path.is_file())
    if not source_files:
        raise RawArchiveError("source rosbag directory contains no files")
    if not any(path.suffix.lower() in PAYLOAD_SUFFIXES for path in source_files):
        raise RawArchiveError("source rosbag has no registered binary payload")
    if final.exists():
        raise RawArchiveError(f"refusing to overwrite retained archive: {final}")
    archive_root.mkdir(parents=True, exist_ok=True)
    temporary_slot = archive_root / f".{final.parent.name}.tmp-{os.getpid()}"
    if temporary_slot.exists():
        raise RawArchiveError(f"stale temporary archive exists: {temporary_slot}")
    temporary = temporary_slot / "rosbag"
    temporary.mkdir(parents=True)
    inventory = []
    for source in source_files:
        relative = source.relative_to(source_root)
        destination = temporary / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, destination)
        with destination.open("rb") as stream:
            os.fsync(stream.fileno())
        source_sha = sha256_file(source)
        archive_sha = sha256_file(destination)
        source_size = source.stat().st_size
        archive_size = destination.stat().st_size
        equal = source_sha == archive_sha and source_size == archive_size
        if not equal:
            raise RawArchiveError(f"source/archive verification failed: {relative}")
        inventory.append({
            "source_relative_path": str(Path("raw/rosbag") / relative),
            "source_byte_size": source_size,
            "source_sha256": source_sha,
            "archived_relative_path": str(final.relative_to(archive_root) / relative),
            "archived_byte_size": archive_size,
            "archived_sha256": archive_sha,
            "source_archive_hash_equal": True,
        })
    for directory in sorted(
        {path.parent for path in temporary.rglob("*") if path.is_file()},
        key=lambda value: len(value.parts), reverse=True,
    ):
        fsync_directory(directory)
    fsync_directory(temporary)
    os.replace(temporary_slot, final.parent)
    fsync_directory(archive_root)
    return inventory


def append_archive_ledger(path: Path, record: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    lock_path = path.parent / ".append.lock"
    with lock_path.open("a+") as lock:
        fcntl.flock(lock.fileno(), fcntl.LOCK_EX)
        records = [] if not path.exists() else read_json_lines(path)
        if any(
            item.get("campaign_position") == record["campaign_position"]
            or item.get("trial_id") == record["trial_id"]
            for item in records
        ):
            raise RawArchiveError("raw archive ledger already contains this attempt")
        descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o644)
        with os.fdopen(descriptor, "a", encoding="utf-8") as stream:
            stream.write(json.dumps(record, sort_keys=True, separators=(",", ":")) + "\n")
            stream.flush()
            os.fsync(stream.fileno())
        fsync_directory(path.parent)


def archive_attempt(
    attempt_dir: Path,
    archive_root: Path,
    campaign_journal: Path = DEFAULT_CAMPAIGN_JOURNAL,
    archive_ledger: Path = DEFAULT_ARCHIVE_LEDGER,
) -> dict:
    attempt_dir = attempt_dir.resolve()
    archive_root = resolve_archive_root(archive_root)
    attempt_path = attempt_dir / "attempt.json"
    rosbag = attempt_dir / "raw/rosbag"
    inventory_path = attempt_dir / "raw_archive_inventory.json"
    if not attempt_path.is_file() or not rosbag.is_dir():
        raise RawArchiveError("completed attempt or source rosbag is absent")
    if inventory_path.exists():
        raise RawArchiveError("raw archive inventory already exists")
    attempt_bytes = attempt_path.read_bytes()
    attempt = json.loads(attempt_bytes)
    attempt_sha = hashlib.sha256(attempt_bytes).hexdigest()
    journaled_attempt(attempt, attempt_sha, campaign_journal.resolve())
    position = int(attempt["campaign_position"])
    trial_id = str(attempt["trial_id"])
    slot_name = f"slot_{position:06d}__{trial_id}"
    final_rosbag = archive_root / slot_name / "rosbag"
    files = copy_and_verify(rosbag, archive_root, final_rosbag)
    payload = [
        {
            "source_relative_path": item["source_relative_path"],
            "source_byte_size": item["source_byte_size"],
            "source_sha256": item["source_sha256"],
        }
        for item in files
    ]
    inventory = {
        "schema": "E3_v4_raw_archive_inventory_v1",
        "status": "RAW_ARCHIVE_VERIFIED",
        "campaign_position": position,
        "trial_id": trial_id,
        "attempt_artifact_sha256": attempt_sha,
        "archive_timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "archive_root_path": str(archive_root),
        "archive_root_identifier_sha256": hashlib.sha256(str(archive_root).encode()).hexdigest(),
        "archive_slot_relative_path": slot_name,
        "raw_payload_canonical_sha256": canonical_sha256(payload),
        "files": files,
        "all_source_archive_hashes_equal": all(
            item["source_archive_hash_equal"] for item in files
        ),
        "backup_verification_status": "RAW_ARCHIVE_VERIFIED",
        "source_retained": rosbag.is_dir(),
        "archive_retained": final_rosbag.is_dir(),
    }
    if not inventory["source_retained"] or not inventory["archive_retained"]:
        raise RawArchiveError("source/archive retention verification failed")
    durable_json(inventory_path, inventory)
    inventory_sha = sha256_file(inventory_path)
    ledger_record = {
        "schema": "E3_v4_raw_archive_ledger_record_v1",
        "campaign_position": position,
        "trial_id": trial_id,
        "attempt_artifact_sha256": attempt_sha,
        "raw_archive_inventory_sha256": inventory_sha,
        "raw_payload_canonical_sha256": inventory["raw_payload_canonical_sha256"],
        "backup_verified": True,
        "source_retained": True,
        "archive_retained": True,
    }
    append_archive_ledger(archive_ledger.resolve(), ledger_record)
    return {
        "status": inventory["status"],
        "campaign_position": position,
        "trial_id": trial_id,
        "archive_path": str(final_rosbag),
        "raw_archive_inventory_sha256": inventory_sha,
        "raw_payload_canonical_sha256": inventory["raw_payload_canonical_sha256"],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--attempt-dir", type=Path, required=True)
    parser.add_argument("--archive-root", type=Path)
    parser.add_argument("--campaign-journal", type=Path, default=DEFAULT_CAMPAIGN_JOURNAL)
    parser.add_argument("--archive-ledger", type=Path, default=DEFAULT_ARCHIVE_LEDGER)
    args = parser.parse_args()
    root = resolve_archive_root(args.archive_root)
    result = archive_attempt(
        args.attempt_dir, root, args.campaign_journal, args.archive_ledger
    )
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
