#!/usr/bin/env python3
"""Build the final E5-v2 formal-execution source/input bundle manifest."""

from __future__ import annotations

import argparse
from pathlib import Path

from e5_v2_activation_common import formal_execution_bundle_files
from e5_v2_common import E5_DIR, REPO_ROOT, sha256_file
from e5_v2_formal_common import (
    RECOVERY_BUNDLE_PATH, TOOLING_BUNDLE_V2_PATH, canonical_sha256, exclusive_json,
)


EXECUTION_SOURCES = (
    "e5_v2_formal_common.py", "e5_v2_formal_adapter.py",
    "e5_v2_formal_readiness.py", "e5_v2_formal_trial.py",
    "e5_v2_formal_backend.py", "e5_v2_campaign_journal.py",
    "e5_v2_raw_storage.py", "e5_v2_formal_metrics.py",
    "e5_v2_formal_orchestrator.py", "e5_v2_formal_environment.sh",
)
EXECUTION_INPUTS = (
    "E5_v2_formal_execution_config.yaml",
    "E5_v2_formal_classification_policy_v1.md",
    "E5_v2_raw_storage_policy_v1.md",
    "E5_v2_endpoint_availability_adjudication_v1.json",
    "E5_v2_remaining_endpoint_mapping_audit.json",
    "E5_v2_formal_infrastructure_amendment_v1.json",
)
RECOVERY_SOURCES = (
    "e5_v2_formal_common.py", "e5_v2_formal_adapter.py",
    "e5_v2_campaign_journal.py", "e5_v2_raw_storage.py",
    "e5_v2_formal_metrics.py", "e5_v2_recover_preserved_attempt.py",
    "e5_v2_formal_environment.sh",
)
RECOVERY_INPUTS = (
    "E5_v2_registry.yaml", "E5_v2_seed_registry.yaml",
    "E5_v2_formal_trial_order.txt", "E5_v2_analysis_contract.md",
    "E5_v2_endpoint_availability_adjudication_v1.json",
    "E5_v2_remaining_endpoint_mapping_audit.json",
    "E5_v2_formal_infrastructure_amendment_v1.json",
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


def recovery_bundle_files():
    tooling = Path(__file__).parent
    files = {tooling / name for name in RECOVERY_SOURCES}
    files.update(E5_DIR / name for name in RECOVERY_INPUTS)
    files.add(REPO_ROOT / "lfs_policy/config/lfs_policy.paper_current.yaml")
    missing = [path for path in files if not path.is_file()]
    if missing:
        raise FileNotFoundError(f"recovery bundle files missing: {missing}")
    return sorted(files, key=lambda path: path.relative_to(REPO_ROOT).as_posix())


def _build(files, schema):
    records = [{"path": path.relative_to(REPO_ROOT).as_posix(),
                "sha256": sha256_file(path)} for path in files]
    return {
        "schema": schema,
        "algorithm": "sha256(canonical-json(sorted repo-relative path+sha256 records))",
        "file_count": len(records),
        "files": records,
        "bundle_sha256": canonical_sha256(records),
        "original_slot1_physical_execution_bundle_sha256":
            "422d82b593ba927dffaee3c14bcf8b6996304a8ae302cdc525ab3c525b786ecb",
        "engineering_smoke_tools_included": False,
    }


def build_execution_bundle_v2():
    result = _build(bundle_files(), "E5_v2_formal_execution_tooling_bundle_v2")
    result["scope"] = "future physical formal slots 2 through 60"
    result["requires_completed_prefix_length"] = 1
    result["next_start_position"] = 2
    return result


def build_recovery_bundle_v1():
    result = _build(recovery_bundle_files(), "E5_v2_slot1_recovery_tooling_bundle_v1")
    result["scope"] = "preserved slot-1 transaction recovery only"
    result["physical_execution_available"] = False
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--kind", choices=("recovery-v1", "execution-v2"), required=True)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    output = args.output or (
        RECOVERY_BUNDLE_PATH if args.kind == "recovery-v1" else TOOLING_BUNDLE_V2_PATH)
    if output.exists():
        raise SystemExit(f"refusing to replace frozen bundle: {output}")
    bundle = (build_recovery_bundle_v1() if args.kind == "recovery-v1"
              else build_execution_bundle_v2())
    exclusive_json(output, bundle)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
