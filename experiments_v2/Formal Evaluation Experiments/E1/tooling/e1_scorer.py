#!/usr/bin/env python3
"""Offline scorer implementing the sealed E1 scoring contracts."""

from __future__ import annotations

import argparse
import copy
from decimal import Decimal
from fractions import Fraction
import json
import math
from pathlib import Path
import statistics
import sys
from typing import Any, Dict, Iterable, List, Sequence, Tuple

from e1_common import REPO_ROOT, E1ToolingError, load_dataset, load_order, utc_now
from e1_journal import EventJournal
from e1_run_state import RunState


SEMANTIC_FIELDS = ("U", "F", "c", "r", "T", "m", "s", "q")
RELATION_FIELD = "mission_relations"


def _load_schema_validator():
    package_root = REPO_ROOT / "location_allocate"
    if str(package_root) not in sys.path:
        sys.path.insert(0, str(package_root))
    from location_allocate.paper_lfs_validator import validate_candidate_schema

    return validate_candidate_schema


def _number(value: int | float) -> Fraction:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise E1ToolingError(f"not a JSON number: {value!r}")
    if not math.isfinite(float(value)):
        raise E1ToolingError("non-finite JSON number")
    return Fraction(Decimal(str(value)))


def _canonical_value(value: Any) -> Any:
    if isinstance(value, bool) or value is None or isinstance(value, str):
        return value
    if isinstance(value, (int, float)):
        return _number(value)
    if isinstance(value, list):
        return tuple(_canonical_value(item) for item in value)
    if isinstance(value, dict):
        return tuple(
            (str(key), _canonical_value(item))
            for key, item in sorted(value.items())
        )
    raise E1ToolingError(f"unsupported Candidate value: {type(value).__name__}")


def _task_sort_key(task: Dict[str, Any]) -> Tuple[Any, Any]:
    without_id = {key: value for key, value in task.items() if key != "task_id"}
    return (
        tuple(sorted(int(uid) for uid in task["U"])),
        _canonical_value(without_id),
    )


def _rewrite_references(value: Any, id_map: Dict[int, int]) -> None:
    """Rewrite any schema-valid task-ID references through the same ID map."""
    if isinstance(value, list):
        for item in value:
            _rewrite_references(item, id_map)
        return
    if not isinstance(value, dict):
        return
    for key, item in list(value.items()):
        if key != "task_id" and key.endswith("task_id") and isinstance(item, int):
            if item not in id_map:
                raise E1ToolingError(f"unresolved task reference: {item}")
            value[key] = id_map[item]
        elif key.endswith("task_ids") and isinstance(item, list):
            if any(ref not in id_map for ref in item):
                raise E1ToolingError(f"unresolved task reference list: {item}")
            value[key] = [id_map[ref] for ref in item]
        else:
            _rewrite_references(item, id_map)


def canonicalize_candidate(candidate: Dict[str, Any]) -> Dict[str, Any]:
    """Apply only the normalization sealed in e1_protocol_v1.yaml."""
    validator = _load_schema_validator()
    validator(candidate)
    normalized = copy.deepcopy(candidate)
    tasks: List[Dict[str, Any]] = []
    seen_ids = set()
    for node in normalized["mission"]["nodes"]:
        node_tasks = [node["task"]] if node["type"] == "task" else node["tasks"]
        for task in node_tasks:
            raw_id = task["task_id"]
            if isinstance(raw_id, bool) or not isinstance(raw_id, int) or raw_id <= 0:
                raise E1ToolingError("task_id must be a positive integer")
            if raw_id in seen_ids:
                raise E1ToolingError(f"duplicate task_id: {raw_id}")
            seen_ids.add(raw_id)
            task["U"] = sorted(task["U"])
        if node["type"] == "parallel":
            node["tasks"] = sorted(node_tasks, key=_task_sort_key)
            node_tasks = node["tasks"]
        tasks.extend(node_tasks)

    id_map = {
        int(task["task_id"]): canonical_id
        for canonical_id, task in enumerate(tasks, start=1)
    }
    _rewrite_references(normalized, id_map)
    for canonical_id, task in enumerate(tasks, start=1):
        task["task_id"] = canonical_id
    return normalized


