#!/usr/bin/env python3
"""Fail closed unless C0-A-prereg-v2 and its schedule are fully executable."""

from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CONFIG = ROOT / "configs" / "c0a_prereg_v2.json"
DEFAULT_SCHEDULE = ROOT / "trial_order_v2.json"
DEFAULT_OUTPUT = ROOT / "logs" / "protocol_executable_audit_v2.json"
PROTOCOL = ROOT / "CALIBRATION_PROTOCOL.md"
V1_MANIFEST = ROOT / "history" / "C0-A-prereg-v1_manifest.json"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def require(condition: bool, message: str, checks: list[str]) -> None:
    if not condition:
        raise AssertionError(message)
    checks.append(message)


def audit(config: dict, schedule: dict) -> dict:
    checks: list[str] = []
    protocol_text = PROTOCOL.read_text(encoding="utf-8")
    require(
        "Protocol version: `C0-A-prereg-v2`" in protocol_text,
        "protocol version = C0-A-prereg-v2",
        checks,
    )
    require(
        "No formal C0-A\ntrial had been executed under v1" in protocol_text,
        "v2 records pre-outcome clarification",
        checks,
    )
    require(
        schedule["protocol_sha256"] == sha256(PROTOCOL),
        "schedule protocol SHA-256 matches current v2",
        checks,
    )
    require(schedule["schedule_complete"] is True, "trial schedule complete = true", checks)
    require(
        schedule["unresolved_protocol_ambiguity"] == 0,
        "unresolved protocol ambiguity = 0",
        checks,
    )
    require(schedule["ordering_seed"] == 41999, "ordering seed = 41999", checks)
    require(schedule["potential_trial_count"] == 2889, "potential trial count = 2889", checks)
    require(schedule["stage_counts"] == {
        "A1_SCREENING": 300,
        "A1_CONFIRMATION": 300,
        "A2_SCREENING": 1134,
        "A2_CONFIRMATION": 900,
        "A3_VALIDATION": 240,
        "SCALE_VALIDATION": 15,
    }, "all stage schedule counts match v2", checks)

    entries = schedule["entries"]
    required_fields = set(schedule["required_entry_fields"])
    require(
        all(required_fields <= set(entry) for entry in entries),
        "every entry contains all required fields",
        checks,
    )
    require(
        len({entry["trial_id"] for entry in entries}) == len(entries),
        "all trial IDs are unique",
        checks,
    )
    require(
        [entry["schedule_index"] for entry in entries] == list(range(1, 2890)),
        "schedule indices are contiguous",
        checks,
    )

    by_stage: dict[str, list[dict]] = defaultdict(list)
    for entry in entries:
        by_stage[entry["stage"]].append(entry)
    a1_counts = Counter(entry["candidate_id"] for entry in by_stage["A1_SCREENING"])
    require(len(a1_counts) == 25, "A1 candidate count = 25", checks)
    require(set(a1_counts.values()) == {12}, "A1 screening trials per candidate = 12", checks)
    require(
        {entry["seed"] for entry in by_stage["A1_SCREENING"]} == {41001, 41002, 41003},
        "A1 screening seeds exact",
        checks,
    )
    require(
        {entry["duration_condition"]["value"] for entry in by_stage["A1_SCREENING"]} == {1.25},
        "A1 duration condition = 1.25*T_min",
        checks,
    )

    a1c_counts = Counter(entry["candidate_id"] for entry in by_stage["A1_CONFIRMATION"])
    require(
        a1c_counts == Counter({f"A1-RANK-{rank:02d}": 60 for rank in range(1, 6)}),
        "A1 confirmation rank slots cover 12 cases x 5 seeds",
        checks,
    )
    a2_counts = Counter(entry["candidate_id"] for entry in by_stage["A2_SCREENING"])
    require(len(a2_counts) == 18, "A2 candidate count = 18", checks)
    require(set(a2_counts.values()) == {63}, "A2 screening conditions per candidate = 63", checks)
    require(
        {entry["duration_condition"]["value"] for entry in by_stage["A2_SCREENING"]}
        == {1.0, 1.15, 1.3},
        "A2 duration stress conditions exact",
        checks,
    )
    require(
        all(
            "duration_multiplier" not in entry["candidate_parameters"]
            for entry in by_stage["A2_SCREENING"]
        ),
        "A2 duration is not part of candidate identity",
        checks,
    )
    a2c_counts = Counter(entry["candidate_id"] for entry in by_stage["A2_CONFIRMATION"])
    require(
        a2c_counts == Counter({f"A2-RANK-{rank:02d}": 180 for rank in range(1, 6)}),
        "A2 confirmation rank slots cover 12 cases x 3 durations x 5 seeds",
        checks,
    )
    a3_counts = Counter(entry["candidate_id"] for entry in by_stage["A3_VALIDATION"])
    require(len(a3_counts) == 12, "A3 clamp candidate count = 12", checks)
    require(set(a3_counts.values()) == {20}, "A3 trials per clamp candidate = 20", checks)
    require(
        {entry["duration_condition"]["value"] for entry in by_stage["A3_VALIDATION"]} == {1.25},
        "A3 duration condition = 1.25*T_min",
        checks,
    )

    scale = by_stage["SCALE_VALIDATION"]
    require(
        Counter(entry["scenario_id"] for entry in scale)
        == Counter({"C0A-M-1": 5, "C0A-M-4": 5, "C0A-M-8": 5}),
        "scale scenarios each contain five seeds",
        checks,
    )
    require(
        [entry["scenario_id"] for entry in scale]
        == ["C0A-M-1"] * 5 + ["C0A-M-4"] * 5 + ["C0A-M-8"] * 5,
        "scale condition order is M-1 then M-4 then M-8",
        checks,
    )
    require(
        all(entry["signed_displacement_id"] == "POS_X_8" for entry in scale),
        "scale per-UAV displacement is +8 m X",
        checks,
    )
    require(
        {entry["duration_condition"]["value"] for entry in scale} == {1.25},
        "scale duration = 1.25*T_min(D=8 m)",
        checks,
    )

    fixed = schedule["fixed_conditions"]
    require(fixed["control_mode"] == "ladrc_acceleration", "control mode fixed", checks)
    require(fixed["motion_style"] == "normal", "motion style fixed to normal", checks)
    require(fixed["style_gain"] == 1.0, "normal style gain = 1.0", checks)
    require(fixed["safety_factor"] == 1.0, "safety factor = 1.0", checks)
    require(fixed["avoidance_mode"] == "iapf_dual", "avoidance mode fixed", checks)
    require(fixed["iapf_escape_mode"] == "id_order", "escape mode fixed", checks)

    for name, expected in config["v1_archive_sha256"].items():
        require(
            sha256(ROOT / "history" / name) == expected,
            f"v1 archive hash preserved: {name}",
            checks,
        )
    v1_manifest = json.loads(V1_MANIFEST.read_text(encoding="utf-8"))
    require(v1_manifest["formal_trials_started"] is False, "v1 formal trials = 0", checks)
    require(v1_manifest["trial_count"] == 0, "v1 trial count = 0", checks)
    require(v1_manifest["selected_candidate"] is None, "v1 selected candidate = null", checks)
    require(v1_manifest["frozen_parameter_commit"] is None, "v1 freeze commit = null", checks)
    require(v1_manifest["checkpoint_tag"] is None, "v1 checkpoint tag = null", checks)

    return {
        "protocol_version": config["protocol_version"],
        "protocol_sha256": sha256(PROTOCOL),
        "trial_schedule_sha256": sha256(DEFAULT_SCHEDULE),
        "trial_schedule_complete": True,
        "unresolved_protocol_ambiguity": 0,
        "potential_trial_count": len(entries),
        "checks_passed": len(checks),
        "checks": checks,
        "status": "PASS",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--schedule", type=Path, default=DEFAULT_SCHEDULE)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    config = json.loads(args.config.read_text(encoding="utf-8"))
    schedule = json.loads(args.schedule.read_text(encoding="utf-8"))
    result = audit(config, schedule)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print("protocol version = C0-A-prereg-v2")
    print("trial schedule complete = true")
    print("unresolved protocol ambiguity = 0")
    print(f"protocol executable audit = PASS ({result['checks_passed']} checks)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
