#!/usr/bin/env python3
"""Build the deterministic formal-analysis-v1 tooling bundle manifest."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import subprocess

from analysis_common import canonical_bytes, canonical_sha256, sha256_file
from attempt_context import FREEZE_DIR, REPO_ROOT


def bundle_files() -> list[Path]:
    files = [FREEZE_DIR / "analysis_semantics_v1.yaml", FREEZE_DIR / "analysis_semantics_v1.md",
             FREEZE_DIR / "e2_preserved_scorer_identity.json"]
    files.extend(sorted(path for path in (FREEZE_DIR / "tooling").glob("*.py") if path.is_file()))
    files.extend(sorted(path for path in (FREEZE_DIR / "schemas").glob("*.json") if path.is_file()))
    return files


def build(source_commit: str | None = None) -> dict:
    if source_commit is None:
        source_commit = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=REPO_ROOT,
                                                text=True).strip()
    hashes = {path.relative_to(REPO_ROOT).as_posix(): sha256_file(path) for path in bundle_files()}
    manifest = {
        "schema": "formal_analysis_v1_bundle_manifest_v1",
        "analysis_version": "formal-analysis-v1",
        "analysis_semantics_version": "formal-analysis-semantics-v1",
        "branch": "formal/analysis-v1",
        "tooling_source_commit": source_commit,
        "file_count": len(hashes), "files": hashes,
        "bundle_sha256_definition": "SHA-256 of canonical JSON file-path-to-SHA-256 map",
        "formal_analysis_v1_bundle_sha256": canonical_sha256(hashes),
        "campaign_v2_created": False,
    }
    return manifest


def main() -> int:
    parser = argparse.ArgumentParser(); parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--source-commit")
    args = parser.parse_args(); manifest = build(args.source_commit)
    args.output.write_bytes(canonical_bytes(manifest))
    print(json.dumps(manifest, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__": raise SystemExit(main())
