#!/usr/bin/env python3
"""Generate or verify the immutable inventory for the diagnostic metric audit."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import subprocess
import sys


AUDIT_ROOT = Path(__file__).resolve().parents[1]
C0A_ROOT = AUDIT_ROOT.parent
REPOSITORY = C0A_ROOT.parents[2]
MANIFEST = AUDIT_ROOT / "AUDIT_MANIFEST.json"


def digest(path):
    value = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            value.update(block)
    return value.hexdigest()


def audit_files():
    return sorted(
        path for path in AUDIT_ROOT.rglob("*")
        if path.is_file()
        and path != MANIFEST
        and "__pycache__" not in path.parts
        and path.suffix != ".pyc"
    )


def run_gate(command):
    result = subprocess.run(command, cwd=REPOSITORY, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    return {"command": command, "returncode": result.returncode, "output": result.stdout.strip()}


def validate_semantics():
    summary = json.loads((AUDIT_ROOT / "metrics" / "audit_summary.json").read_text(encoding="utf-8"))
    v2_manifest = json.loads((C0A_ROOT / "manifest_v2.json").read_text(encoding="utf-8"))
    audit_text = (AUDIT_ROOT / "METRIC_VALIDITY_AUDIT.md").read_text(encoding="utf-8")
    draft_text = (C0A_ROOT / "C0-A-prereg-v3_DRAFT.md").read_text(encoding="utf-8")
    checks = {
        "dataset_class_diagnostic": summary["dataset_class"] == "calibration_diagnostic",
        "v2_status_preserved": v2_manifest["status"] == "NO_ACCEPTABLE_CONFIGURATION",
        "v2_formal_count_preserved": v2_manifest["formal_trial_count"] == 300,
        "v2_no_winner": all(value is None for value in v2_manifest["winners"].values()),
        "v2_no_freeze_or_tag": v2_manifest["frozen_parameter_commit"] is None and v2_manifest["checkpoint_tag"] is None,
        "v2_not_ready_for_c0_b": v2_manifest["ready_for_c0_b"] is False,
        "audit_outcome_b": "### Outcome B" in audit_text,
        "v3_post_outcome_disclosure": "C0-A-prereg-v3 is a post-outcome metric-definition amendment." in draft_text,
        "v3_not_executable": "Formal v3 trials started: `false`" in draft_text and "READY_TO_RUN_C0_A_V3 = NO" in draft_text,
        "cross_metric_count": summary["zero_crossings_cross_metric_only_count"] == 263,
        "time_series_count": summary["valid_time_series_count"] == 295,
        "jerk_failure_count": summary["command_jerk"]["failure_count"] == 31,
    }
    return checks


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--verify", action="store_true")
    args = parser.parse_args()
    algorithm_gate = run_gate([sys.executable, "experiments/calibration/scripts/check_algorithm_freeze.py"])
    ownership_gate = run_gate([
        sys.executable,
        "experiments/calibration/scripts/check_parameter_ownership.py",
        "--calibration", "C0-A",
        "--baseline-ref", "origin/paper/calibration",
    ])
    semantic_checks = validate_semantics()
    files = audit_files()
    observed = {
        path.relative_to(AUDIT_ROOT).as_posix(): {
            "bytes": path.stat().st_size,
            "sha256": digest(path),
        }
        for path in files
    }
    if args.verify:
        manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
        passed = (
            manifest["files"] == observed
            and all(semantic_checks.values())
            and algorithm_gate["returncode"] == 0
            and ownership_gate["returncode"] == 0
            and digest(C0A_ROOT / "C0-A-prereg-v3_DRAFT.md") == manifest["v3_draft_sha256"]
            and digest(C0A_ROOT / "CALIBRATION_RESULT_v2.md") == manifest["v2_result_sha256"]
            and digest(C0A_ROOT / "manifest_v2.json") == manifest["v2_manifest_sha256"]
        )
        print(json.dumps({
            "algorithm_freeze": algorithm_gate,
            "file_count": len(observed),
            "overall": "PASS" if passed else "FAIL",
            "parameter_ownership": ownership_gate,
            "semantic_checks": semantic_checks,
        }, sort_keys=True))
        return 0 if passed else 1
    if algorithm_gate["returncode"] or ownership_gate["returncode"] or not all(semantic_checks.values()):
        raise RuntimeError("audit finalization gates failed")
    source_commit = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=REPOSITORY, text=True).strip()
    manifest = {
        "audit_id": "C0-A-prereg-v2-zero-crossing-and-command-jerk-validity",
        "dataset_class": "calibration_diagnostic",
        "metric_audit_conclusion": "B",
        "source_commit": source_commit,
        "protocol_result_preserved": "C0-A-prereg-v2 NO_ACCEPTABLE_CONFIGURATION",
        "formal_trials_modified": 0,
        "diagnostic_reruns_started": 0,
        "v3_draft_only": True,
        "v3_trials_started": False,
        "parameters_changed": False,
        "parameters_frozen": False,
        "ready_to_run_c0_a_v3": False,
        "ready_for_c0_b": False,
        "algorithm_freeze": algorithm_gate,
        "parameter_ownership": ownership_gate,
        "semantic_checks": semantic_checks,
        "files": observed,
        "v2_result_sha256": digest(C0A_ROOT / "CALIBRATION_RESULT_v2.md"),
        "v2_manifest_sha256": digest(C0A_ROOT / "manifest_v2.json"),
        "v3_draft_sha256": digest(C0A_ROOT / "C0-A-prereg-v3_DRAFT.md"),
        "generated_utc": datetime.now(timezone.utc).isoformat(),
    }
    MANIFEST.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"file_count": len(observed), "manifest": str(MANIFEST), "overall": "PASS"}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
