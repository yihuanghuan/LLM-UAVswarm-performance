#!/usr/bin/env python3
"""Lock the first passing C0-F candidate and stop parameter search."""
from __future__ import annotations

import csv
from datetime import datetime, timezone
import shutil
import subprocess

import yaml

from common import CANONICAL_POLICY, RESULTS, SCENES_FILE, START_SHA, load_yaml, sha256


def passing(path, expected):
    with path.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    if len(rows) != expected or any(row["condition_result"] != "PASS" for row in rows):
        raise SystemExit(f"cannot lock: {path.name} is not {expected}/{expected} PASS")
    return rows


def main() -> None:
    screening = passing(RESULTS / "screening_results.csv", 12)
    with (RESULTS / "style_switch_smoke.csv").open(newline="", encoding="utf-8") as handle:
        smokes = list(csv.DictReader(handle))
    screen_smoke = [row for row in smokes if row["stage"] == "style_switch_screening"]
    if len(screen_smoke) != 1 or screen_smoke[0]["condition_result"] != "PASS":
        raise SystemExit("cannot lock: alpha=1.0 style-switch screening smoke failed")
    policy = load_yaml(CANONICAL_POLICY)
    policy_hash = sha256(CANONICAL_POLICY)
    prelock_commit = subprocess.check_output(
        ["git", "rev-parse", "HEAD"], cwd=CANONICAL_POLICY.parents[2], text=True
    ).strip()
    lock = {
        "schema_version": "c0f-candidate-lock-v1",
        "status": "LOCKED_NO_RETUNING",
        "locked_utc": datetime.now(timezone.utc).isoformat(),
        "source_commit": START_SHA,
        "prelock_tooling_commit": prelock_commit,
        "source_configuration_id": policy["configuration_id"],
        "policy_sha256": policy_hash,
        "auto_style_factors": policy["timing"]["auto_style_factors"],
        "style_gains": policy["execution_profile"]["style_gains"],
        "smoothing_alpha": policy["controller_hard_clamps"]["smoothing_alpha"],
        "task_adaptation_type": policy["execution_profile"]["task_adaptation_type"],
        "task_gain": 1.0,
        "selection_rule": [
            "hard-safety/dynamic-feasibility", "mission/stability",
            "saturation/clamp", "semantic-ordering", "tracking/final-error",
            "minimum-deviation-from-provisional",
        ],
        "screening": {"valid": len(screening), "required": 12, "result": "PASS"},
        "style_switch_screening": {"valid": 1, "required": 1, "result": "PASS"},
        "evidence_sha256": {
            "screening_results.csv": sha256(RESULTS / "screening_results.csv"),
            "style_switch_smoke.csv": sha256(RESULTS / "style_switch_smoke.csv"),
            "scene_definitions.yaml": sha256(SCENES_FILE),
        },
        "fallback_stage_entered": False,
        "parameter_search_stopped": True,
    }
    RESULTS.mkdir(parents=True, exist_ok=True)
    (RESULTS / "candidate_lock.yaml").write_text(
        yaml.safe_dump(lock, sort_keys=False), encoding="utf-8"
    )
    shutil.copyfile(CANONICAL_POLICY, RESULTS / "locked_candidate_policy.yaml")
    if sha256(RESULTS / "locked_candidate_policy.yaml") != policy_hash:
        raise SystemExit("locked policy copy hash mismatch")


if __name__ == "__main__":
    main()
