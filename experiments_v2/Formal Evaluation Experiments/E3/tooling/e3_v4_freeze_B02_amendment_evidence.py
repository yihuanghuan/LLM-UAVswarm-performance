#!/usr/bin/env python3
"""Freeze complete F0-only evidence for the B-02 amendment-v1 screen."""

from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import hashlib
import json
from pathlib import Path
from typing import Any

import yaml


TOOLING_DIR = Path(__file__).resolve().parent
E3_DIR = TOOLING_DIR.parent
GRID_PATH = E3_DIR / "E3_v4_B02_amendment_v1_grid.yaml"
SCREEN_SEEDS_PATH = E3_DIR / "E3_v4_qualification_seeds.yaml"
HOLDOUT_SEEDS_PATH = E3_DIR / "E3_v4_B02_holdout_qualification_seeds.yaml"
SELECTION_PATH = E3_DIR / "E3_v4_B02_amendment_screening_selection.yaml"
RAW_ROOT = E3_DIR / "results" / "qualification" / "raw"
ALLOWED_CONDITIONS = ("P0_F0", "P1_F0")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def load_attempts() -> tuple[list[tuple[Path, dict[str, Any]]], int, int]:
    amendment: list[tuple[Path, dict[str, Any]]] = []
    f1_count = 0
    holdout_count = 0
    for attempt_path in sorted(RAW_ROOT.glob("E3V4Q-*/attempt.json")):
        attempt = json.loads(attempt_path.read_text(encoding="utf-8"))
        condition = str(attempt["condition"])
        if condition.endswith("F1") or attempt.get("feedback") == "F1":
            f1_count += 1
        if attempt.get("execution_spec", {}).get("qualification_seed_role") == "holdout":
            holdout_count += 1
        if str(attempt.get("candidate_id", "")).startswith("B02-V1-"):
            amendment.append((attempt_path, attempt))
    return amendment, f1_count, holdout_count


def aggregate(attempts: list[dict[str, Any]]) -> dict[str, Any]:
    metrics = [item["metrics"] for item in attempts]
    predicted_d = [value["predicted"]["d_min_m"] for value in metrics]
    actual_d = [value["realized"]["d_min_m"] for value in metrics]
    d_min_times = [value["realized"]["d_min_time_relative_s"] for value in metrics]
    force_starts = [value["disturbance_timing"]["force_start_relative_s"] for value in metrics]
    force_ends = [value["disturbance_timing"]["force_end_relative_s"] for value in metrics]
    exposure = [value["realized"]["hard_risk_exposure_pair_s"] for value in metrics]
    event_attempts = sum(value["realized"]["hard_risk_event_count"] > 0 for value in metrics)
    affected_pair_events = sum(
        value["causal_alignment"]["affected_pair_event_count"] > 0 for value in metrics
    )
    response = {uav: [] for uav in ("2", "3")}
    for value in metrics:
        for uav in response:
            response[uav].append(value["affected_uav_response"][uav])
    return {
        "scientific_n": len(attempts),
        "seeds": [int(value["seed"]) for value in attempts],
        "predicted_d_min_range_m": [min(predicted_d), max(predicted_d)],
        "predicted_hard_violation_values": sorted({
            int(value["predicted"]["hard_violations"]) for value in metrics
        }),
        "predicted_assignment_values": sorted({
            tuple(value["predicted"]["assignment"]) for value in metrics
        }),
        "event_attempts": event_attempts,
        "event_prevalence": event_attempts / len(metrics),
        "aggregate_hard_risk_exposure_pair_s": sum(exposure),
        "actual_d_min_range_m": [min(actual_d), max(actual_d)],
        "d_min_pair_counts": dict(sorted(Counter(
            value["realized"]["d_min_pair"] for value in metrics
        ).items())),
        "d_min_time_relative_range_s": [min(d_min_times), max(d_min_times)],
        "force_start_relative_range_s": [min(force_starts), max(force_starts)],
        "force_end_relative_range_s": [min(force_ends), max(force_ends)],
        "affected_pair_event_attempts": affected_pair_events,
        "all_registered_events_after_onset": all(
            value["causal_alignment"]["all_affected_pair_events_after_onset"]
            for value in metrics if value["causal_alignment"]["affected_pair_event_count"] > 0
        ),
        "mission_success_attempts": sum(
            bool(value["stability"]["mission_success"]) for value in metrics
        ),
        "failsafe_attempts": sum(
            bool(value["stability"]["failsafe_seen"]) for value in metrics
        ),
        "d_min_le_0p25_attempts": sum(
            bool(value["stability"]["actual_d_min_le_0p25_m"]) for value in metrics
        ),
        "affected_uav_response_ranges": {
            uav: {
                field: [min(item[field] for item in values), max(item[field] for item in values)]
                for field in (
                    "max_inward_tracking_displacement_m",
                    "end_inward_tracking_displacement_m",
                    "max_inward_velocity_mps",
                    "max_ladrc_output_norm_diagnostic",
                )
            }
            for uav, values in response.items()
        },
    }


