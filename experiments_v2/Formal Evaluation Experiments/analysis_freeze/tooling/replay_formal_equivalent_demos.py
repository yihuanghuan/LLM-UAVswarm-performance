#!/usr/bin/env python3
"""Deterministically replay all retained E3/E4/E5 engineering-validation demos."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Callable

from analysis_common import (ANALYSIS_VERSION, SEMANTICS_VERSION, canonical_bytes,
                             canonical_sha256, file_inventory)
from attempt_context import REPO_ROOT
from e3_live_metric_extractor import extract as extract_e3
from e4a_live_metric_extractor import extract as extract_e4a
from e4b_live_metric_extractor import extract as extract_e4b
from e5_live_metric_extractor import extract as extract_e5
from population_analysis import population_result


WORKSPACE = REPO_ROOT.parent
DEFAULT_MATRIX = (WORKSPACE / "e3_adapter_worktree/experiments_v2/Formal Evaluation Experiments/"
                  "formal_equivalent_demos/formal_equivalent_demo_matrix.json")
ROOTS = {
    "E3": WORKSPACE / "e3_adapter_worktree/experiments_v2/Formal Evaluation Experiments/formal_equivalent_demos/E3",
    "E4A": WORKSPACE / "e4a_adapter_worktree/experiments_v2/Formal Evaluation Experiments/formal_equivalent_demos/E4A",
    "E4B": WORKSPACE / "e4b_adapter_worktree/experiments_v2/Formal Evaluation Experiments/formal_equivalent_demos/E4B",
    "E5": WORKSPACE / "e5_adapter_worktree/experiments_v2/Formal Evaluation Experiments/formal_equivalent_demos/E5",
}
EXTRACTORS: dict[str, Callable[..., dict[str, Any]]] = {
    "E3": extract_e3, "E4A": extract_e4a, "E4B": extract_e4b, "E5": extract_e5,
}


def fail_closed_record(family: str, demo_id: str, attempt_dir: Path,
                       inventory: dict[str, str], exc: Exception) -> dict[str, Any]:
    manifest = json.loads((attempt_dir / "demo_manifest.json").read_text())
    record = {
        "schema": "live_attempt_analysis_result_v1",
        "analysis_version": ANALYSIS_VERSION,
        "analysis_semantics_version": SEMANTICS_VERSION,
        "dataset_class": "engineering_validation",
        "accepted_formal_result": False,
        "scientific_use": "analysis_tool_validation_only",
        "result_notice": "NOT_FORMAL_RESULT",
        "experiment": family, "trial_id": manifest.get("registered_trial_id"),
        "demo_instance_id": demo_id,
        "raw_attempt_identity_sha256": canonical_sha256(inventory),
        "analysis_status": "FAIL_CLOSED",
        "terminal_attempt_classification": manifest.get("scientific_outcome", {}).get(
            "backend_terminal_status", "infrastructure_failure"),
        "infrastructure_status": manifest.get("infrastructure_status"),
        "fail_closed_error": {"type": type(exc).__name__, "message": str(exc)},
        "metrics": {}, "source_coverage": {}, "scored_interval": None,
    }
    record["canonical_result_sha256"] = canonical_sha256(record)
    return record


def run(matrix_path: Path, output_root: Path) -> dict[str, Any]:
    matrix = json.loads(matrix_path.read_text())
    records = []
    deterministic = True
    by_family = {}
    output_root.mkdir(parents=True, exist_ok=True)
    for family in ("E3", "E4A", "E4B", "E5"):
        ids = matrix["by_family"][family]["demo_instance_ids"]
        family_counts = {"attempts": 0, "complete": 0, "partial": 0, "fail_closed": 0,
                         "deterministic": 0, "canonical_hashes": {}}
        family_dir = output_root / family
        family_dir.mkdir(parents=True, exist_ok=True)
        for demo_id in ids:
            attempt_dir = ROOTS[family] / demo_id
            inventory = file_inventory(attempt_dir)
            try:
                first = EXTRACTORS[family](attempt_dir, raw_inventory=inventory)
                second = EXTRACTORS[family](attempt_dir, raw_inventory=inventory)
            except Exception as exc:
                first = fail_closed_record(family, demo_id, attempt_dir, inventory, exc)
                second = fail_closed_record(family, demo_id, attempt_dir, inventory, exc)
            same = canonical_bytes(first) == canonical_bytes(second)
            deterministic = deterministic and same
            if not same:
                raise RuntimeError(f"nondeterministic extractor output for {demo_id}")
            (family_dir / f"{demo_id}.json").write_bytes(canonical_bytes(first))
            records.append(first)
            status = first["analysis_status"]
            family_counts["attempts"] += 1
            if status == "COMPLETE": family_counts["complete"] += 1
            elif status == "FAIL_CLOSED": family_counts["fail_closed"] += 1
            else: family_counts["partial"] += 1
            family_counts["deterministic"] += int(same)
            family_counts["canonical_hashes"][demo_id] = first["canonical_result_sha256"]
        by_family[family] = family_counts
    population = population_result(records)
    (output_root / "population_preparation.json").write_bytes(canonical_bytes(population))
    summary = {
        "schema": "formal_equivalent_demo_analysis_replay_v1",
        "analysis_version": ANALYSIS_VERSION,
        "dataset_class": "engineering_validation", "accepted_formal_result": False,
        "scientific_use": "analysis_tool_validation_only", "result_notice": "NOT_FORMAL_RESULT",
        "attempt_count": len(records), "by_family": by_family,
        "deterministic_double_replay": deterministic,
        "population_preparation_sha256": population["canonical_population_sha256"],
        "scientific_effect_interpretation_performed": False,
    }
    summary["canonical_replay_summary_sha256"] = canonical_sha256(summary)
    (output_root / "replay_summary.json").write_bytes(canonical_bytes(summary))
    return summary


def finalize_existing(matrix_path: Path, output_root: Path) -> dict[str, Any]:
    """Finalize a completed double replay if population preparation was interrupted."""
    matrix = json.loads(matrix_path.read_text())
    records = []; by_family = {}
    for family in ("E3", "E4A", "E4B", "E5"):
        ids = matrix["by_family"][family]["demo_instance_ids"]
        counts = {"attempts": 0, "complete": 0, "partial": 0, "fail_closed": 0,
                  "deterministic": 0, "canonical_hashes": {}}
        for demo_id in ids:
            path = output_root / family / f"{demo_id}.json"
            record = json.loads(path.read_text())
            recorded_hash = record.pop("canonical_result_sha256")
            if canonical_sha256(record) != recorded_hash:
                raise RuntimeError(f"retained replay result hash mismatch: {demo_id}")
            record["canonical_result_sha256"] = recorded_hash
            records.append(record); counts["attempts"] += 1; counts["deterministic"] += 1
            status = record["analysis_status"]
            if status == "COMPLETE": counts["complete"] += 1
            elif status == "FAIL_CLOSED": counts["fail_closed"] += 1
            else: counts["partial"] += 1
            counts["canonical_hashes"][demo_id] = recorded_hash
        by_family[family] = counts
    population = population_result(records)
    (output_root / "population_preparation.json").write_bytes(canonical_bytes(population))
    summary = {
        "schema": "formal_equivalent_demo_analysis_replay_v1", "analysis_version": ANALYSIS_VERSION,
        "dataset_class": "engineering_validation", "accepted_formal_result": False,
        "scientific_use": "analysis_tool_validation_only", "result_notice": "NOT_FORMAL_RESULT",
        "attempt_count": len(records), "by_family": by_family,
        "deterministic_double_replay": True,
        "population_preparation_sha256": population["canonical_population_sha256"],
        "scientific_effect_interpretation_performed": False,
    }
    summary["canonical_replay_summary_sha256"] = canonical_sha256(summary)
    (output_root / "replay_summary.json").write_bytes(canonical_bytes(summary))
    return summary


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--matrix", type=Path, default=DEFAULT_MATRIX)
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--finalize-existing", action="store_true")
    args = parser.parse_args()
    function = finalize_existing if args.finalize_existing else run
    print(json.dumps(function(args.matrix, args.output_root), sort_keys=True, indent=2))
    return 0


if __name__ == "__main__": raise SystemExit(main())
