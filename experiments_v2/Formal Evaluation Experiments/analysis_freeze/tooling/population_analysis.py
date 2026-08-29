#!/usr/bin/env python3
"""Frozen population preparation and descriptive paired-effect infrastructure."""

from __future__ import annotations

from collections import defaultdict
import math
from typing import Any, Callable, Iterable, Sequence

import numpy as np
from scipy import stats
import yaml

from analysis_common import EvidenceError, canonical_sha256
from attempt_context import FORMAL_ROOT


def _registries() -> tuple[dict[str, Any], dict[str, Any]]:
    e3 = yaml.safe_load((FORMAL_ROOT / "E3/e3_factorial_registry_v3.yaml").read_text())
    e4 = yaml.safe_load((FORMAL_ROOT / "E4/e4_motion_style_registry_v1.yaml").read_text())
    return e3, e4


def expected_e3_trials() -> set[str]:
    registry, _ = _registries()
    return {f"{scenario['scenario_id']}__{condition}__S{seed}"
            for scenario in registry["scenarios"]
            for condition in registry["factorial_mapping"]["conditions"]
            for seed in registry["paired_seeds"]}


def expected_e4a_trials() -> set[str]:
    _, registry = _registries()
    return {f"{scenario['scenario_id']}__{style}__S{seed}"
            for scenario in registry["E4_A"]["scenarios"]
            for style in registry["common"]["styles"]
            for seed in registry["E4_A"]["seeds"]}


def expected_e4b_trials() -> set[str]:
    _, registry = _registries()
    return {f"{scenario['scenario_id']}__{style}__S{seed}"
            for scenario in registry["E4_B"]["scenarios"]
            for style in registry["common"]["styles"]
            for seed in registry["E4_B"]["seeds"]}


def expected_e5_trials() -> set[str]:
    registry = yaml.safe_load((FORMAL_ROOT / "E5/e5_end_to_end_registry_v1.yaml").read_text())
    return {f"{scenario['scenario_id']}__Full_Method__S{seed}"
            for scenario in registry["scenarios"] for seed in registry["seeds"]}


def assert_exact_trials(records: Sequence[dict[str, Any]], experiment: str,
                        expected: set[str]) -> None:
    observed = [record["trial_id"] for record in records if record.get("experiment") == experiment]
    if len(observed) != len(expected) or set(observed) != expected:
        raise EvidenceError(f"{experiment} population is not the exact registered membership")


def descriptive(values: Sequence[float | None]) -> dict[str, Any]:
    valid = np.asarray([float(value) for value in values if value is not None and math.isfinite(float(value))])
    na_n = len(values) - valid.size
    if valid.size == 0:
        return {"valid_N": 0, "NA_N": na_n, "mean": None, "standard_deviation": None,
                "median": None, "IQR": None, "q1": None, "q3": None,
                "mean_95pct_t_CI": None}
    q1, median, q3 = np.quantile(valid, [0.25, 0.5, 0.75], method="linear")
    sd = float(np.std(valid, ddof=1)) if valid.size >= 2 else None
    ci = None
    if valid.size >= 2:
        half = float(stats.t.ppf(0.975, valid.size - 1) * sd / math.sqrt(valid.size))
        ci = [float(np.mean(valid) - half), float(np.mean(valid) + half)]
    return {"valid_N": int(valid.size), "NA_N": int(na_n), "mean": float(np.mean(valid)),
            "standard_deviation": sd, "median": float(median), "IQR": float(q3 - q1),
            "q1": float(q1), "q3": float(q3), "mean_95pct_t_CI": ci}


def paired_effect(first: Sequence[float], second: Sequence[float]) -> dict[str, Any]:
    if len(first) != len(second) or not first:
        raise EvidenceError("paired effect requires equal nonempty paired samples")
    differences = np.asarray(second, dtype=float) - np.asarray(first, dtype=float)
    if not np.all(np.isfinite(differences)):
        raise EvidenceError("paired effect received non-finite values")
    summary = descriptive(differences.tolist())
    sd = summary["standard_deviation"]
    summary.update({"direction": "second-minus-first", "paired_differences": differences.tolist(),
                    "cohen_dz": None if sd in (None, 0.0) else float(np.mean(differences) / sd)})
    return summary


def metric_number(record: dict[str, Any], name: str) -> float | None:
    item = record.get("metrics", {}).get(name)
    if not isinstance(item, dict) or item.get("valid") is not True:
        return None
    value = item.get("value")
    return float(value) if isinstance(value, (int, float)) and not isinstance(value, bool) else None


def assert_unique(records: Iterable[dict[str, Any]], key: Callable[[dict[str, Any]], tuple[Any, ...]]) -> None:
    seen = set()
    for record in records:
        current = key(record)
        if current in seen:
            raise EvidenceError(f"duplicate population member: {current}")
        seen.add(current)