def build() -> dict[str, Any]:
    grid = yaml.safe_load(GRID_PATH.read_text(encoding="utf-8"))
    screen_registry = yaml.safe_load(SCREEN_SEEDS_PATH.read_text(encoding="utf-8"))
    holdout_registry = yaml.safe_load(HOLDOUT_SEEDS_PATH.read_text(encoding="utf-8"))
    screen_seeds = [int(value) for value in screen_registry["seeds"]]
    holdout_seeds = [int(value) for value in holdout_registry["seeds"]]
    candidate_ids = list(grid["screening_order"])

    attempts_with_paths, f1_count, holdout_count = load_attempts()
    if f1_count:
        raise RuntimeError(f"feedback firewall violated: {f1_count} F1 attempts found")
    if holdout_count:
        raise RuntimeError(f"holdout firewall violated: {holdout_count} holdout attempts found")
    if SELECTION_PATH.exists():
        raise RuntimeError("selection freeze must not exist when no screening candidate passes")

    expected = {
        (candidate, condition, seed)
        for candidate in candidate_ids
        for condition in ALLOWED_CONDITIONS
        for seed in screen_seeds
    }
    keyed: dict[tuple[str, str, int], list[tuple[Path, dict[str, Any]]]] = defaultdict(list)
    rows: list[dict[str, Any]] = []
    for attempt_path, attempt in attempts_with_paths:
        candidate = str(attempt["candidate_id"])
        condition = str(attempt["condition"])
        seed = int(attempt["seed"])
        key = (candidate, condition, seed)
        keyed[key].append((attempt_path, attempt))
        spec = attempt["execution_spec"]
        if condition not in ALLOWED_CONDITIONS or attempt.get("feedback") != "F0":
            raise RuntimeError(f"feedback firewall violation: {attempt_path}")
        if spec.get("avoidance_mode") != "off":
            raise RuntimeError(f"avoidance-mode firewall violation: {attempt_path}")
        if spec.get("qualification_seed_role") != "screening":
            raise RuntimeError(f"non-screen attempt in amendment screen: {attempt_path}")
        if attempt.get("accepted_formal_result") or attempt.get("formal_cursor_consumed"):
            raise RuntimeError(f"formal-result firewall violation: {attempt_path}")
        metric_path = attempt_path.parent / "qualification_metrics.json"
        rows.append({
            "attempt_instance_id": attempt.get("attempt_instance_id", attempt["trial_id"]),
            "trial_id": attempt["trial_id"],
            "candidate_id": candidate,
            "condition": condition,
            "seed": seed,
            "attempt_status": attempt["attempt_status"],
            "error": attempt.get("error"),
            "retry_of": attempt.get("retry_of"),
            "attempt_json_sha256": sha256_file(attempt_path),
            "qualification_metrics_sha256": (
                sha256_file(metric_path) if metric_path.is_file() else None
            ),
            "raw_inventory_sha256": (
                attempt.get("metrics", {}).get("raw_inventory_sha256")
            ),
        })

    missing = sorted(expected - set(keyed))
    unexpected = sorted(set(keyed) - expected)
    duplicates = sorted(key for key, values in keyed.items() if len(values) != 1)
    if missing or unexpected or duplicates:
        raise RuntimeError(
            f"screening key mismatch: missing={missing}, unexpected={unexpected}, "
            f"duplicates={duplicates}"
        )
    if any(attempt["attempt_status"] != "success" for _, attempt in attempts_with_paths):
        raise RuntimeError("amendment screen includes infrastructure failures")

    candidates: dict[str, Any] = {}
    passing: list[str] = []
    for candidate_id in candidate_ids:
        definition = grid["candidates"][candidate_id]
        summaries = {}
        reasons: set[str] = set()
        for condition in ALLOWED_CONDITIONS:
            selected = [
                keyed[(candidate_id, condition, seed)][0][1]
                for seed in screen_seeds
            ]
            summary = aggregate(selected)
            summaries[condition] = summary
            if summary["predicted_hard_violation_values"] != [0]:
                reasons.add("REJECT_NOMINAL_SAFETY")
            if summary["event_attempts"] == 0:
                reasons.add("REJECT_FLOOR")
            if summary["event_attempts"] == 5:
                reasons.add("REJECT_CEILING")
            if summary["aggregate_hard_risk_exposure_pair_s"] <= 0:
                reasons.add("REJECT_ZERO_EXPOSURE")
            if summary["event_attempts"] != summary["affected_pair_event_attempts"]:
                reasons.add("REJECT_CAUSAL_ALIGNMENT")
            if summary["mission_success_attempts"] < 5 or summary["failsafe_attempts"]:
                reasons.add("REJECT_STABILITY")
            if summary["d_min_le_0p25_attempts"]:
                reasons.add("REJECT_CATASTROPHIC")
        classification = sorted(reasons) if reasons else ["PASS"]
        if classification == ["PASS"]:
            passing.append(candidate_id)
        candidates[candidate_id] = {
            "definition": definition,
            "geometry": grid["geometries"][definition["geometry"]],
            "disturbance_profile": grid["disturbance_profiles"][definition["profile"]],
            "classification": classification,
            "condition_summary": summaries,
        }
    if passing:
        raise RuntimeError(f"blocked freeze invalid because candidates passed: {passing}")

    return {
        "schema": "E3_v4_B02_amendment_v1_qualification_evidence_v1",
        "status": "BLOCKED_AT_E3_B02_AMENDMENT_V1_EXHAUSTED",
        "dataset_class": "calibration_pilot",
        "accepted_formal_result": False,
        "formal_cursor_consumed": False,
        "preregistered_amendment_commit": "3b183530",
        "feedback_conditions_present": ["F0"],
        "f1_attempt_count": f1_count,
        "holdout_attempt_count": holdout_count,
        "selection_freeze_exists": SELECTION_PATH.exists(),
        "passing_candidate_ids": passing,
        "screening_seeds": screen_seeds,
        "holdout_seeds_reserved_not_run": holdout_seeds,
        "candidate_grid_sha256": sha256_file(GRID_PATH),
        "screening_seeds_sha256": sha256_file(SCREEN_SEEDS_PATH),
        "holdout_seeds_sha256": sha256_file(HOLDOUT_SEEDS_PATH),
        "attempt_count": len(rows),
        "successful_scientific_attempt_count": sum(
            row["attempt_status"] == "success" for row in rows
        ),
        "infrastructure_failure_attempt_count": sum(
            row["attempt_status"] != "success" for row in rows
        ),
        "expected_complete_key_count": len(expected),
        "candidates": candidates,
        "attempt_evidence": sorted(
            rows,
            key=lambda row: (
                candidate_ids.index(row["candidate_id"]),
                ALLOWED_CONDITIONS.index(row["condition"]),
                screen_seeds.index(row["seed"]),
            ),
        ),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    if args.output.exists():
        raise FileExistsError(f"refusing to overwrite {args.output}")
    args.output.write_text(
        json.dumps(build(), ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
