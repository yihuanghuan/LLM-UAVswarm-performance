#!/usr/bin/env python3
"""Record immutable configuration hashes after pilot acceptance."""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
from pathlib import Path


EXPERIMENT_ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("pilot_batch", type=Path)
    args = parser.parse_args()
    if not (args.pilot_batch / "PILOT_ACCEPTED").is_file():
        raise ValueError("pilot has not been accepted")
    files = sorted(
        path for path in (EXPERIMENT_ROOT / "configs").rglob("*")
        if path.is_file())
    manifest = {
        "experiment": "09",
        "pilot_batch": args.pilot_batch.name,
        "source_commit": subprocess.run(
            ["git", "rev-parse", "HEAD"], check=True, text=True,
            stdout=subprocess.PIPE).stdout.strip(),
        "files": [{
            "path": str(path.relative_to(EXPERIMENT_ROOT)),
            "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        } for path in files],
    }
    output = args.pilot_batch / "frozen_protocol.json"
    output.write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")
    print(output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