def prepare_e3(records: Sequence[dict[str, Any]], *, strict_complete_factorial: bool = True) -> dict[str, Any]:
    e3 = [record for record in records if record.get("experiment") == "E3"]
    parsed = []
    for record in e3:
        trial = record["trial_id"]
        scenario, condition, seed_text = trial.split("__")
        planning, feedback = condition.split("_")
        parsed.append((scenario, int(seed_text[1:]), planning, feedback, record))
    assert_unique([x[-1] for x in parsed], lambda r: (r["trial_id"], r.get("demo_instance_id")))
    cells: dict[tuple[str, int], dict[str, list[dict[str, Any]]]] = defaultdict(lambda: defaultdict(list))
    for scenario, seed, planning, feedback, record in parsed:
        condition = f"{planning}_{feedback}"
        cells[(scenario, seed)][condition].append(record)
    required = {"P0_F0", "P0_F1", "P1_F0", "P1_F1"}
    missing = {f"{scenario}__S{seed}": sorted(required - set(group))
               for (scenario, seed), group in cells.items() if set(group) != required}
    duplicates = {f"{scenario}__S{seed}__{condition}": [r.get("demo_instance_id") for r in members]
                  for (scenario, seed), group in cells.items() for condition, members in group.items()
                  if len(members) > 1}
    observed_trials = [record["trial_id"] for record in e3]
    expected = expected_e3_trials()
    population_missing = sorted(expected - set(observed_trials))
    population_extra = sorted(set(observed_trials) - expected)
    if strict_complete_factorial and (missing or duplicates or population_missing or population_extra
                                      or len(observed_trials) != len(expected)):
        raise EvidenceError("invalid E3 exact registered population membership")
    return {"pairing_keys": ["scenario", "seed", "planning", "feedback"],
            "group_count": len(cells), "missing_cells": missing, "diagnostic_duplicate_cells": duplicates,
            "expected_formal_attempt_count": len(expected), "observed_attempt_count": len(observed_trials),
            "missing_registered_trial_count": len(population_missing), "extra_trial_ids": population_extra,
            "supports_contrasts": ["planning under fixed feedback", "feedback under fixed planning",
                                   "Full versus individual mechanisms", "reactive burden",
                                   "predicted versus actual risk"]}


def prepare_e4a(records: Sequence[dict[str, Any]], *, strict_style_triplets: bool = True) -> dict[str, Any]:
    groups: dict[tuple[str, int], set[str]] = defaultdict(set)
    identities: dict[tuple[str, int], set[str]] = defaultdict(set)
    observed_trials = []
    for record in records:
        if record.get("experiment") != "E4A": continue
        scenario, style, seed_text = record["trial_id"].split("__")
        key = (scenario, int(seed_text[1:]))
        if style in groups[key]: raise EvidenceError(f"duplicate E4A style cell {key, style}")
        groups[key].add(style)
        observed_trials.append(record["trial_id"])
        identity = record.get("metrics", {}).get("reference_identity", {})
        if identity.get("validated") is True and identity.get("sha256"):
            identities[key].add(identity["sha256"])
    required = {"smooth", "normal", "aggressive"}
    missing = {f"{scenario}__S{seed}": sorted(required - styles)
               for (scenario, seed), styles in groups.items() if styles != required}
    identity_mismatches = {f"{scenario}__S{seed}": sorted(values)
                           for (scenario, seed), values in identities.items() if len(values) > 1}
    expected = expected_e4a_trials()
    population_missing = expected - set(observed_trials)
    population_extra = set(observed_trials) - expected
    if strict_style_triplets and (missing or identity_mismatches or population_missing or population_extra
                                  or len(observed_trials) != len(expected)):
        raise EvidenceError("invalid E4A exact paired population/reference membership")
    return {"pairing_keys": ["scenario", "geometry", "seed", "style"],
            "group_count": len(groups), "missing_styles": missing,
            "reference_identity_mismatches": identity_mismatches,
            "expected_formal_attempt_count": len(expected), "observed_attempt_count": len(observed_trials),
            "missing_registered_trial_count": len(population_missing), "extra_trial_ids": sorted(population_extra),
            "NA_values_retained": True}


def summarize_e4b_priority(records: Sequence[dict[str, Any]]) -> dict[str, Any]:
    attempts = [record for record in records if record.get("experiment") == "E4B"]
    values = [record["metrics"]["priority_preserved"]["value"] is True for record in attempts]
    return {"denominator": len(attempts), "numerator": sum(values),
            "Priority_Preservation_Rate": sum(values) / len(attempts) if attempts else None,
            "attempt_result_hashes": [record["canonical_result_sha256"] for record in attempts]}


def summarize_e5_success(records: Sequence[dict[str, Any]]) -> dict[str, Any]:
    attempts = [record for record in records if record.get("experiment") == "E5"]
    success = [record["metrics"]["mission_success"]["value"] is True for record in attempts]
    return {"denominator": len(attempts), "successes": sum(success),
            "all_attempt_mission_success_rate": sum(success) / len(attempts) if attempts else None,
            "attempt_result_hashes": [record["canonical_result_sha256"] for record in attempts],
            "infrastructure_failures_retained": sum(record.get("infrastructure_status") != "PASS" for record in attempts)}


def population_result(records: Sequence[dict[str, Any]], *, require_exact_registered_population: bool = False) -> dict[str, Any]:
    if require_exact_registered_population:
        prepare_e3(records, strict_complete_factorial=True)
        prepare_e4a(records, strict_style_triplets=True)
        assert_exact_trials(records, "E4B", expected_e4b_trials())
        assert_exact_trials(records, "E5", expected_e5_trials())
    consumed = [record["canonical_result_sha256"] for record in records]
    result = {"schema": "formal_analysis_population_preparation_v1",
              "attempt_result_hashes": consumed, "attempt_count": len(records),
              "E3": prepare_e3(records, strict_complete_factorial=False),
              "E4A": prepare_e4a(records, strict_style_triplets=False),
              "E4B": summarize_e4b_priority(records), "E5": summarize_e5_success(records),
              "exact_registered_population_required": require_exact_registered_population,
              "post_hoc_filtering": False, "continuous_NA_policy": "report valid_N and NA_N separately"}
    result["canonical_population_sha256"] = canonical_sha256(result)
    return result