def candidates_equal(left: Dict[str, Any], right: Dict[str, Any]) -> bool:
    return _canonical_value(canonicalize_candidate(left)) == _canonical_value(
        canonicalize_candidate(right)
    )


def _flatten_tasks(candidate: Dict[str, Any]) -> List[Dict[str, Any]]:
    tasks = []
    for node in candidate["mission"]["nodes"]:
        tasks.extend([node["task"]] if node["type"] == "task" else node["tasks"])
    return tasks


def _mission_relations(candidate: Dict[str, Any]) -> Tuple[Any, ...]:
    relations = []
    for node in candidate["mission"]["nodes"]:
        if node["type"] == "task":
            relations.append(("task", node["task"]["task_id"]))
        else:
            relations.append((
                "parallel",
                node["completion_mode"],
                tuple(task["task_id"] for task in node["tasks"]),
            ))
    return tuple(relations)


def semantic_field_matches(
    predicted: Dict[str, Any], ground_truth: Dict[str, Any]
) -> Dict[str, bool]:
    predicted_normal = canonicalize_candidate(predicted)
    truth_normal = canonicalize_candidate(ground_truth)
    predicted_tasks = _flatten_tasks(predicted_normal)
    truth_tasks = _flatten_tasks(truth_normal)
    matches = {}
    for field in SEMANTIC_FIELDS:
        predicted_values = tuple(
            _canonical_value(task[field]) for task in predicted_tasks
        )
        truth_values = tuple(_canonical_value(task[field]) for task in truth_tasks)
        matches[field] = predicted_values == truth_values
    matches[RELATION_FIELD] = (
        _mission_relations(predicted_normal) == _mission_relations(truth_normal)
    )
    return matches


def premature_commitment_counts(
    predicted: Dict[str, Any] | None,
    ground_truth: Dict[str, Any],
) -> Tuple[int, int]:
    truth_tasks = _flatten_tasks(canonicalize_candidate(ground_truth))
    predicted_tasks = (
        _flatten_tasks(canonicalize_candidate(predicted))
        if predicted is not None else []
    )
    numerator = 0
    denominator = 0
    for index, truth_task in enumerate(truth_tasks):
        predicted_task = predicted_tasks[index] if index < len(predicted_tasks) else None
        eligible = {
            "c": truth_task["c"]["mode"] in {
                "relative", "maintain_current_centroid", "auto"
            },
            "r": truth_task["r"]["mode"] in {"qualitative", "auto"},
            "T": truth_task["T"]["mode"] == "auto",
        }
        numerical = {
            "c": predicted_task is not None
            and predicted_task["c"]["mode"] == "absolute",
            "r": predicted_task is not None
            and predicted_task["r"]["mode"] == "explicit",
            "T": predicted_task is not None
            and predicted_task["T"]["mode"] == "explicit",
        }
        for field in ("c", "r", "T"):
            if eligible[field]:
                denominator += 1
                if numerical[field]:
                    numerator += 1
    return numerator, denominator


def _percentile(values: Sequence[float], probability: float) -> float | None:
    if not values:
        return None
    ordered = sorted(float(value) for value in values)
    if len(ordered) == 1:
        return ordered[0]
    rank = (len(ordered) - 1) * probability
    lower = math.floor(rank)
    upper = math.ceil(rank)
    if lower == upper:
        return ordered[lower]
    weight = rank - lower
    return ordered[lower] * (1.0 - weight) + ordered[upper] * weight


def _distribution(values: Iterable[float]) -> Dict[str, Any]:
    normalized = [float(value) for value in values]
    return {
        "count": len(normalized),
        "median": statistics.median(normalized) if normalized else None,
        "p90": _percentile(normalized, 0.90),
        "p95": _percentile(normalized, 0.95),
        "p99": _percentile(normalized, 0.99),
        "sum": sum(normalized) if normalized else None,
        "percentile_method": "linear_interpolation_rank_(n-1)*p",
    }


