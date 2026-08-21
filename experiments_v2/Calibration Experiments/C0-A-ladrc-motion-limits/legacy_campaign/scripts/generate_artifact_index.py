#!/usr/bin/env python3
"""Create a deterministic SHA-256 inventory for the external C0-A evidence."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sys


def file_hash(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--artifact-root", type=Path, required=True)
    parser.add_argument("--verify", action="store_true")
    args = parser.parse_args()
    root = args.artifact_root.resolve()
    output = root / "artifact_index_v2.json"
    paths = sorted(path for path in root.rglob("*") if path.is_file() and path != output)
    if args.verify:
        index = json.loads(output.read_text(encoding="utf-8"))
        expected = {item["path"]: item for item in index["files"]}
        observed_paths = {path.relative_to(root).as_posix(): path for path in paths}
        missing = sorted(set(expected) - set(observed_paths))
        unexpected = sorted(set(observed_paths) - set(expected))
        mismatched = []
        for relative in sorted(set(expected) & set(observed_paths)):
            path = observed_paths[relative]
            item = expected[relative]
            if path.stat().st_size != item["bytes"] or file_hash(path) != item["sha256"]:
                mismatched.append(relative)
        passed = not missing and not unexpected and not mismatched
        print(json.dumps({
            "file_count": len(observed_paths),
            "missing": missing,
            "mismatched": mismatched,
            "overall": "PASS" if passed else "FAIL",
            "unexpected": unexpected,
        }, sort_keys=True))
        sys.exit(0 if passed else 1)
    records = []
    for path in paths:
        records.append({
            "path": path.relative_to(root).as_posix(),
            "bytes": path.stat().st_size,
            "sha256": file_hash(path),
        })
    index = {
        "artifact_root": str(root),
        "calibration_id": "C0-A",
        "file_count": len(records),
        "files": records,
        "generated_utc": datetime.now(timezone.utc).isoformat(),
        "protocol_version": "C0-A-prereg-v2",
        "total_bytes": sum(item["bytes"] for item in records),
    }
    output.write_text(json.dumps(index, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({
        "file_count": index["file_count"],
        "output": str(output),
        "total_bytes": index["total_bytes"],
    }, sort_keys=True))


if __name__ == "__main__":
    main()
