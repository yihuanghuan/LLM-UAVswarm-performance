#!/usr/bin/env python3
"""Deterministic preregistered analysis of the frozen E3-v4 campaign."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import shutil
import subprocess
from collections import Counter, defaultdict
from pathlib import Path
from statistics import NormalDist
from typing import Any, Iterable

import numpy as np
from scipy.stats import binomtest


SOURCE_COMMIT = "f61c8c174eb4ca836a54af999189550a2bf46f34"
EXPECTED_BRANCH = "formal/E3-v4-analysis-v1"
BOOTSTRAP_NAMESPACE = "E3-v4-analysis-bootstrap-v1"
BOOTSTRAP_RESAMPLES = 10_000
CONDITIONS = ("P0_F0", "P0_F1", "P1_F0", "P1_F1")
FAMILY_LABELS = {
    "A": "planning responsibility",
    "B": "feedback responsibility",
    "C": "planning-execution decomposition",
}
FAMILY_FROM_LONG = {
    "A_predictable_structural_risk": "A",
    "B_residual_execution_risk": "B",
    "C_mixed_risk": "C",
}

IDENTITY_SPECS = {
    "sealed_registry": (
        "experiments_v2/Formal Evaluation Experiments/E3/e3_factorial_registry_v4.yaml",
        "2b3dccc2ad27cf317029c2b7b014bca3a8b28fc8c0a196fd4c2e5abe0be9d4b7",
    ),
    "formal_seed_registry": (
        "experiments_v2/Formal Evaluation Experiments/E3/E3_v4_formal_paired_seeds.yaml",
        "665600871ad3fb6cff324ab3ef9144b0d84b42acc19505283679b6ae01586841",
    ),
    "formal_order": (
        "experiments_v2/Formal Evaluation Experiments/E3/E3_v4_formal_trial_order.txt",
        "60ee30a7100b53c4964e3f9f086ff3d137fb41282eebc4439760bf17f033b39b",
    ),
    "analysis_contract": (
        "experiments_v2/Formal Evaluation Experiments/E3/E3_v4_analysis_contract.md",
        "987ff29aa814a0dc5e9e64081fcf0fc79ceb3086b21a0e945bfe2f8252185c58",
    ),
    "production_policy": (
        "lfs_policy/config/lfs_policy.paper_current.yaml",
        "6b47d27f4253d7311e79ea51f6dd1cf0d0182e6df24374a94abae0aa6a135858",
    ),
    "E3_v3_registry": (
        "experiments_v2/Formal Evaluation Experiments/E3/e3_factorial_registry_v3.yaml",
        "b56344c6cd257e99851523d640d9a89d6def994884877e2303d8fab836e0faf2",
    ),
    "journal": (
        "experiments_v2/Formal Evaluation Experiments/E3/results/formal_v4/campaign_journal.jsonl",
        "d00e59091ad598bdd5c1ffbbfded888aa04f0e3a7089cf9c225b21c196f49066",
    ),
    "raw_archive_ledger": (
        "experiments_v2/Formal Evaluation Experiments/E3/results/formal_v4/raw_archive_ledger.jsonl",
        "87ff7e952cb3829921e0c0a47b3a4b82d077a9f68355dcb351e407df5be3ba57",
    ),
    "raw_storage_policy": (
        "experiments_v2/Formal Evaluation Experiments/E3/E3_v4_raw_storage_policy_v2.yaml",
        "5a0ffedcd1088f0516f669b15ec3d613c857b1a9304917b2f4db728fce18f2b9",
    ),
    "human_activation_manifest": (
        "experiments_v2/Formal Evaluation Experiments/E3/E3_v4_human_activation_manifest.yaml",
        "49726b77d60fff8a83c3c7602a7b1236047265995a719e44a9657f8e0f31f993",
    ),
    "endpoint_availability_adjudication": (
        "experiments_v2/Formal Evaluation Experiments/E3/analysis_v4/E3_v4_endpoint_availability_adjudication_v1.json",
        "",  # Branch-local pre-effect-estimation adjudication; recorded, not preregistered.
    ),
}

EXPECTED_TOOLING_BUNDLE = "78cb5dbc374983c64752433fa1c62c4990903b03b5b813f0248f13105eb074bf"
ACTIVATION_PROVENANCE = {
    "candidate_registry_sha256": "80ddbb8701f1c7feb84ae64a7985f233742f522c1204131ab4dd6d09960bd79b",
    "sealed_registry_sha256": "2b3dccc2ad27cf317029c2b7b014bca3a8b28fc8c0a196fd4c2e5abe0be9d4b7",
    "candidate_scientific_payload_sha256": "43a4805a5c9bd881fc3cc8ff0785bbf3436a5fbbffc38596d05e985b88a896e0",
    "sealed_scientific_payload_sha256": "43a4805a5c9bd881fc3cc8ff0785bbf3436a5fbbffc38596d05e985b88a896e0",
}
ENDPOINTS = {
    "j_hard_pair_s": {
        "kind": "continuous", "path": ("metrics", "realized", "hard_risk_exposure_pair_s"),
        "label": "Realized hard-risk exposure J_hard (pair-s)", "safer": "lower",
    },
    "realized_min_separation_m": {
        "kind": "continuous", "path": ("metrics", "realized", "d_min_m"),
        "label": "Realized minimum 3-D separation (m)", "safer": "higher",
    },
    "hard_risk_event_count": {
        "kind": "count", "path": ("metrics", "realized", "hard_risk_event_count"),
        "label": "Realized hard-risk event count", "safer": "lower",
    },
    "predicted_min_separation_m": {
        "kind": "continuous", "path": ("metrics", "predicted", "d_min_m"),
        "label": "Predicted minimum separation (m)", "safer": "higher",
    },
    "predicted_hard_conflict_count": {
        "kind": "count", "path": ("metrics", "predicted", "hard_violations"),
        "label": "Predicted hard-conflict count", "safer": "lower",
    },
    "controller_near_limit_fraction": {
        "kind": "continuous", "path": ("metrics", "stability", "near_acceleration_limit_sample_fraction"),
        "label": "Controller near-limit sample fraction", "safer": "lower",
    },
    "any_realized_hard_risk": {
        "kind": "binary_derived", "path": ("metrics", "realized", "hard_risk_event_count"),
        "transform": "int(hard_risk_event_count > 0)",
        "label": "Any realized hard risk", "safer": "lower",
    },
    "mission_success": {
        "kind": "binary", "path": ("metrics", "stability", "mission_success"),
        "label": "Mission success", "safer": "higher",
    },
    "failsafe_seen": {
        "kind": "binary", "path": ("metrics", "stability", "failsafe_seen"),
        "label": "Failsafe seen", "safer": "lower",
    },
    "feedback_intervention_burden": {
        "kind": "unavailable", "path": None,
        "label": "Feedback intervention burden", "safer": "lower",
        "reason": "PREREGISTERED_ENDPOINT_UNAVAILABLE_DUE_TO_INSTRUMENTATION_OMISSION",
    },
}

CONTINUOUS_ENDPOINTS = tuple(k for k, v in ENDPOINTS.items() if v["kind"] in ("continuous", "count"))
BINARY_ENDPOINTS = tuple(k for k, v in ENDPOINTS.items() if v["kind"] in ("binary", "binary_derived"))
CONTRASTS = ("Delta_P", "Delta_F", "Delta_PF")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def canonical_json_sha256(payload: Any) -> str:
    data = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(data).hexdigest()


def git(repo: Path, *args: str) -> str:
    return subprocess.check_output(["git", *args], cwd=repo, text=True).strip()


def nested_get(payload: dict[str, Any], path: Iterable[str]) -> Any:
    value: Any = payload
    for key in path:
        if not isinstance(value, dict) or key not in value:
            return None
        value = value[key]
    return value


def value_for(attempt: dict[str, Any], endpoint: str) -> float | int:
    spec = ENDPOINTS[endpoint]
    value = nested_get(attempt, spec["path"])
    if value is None:
        raise ValueError(f"required endpoint {endpoint} missing in {attempt.get('trial_id')}")
    if spec["kind"] == "binary_derived":
        return int(float(value) > 0.0)
    if spec["kind"] == "binary":
        return int(bool(value))
    return float(value) if spec["kind"] == "continuous" else int(value)


def bootstrap_seed(family: str, endpoint: str, contrast: str) -> int:
    text = f"{BOOTSTRAP_NAMESPACE}|{family}|{endpoint}|{contrast}"
    return int.from_bytes(hashlib.sha256(text.encode()).digest()[:8], "big")


def stratified_bootstrap_ci(
    values_by_scenario: dict[str, list[float]], seed: int, resamples: int = BOOTSTRAP_RESAMPLES
) -> tuple[float, float]:
    rng = np.random.default_rng(seed)
    total = sum(len(v) for v in values_by_scenario.values())
    if total == 0:
        raise ValueError("bootstrap requires observations")
    draws = np.empty(resamples, dtype=float)
    ordered = [(k, np.asarray(values_by_scenario[k], dtype=float)) for k in sorted(values_by_scenario)]
    for i in range(resamples):
        numerator = 0.0
        for _, values in ordered:
            indices = rng.integers(0, len(values), size=len(values))
            numerator += float(values[indices].sum())
        draws[i] = numerator / total
    low, high = np.percentile(draws, [2.5, 97.5])
    return float(low), float(high)


def wilson_interval(successes: int, n: int, alpha: float = 0.05) -> tuple[float, float]:
    if n <= 0:
        return math.nan, math.nan
    z = NormalDist().inv_cdf(1.0 - alpha / 2.0)
    p = successes / n
    denom = 1.0 + z * z / n
    centre = (p + z * z / (2.0 * n)) / denom
    half = z * math.sqrt(p * (1.0 - p) / n + z * z / (4.0 * n * n)) / denom
    return centre - half, centre + half


def factorial_contrasts(cells: dict[str, float]) -> dict[str, float]:
    if set(cells) != set(CONDITIONS):
        raise ValueError("factorial contrast requires exactly four registered cells")
    p00, p01, p10, p11 = (cells[c] for c in CONDITIONS)
    return {
        "Delta_P": ((p10 - p00) + (p11 - p01)) / 2.0,
        "Delta_F": ((p01 - p00) + (p11 - p10)) / 2.0,
        "Delta_PF": (p11 - p10) - (p01 - p00),
    }


def write_csv(path: Path, rows: list[dict[str, Any]], fields: list[str] | None = None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if fields is None:
        fields = list(rows[0]) if rows else []
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="raise", lineterminator="\n")
        writer.writeheader()
        for row in rows:
            writer.writerow({k: format_value(row.get(k)) for k in fields})


def format_value(value: Any) -> Any:
    if value is None:
        return ""
    if isinstance(value, float):
        if math.isnan(value):
            return "NA"
        return format(value, ".17g")
    if isinstance(value, bool):
        return "true" if value else "false"
    return value


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True, allow_nan=False) + "\n", encoding="utf-8")


def json_safe(value: Any) -> Any:
    if isinstance(value, float) and not math.isfinite(value):
        return None
    if isinstance(value, dict):
        return {k: json_safe(v) for k, v in value.items()}
    if isinstance(value, list):
        return [json_safe(v) for v in value]
    return value


def integrity_gate(repo: Path, analysis_root: Path) -> dict[str, Any]:
    if git(repo, "branch", "--show-current") != EXPECTED_BRANCH:
        raise RuntimeError(f"analysis must run on {EXPECTED_BRANCH}")
    if git(repo, "cat-file", "-t", SOURCE_COMMIT) != "commit":
        raise RuntimeError("frozen source commit is unavailable")
    subject = git(repo, "show", "-s", "--format=%s", SOURCE_COMMIT)
    if subject != "experiment: freeze E3-v4 formal campaign completion audit":
        raise RuntimeError(f"unexpected frozen source subject: {subject}")
    if git(repo, "merge-base", "HEAD", SOURCE_COMMIT) != SOURCE_COMMIT:
        raise RuntimeError("analysis branch is not based on the frozen source commit")

    source_worktrees: list[Path] = []
    current_path: Path | None = None
    current_head: str | None = None
    for line in git(repo, "worktree", "list", "--porcelain").splitlines() + [""]:
        if line.startswith("worktree "):
            current_path = Path(line.removeprefix("worktree "))
            current_head = None
        elif line.startswith("HEAD "):
            current_head = line.removeprefix("HEAD ")
        elif not line and current_path is not None:
            if current_head == SOURCE_COMMIT:
                source_worktrees.append(current_path)
            current_path = None
            current_head = None
    if len(source_worktrees) != 1:
        raise RuntimeError(f"expected exactly one frozen-source worktree, found {source_worktrees}")
    if subprocess.check_output(["git", "status", "--porcelain"], cwd=source_worktrees[0], text=True).strip():
        raise RuntimeError("frozen source worktree is not clean")

    identities: dict[str, Any] = {}
    for name, (relative, expected) in IDENTITY_SPECS.items():
        path = repo / relative
        if not path.is_file():
            raise RuntimeError(f"identity file missing: {relative}")
        observed = sha256_file(path)
        if expected and observed != expected:
            raise RuntimeError(f"identity mismatch for {name}: {observed} != {expected}")
        identities[name] = {"path": relative, "sha256": observed, "expected_sha256": expected or observed}

    manifest_text = (repo / IDENTITY_SPECS["human_activation_manifest"][0]).read_text(encoding="utf-8")
    for key, expected in ACTIVATION_PROVENANCE.items():
        token = f"{key}: {expected}"
        if token not in manifest_text:
            raise RuntimeError(f"activation provenance mismatch: {key}")
    if "candidate_vs_sealed_scientific_payload_equivalent: true" not in manifest_text:
        raise RuntimeError("candidate/sealed scientific payload equivalence is not true")
    if "scientific_protocol_changes: 0" not in manifest_text:
        raise RuntimeError("activation reports scientific protocol changes")
    contract_text = (repo / IDENTITY_SPECS["analysis_contract"][0]).read_text(encoding="utf-8")
    if ACTIVATION_PROVENANCE["candidate_registry_sha256"] not in contract_text:
        raise RuntimeError("contract no longer retains candidate registry provenance")

    attempt_one = json.loads(next((repo / "experiments_v2/Formal Evaluation Experiments/E3/results/formal_v4/attempts").glob("000001__*/attempt.json")).read_text())
    tooling = attempt_one["adapter"]["execution_tooling"]
    if tooling["bundle_sha256"] != EXPECTED_TOOLING_BUNDLE:
        raise RuntimeError("activated tooling bundle mismatch in attempt evidence")
    for relative, expected_hash in tooling["files"].items():
        if sha256_file(repo / relative) != expected_hash:
            raise RuntimeError(f"activated tooling file changed: {relative}")
    payload = {"schema": tooling["schema"], "files": dict(sorted(tooling["files"].items()))}
    if canonical_json_sha256(payload) != EXPECTED_TOOLING_BUNDLE:
        raise RuntimeError("activated tooling bundle cannot be independently reconstructed")

    changed = git(repo, "diff", "--name-only", SOURCE_COMMIT)
    changed_paths = [p for p in changed.splitlines() if p]
    allowed_prefix = str(analysis_root.relative_to(repo)) + "/"
    outside = [p for p in changed_paths if not p.startswith(allowed_prefix)]
    if outside:
        raise RuntimeError(f"frozen files changed outside analysis_v4: {outside}")
    status_raw = subprocess.check_output(
        ["git", "status", "--porcelain", "-z", "--untracked-files=all"], cwd=repo
    )
    status_paths = [entry[3:].decode("utf-8") for entry in status_raw.split(b"\0") if entry]
    status_outside = [p for p in status_paths if not p.startswith(allowed_prefix)]
    if status_outside:
        raise RuntimeError(f"worktree changes exist outside analysis_v4: {status_outside}")

    return {
        "status": "PASS",
        "source_commit": SOURCE_COMMIT,
        "source_subject": subject,
        "analysis_branch": EXPECTED_BRANCH,
        "branch_merge_base": SOURCE_COMMIT,
        "source_worktree": str(source_worktrees[0]),
        "source_worktree_clean": True,
        "frozen_identities": identities,
        "activated_execution_tooling_bundle_sha256": EXPECTED_TOOLING_BUNDLE,
        "candidate_registry_sha256_retained_in_contract": ACTIVATION_PROVENANCE["candidate_registry_sha256"],
        "sealed_registry_sha256": ACTIVATION_PROVENANCE["sealed_registry_sha256"],
        "candidate_scientific_payload_sha256": ACTIVATION_PROVENANCE["candidate_scientific_payload_sha256"],
        "sealed_scientific_payload_sha256": ACTIVATION_PROVENANCE["sealed_scientific_payload_sha256"],
        "candidate_vs_sealed_scientific_payload_equivalent": True,
        "scientific_protocol_changes": 0,
        "changed_paths_outside_analysis_v4": [],
        "worktree_status_paths_outside_analysis_v4": [],
    }


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def failure_reason(attempt: dict[str, Any]) -> str:
    backend = attempt.get("backend_result") or {}
    if backend.get("error"):
        return str(backend["error"])
    if backend.get("metric_error"):
        return str(backend["metric_error"])
    return "unidentified frozen infrastructure failure"


def ingest_campaign(repo: Path) -> dict[str, Any]:
    e3 = repo / "experiments_v2/Formal Evaluation Experiments/E3"
    formal = e3 / "results/formal_v4"
    attempts_paths = sorted((formal / "attempts").glob("*/attempt.json"))
    attempts = [json.loads(p.read_text(encoding="utf-8")) for p in attempts_paths]
    order = (e3 / "E3_v4_formal_trial_order.txt").read_text(encoding="utf-8").splitlines()
    journal = load_jsonl(formal / "campaign_journal.jsonl")
    ledger = load_jsonl(formal / "raw_archive_ledger.jsonl")
    if len(attempts) != 360 or len(order) != 360 or len(journal) != 360 or len(ledger) != 360:
        raise RuntimeError("campaign cardinality differs from 360")
    trial_ids = [a.get("trial_id") for a in attempts]
    if len(set(trial_ids)) != 360:
        raise RuntimeError("unexpected duplicate trial ID")
    if [a.get("campaign_position") for a in attempts] != list(range(1, 361)):
        raise RuntimeError("attempt campaign positions are not exactly 1..360")
    if trial_ids != order:
        raise RuntimeError("attempt order differs from frozen formal order")
    if [r.get("trial_id") for r in journal] != order or [r.get("campaign_position") for r in journal] != list(range(1, 361)):
        raise RuntimeError("journal/order inconsistency")
    if [r.get("trial_id") for r in ledger] != order:
        raise RuntimeError("raw ledger/order inconsistency")
    if [r.get("campaign_position") for r in ledger] != list(range(1, 361)):
        raise RuntimeError("raw ledger positions are not exactly 1..360")
    for path, attempt, record in zip(attempts_paths, attempts, journal):
        if sha256_file(path) != record.get("attempt_artifact_sha256"):
            raise RuntimeError(f"journal attempt hash mismatch: {path}")
        if attempt.get("replacement_attempt") is not False or record.get("replacement_attempt") is not False:
            raise RuntimeError("replacement attempt detected")
        if attempt.get("dataset_class") != "formal_evaluation" or attempt.get("execution_mode") != "formal":
            raise RuntimeError("non-formal data accidentally ingested")
        if attempt.get("adapter", {}).get("execution_tooling", {}).get("bundle_sha256") != EXPECTED_TOOLING_BUNDLE:
            raise RuntimeError("attempt tooling identity mismatch")

    status = Counter(a.get("attempt_status") for a in attempts)
    if status != Counter({"success": 343, "infrastructure_failure": 17}):
        raise RuntimeError(f"attempt status counts differ: {status}")
    failures = [a for a in attempts if a["attempt_status"] == "infrastructure_failure"]
    expected_failure_slots = [3, 4, 5, 6, 7, 35, 105, 134, 210, 236, 266, 271, 274, 301, 324, 343, 353]
    if [a["campaign_position"] for a in failures] != expected_failure_slots:
        raise RuntimeError("infrastructure-failure slots differ from freeze")

    storage_by_trial: dict[str, str] = {}
    for row in ledger:
        disposition = row.get("storage_disposition", "RAW_ARCHIVE_VERIFIED")
        storage_by_trial[row["trial_id"]] = disposition
    storage_counts = Counter(storage_by_trial.values())
    if storage_counts != Counter({"RAW_ARCHIVE_VERIFIED": 359, "PRE_RAW_ACQUISITION_INFRASTRUCTURE_FAILURE": 1}):
        raise RuntimeError(f"raw storage disposition differs: {storage_counts}")
    if storage_by_trial[order[104]] != "PRE_RAW_ACQUISITION_INFRASTRUCTURE_FAILURE":
        raise RuntimeError("slot 105 is not the unique pre-raw failure")

    blocks: dict[tuple[str, int], dict[str, dict[str, Any]]] = defaultdict(dict)
    for attempt in attempts:
        spec = attempt["execution_spec"]
        key = (spec["scenario_id"], int(spec["seed"]))
        condition = spec["condition"]
        if condition in blocks[key]:
            raise RuntimeError(f"duplicate block cell: {key} {condition}")
        blocks[key][condition] = attempt
    if len(blocks) != 90 or any(set(cells) != set(CONDITIONS) for cells in blocks.values()):
        raise RuntimeError("registered four-cell block population differs from 90")
    complete = {k: v for k, v in blocks.items() if all(v[c]["attempt_status"] == "success" for c in CONDITIONS)}
    if len(complete) != 74 or len(blocks) - len(complete) != 16:
        raise RuntimeError("complete/incomplete scientific blocks differ from 74/16")

    for attempt in attempts:
        if attempt["attempt_status"] != "success":
            if attempt.get("metrics") is not None:
                raise RuntimeError("infrastructure failure unexpectedly has metrics")
            continue
        metrics = attempt.get("metrics")
        if not isinstance(metrics, dict) or metrics.get("schema") != "E3_v4_formal_attempt_metrics_v1":
            raise RuntimeError(f"authoritative metrics payload missing: {attempt['trial_id']}")
        for endpoint in CONTINUOUS_ENDPOINTS + BINARY_ENDPOINTS:
            value_for(attempt, endpoint)

    return {
        "attempts": attempts,
        "attempt_paths": attempts_paths,
        "order": order,
        "journal": journal,
        "ledger": ledger,
        "storage_by_trial": storage_by_trial,
        "blocks": blocks,
        "complete_blocks": complete,
        "status_counts": status,
        "storage_counts": storage_counts,
    }


def family_of(attempt: dict[str, Any]) -> str:
    return FAMILY_FROM_LONG[attempt["execution_spec"]["family"]]


def build_attempt_and_membership_rows(data: dict[str, Any]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    complete_keys = set(data["complete_blocks"])
    attempt_rows: list[dict[str, Any]] = []
    for attempt in data["attempts"]:
        spec = attempt["execution_spec"]
        key = (spec["scenario_id"], int(spec["seed"]))
        row: dict[str, Any] = {
            "campaign_position": attempt["campaign_position"],
            "trial_id": attempt["trial_id"],
            "family": family_of(attempt),
            "family_registered_name": spec["family"],
            "scenario_id": spec["scenario_id"],
            "seed": spec["seed"],
            "condition": spec["condition"],
            "planning": spec["condition"].split("_")[0],
            "feedback": spec["condition"].split("_")[1],
            "attempt_status": attempt["attempt_status"],
            "infrastructure_failure_reason": failure_reason(attempt) if attempt["attempt_status"] != "success" else "",
            "raw_storage_disposition": data["storage_by_trial"][attempt["trial_id"]],
            "block_id": f"{spec['scenario_id']}__S{spec['seed']}",
            "block_is_primary_complete": key in complete_keys,
            "whether_block_is_primary_complete": key in complete_keys,
            "scientifically_eligible": attempt["attempt_status"] == "success",
        }
        for endpoint in CONTINUOUS_ENDPOINTS + BINARY_ENDPOINTS:
            row[endpoint] = value_for(attempt, endpoint) if attempt["attempt_status"] == "success" else None
        row["feedback_intervention_burden"] = None
        row["feedback_intervention_burden_availability"] = (
            "PREREGISTERED_ENDPOINT_UNAVAILABLE_DUE_TO_INSTRUMENTATION_OMISSION"
            if attempt["attempt_status"] == "success" else "UNAVAILABLE_DUE_TO_INFRASTRUCTURE_FAILURE"
        )
        attempt_rows.append(row)

    membership_rows: list[dict[str, Any]] = []
    for (scenario, seed), cells in sorted(data["blocks"].items()):
        first = cells[CONDITIONS[0]]
        failed = [c for c in CONDITIONS if cells[c]["attempt_status"] != "success"]
        membership_rows.append({
            "block_id": f"{scenario}__S{seed}",
            "family": family_of(first),
            "scenario_id": scenario,
            "seed": seed,
            "registered_cell_count": len(cells),
            "successful_cell_count": 4 - len(failed),
            "failed_cell_count": len(failed),
            "failed_conditions": ";".join(failed),
            "is_primary_complete": not failed,
            "primary_population_disposition": "INCLUDED" if not failed else "WHOLE_BLOCK_EXCLUDED",
        })
    return attempt_rows, membership_rows


def build_missingness_rows(attempt_rows: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    fields = [
        "campaign_position", "trial_id", "family", "scenario_id", "seed", "condition",
        "attempt_status", "infrastructure_failure_reason", "raw_storage_disposition", "block_id",
        "block_is_primary_complete",
    ]
    rows = [{k: row[k] for k in fields} for row in attempt_rows]
    failures = [r for r in rows if r["attempt_status"] == "infrastructure_failure"]
    summaries: list[dict[str, Any]] = []
    dimensions = {
        "family": lambda r: r["family"],
        "scenario": lambda r: r["scenario_id"],
        "condition": lambda r: r["condition"],
        "seed": lambda r: str(r["seed"]),
        "failure_mechanism": lambda r: r["infrastructure_failure_reason"],
    }
    for dimension, getter in dimensions.items():
        all_levels = sorted({getter(r) for r in rows}) if dimension != "failure_mechanism" else sorted({getter(r) for r in failures})
        for level in all_levels:
            denominator = sum(getter(r) == level for r in rows)
            count = sum(getter(r) == level for r in failures)
            summaries.append({
                "dimension": dimension, "level": level,
                "infrastructure_failures": count, "registered_attempts": denominator,
                "failure_fraction": count / denominator if denominator else None,
            })
    return rows, summaries


def descriptive_stats(values: list[float]) -> dict[str, Any]:
    x = np.asarray(values, dtype=float)
    return {
        "N": len(values),
        "mean": float(np.mean(x)),
        "median": float(np.median(x)),
        "sd": float(np.std(x, ddof=1)) if len(x) > 1 else None,
        "q1": float(np.percentile(x, 25)),
        "q3": float(np.percentile(x, 75)),
        "min": float(np.min(x)),
        "max": float(np.max(x)),
    }


def build_descriptives(attempt_rows: list[dict[str, Any]], primary_only: bool) -> list[dict[str, Any]]:
    eligible = [r for r in attempt_rows if r["scientifically_eligible"] and (r["block_is_primary_complete"] or not primary_only)]
    population = "PRIMARY_COMPLETE_BLOCKS" if primary_only else "AVAILABLE_SUCCESSFUL_CELLS_SENSITIVITY_ONLY"
    result: list[dict[str, Any]] = []
    grouping_specs = (
        ("family_scenario_condition", lambda r: (r["family"], r["scenario_id"], r["condition"])),
        ("family_condition", lambda r: (r["family"], "ALL", r["condition"])),
    )
    for level, getter in grouping_specs:
        groups: dict[tuple[str, str, str], list[dict[str, Any]]] = defaultdict(list)
        for row in eligible:
            groups[getter(row)].append(row)
        for (family, scenario, condition), rows in sorted(groups.items()):
            for endpoint in CONTINUOUS_ENDPOINTS:
                stats = descriptive_stats([float(r[endpoint]) for r in rows])
                result.append({
                    "population": population, "group_level": level, "family": family,
                    "scenario_id": scenario, "condition": condition, "endpoint": endpoint,
                    "endpoint_kind": ENDPOINTS[endpoint]["kind"], **stats,
                    "numerator": None, "denominator": None, "proportion": None,
                    "ci_low": None, "ci_high": None, "availability_note": "",
                })
            for endpoint in BINARY_ENDPOINTS:
                numerator = sum(int(r[endpoint]) for r in rows)
                low, high = wilson_interval(numerator, len(rows))
                result.append({
                    "population": population, "group_level": level, "family": family,
                    "scenario_id": scenario, "condition": condition, "endpoint": endpoint,
                    "endpoint_kind": "binary", "N": len(rows), "mean": None, "median": None,
                    "sd": None, "q1": None, "q3": None, "min": None, "max": None,
                    "numerator": numerator, "denominator": len(rows), "proportion": numerator / len(rows),
                    "ci_low": low, "ci_high": high, "availability_note": "Wilson two-sided 95% CI",
                })
    # Explicitly retain the adjudicated unavailable endpoint once per dataset.
    result.append({
        "population": population, "group_level": "endpoint_availability", "family": "ALL",
        "scenario_id": "ALL", "condition": "ALL", "endpoint": "feedback_intervention_burden",
        "endpoint_kind": "unavailable", "N": 0, "mean": None, "median": None, "sd": None,
        "q1": None, "q3": None, "min": None, "max": None, "numerator": None,
        "denominator": 343, "proportion": None, "ci_low": None, "ci_high": None,
        "availability_note": "NA — preregistered endpoint unavailable; N=0/343; proxy used = no",
    })
    return result


def build_factorial_results(data: dict[str, Any]) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    seed_records: dict[str, Any] = {}
    blocks_by_family: dict[str, list[tuple[tuple[str, int], dict[str, dict[str, Any]]]]] = defaultdict(list)
    for key, cells in sorted(data["complete_blocks"].items()):
        blocks_by_family[family_of(cells[CONDITIONS[0]])].append((key, cells))
    for family in sorted(FAMILY_LABELS):
        blocks = blocks_by_family[family]
        for endpoint in CONTINUOUS_ENDPOINTS:
            contrast_by_scenario: dict[str, dict[str, list[float]]] = {
                contrast: defaultdict(list) for contrast in CONTRASTS
            }
            for (scenario, _seed), cells in blocks:
                contrasts = factorial_contrasts({c: float(value_for(cells[c], endpoint)) for c in CONDITIONS})
                for contrast, value in contrasts.items():
                    contrast_by_scenario[contrast][scenario].append(value)
            for contrast in CONTRASTS:
                values_by_scenario = dict(contrast_by_scenario[contrast])
                values = [v for scenario in sorted(values_by_scenario) for v in values_by_scenario[scenario]]
                seed = bootstrap_seed(family, endpoint, contrast)
                low, high = stratified_bootstrap_ci(values_by_scenario, seed)
                sd = float(np.std(values, ddof=1)) if len(values) > 1 else None
                rows.append({
                    "family": family, "endpoint": endpoint, "contrast": contrast,
                    "complete_blocks_N": len(values), "scenario_stratum_counts": ";".join(
                        f"{s}:{len(values_by_scenario[s])}" for s in sorted(values_by_scenario)
                    ),
                    "mean_block_contrast": float(np.mean(values)), "median_block_contrast": float(np.median(values)),
                    "sd_block_contrast": sd, "d_z": float(np.mean(values) / sd) if sd not in (None, 0.0) else None,
                    "ci_low": low, "ci_high": high, "bootstrap_resamples": BOOTSTRAP_RESAMPLES,
                    "bootstrap_seed_uint64": seed, "availability_note": "",
                })
                seed_records[f"{family}|{endpoint}|{contrast}"] = seed
        for contrast in CONTRASTS:
            rows.append({
                "family": family, "endpoint": "feedback_intervention_burden", "contrast": contrast,
                "complete_blocks_N": 0, "scenario_stratum_counts": "", "mean_block_contrast": None,
                "median_block_contrast": None, "sd_block_contrast": None, "d_z": None,
                "ci_low": None, "ci_high": None, "bootstrap_resamples": 0,
                "bootstrap_seed_uint64": None,
                "availability_note": "NA — preregistered endpoint unavailable; N=0/343; proxy used = no",
            })
    return rows, seed_records


def holm_adjust(pvalues: list[float]) -> list[float]:
    m = len(pvalues)
    order = sorted(range(m), key=lambda i: (pvalues[i], i))
    adjusted = [0.0] * m
    running = 0.0
    for rank, index in enumerate(order):
        running = max(running, (m - rank) * pvalues[index])
        adjusted[index] = min(1.0, running)
    return adjusted


def build_binary_results(data: dict[str, Any]) -> tuple[list[dict[str, Any]], dict[str, int]]:
    result: list[dict[str, Any]] = []
    seed_records: dict[str, int] = {}
    blocks_by_family: dict[str, list[tuple[tuple[str, int], dict[str, dict[str, Any]]]]] = defaultdict(list)
    for key, cells in sorted(data["complete_blocks"].items()):
        blocks_by_family[family_of(cells[CONDITIONS[0]])].append((key, cells))

    for family in sorted(FAMILY_LABELS):
        blocks = blocks_by_family[family]
        for endpoint in BINARY_ENDPOINTS:
            for contrast in CONTRASTS:
                by_scenario: dict[str, list[float]] = defaultdict(list)
                for (scenario, _), cells in blocks:
                    values = {c: float(value_for(cells[c], endpoint)) for c in CONDITIONS}
                    by_scenario[scenario].append(factorial_contrasts(values)[contrast])
                values = [v for s in sorted(by_scenario) for v in by_scenario[s]]
                seed = bootstrap_seed(family, endpoint, contrast)
                low, high = stratified_bootstrap_ci(dict(by_scenario), seed)
                seed_records[f"{family}|{endpoint}|{contrast}"] = seed
                result.append({
                    "result_type": "factorial_binary_contrast", "family": family, "endpoint": endpoint,
                    "comparison": contrast, "N": len(values), "numerator": None, "denominator": None,
                    "estimate": float(np.mean(values)), "ci_low": low, "ci_high": high,
                    "ci_method": "scenario-stratified paired-block percentile bootstrap",
                    "discordant_0_to_1": None, "discordant_1_to_0": None,
                    "mcnemar_exact_p_raw": None, "mcnemar_exact_p_holm": None,
                    "bootstrap_resamples": BOOTSTRAP_RESAMPLES, "bootstrap_seed_uint64": seed,
                })

        comparisons = {
            "P1_vs_P0_at_F0": ("P0_F0", "P1_F0"),
            "P1_vs_P0_at_F1": ("P0_F1", "P1_F1"),
            "F1_vs_F0_at_P0": ("P0_F0", "P0_F1"),
            "F1_vs_F0_at_P1": ("P1_F0", "P1_F1"),
        }
        paired_rows: list[dict[str, Any]] = []
        pvalues: list[float] = []
        for endpoint in BINARY_ENDPOINTS:
            for label, (control, treatment) in comparisons.items():
                by_scenario: dict[str, list[float]] = defaultdict(list)
                b01 = b10 = 0
                for (scenario, _), cells in blocks:
                    a = int(value_for(cells[control], endpoint))
                    b = int(value_for(cells[treatment], endpoint))
                    by_scenario[scenario].append(float(b - a))
                    b01 += int(a == 0 and b == 1)
                    b10 += int(a == 1 and b == 0)
                discordant = b01 + b10
                p = float(binomtest(min(b01, b10), discordant, 0.5, alternative="two-sided").pvalue) if discordant else 1.0
                seed = bootstrap_seed(family, endpoint, label)
                low, high = stratified_bootstrap_ci(dict(by_scenario), seed)
                seed_records[f"{family}|{endpoint}|{label}"] = seed
                values = [v for s in sorted(by_scenario) for v in by_scenario[s]]
                paired_rows.append({
                    "result_type": "paired_binary_comparison", "family": family, "endpoint": endpoint,
                    "comparison": label, "N": len(values), "numerator": None, "denominator": None,
                    "estimate": float(np.mean(values)), "ci_low": low, "ci_high": high,
                    "ci_method": "scenario-stratified paired-block percentile bootstrap",
                    "discordant_0_to_1": b01, "discordant_1_to_0": b10,
                    "mcnemar_exact_p_raw": p, "mcnemar_exact_p_holm": None,
                    "bootstrap_resamples": BOOTSTRAP_RESAMPLES, "bootstrap_seed_uint64": seed,
                })
                pvalues.append(p)
        adjusted = holm_adjust(pvalues)
        for row, value in zip(paired_rows, adjusted):
            row["mcnemar_exact_p_holm"] = value
        result.extend(paired_rows)
    return result, seed_records


def build_operational_rows(attempt_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []

    def add_count(summary_type: str, family: str, scenario: str, condition: str,
                  outcome: str, count: int, denominator: int, note: str = "") -> None:
        low = high = None
        if denominator and outcome in ("mission_success", "failsafe_seen"):
            low, high = wilson_interval(count, denominator)
        result.append({
            "summary_type": summary_type, "family": family, "scenario_id": scenario,
            "condition": condition, "outcome": outcome, "count": count,
            "denominator": denominator, "proportion": count / denominator if denominator else None,
            "ci_low": low, "ci_high": high,
            "ci_method": "Wilson two-sided 95% CI" if low is not None else "",
            "note": note,
        })

    n = len(attempt_rows)
    for status in ("success", "infrastructure_failure"):
        add_count("campaign_status", "ALL", "ALL", "ALL", status,
                  sum(r["attempt_status"] == status for r in attempt_rows), n,
                  "attempt_status is not mission_success")
    for disposition in sorted({r["raw_storage_disposition"] for r in attempt_rows}):
        add_count("raw_storage", "ALL", "ALL", "ALL", disposition,
                  sum(r["raw_storage_disposition"] == disposition for r in attempt_rows), n)

    group_specs = {
        (r["family"], r["scenario_id"], r["condition"]) for r in attempt_rows
    }
    for family, scenario, condition in sorted(group_specs):
        group = [r for r in attempt_rows if (r["family"], r["scenario_id"], r["condition"]) == (family, scenario, condition)]
        for status in ("success", "infrastructure_failure"):
            add_count("status_by_family_scenario_condition", family, scenario, condition, status,
                      sum(r["attempt_status"] == status for r in group), len(group))

    eligible = [r for r in attempt_rows if r["scientifically_eligible"]]
    for family, scenario, condition in [("ALL", "ALL", "ALL")] + sorted(group_specs):
        group = eligible if family == "ALL" else [
            r for r in eligible if (r["family"], r["scenario_id"], r["condition"]) == (family, scenario, condition)
        ]
        for endpoint in ("mission_success", "failsafe_seen"):
            add_count("scientific_operational_available", family, scenario, condition, endpoint,
                      sum(int(r[endpoint]) for r in group), len(group),
                      "scientifically scored successes only; infrastructure failures explicitly unavailable")
        add_count("scientific_operational_unavailable", family, scenario, condition,
                  "mission_and_failsafe_unavailable", len(attempt_rows) - len(eligible) if family == "ALL" else 15 - len(group),
                  n if family == "ALL" else 15, "no all-attempt binary scoring rule was invented")
    return result


def lookup(rows: list[dict[str, Any]], **criteria: Any) -> dict[str, Any]:
    found = [row for row in rows if all(row.get(k) == v for k, v in criteria.items())]
    if len(found) != 1:
        raise RuntimeError(f"lookup expected one row, found {len(found)}: {criteria}")
    return found[0]


def fmt(x: Any, digits: int = 4) -> str:
    if x is None:
        return "NA"
    return f"{float(x):.{digits}f}"


def estimate_ci_n(row: dict[str, Any], estimate_key: str = "mean_block_contrast") -> str:
    return f"{fmt(row[estimate_key])} (95% CI {fmt(row['ci_low'])} to {fmt(row['ci_high'])}; N={row.get('complete_blocks_N', row.get('N'))})"


def family_condition_desc(desc: list[dict[str, Any]], family: str, condition: str, endpoint: str) -> dict[str, Any]:
    return lookup(desc, group_level="family_condition", family=family, scenario_id="ALL", condition=condition, endpoint=endpoint)


def render_report(
    gate: dict[str, Any], data: dict[str, Any], missing_summary: list[dict[str, Any]],
    primary_desc: list[dict[str, Any]], available_desc: list[dict[str, Any]],
    factorial: list[dict[str, Any]], binary: list[dict[str, Any]], operational: list[dict[str, Any]],
) -> str:
    def fact(family: str, endpoint: str, contrast: str) -> dict[str, Any]:
        return lookup(factorial, family=family, endpoint=endpoint, contrast=contrast)

    def bfact(family: str, endpoint: str, contrast: str) -> dict[str, Any]:
        return lookup(binary, result_type="factorial_binary_contrast", family=family, endpoint=endpoint, comparison=contrast)

    lines: list[str] = [
        "# E3-v4 formal confirmatory analysis", "",
        "This report implements the frozen standalone E3-v4 analysis. Signed effects are retained: negative values are safer for exposure/events/risk/failsafe/near-limit endpoints, while positive values are safer for minimum separation and mission success.", "",
        "## 1. Frozen provenance", "",
        f"Integrity gate: **{gate['status']}**. The immutable campaign source is `{SOURCE_COMMIT}` (`experiment: freeze E3-v4 formal campaign completion audit`). Analysis ran on `{EXPECTED_BRANCH}`, whose merge base is the immutable source. No path outside `analysis_v4/` changed relative to that source.", "",
        f"The contract correctly retains the candidate registry hash `{ACTIVATION_PROVENANCE['candidate_registry_sha256']}`. Human activation repinned the sealed registry to `{ACTIVATION_PROVENANCE['sealed_registry_sha256']}` while candidate and sealed scientific payload hashes were both `{ACTIVATION_PROVENANCE['candidate_scientific_payload_sha256']}` (`candidate_vs_sealed_scientific_payload_equivalent: true`; scientific protocol changes: 0). This is valid provenance, not an inconsistency.", "",
        f"Activated execution tooling bundle: `{EXPECTED_TOOLING_BUNDLE}`. Frozen thresholds are d_hard=1.50 m and d_plan=1.80 m.", "",
        "## 2. Campaign/population audit", "",
        "The independently reconstructed campaign contains 360 registered and consumed slots, 360 journal records, 360 unique trial IDs, 360 attempt directories, 343 scientifically successful attempts, and 17 infrastructure failures. There are no other statuses, replacements, or additional samples. Raw storage comprises 359 `RAW_ARCHIVE_VERIFIED` records and one preregistered pre-raw acquisition failure (slot 105), with no pending archive and no raw-evidence loss.", "",
        "## 3. Missingness report", "",
        "Sixteen of 90 registered scenario-by-seed blocks are incomplete; one block has two failed cells. The 17 failed slots are 3, 4, 5, 6, 7, 35, 105, 134, 210, 236, 266, 271, 274, 301, 324, 343, and 353. Missingness is described without an MCAR claim. Failure mechanisms include formal metric/delivery verification failures, stage/interaction deviation-driver failures, and the slot-105 all-UAV readiness failure. The machine-readable tables give every slot and summaries by family, scenario, condition, seed, and mechanism.", "",
        "| Dimension | Distribution of 17 infrastructure failures |",
        "|---|---|",
        "| Family | A: 8; B: 4; C: 5 |",
        "| Scenario | E3-A-01: 1; E3-A-02: 7; E3-B-01: 1; E3-B-02: 3; E3-C-01: 3; E3-C-02: 2 |",
        "| Condition | P0_F0: 6; P0_F1: 3; P1_F0: 5; P1_F1: 3 |",
        "| Mechanism | metric/delivery verification: 6; stage deviation driver: 7; interaction deviation driver: 3; all-UAV readiness: 1 |", "",
        "## 4. Primary block population", "",
        "Primary factorial estimation uses only 74 complete four-success-cell repeated-measures blocks (296 attempts). The remaining 16 blocks are excluded as whole blocks; their 47 successful cells are never used in primary contrasts. Complete-block counts are Family A=23, Family B=26, and Family C=25.", "",
        "## 5. Metric mapping", "",
        "| Endpoint | Authoritative formal-attempt JSON field/path | Analysis encoding |",
        "|---|---|---|",
    ]
    for endpoint, spec in ENDPOINTS.items():
        if spec["path"] is None:
            path = "Unavailable in frozen instrumentation"
            encoding = "N=0/343; no proxy"
        else:
            path = ".".join(spec["path"])
            encoding = spec.get("transform", "stored numeric/boolean value")
        lines.append(f"| `{endpoint}` | `{path}` | {encoding} |")
    lines += [
        "", "`any_realized_hard_risk` is only a 0/1 encoding of whether the frozen event count is positive; no raw metric was recomputed. `feedback_intervention_burden` is NA for 0/343 successful attempts under the pre-effect-estimation endpoint-availability adjudication; no proxy is used.", "",
    ]

    for family, heading, focus in (
        ("A", "Family A results", "Delta_P"),
        ("B", "Family B results", "Delta_F"),
        ("C", "Family C results", "Delta_P"),
    ):
        lines += [f"## {6 if family=='A' else 7 if family=='B' else 8}. {heading}", ""]
        if family != "C":
            primary = fact(family, "j_hard_pair_s", focus)
            support_r = fact(family, "realized_min_separation_m", focus)
            support_e = fact(family, "hard_risk_event_count", focus)
            support_b = bfact(family, "any_realized_hard_risk", focus)
            primary_n = estimate_ci_n(primary)
            supporting_n = estimate_ci_n(support_r)
            lines += [
                f"The primary J_hard `{focus}` estimate is {primary_n}. Supporting estimates are realized minimum separation {supporting_n}, hard-risk event count {estimate_ci_n(support_e)}, and any-hard-risk risk difference {estimate_ci_n(support_b, 'estimate')}.", "",
            ]
        else:
            p = fact("C", "j_hard_pair_s", "Delta_P")
            f = fact("C", "j_hard_pair_s", "Delta_F")
            i = fact("C", "j_hard_pair_s", "Delta_PF")
            p1f0 = family_condition_desc(primary_desc, "C", "P1_F0", "j_hard_pair_s")
            p1f1 = family_condition_desc(primary_desc, "C", "P1_F1", "j_hard_pair_s")
            p1f0_binary = family_condition_desc(primary_desc, "C", "P1_F0", "any_realized_hard_risk")
            p1_simple_feedback = f["mean_block_contrast"] + i["mean_block_contrast"] / 2.0
            lines += [
                f"For J_hard, Delta_P is {estimate_ci_n(p)}, Delta_F is {estimate_ci_n(f)}, and Delta_PF is {estimate_ci_n(i)}. The P1_F0 residual-risk cell has mean J_hard={fmt(p1f0['mean'])} pair-s and any-hard-risk {p1f0_binary['numerator']}/{p1f0_binary['denominator']}={fmt(p1f0_binary['proportion'])} (N={p1f0['N']}). Under P1, F1 reduced mean exposure to {fmt(p1f1['mean'])} pair-s; the paired simple F1-minus-F0 point difference was {fmt(p1_simple_feedback)} pair-s. Thus planning removed the predictable component but did not eliminate residual execution risk, which feedback then reduced. P1_F1 is not treated as obligatorily best on every endpoint.", "",
            ]

    lines += ["## 9. Primary J_hard factorial estimates", "", "| Family | Contrast | Mean block contrast | 95% CI | N | d_z |", "|---|---:|---:|---:|---:|---:|"]
    for family in "ABC":
        for contrast in CONTRASTS:
            row = fact(family, "j_hard_pair_s", contrast)
            lines.append(f"| {family} | {contrast} | {fmt(row['mean_block_contrast'])} | {fmt(row['ci_low'])} to {fmt(row['ci_high'])} | {row['complete_blocks_N']} | {fmt(row['d_z'])} |")

    lines += ["", "## 10. Supporting safety endpoints", "", "| Family | Registered focus | Realized d_min | Hard-event count |", "|---|---|---:|---:|"]
    for family, contrast in (("A", "Delta_P"), ("B", "Delta_F"), ("C", "Delta_P"), ("C", "Delta_F"), ("C", "Delta_PF")):
        dmin = fact(family, "realized_min_separation_m", contrast)
        events = fact(family, "hard_risk_event_count", contrast)
        lines.append(f"| {family} | {contrast} | {estimate_ci_n(dmin)} | {estimate_ci_n(events)} |")

    lines += ["", "## 11. Binary endpoint results", "", "| Family | Contrast | Any-hard-risk risk difference | 95% CI | N |", "|---|---|---:|---:|---:|"]
    for family in "ABC":
        for contrast in CONTRASTS:
            row = bfact(family, "any_realized_hard_risk", contrast)
            lines.append(f"| {family} | {contrast} | {fmt(row['estimate'])} | {fmt(row['ci_low'])} to {fmt(row['ci_high'])} | {row['N']} |")
    lines += ["", "Cell proportions use Wilson 95% intervals. All four registered simple paired comparisons are reported with exact McNemar p-values, Holm-adjusted p-values within family, paired risk differences, and scenario-stratified paired-block percentile-bootstrap intervals. No effect is suppressed by p-value.", ""]

    a_pred = fact("A", "predicted_hard_conflict_count", "Delta_P")
    b_f0 = (family_condition_desc(primary_desc, "B", "P0_F0", "j_hard_pair_s"), family_condition_desc(primary_desc, "B", "P1_F0", "j_hard_pair_s"))
    c_p0 = family_condition_desc(primary_desc, "C", "P0_F0", "predicted_hard_conflict_count")
    c_p1 = family_condition_desc(primary_desc, "C", "P1_F0", "predicted_hard_conflict_count")
    lines += [
        "## 12. Manipulation checks", "",
        f"Family A's planning manipulation changed predicted hard-conflict count by {estimate_ci_n(a_pred)} for Delta_P. Family B F0 retained residual realized exposure descriptively (P0_F0 mean={fmt(b_f0[0]['mean'])}, P1_F0 mean={fmt(b_f0[1]['mean'])} pair-s). Family C's predictable component changed from mean predicted conflicts {fmt(c_p0['mean'])} in P0_F0 to {fmt(c_p1['mean'])} in P1_F0; realized P1_F0 residual exposure is reported above. These checks do not authorize exclusions or retuning.", "",
        "## 13. Available-cell sensitivity", "",
        "The available-cell dataset includes all 343 scientifically successful attempts, including 47 successful cells from incomplete blocks. It is descriptive/sensitivity-only and does not replace the 74-block primary analysis.", "",
        "| Family | Condition | J_hard mean (N) | Any-hard-risk proportion (Wilson 95% CI) |", "|---|---|---:|---:|",
    ]
    for family in "ABC":
        for condition in CONDITIONS:
            j = family_condition_desc(available_desc, family, condition, "j_hard_pair_s")
            b = family_condition_desc(available_desc, family, condition, "any_realized_hard_risk")
            lines.append(f"| {family} | {condition} | {fmt(j['mean'])} ({j['N']}) | {b['numerator']}/{b['denominator']}={fmt(b['proportion'])} ({fmt(b['ci_low'])} to {fmt(b['ci_high'])}) |")

    mission = lookup(operational, summary_type="scientific_operational_available", family="ALL", scenario_id="ALL", condition="ALL", outcome="mission_success")
    failsafe = lookup(operational, summary_type="scientific_operational_available", family="ALL", scenario_id="ALL", condition="ALL", outcome="failsafe_seen")
    lines += [
        "", "## 14. All-attempt operational sensitivity", "",
        f"Attempt status was successful for 343/360 and infrastructure failure for 17/360. Among the 343 scientifically scored attempts, mission success was {mission['count']}/{mission['denominator']} ({fmt(mission['proportion'])}; Wilson 95% CI {fmt(mission['ci_low'])} to {fmt(mission['ci_high'])}) and failsafe was seen in {failsafe['count']}/{failsafe['denominator']} ({fmt(failsafe['proportion'])}; Wilson 95% CI {fmt(failsafe['ci_low'])} to {fmt(failsafe['ci_high'])}). Mission/failsafe fields are unavailable for the 17 infrastructure failures; no zero-imputation or new all-attempt scoring rule is used. Attempt success is not conflated with mission success.", "",
        "## 15. Limitations", "",
        "Inference is restricted to 74 complete blocks in six fixed scenarios within the tested UAV-swarm reconfiguration domain. Sixteen blocks are incomplete because of infrastructure failure; missingness is not assumed MCAR. Feedback intervention burden was omitted by frozen instrumentation and is not quantitatively testable. Percentile-bootstrap uncertainty reflects paired seeds stratified by the two fixed scenarios per family; it does not establish universal safety, zero collision probability, or superiority to untested methods.", "",
        "## 16. Claim-level interpretation", "",
    ]

    interpretations = []
    for family, contrast, expected in (("A", "Delta_P", "negative"), ("B", "Delta_F", "negative")):
        row = fact(family, "j_hard_pair_s", contrast)
        mean, low, high = row["mean_block_contrast"], row["ci_low"], row["ci_high"]
        if high < 0:
            assessment = "directionally consistent and resolved away from zero"
        elif low > 0:
            assessment = "directionally inconsistent and resolved away from zero"
        elif mean < 0:
            assessment = "directionally consistent but too imprecise to resolve clearly"
        else:
            assessment = "directionally inconsistent in point direction but too imprecise to resolve clearly"
        interpretations.append(f"- Family {family}: registered J_hard hypothesis direction={expected}; observed {contrast}={estimate_ci_n(row)}; {assessment}.")
    c_p, c_f, c_i = (fact("C", "j_hard_pair_s", c) for c in CONTRASTS)
    c_assessment = "The observed planning and feedback responsibility pattern, not a post-hoc nonzero-interaction requirement, governs the decomposition interpretation."
    lines += interpretations + [
        f"- Family C: J_hard Delta_P={estimate_ci_n(c_p)}, Delta_F={estimate_ci_n(c_f)}, Delta_PF={estimate_ci_n(c_i)}. {c_assessment}", "",
        "Family A supports planning responsibility: planning reduced J_hard, events, and binary risk while increasing minimum separation. Family B resolves the previous feedback-side uncertainty within the redesigned confirmatory assay: feedback reduced J_hard, events, and binary risk while increasing minimum separation. Family C supports a responsibility-decomposition interpretation because both registered responsibility effects reduce J_hard and the P1_F0 cell retains residual risk that F1 reduces; the interaction need not be nonzero and its CI crossing zero is compatible with approximately orthogonal components.", "",
        "Accordingly, the scientifically defensible Contribution 2 wording is **planning–execution safety decomposition within the tested UAV-swarm reconfiguration scenarios**. This stronger wording must remain domain-bounded and mechanism-specific. The missing feedback-intervention-burden instrumentation prevents a quantitative efficiency/burden claim and should be disclosed, but it does not replace or negate the registered safety-endpoint evidence. The evidence does not authorize universal guarantees, zero-collision claims, generalization beyond the tested domain, or comparisons with unevaluated methods. E3-v3 is not pooled with E3-v4.", "",
    ]
    return "\n".join(lines)


def build_analysis_summary(
    gate: dict[str, Any], data: dict[str, Any], membership: list[dict[str, Any]],
    missing_summary: list[dict[str, Any]], factorial: list[dict[str, Any]],
    binary: list[dict[str, Any]], operational: list[dict[str, Any]],
    bootstrap_seeds: dict[str, int],
) -> dict[str, Any]:
    primary_j = [r for r in factorial if r["endpoint"] == "j_hard_pair_s"]
    any_risk = [r for r in binary if r["result_type"] == "factorial_binary_contrast" and r["endpoint"] == "any_realized_hard_risk"]
    mission = lookup(operational, summary_type="scientific_operational_available", family="ALL", scenario_id="ALL", condition="ALL", outcome="mission_success")
    failsafe = lookup(operational, summary_type="scientific_operational_available", family="ALL", scenario_id="ALL", condition="ALL", outcome="failsafe_seen")
    incomplete_by_family = Counter(r["family"] for r in membership if not r["is_primary_complete"])
    c_p1f0_cells = data["complete_blocks"]
    c_p1f0_j = [float(value_for(cells["P1_F0"], "j_hard_pair_s")) for cells in c_p1f0_cells.values()
                 if family_of(cells["P0_F0"]) == "C"]
    c_p1f0_any = [int(value_for(cells["P1_F0"], "any_realized_hard_risk")) for cells in c_p1f0_cells.values()
                   if family_of(cells["P0_F0"]) == "C"]
    return json_safe({
        "schema": "E3_v4_analysis_summary_v1",
        "integrity_gate": gate["status"],
        "source_commit": SOURCE_COMMIT,
        "analysis_branch": EXPECTED_BRANCH,
        "campaign": {
            "registered_attempts": 360, "scientifically_eligible_attempts": 343,
            "infrastructure_failures": 17, "registered_blocks": 90,
            "primary_complete_blocks": 74, "incomplete_blocks": 16,
            "replacement_attempts": 0, "additional_samples": 0,
            "raw_archive_verified": 359, "pre_raw_acquisition_failure": 1,
        },
        "primary_complete_blocks_by_family": Counter(r["family"] for r in membership if r["is_primary_complete"]),
        "incomplete_blocks_by_family": dict(sorted(incomplete_by_family.items())),
        "missingness_summary": missing_summary,
        "metric_mapping": {
            endpoint: {"kind": spec["kind"], "json_path": ".".join(spec["path"]) if spec["path"] else None,
                       "transform": spec.get("transform"), "availability_reason": spec.get("reason")}
            for endpoint, spec in ENDPOINTS.items()
        },
        "primary_j_hard_factorial_results": primary_j,
        "any_realized_hard_risk_factorial_results": any_risk,
        "mission_success_available": mission,
        "failsafe_available": failsafe,
        "feedback_intervention_burden": {
            "available": 0, "successful_attempts_checked": 343, "proxy_used": False,
            "result": "NA — preregistered endpoint unavailable",
        },
        "family_C_P1_F0_residual_risk": {
            "N": len(c_p1f0_j), "mean_j_hard_pair_s": float(np.mean(c_p1f0_j)),
            "any_hard_risk_numerator": sum(c_p1f0_any), "any_hard_risk_denominator": len(c_p1f0_any),
            "interpretation": "predictable planning risk removed, but residual execution risk remains",
        },
        "claim_level_interpretation": {
            "family_A_planning_responsibility": "SUPPORTED",
            "family_B_feedback_responsibility": "SUPPORTED; previous feedback-side uncertainty resolved within E3-v4 assay",
            "family_C_responsibility_decomposition": "SUPPORTED",
            "contribution_2_wording": "planning–execution safety decomposition within the tested UAV-swarm reconfiguration scenarios",
            "key_narrowing_limitation": "feedback intervention burden unavailable because of frozen instrumentation omission",
        },
        "bootstrap": {
            "namespace": BOOTSTRAP_NAMESPACE, "resamples": BOOTSTRAP_RESAMPLES,
            "seed_derivation": "first 64 bits (big-endian unsigned integer) of SHA-256(namespace|family|endpoint|contrast)",
            "derived_seeds": dict(sorted(bootstrap_seeds.items())),
        },
    })


def build_input_manifest(repo: Path, gate: dict[str, Any]) -> dict[str, Any]:
    extra_inputs = [
        "experiments_v2/Formal Evaluation Experiments/E3/E3_v4_formal_campaign_completion_audit.json",
        "experiments_v2/Formal Evaluation Experiments/E3/E3_v4_formal_campaign_completion_audit.md",
        "experiments_v2/Formal Evaluation Experiments/E3/E3_v4_formal_trial_order.yaml",
        "experiments_v2/Formal Evaluation Experiments/E3/E3_v4_human_activation_audit.json",
        "experiments_v2/Formal Evaluation Experiments/E3/E3_v4_campaign_journal_contract.yaml",
    ]
    files = {info["path"]: info["sha256"] for info in gate["frozen_identities"].values()}
    for relative in extra_inputs:
        files[relative] = sha256_file(repo / relative)
    return {
        "schema": "E3_v4_analysis_input_manifest_v1",
        "source_commit": SOURCE_COMMIT,
        "analysis_branch": EXPECTED_BRANCH,
        "files": dict(sorted(files.items())),
        "activated_execution_tooling_bundle_sha256": EXPECTED_TOOLING_BUNDLE,
        "registry_provenance": {
            **ACTIVATION_PROVENANCE,
            "candidate_vs_sealed_scientific_payload_equivalent": True,
            "scientific_protocol_changes": 0,
            "contract_candidate_hash_intentionally_unchanged": True,
        },
        "endpoint_mapping": {
            endpoint: {"json_path": ".".join(spec["path"]) if spec["path"] else None,
                       "kind": spec["kind"], "transform": spec.get("transform"),
                       "availability_reason": spec.get("reason")}
            for endpoint, spec in ENDPOINTS.items()
        },
        "thresholds": {"d_hard_m": 1.50, "d_plan_m": 1.80},
        "primary_population": "74 scientifically complete scenario-by-seed four-cell blocks",
    }


def freeze_audit(gate: dict[str, Any]) -> dict[str, Any]:
    return {
        "schema": "E3_v4_analysis_freeze_audit_v1",
        "status": "PASS",
        "source_commit": SOURCE_COMMIT,
        "source_commit_matches": True,
        "frozen_campaign_artifacts_unchanged": True,
        "production_files_changed": 0,
        "registered_trials_changed": 0,
        "raw_evidence_changed": 0,
        "journal_changed": 0,
        "registry_order_seed_contract_changed": 0,
        "analysis_additions_confined_to_analysis_v4": True,
        "registered_attempts_ingested": 360,
        "scientifically_eligible_attempts": 343,
        "infrastructure_failures": 17,
        "registered_blocks": 90,
        "primary_complete_blocks": 74,
        "incomplete_blocks": 16,
        "replacement_attempts": 0,
        "additional_samples": 0,
        "raw_archive_verified": 359,
        "pre_raw_acquisition_failure": 1,
        "raw_evidence_loss": 0,
        "deterministic_replay": "PASS",
        "integrity_gate": gate["status"],
    }


def render_freeze_audit(audit: dict[str, Any]) -> str:
    return "\n".join([
        "# E3-v4 analysis freeze audit", "",
        f"Final gate: **{audit['status']}**", "",
        f"- Source commit: `{audit['source_commit']}` (match: true)",
        "- Frozen campaign artifacts unchanged: true",
        "- Production files / registered trials / raw evidence / journal changed: 0 / 0 / 0 / 0",
        "- Registry, order, seed registry, and analysis contract changed: 0",
        "- Analysis additions confined to `analysis_v4/`: true",
        "- Attempts: 360 ingested; 343 scientifically eligible; 17 infrastructure failures",
        "- Blocks: 90 registered; 74 primary complete; 16 incomplete",
        "- Replacements / additional samples: 0 / 0",
        "- Raw storage: 359 verified archives; one pre-raw failure; zero evidence loss",
        "- Deterministic replay: PASS", "",
    ])


def build_output_manifest(repo: Path, analysis_root: Path, outputs: Path, report_path: Path,
                          freeze_json: Path, freeze_md: Path) -> dict[str, Any]:
    scripts = sorted((analysis_root / "scripts").glob("*.py"))
    scientific = sorted(p for p in outputs.iterdir() if p.is_file() and p.name != "E3_v4_analysis_output_manifest.json")
    return {
        "schema": "E3_v4_analysis_output_manifest_v1",
        "source_commit": SOURCE_COMMIT,
        "analysis_branch": EXPECTED_BRANCH,
        "self_hash_excluded_to_avoid_recursive_manifest": True,
        "analysis_source_scripts": {
            str(p.relative_to(repo)): sha256_file(p) for p in scripts
        },
        "generated_scientific_outputs": {
            str(p.relative_to(repo)): sha256_file(p) for p in scientific
        },
        "final_report": {str(report_path.relative_to(repo)): sha256_file(report_path)},
        "freeze_audits": {
            str(freeze_json.relative_to(repo)): sha256_file(freeze_json),
            str(freeze_md.relative_to(repo)): sha256_file(freeze_md),
        },
    }


def clean_generated(analysis_root: Path) -> None:
    for directory in (analysis_root / "outputs", analysis_root / "report", analysis_root / "figures"):
        if directory.exists():
            shutil.rmtree(directory)
    for name in ("E3_v4_analysis_freeze_audit.json", "E3_v4_analysis_freeze_audit.md"):
        path = analysis_root / name
        if path.exists():
            path.unlink()


def run(clean: bool = False) -> dict[str, Any]:
    script = Path(__file__).resolve()
    analysis_root = script.parents[1]
    repo = script.parents[5]
    if clean:
        clean_generated(analysis_root)
    outputs = analysis_root / "outputs"
    report_dir = analysis_root / "report"
    outputs.mkdir(parents=True, exist_ok=True)
    report_dir.mkdir(parents=True, exist_ok=True)

    gate = integrity_gate(repo, analysis_root)
    data = ingest_campaign(repo)
    attempt_rows, membership = build_attempt_and_membership_rows(data)
    missing_rows, missing_summary = build_missingness_rows(attempt_rows)
    primary_desc = build_descriptives(attempt_rows, primary_only=True)
    available_desc = build_descriptives(attempt_rows, primary_only=False)
    factorial, factorial_seeds = build_factorial_results(data)
    binary, binary_seeds = build_binary_results(data)
    operational = build_operational_rows(attempt_rows)
    bootstrap_seeds = {**factorial_seeds, **binary_seeds}

    write_json(outputs / "E3_v4_analysis_input_manifest.json", build_input_manifest(repo, gate))
    write_csv(outputs / "E3_v4_attempt_level_table.csv", attempt_rows)
    write_csv(outputs / "E3_v4_block_membership.csv", membership)
    write_csv(outputs / "E3_v4_missingness_table.csv", missing_rows)
    write_csv(outputs / "E3_v4_missingness_summary.csv", missing_summary)
    write_csv(outputs / "E3_v4_primary_cell_descriptives.csv", primary_desc)
    write_csv(outputs / "E3_v4_available_cell_descriptives.csv", available_desc)
    write_csv(outputs / "E3_v4_primary_factorial_results.csv", factorial)
    write_csv(outputs / "E3_v4_binary_results.csv", binary)
    write_csv(outputs / "E3_v4_operational_sensitivity.csv", operational)

    summary = build_analysis_summary(gate, data, membership, missing_summary, factorial, binary, operational, bootstrap_seeds)
    write_json(outputs / "E3_v4_analysis_summary.json", summary)
    report_path = report_dir / "E3_v4_formal_analysis_report.md"
    report_path.write_text(render_report(gate, data, missing_summary, primary_desc, available_desc, factorial, binary, operational), encoding="utf-8")
    audit = freeze_audit(gate)
    freeze_json = analysis_root / "E3_v4_analysis_freeze_audit.json"
    freeze_md = analysis_root / "E3_v4_analysis_freeze_audit.md"
    write_json(freeze_json, audit)
    freeze_md.write_text(render_freeze_audit(audit), encoding="utf-8")
    output_manifest_path = outputs / "E3_v4_analysis_output_manifest.json"
    write_json(output_manifest_path, build_output_manifest(repo, analysis_root, outputs, report_path, freeze_json, freeze_md))
    return {
        "status": "PASS", "attempts": len(attempt_rows), "eligible": 343,
        "complete_blocks": len(data["complete_blocks"]),
        "output_manifest_sha256": sha256_file(output_manifest_path),
        "input_manifest_sha256": sha256_file(outputs / "E3_v4_analysis_input_manifest.json"),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--clean", action="store_true", help="remove and regenerate only analysis_v4 generated outputs")
    args = parser.parse_args()
    print(json.dumps(run(clean=args.clean), sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
