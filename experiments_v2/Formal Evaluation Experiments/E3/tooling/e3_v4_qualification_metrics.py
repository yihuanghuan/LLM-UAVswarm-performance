#!/usr/bin/env python3
"""Extract E3-v4 qualification-only F0 manipulation metrics from retained raw data."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path
import sys
from typing import Any

import numpy as np

TOOLING_DIR = Path(__file__).resolve().parent
E3_DIR = TOOLING_DIR.parent
FORMAL_DIR = E3_DIR.parent
ANALYSIS_TOOLS = FORMAL_DIR / "analysis_freeze" / "tooling"
sys.path.insert(0, str(ANALYSIS_TOOLS))

from live_metric_helpers import command_time, pairwise_distance_metrics  # noqa: E402
from rosbag_evidence import read_bag, records_for  # noqa: E402


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def canonical_sha256(value: Any) -> str:
    payload = json.dumps(value, ensure_ascii=False, sort_keys=True,
                         separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def raw_inventory(raw_dir: Path) -> tuple[dict[str, str], str]:
    files = {
        path.relative_to(raw_dir).as_posix(): sha256_file(path)
        for path in sorted(raw_dir.rglob("*"))
        if path.is_file() and path.name != "qualification_metrics.json"
    }
    return files, canonical_sha256(files)


def _point(value: Any) -> np.ndarray:
    return np.array([float(value.x), float(value.y), float(value.z)])


def _vector(value: Any) -> np.ndarray:
    return np.array([float(value.x), float(value.y), float(value.z)])


def extract(raw_dir: Path) -> dict[str, Any]:
    raw_dir = Path(raw_dir).resolve()
    spec = json.loads((raw_dir / "runtime_spec.json").read_text(encoding="utf-8"))
    interaction = json.loads((raw_dir / "interaction_result.json").read_text(encoding="utf-8"))
    physical = json.loads((raw_dir / "physical_result.json").read_text(encoding="utf-8"))
    if spec.get("dataset_class") != "calibration_pilot":
        raise ValueError("qualification extractor refuses non-pilot data")
    if spec.get("avoidance_mode") != "off":
        raise ValueError("qualification extractor refuses feedback-on data")

    suffixes = ("/execution_command", "/swarm_state", "/control_tracking_debug",
                "/status", "/disturbance_arm")
    records = read_bag(raw_dir / "rosbag", lambda topic: topic.endswith(suffixes))
    mission_id = int(interaction["mission_id"])
    t0 = command_time(records, mission_id)
    end = t0 + float(spec["duration_s"]) + 2.0
    distance, coverage = pairwise_distance_metrics(
        records, [int(value) for value in spec["uav_ids"]], t0, end,
        float(spec["allocator_diagnostics"]["d_hard"]),
    )

    arm_records = [record for record in records if record.topic == "/e3/disturbance_arm"]
    if len(arm_records) != 1:
        raise ValueError(f"expected exactly one disturbance arm record, got {len(arm_records)}")
    arm_offset = float(arm_records[0].bag_timestamp - t0)
    force_start = arm_offset + float(spec["disturbance"]["onset_s"])
    force_end = force_start + float(spec["disturbance"]["duration_s"])

    affected = {}
    for uid in [int(value) for value in spec["disturbance"]["affected_uavs"]]:
        vector = spec["disturbance"]["vectors_N"]
        force = np.array(vector.get(str(uid), vector.get(uid)), dtype=float)
        unit = force / np.linalg.norm(force)
        subset = [
            record for record in records
            if record.topic == f"/uav{uid}/control_tracking_debug"
            and t0 + force_start <= record.timestamp <= t0 + force_end
        ]
        displacement = [
            float(np.dot(_point(record.message.actual_position)
                         - _point(record.message.nominal_position), unit))
            for record in subset
        ]
        velocity = [float(np.dot(_vector(record.message.actual_velocity), unit))
                    for record in subset]
        ladrc = [float(np.linalg.norm(_vector(record.message.ladrc_output)))
                 for record in subset]
        affected[str(uid)] = {
            "sample_count": len(subset),
            "max_inward_tracking_displacement_m": max(displacement) if displacement else None,
            "end_inward_tracking_displacement_m": displacement[-1] if displacement else None,
            "max_inward_velocity_mps": max(velocity) if velocity else None,
            "max_ladrc_output_norm_diagnostic": max(ladrc) if ladrc else None,
        }

    statuses = records_for(records, "/status", mission_id=mission_id)
    failsafe = any(bool(record.message.failsafe) for record in statuses)
    minimum = distance["actual_d_min"]
    risk = distance["hard_risk_pair_diagnostics"]
    affected_pair = "-".join(map(str, sorted(spec["disturbance"]["affected_uavs"])))
    affected_events = risk.get(affected_pair, {}).get("events", [])
    event_starts_relative = []
    for event in affected_events:
        start = event.get("start", event.get("start_time", event.get("start_s")))
        if start is not None:
            event_starts_relative.append(float(start) - t0)

    inventory, inventory_sha = raw_inventory(raw_dir)
    mission_success = bool(
        physical.get("attempt_status") == "success"
        and interaction.get("success")
        and interaction.get("termination_reason") == "SUCCESS"
        and not failsafe
    )
    result = {
        "schema": "E3_v4_qualification_metrics_v1",
        "dataset_class": "calibration_pilot",
        "accepted_formal_result": False,
        "result_notice": "NOT_FORMAL_RESULT",
        "trial_id": spec["trial_id"],
        "candidate_id": spec["candidate_id"],
        "scenario_id": spec["scenario_id"],
        "condition": spec["condition"],
        "seed": int(spec["seed"]),
        "feedback": "F0",
        "predicted": {
            "d_min_m": float(spec["allocator_metrics"]["min_distance"]),
            "hard_violations": int(spec["allocator_metrics"]["hard_violations"]),
            "assignment": spec["allocator_diagnostics"]["final_assignment"],
        },
        "realized": {
            "d_min_m": float(minimum["value"]),
            "d_min_pair": minimum["pair"],
            "d_min_time_relative_s": float(minimum["timestamp"] - t0),
            "hard_risk_event_count": int(distance["hard_risk_event_count"]["value"]),
            "hard_risk_exposure_pair_s": float(distance["hard_risk_exposure_duration"]["value"]),
            "any_pair_hard_risk_duration_s": float(distance["any_pair_hard_risk_duration"]["value"]),
            "pair_diagnostics": risk,
        },
        "causal_alignment": {
            "affected_pair": affected_pair,
            "affected_pair_event_count": int(risk.get(affected_pair, {}).get("event_count", 0)),
            "affected_pair_event_starts_relative_s": event_starts_relative,
            "all_affected_pair_events_after_onset": bool(event_starts_relative) and all(
                start >= force_start for start in event_starts_relative
            ),
        },
        "disturbance_timing": {
            "arm_offset_from_t0_s": arm_offset,
            "force_start_relative_s": force_start,
            "force_end_relative_s": force_end,
        },
        "affected_uav_response": affected,
        "stability": {
            "mission_success": mission_success,
            "physical_attempt_status": physical.get("attempt_status"),
            "interaction_termination_reason": interaction.get("termination_reason"),
            "failsafe_seen": failsafe,
            "actual_d_min_le_0p25_m": float(minimum["value"]) <= 0.25,
            "vehicle_contact_topic_registered": False,
        },
        "coverage": coverage,
        "runtime_spec_sha256": sha256_file(raw_dir / "runtime_spec.json"),
        "raw_inventory": inventory,
        "raw_inventory_sha256": inventory_sha,
    }
    if not math.isfinite(result["realized"]["d_min_m"]):
        raise ValueError("non-finite realized minimum")
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("raw_dir", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    value = extract(args.raw_dir)
    text = json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    if args.output:
        if args.output.exists():
            raise FileExistsError(f"refusing to overwrite {args.output}")
        args.output.write_text(text, encoding="utf-8")
    else:
        print(text, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
