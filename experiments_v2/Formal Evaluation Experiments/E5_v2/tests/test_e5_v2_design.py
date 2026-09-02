"""Governance and determinism checks for the prospective E5-v2 protocol."""

from __future__ import annotations

import hashlib
import importlib.util
import json
import subprocess
import sys
from collections import Counter
from pathlib import Path

import pytest


HERE = Path(__file__).resolve()
E5_DIR = HERE.parents[1]
TOOLING = E5_DIR / "tooling"
REPO = HERE.parents[4]
sys.path.insert(0, str(TOOLING))

from e5_v2_common import (  # noqa: E402
    BASELINE_COMMIT,
    OLD_E5_REGISTRY_PATH,
    OLD_E5_REGISTRY_SHA256,
    OLD_E5_SOURCE_COMMIT,
    ORDER_METADATA_PATH,
    ORDER_PATH,
    PRODUCTION_METHOD_PATHS,
    REGISTRY_PATH,
    SEED_REGISTRY_PATH,
    attempt_order_text,
    canonical_attempts,
    flatten_conditions,
    load_yaml,
    ordered_attempts,
    sha256_file,
    uav_ids,
)
from e5_v2_formal_adapter import (  # noqa: E402
    FormalActivationError,
    assert_formal_activation,
)
from e5_v2_freeze import render  # noqa: E402


def test_registered_configuration_parsing_and_dynamic_ids():
    registry = load_yaml(REGISTRY_PATH)
    assert sorted(int(value) for value in registry["common"]["swarm_ids_by_n"]) == [8, 12, 16]
    for n in (8, 12, 16):
        assert registry["common"]["swarm_ids_by_n"][n] == uav_ids(n)
    with pytest.raises(ValueError):
        uav_ids(10)


def test_no_hard_coded_eight_uav_assumption_in_e5_v2_python_infrastructure():
    forbidden = ("range(1, 9)", "range(8)", "uav_count = 8", "-n\", \"8")
    offenders = []
    for path in TOOLING.glob("*.py"):
        source = path.read_text(encoding="utf-8")
        if any(token in source for token in forbidden):
            offenders.append(path.name)
    assert offenders == []


def test_candidate_registry_completeness_and_exact_ground_truth():
    registry = load_yaml(REGISTRY_PATH)
    conditions = flatten_conditions(registry)
    assert registry["registry_id"] == "E5-end-to-end-v2"
    assert registry["status"] == "CANDIDATE_FOR_HUMAN_REVIEW"
    assert len(conditions) == 12
    assert len(registry["scenarios"]["E5-v2A"]) == 3
    assert len(registry["scenarios"]["E5-v2B"]) == 9
    assert all(value["exact_command"].strip() for value in conditions)
    assert all(
        value["candidate_semantic_ground_truth"]["lfs_version"] == "2.1"
        for value in conditions
    )


def test_feasibility_audit_is_current_and_deterministic():
    completed = subprocess.run(
        [sys.executable, str(TOOLING / "e5_v2_feasibility.py"), "--check"],
        cwd=REPO,
        text=True,
        capture_output=True,
        timeout=180,
    )
    assert completed.returncode == 0, completed.stdout + completed.stderr
    audit = json.loads((E5_DIR / "E5_v2_feasibility_audit.json").read_text())
    assert audit["status"] == "PASS"
    assert audit["selected_scale_cells"] == 12
    assert all(row["feasible"] for row in audit["rows"] if row["selected"])


def test_seed_uniqueness_population_and_cell_counts():
    document = load_yaml(SEED_REGISTRY_PATH)
    attempts = document["attempts"]
    seeds = [int(item["seed"]) for item in attempts]
    excluded = {
        int(seed)
        for values in document["collision_exclusions"].values()
        for seed in values
    }
    assert attempts == canonical_attempts()
    assert len(attempts) == 60
    assert len(seeds) == len(set(seeds))
    assert not set(seeds).intersection(excluded)
    assert sum(item["substudy"] == "E5-v2A" for item in attempts) == 15
    assert sum(item["substudy"] == "E5-v2B" for item in attempts) == 45
    counts = Counter(
        (item["N"], item.get("task_family"))
        for item in attempts if item["substudy"] == "E5-v2B"
    )
    assert all(
        counts[(n, family)] == 5
        for n in (8, 12, 16)
        for family in ("SIMPLE", "UNDER_SPECIFIED", "COMPOSITIONAL")
    )


def test_trial_order_is_deterministic_exact_and_interleaved():
    seed_yaml, order_text, metadata_json = render()
    assert SEED_REGISTRY_PATH.read_text(encoding="utf-8") == seed_yaml
    assert ORDER_PATH.read_text(encoding="utf-8") == order_text
    assert ORDER_METADATA_PATH.read_text(encoding="utf-8") == metadata_json
    order = ordered_attempts()
    assert len(order) == 60
    assert len({item["attempt_id"] for item in order}) == 60
    # Each chronological 12-attempt stratum contains all 12 conditions once.
    for offset in range(0, 60, 12):
        block = order[offset:offset + 12]
        assert len({item["scenario_id"] for item in block}) == 12
        assert {item["N"] for item in block} == {8, 12, 16}
        assert {item["substudy"] for item in block} == {"E5-v2A", "E5-v2B"}


def test_formal_adapter_refuses_candidate_and_requires_human_activation():
    with pytest.raises(FormalActivationError, match="refuses non-activated"):
        assert_formal_activation(REGISTRY_PATH, None)
    completed = subprocess.run(
        [
            sys.executable, str(TOOLING / "e5_v2_formal_adapter.py"),
            "--authorization-check",
        ],
        cwd=REPO,
        text=True,
        capture_output=True,
    )
    assert completed.returncode == 2
    result = json.loads(completed.stdout)
    assert result["authorized"] is False
    assert result["formal_execution_started"] is False


def test_old_e5_v1_registry_byte_hash_unchanged():
    content = subprocess.check_output(
        ["git", "show", f"{OLD_E5_SOURCE_COMMIT}:{OLD_E5_REGISTRY_PATH}"],
        cwd=REPO,
    )
    assert hashlib.sha256(content).hexdigest() == OLD_E5_REGISTRY_SHA256


def test_production_method_files_unchanged_from_frozen_baseline():
    completed = subprocess.run(
        ["git", "diff", "--quiet", BASELINE_COMMIT, "--", *PRODUCTION_METHOD_PATHS],
        cwd=REPO,
    )
    assert completed.returncode == 0


def test_no_formal_e5_v2_attempt_or_journal_exists():
    registry = load_yaml(REGISTRY_PATH)
    assert registry["formal_execution_started"] is False
    assert registry["accepted_formal_results_created"] is False
    assert registry["governance"]["formal_trials_created"] == 0
    assert not (E5_DIR / "results/formal").exists()
    assert not (E5_DIR / "formal_journal").exists()
