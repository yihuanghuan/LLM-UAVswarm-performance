#!/usr/bin/env python3
"""Freeze compact, F0-only E3-v4 qualification evidence from retained pilots."""

from __future__ import annotations

import argparse
from collections import defaultdict
import hashlib
import json
from pathlib import Path
from typing import Any

import yaml


TOOLING_DIR = Path(__file__).resolve().parent
E3_DIR = TOOLING_DIR.parent
GRID_PATH = E3_DIR / "E3_v4_candidate_disturbance_grid.yaml"
SEEDS_PATH = E3_DIR / "E3_v4_qualification_seeds.yaml"
RAW_ROOT = E3_DIR / "results" / "qualification" / "raw"
ALLOWED_CONDITIONS = {"P0_F0", "P1_F0"}


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def aggregate(attempts: list[dict[str, Any]], condition: str,
              seeds: list[int]) -> dict[str, Any]:
    by_seed: dict[int, list[dict[str, Any]]] = defaultdict(list)
    for attempt in attempts:
        if attempt["condition"] == condition:
            by_seed[int(attempt["seed"])].append(attempt)
    scientific = []
    for seed in seeds:
        successful = [item for item in by_seed[seed]
                      if item["attempt_status"] == "success"]
        if len(successful) > 1:
            raise RuntimeError(f"multiple successful attempts for {condition} seed {seed}")
        if successful:
            scientific.append(successful[0])
    metrics = [item["metrics"] for item in scientific]
    if not metrics:
        return {"scientific_n": 0}
    return {
        "scientific_n": len(metrics),
        "event_attempts": sum(
            value["realized"]["hard_risk_event_count"] > 0 for value in metrics
        ),
        "event_prevalence": sum(
            value["realized"]["hard_risk_event_count"] > 0 for value in metrics
        ) / len(metrics),
        "aggregate_hard_risk_exposure_pair_s": sum(
            value["realized"]["hard_risk_exposure_pair_s"] for value in metrics
        ),
        "actual_d_min_range_m": [
            min(value["realized"]["d_min_m"] for value in metrics),
            max(value["realized"]["d_min_m"] for value in metrics),
        ],
        "affected_pair_event_attempts": sum(
            value["causal_alignment"]["affected_pair_event_count"] > 0
            for value in metrics
        ),
        "mission_success_attempts": sum(
            value["stability"]["mission_success"] for value in metrics
        ),
        "d_min_le_0p25_attempts": sum(
            value["stability"]["actual_d_min_le_0p25_m"] for value in metrics
        ),
        "seeds": [int(value["seed"]) for value in scientific],
    }


def classifications(summary: dict[str, dict[str, Any]]) -> list[str]:
    reasons = []
    if any(value.get("scientific_n") != 5 for value in summary.values()):
        reasons.append("INCOMPLETE_INFRASTRUCTURE")
        return reasons
    if any(value["event_attempts"] == 0 for value in summary.values()):
        reasons.append("REJECT_FLOOR")
    if any(value["event_attempts"] == 5 for value in summary.values()):
        reasons.append("REJECT_CEILING")
    if any(value["d_min_le_0p25_attempts"] > 0 or
           value["mission_success_attempts"] < 4 for value in summary.values()):
        reasons.append("REJECT_STABILITY")
    if any(value["event_attempts"] > value["affected_pair_event_attempts"]
           for value in summary.values()):
        reasons.append("REJECT_CAUSAL_ALIGNMENT")
    if not reasons:
        reasons.append("PASS")
    return reasons


def build() -> dict[str, Any]:
    grid = yaml.safe_load(GRID_PATH.read_text(encoding="utf-8"))
    seed_registry = yaml.safe_load(SEEDS_PATH.read_text(encoding="utf-8"))
    seeds = [int(value) for value in seed_registry["seeds"]]
    rows = []
    attempt_objects = []
    for attempt_path in sorted(RAW_ROOT.glob("E3V4Q-*/attempt.json")):
        attempt = json.loads(attempt_path.read_text(encoding="utf-8"))
        if attempt["condition"] not in ALLOWED_CONDITIONS or attempt["feedback"] != "F0":
            raise RuntimeError(f"feedback firewall violation: {attempt_path}")
        if not str(attempt["scenario_id"]).startswith("E3-B-"):
            raise RuntimeError(f"B freeze found later-family pilot: {attempt_path}")
        attempt_objects.append(attempt)
        metric_path = attempt_path.parent / "qualification_metrics.json"
        rows.append({
            "attempt_instance_id": attempt.get("attempt_instance_id", attempt["trial_id"]),
            "trial_id": attempt["trial_id"],
            "candidate_id": attempt["candidate_id"],
            "condition": attempt["condition"],
            "seed": int(attempt["seed"]),
            "attempt_status": attempt["attempt_status"],
            "error": attempt["error"],
            "retry_of": attempt.get("retry_of"),
            "attempt_json_sha256": sha256_file(attempt_path),
            "qualification_metrics_sha256": (
                sha256_file(metric_path) if metric_path.is_file() else None
            ),
            "raw_inventory_sha256": (
                attempt["metrics"].get("raw_inventory_sha256")
                if attempt.get("metrics") else None
            ),
        })

    candidates = {}
    for scenario_id in ("E3-B-01", "E3-B-02"):
        passed = False
        for candidate_id in grid["search_order"][scenario_id]:
            candidate = grid["candidates"][candidate_id]
            geometry = grid["geometries"][candidate["geometry"]]
            if candidate["disposition"] == "REJECT_ANALYTIC_IMPOSSIBILITY":
                status = ["REJECT_ANALYTIC_IMPOSSIBILITY"]
                summary = {}
            else:
                selected = [value for value in attempt_objects
                            if value["candidate_id"] == candidate_id]
                if not selected:
                    status = ["NOT_EVALUATED_AFTER_FIRST_PASS"] if passed else ["NOT_EVALUATED"]
                    summary = {}
                else:
                    summary = {
                        condition: aggregate(selected, condition, seeds)
                        for condition in ("P0_F0", "P1_F0")
                    }
                    status = classifications(summary)
                    passed = status == ["PASS"]
            candidates[candidate_id] = {
                "scenario_id": scenario_id,
                "candidate": candidate,
                "geometry": geometry,
                "classification": status,
                "condition_summary": summary,
            }

    return {
        "schema": "E3_v4_family_B_qualification_evidence_v1",
        "status": "BLOCKED_AT_E3_B_02_FINITE_GRID_EXHAUSTED",
        "dataset_class": "calibration_pilot",
        "accepted_formal_result": False,
        "feedback_conditions_present": ["F0"],
        "f1_attempt_count": 0,
        "qualification_seeds": seeds,
        "candidate_grid_sha256": sha256_file(GRID_PATH),
        "qualification_seeds_sha256": sha256_file(SEEDS_PATH),
        "attempt_count": len(rows),
        "successful_scientific_attempt_count": sum(
            row["attempt_status"] == "success" for row in rows
        ),
        "infrastructure_failure_attempt_count": sum(
            row["attempt_status"] != "success" for row in rows
        ),
        "candidates": candidates,
        "attempt_evidence": rows,
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
