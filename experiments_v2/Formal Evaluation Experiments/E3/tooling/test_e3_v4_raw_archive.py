import hashlib
import json
from pathlib import Path

import pytest

from e3_v4_raw_archive import RawArchiveError, archive_attempt, resolve_archive_root


def fixture(tmp_path: Path):
    attempt_dir = tmp_path / "attempt"
    bag = attempt_dir / "raw/rosbag"
    bag.mkdir(parents=True)
    (bag / "rosbag_0.db3").write_bytes(b"formal-raw-bag")
    (bag / "metadata.yaml").write_text("rosbag2_bagfile_information: {}\n")
    attempt = {
        "campaign_position": 2,
        "trial_id": "E3-C-02__P0_F1__S934882",
        "accepted_formal_result": True,
        "replacement_attempt": False,
    }
    attempt_path = attempt_dir / "attempt.json"
    attempt_path.write_text(json.dumps(attempt, sort_keys=True) + "\n")
    attempt_sha = hashlib.sha256(attempt_path.read_bytes()).hexdigest()
    journal = tmp_path / "campaign_journal.jsonl"
    journal.write_text(json.dumps({
        "campaign_position": 2,
        "trial_id": attempt["trial_id"],
        "attempt_artifact_sha256": attempt_sha,
    }) + "\n")
    return attempt_dir, journal, attempt_sha


def test_archive_root_is_required(monkeypatch):
    monkeypatch.delenv("E3_V4_RAW_ARCHIVE_ROOT", raising=False)
    with pytest.raises(RawArchiveError, match="archive root missing"):
        resolve_archive_root(None)


def test_completed_journaled_attempt_is_archived_and_ledgered(tmp_path):
    attempt_dir, journal, attempt_sha = fixture(tmp_path)
    archive_root = tmp_path / "independent_archive"
    ledger = tmp_path / "raw_archive_ledger.jsonl"
    result = archive_attempt(attempt_dir, archive_root, journal, ledger)
    inventory = json.loads((attempt_dir / "raw_archive_inventory.json").read_text())
    copied = archive_root / "slot_000002__E3-C-02__P0_F1__S934882/rosbag/rosbag_0.db3"
    assert result["status"] == "RAW_ARCHIVE_VERIFIED"
    assert copied.read_bytes() == b"formal-raw-bag"
    assert (attempt_dir / "raw/rosbag/rosbag_0.db3").is_file()
    assert inventory["attempt_artifact_sha256"] == attempt_sha
    assert inventory["all_source_archive_hashes_equal"] is True
    assert inventory["source_retained"] is True
    assert inventory["archive_retained"] is True
    record = json.loads(ledger.read_text())
    assert record["backup_verified"] is True
    assert record["raw_archive_inventory_sha256"] == result["raw_archive_inventory_sha256"]


def test_unjournaled_attempt_fails_closed(tmp_path):
    attempt_dir, journal, _ = fixture(tmp_path)
    journal.write_text("")
    with pytest.raises(RawArchiveError, match="not uniquely present"):
        archive_attempt(attempt_dir, tmp_path / "archive", journal, tmp_path / "ledger")


def test_existing_archive_or_inventory_is_not_overwritten(tmp_path):
    attempt_dir, journal, _ = fixture(tmp_path)
    archive_root = tmp_path / "archive"
    ledger = tmp_path / "ledger"
    archive_attempt(attempt_dir, archive_root, journal, ledger)
    with pytest.raises(RawArchiveError, match="inventory already exists"):
        archive_attempt(attempt_dir, archive_root, journal, ledger)
