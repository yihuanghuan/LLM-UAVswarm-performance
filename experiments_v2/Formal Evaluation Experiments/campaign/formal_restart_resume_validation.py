#!/usr/bin/env python3
"""Retain non-formal evidence from the isolated formal resume regressions."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import re
import subprocess
import sys

from campaign_common import (
    CAMPAIGN_DIR, NOT_FORMAL_RESULT, REPO_ROOT, sha256_file, utc_now,
    write_json_exclusive,
)
from formal_campaign_launcher import formal_cursor_snapshot


TEST_PATH = CAMPAIGN_DIR / "test_formal_campaign_launcher.py"
LAUNCHER_PATH = CAMPAIGN_DIR / "formal_campaign_launcher.py"


def validate() -> dict:
    before = formal_cursor_snapshot()
    environment = dict(os.environ)
    environment["PYTHONPATH"] = str(CAMPAIGN_DIR)
    command = [
        sys.executable, "-m", "pytest", "-q", str(TEST_PATH),
        "-k", "FormalRestartResumeRegressionTests",
    ]
    completed = subprocess.run(
        command, cwd=REPO_ROOT, env=environment, text=True,
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT, check=False,
    )
    after = formal_cursor_snapshot()
    match = re.search(r"(\d+) passed", completed.stdout)
    passed = int(match.group(1)) if match else 0
    status = "PASS" if completed.returncode == 0 and passed >= 8 and before == after else "FAIL"
    return {
        "manifest_type": "isolated_formal_restart_resume_regression_evidence_v1",
        "generated_at_utc": utc_now(),
        "dataset_class": "engineering_validation",
        "accepted_formal_result": False,
        "result_notice": NOT_FORMAL_RESULT,
        "status": status,
        "test_count_passed": passed,
        "pytest_returncode": completed.returncode,
        "pytest_output": completed.stdout.strip(),
        "launcher_source_sha256": sha256_file(LAUNCHER_PATH),
        "test_source_sha256": sha256_file(TEST_PATH),
        "formal_cursor_state_before": before,
        "formal_cursor_state_after": after,
        "formal_cursor_unchanged": before == after,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    report = validate()
    write_json_exclusive(args.output, report)
    print(json.dumps(report, indent=2, sort_keys=True))
    return report["status"] != "PASS"


if __name__ == "__main__":
    raise SystemExit(main())
