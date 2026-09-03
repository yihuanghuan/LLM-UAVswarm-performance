#!/usr/bin/env python3
"""Build the final E5-v2 formal-execution source/input bundle manifest."""

from __future__ import annotations

import argparse
from pathlib import Path

from e5_v2_activation_common import formal_execution_bundle_files
from e5_v2_common import E5_DIR, REPO_ROOT, sha256_file
from e5_v2_formal_common import TOOLING_BUNDLE_PATH, canonical_sha256, exclusive_json


EXECUTION_SOURCES = (
    "e5_v2_formal_common.py", "e5_v2_formal_adapter.py",
    "e5_v2_formal_readiness.py", "e5_v2_formal_trial.py",
    "e5_v2_formal_backend.py", "e5_v2_campaign_journal.py",
    "e5_v2_raw_storage.py", "e5_v2_formal_metrics.py",
    "e5_v2_formal_orchestrator.py",
)
EXECUTION_INPUTS = (
    "E5_v2_formal_execution_config.yaml",
    "E5_v2_formal_classification_policy_v1.md",
    "E5_v2_raw_storage_policy_v1.md",
)


def bundle_files():
    tooling = Path(__file__).parent
    files = set(formal_execution_bundle_files())
    files.update(tooling / name for name in EXECUTION_SOURCES)
    files.update(E5_DIR / name for name in EXECUTION_INPUTS)
    missing = [path for path in files if not path.is_file()]
    if missing:
        raise FileNotFoundError(f"formal bundle files missing: {missing}")
    prohibited = {"e5_v2_engineering_smoke.py", "e5_v2_wait_ready.py"}
    if any(path.name in prohibited for path in files):
        raise ValueError("engineering smoke tooling entered final formal bundle")
    return sorted(files, key=lambda path: path.relative_to(REPO_ROOT).as_posix())


def build_bundle():
    records = [{"path": path.relative_to(REPO_ROOT).as_posix(),
                "sha256": sha256_file(path)} for path in bundle_files()]
    return {
        "schema": "E5_v2_formal_execution_tooling_bundle_v1",
        "algorithm": "sha256(canonical-json(sorted repo-relative path+sha256 records))",
        "file_count": len(records),
        "files": records,
        "bundle_sha256": canonical_sha256(records),
        "supersedes_activation_stage_bundle_sha256":
            "34f0995ba4411b88dab836e639d73002e94b5a2864e44297dcdebfe62bef7119",
        "engineering_smoke_tools_included": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=TOOLING_BUNDLE_PATH)
    parser.add_argument("--replace-before-slot-1", action="store_true")
    args = parser.parse_args()
    if args.output.exists():
        if not args.replace_before_slot_1:
            raise SystemExit("refusing to replace bundle without explicit pre-slot-1 flag")
        args.output.unlink()
    exclusive_json(args.output, build_bundle())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