def score_run_state(
    dataset: List[Dict[str, Any]],
    state: RunState,
) -> Dict[str, Any]:
    records = {record["id"]: record for record in dataset}
    terminal_by_id = {terminal["command_id"]: terminal for terminal in state.terminals}
    expected_valid = [record for record in dataset if record["valid"] is True]
    expected_invalid = [record for record in dataset if record["valid"] is False]
    if len(expected_valid) != 96 or len(expected_invalid) != 24:
        raise E1ToolingError("sealed dataset denominator mismatch")

    schema_valid = 0
    exact = 0
    field_correct = {field: 0 for field in SEMANTIC_FIELDS}
    field_denominators = {field: 0 for field in SEMANTIC_FIELDS}
    relation_correct = 0
    premature_numerator = 0
    premature_denominator = 0
    normalization_errors = []
    exact_by_id = {}
    for record in expected_valid:
        terminal = terminal_by_id.get(record["id"])
        predicted = None
        if terminal and terminal.get("outcome") == "accepted":
            candidate = terminal.get("candidate")
            if isinstance(candidate, dict) and "mission" in candidate:
                try:
                    canonicalize_candidate(candidate)
                    predicted = candidate
                    schema_valid += 1
                except Exception as exc:
                    normalization_errors.append({
                        "command_id": record["id"],
                        "type": type(exc).__name__,
                        "message": str(exc),
                    })
        matches = {field: False for field in (*SEMANTIC_FIELDS, RELATION_FIELD)}
        is_exact = False
        if predicted is not None:
            try:
                matches = semantic_field_matches(predicted, record["ground_truth"])
                is_exact = candidates_equal(predicted, record["ground_truth"])
            except Exception as exc:
                normalization_errors.append({
                    "command_id": record["id"],
                    "type": type(exc).__name__,
                    "message": str(exc),
                })
                predicted = None
        truth_tasks = _flatten_tasks(canonicalize_candidate(record["ground_truth"]))
        predicted_tasks = (
            _flatten_tasks(canonicalize_candidate(predicted))
            if predicted is not None else []
        )
        for field in SEMANTIC_FIELDS:
            field_denominators[field] += len(truth_tasks)
            for task_index, truth_task in enumerate(truth_tasks):
                if task_index >= len(predicted_tasks):
                    continue
                field_correct[field] += int(
                    _canonical_value(predicted_tasks[task_index][field])
                    == _canonical_value(truth_task[field])
                )
        relation_correct += int(matches[RELATION_FIELD])
        exact += int(is_exact)
        exact_by_id[record["id"]] = is_exact
        numerator, denominator = premature_commitment_counts(
            predicted, record["ground_truth"]
        )
        premature_numerator += numerator
        premature_denominator += denominator

    invalid_rejected = 0
    invalid_by_class: Dict[str, Dict[str, int]] = {}
    confusion: Dict[str, Dict[str, int]] = {}
    for record in expected_invalid:
        expected_class = record["expected_rejection_class"]
        terminal = terminal_by_id.get(record["id"])
        outcome = terminal.get("outcome") if terminal else "missing_terminal"
        reported = (
            "rejected" if outcome == "rejected"
            else "infrastructure_failure" if outcome == "infrastructure_failure"
            else "not_rejected"
        )
        class_counts = invalid_by_class.setdefault(
            expected_class, {"rejected": 0, "total": 0}
        )
        class_counts["total"] += 1
        class_counts["rejected"] += int(reported == "rejected")
        invalid_rejected += int(reported == "rejected")
        confusion.setdefault(expected_class, {}).setdefault(reported, 0)
        confusion[expected_class][reported] += 1

    for counts in invalid_by_class.values():
        counts["rate"] = counts["rejected"] / counts["total"]

    completed_attempts = [
        attempt for attempt in state.attempts.values()
        if attempt.provider_result is not None and attempt.completed is not None
    ]
    provider_latencies = [
        attempt.provider_result["provider_wall_latency_ms"]
        for attempt in completed_attempts
        if isinstance(
            attempt.provider_result.get("provider_wall_latency_ms"), (int, float)
        )
    ]
    total_latencies = []
    for terminal in state.terminals:
        value = terminal.get("total_latency_ms")
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            total_latencies.append(value)

    token_metrics = {}
    for token_name in ("prompt_tokens", "completion_tokens", "total_tokens"):
        values = []
        missing = 0
        for attempt in completed_attempts:
            value = attempt.provider_result["provider_token_usage"].get(token_name)
            if isinstance(value, int) and not isinstance(value, bool):
                values.append(value)
            else:
                missing += 1
        token_metrics[token_name] = {
            **_distribution(values),
            "missing_attempts": missing,
        }

    retries: Dict[str, int] = {}
    for terminal in state.terminals:
        attempts_total = int(terminal["attempts_total"])
        retries[str(attempts_total - 1)] = retries.get(str(attempts_total - 1), 0) + 1

    format_attempts = [
        attempt.completed.get("format_compliant") is True
        for attempt in completed_attempts
        if attempt.provider_result.get("provider_status") == "returned"
    ]
    category_accuracy: Dict[str, Dict[str, Dict[str, Any]]] = {}
    for record in expected_valid:
        for category, value in record.get("categories", {}).items():
            bucket = category_accuracy.setdefault(category, {}).setdefault(
                str(value), {"exact": 0, "total": 0}
            )
            bucket["total"] += 1
            bucket["exact"] += int(exact_by_id[record["id"]])
    for values in category_accuracy.values():
        for bucket in values.values():
            bucket["rate"] = bucket["exact"] / bucket["total"]

    component_rates = {
        field: field_correct[field] / field_denominators[field]
        for field in SEMANTIC_FIELDS
    }
    component_rates[RELATION_FIELD] = relation_correct / len(expected_valid)
    semantic_macro_rate = sum(component_rates.values()) / len(component_rates)
    return {
        "score_type": "E1_offline_score_v1",
        "scored_at_utc": utc_now(),
        "dataset_class": state.provenance.get("dataset_class") if state.provenance else None,
        "terminal_command_count": len(state.terminals),
        "all_attempt_count": len(completed_attempts),
        "primary_metrics": {
            "schema_valid_rate": {
                "numerator": schema_valid,
                "denominator": 96,
                "rate": schema_valid / 96,
            },
            "semantic_field_accuracy": {
                "aggregation": (
                    "arithmetic mean of U,F,c,r,T,m,s,q task-field "
                    "accuracies and per-command mission-relation accuracy"
                ),
                "rate": semantic_macro_rate,
                "per_field": {
                    field: {
                        "correct": count,
                        "denominator": field_denominators[field],
                        "rate": component_rates[field],
                    }
                    for field, count in field_correct.items()
                } | {
                    RELATION_FIELD: {
                        "correct": relation_correct,
                        "denominator": len(expected_valid),
                        "rate": component_rates[RELATION_FIELD],
                    }
                },
            },
            "exact_semantic_task_accuracy": {
                "numerator": exact,
                "denominator": 96,
                "rate": exact / 96,
            },
            "invalid_rejection_rate": {
                "numerator": invalid_rejected,
                "denominator": 24,
                "rate": invalid_rejected / 24,
                "per_expected_class": invalid_by_class,
            },
            "premature_numerical_commitment_rate": {
                "numerator": premature_numerator,
                "denominator": premature_denominator,
                "rate": (
                    premature_numerator / premature_denominator
                    if premature_denominator else None
                ),
            },
            "latency_ms": {
                "provider_call_per_attempt": _distribution(provider_latencies),
                "total_to_terminal_per_command": _distribution(total_latencies),
            },
            "provider_reported_tokens_per_attempt": token_metrics,
        },
        "secondary_diagnostics": {
            "strict_json_format_compliance": {
                "compliant": sum(format_attempts),
                "returned_response_attempts": len(format_attempts),
                "rate": (
                    sum(format_attempts) / len(format_attempts)
                    if format_attempts else None
                ),
            },
            "retry_count_distribution": retries,
            "rejection_class_confusion_matrix": confusion,
            "exact_accuracy_by_registered_category": category_accuracy,
            "normalization_errors": normalization_errors,
        },
    }


def score_run(run_dir: Path, *, require_complete: bool = True) -> Dict[str, Any]:
    journal = EventJournal(Path(run_dir) / "journal")
    state = RunState.build(journal.read(), load_order())
    if require_complete and len(state.terminals) != 120:
        raise E1ToolingError(
            f"scoring requires 120 terminal records; found {len(state.terminals)}"
        )
    return score_run_state(load_dataset(), state)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("run_dir", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    score = score_run(args.run_dir)
    serialized = json.dumps(score, indent=2, ensure_ascii=False) + "\n"
    if args.output:
        with args.output.open("x", encoding="utf-8") as stream:
            stream.write(serialized)
    else:
        print(serialized, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
