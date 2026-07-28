#!/usr/bin/env python3
"""Write SHA-256 and byte-size manifests for experiment artifacts."""

import argparse
import hashlib
import json
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("batch_dir", type=Path)
    args = parser.parse_args()
    manifest = []
    for path in sorted(args.batch_dir.rglob("*")):
        if not path.is_file() or path.name == "artifact_checksums.json":
            continue
        digest = hashlib.sha256()
        with path.open("rb") as handle:
            for block in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(block)
        manifest.append({
            "path": str(path.relative_to(args.batch_dir)),
            "bytes": path.stat().st_size,
            "sha256": digest.hexdigest(),
        })
    output = args.batch_dir / "artifact_checksums.json"
    output.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    print(output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
