from __future__ import annotations

import hashlib
import itertools
import math
from pathlib import Path
import sys

import pytest
import yaml

from e3_formal_backend import build_runtime_spec
from e3_trial_registry import (
    CONDITIONS,
    ORDER_PATH,
    POLICY_PATH,
    PROTOCOL_PATH,
    PROTOCOL_SHA256,
    REGISTRY_PATH,
    REGISTRY_SHA256,
    build_exact_spec,
)


E3_DIR = Path(__file__).resolve().parent.parent
CANDIDATE_PROTOCOL = E3_DIR.parent / "protocols" / "E3_protocol_v3_candidate.yaml"
CANDIDATE_REGISTRY = E3_DIR / "e3_factorial_registry_v3_candidate.yaml"
V2_REGISTRY = E3_DIR / "e3_factorial_registry_v2.yaml"
EXPECTED_TARGETS = {
    1: [-3, 4, 3],
    2: [3, 4, 3],
    3: [-2, 12, 3],
    4: [0, 12, 3],
}


def _yaml(path):
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def _scenario_map(registry):
    return {item["scenario_id"]: item for item in registry["scenarios"]}


def _runtime(registry, scenario_id, condition):
    trial_id = f"{scenario_id}__{condition}__S53101"
    return build_runtime_spec(build_exact_spec(trial_id, registry=registry))


def test_candidate_is_preserved_and_defaults_are_active_v3():
    protocol = _yaml(CANDIDATE_PROTOCOL)
    registry = _yaml(CANDIDATE_REGISTRY)
    assert protocol["status"] == "CANDIDATE_FOR_HUMAN_REVIEW_NOT_ACTIVE"
    assert registry["status"] == "CANDIDATE_FOR_HUMAN_REVIEW_NOT_ACTIVE"
    assert protocol["activation_prohibited_without_human_review"] is True
    assert registry["activation_prohibited_without_human_review"] is True
    assert PROTOCOL_PATH.name == "E3_protocol_v3.yaml"
    assert REGISTRY_PATH.name == "e3_factorial_registry_v3.yaml"
    assert hashlib.sha256(PROTOCOL_PATH.read_bytes()).hexdigest() == PROTOCOL_SHA256
    assert hashlib.sha256(REGISTRY_PATH.read_bytes()).hexdigest() == REGISTRY_SHA256


def test_A01_and_C01_share_only_the_candidate_structural_geometry():
    v2 = _scenario_map(_yaml(V2_REGISTRY))
    v3 = _scenario_map(_yaml(CANDIDATE_REGISTRY))
    a01, c01 = v3["E3-A-01"], v3["E3-C-01"]
    assert a01["ordered_targets_m"] == c01["ordered_targets_m"] == EXPECTED_TARGETS
    for scenario_id in ("E3-A-01", "E3-C-01"):
        old, new = v2[scenario_id], v3[scenario_id]
        assert old["initial_positions_m"] == new["initial_positions_m"]
        assert old["uav_ids"] == new["uav_ids"]
        assert old["duration_s"] == new["duration_s"] == 6.0
        assert old["disturbance"] == new["disturbance"]
    assert not a01["disturbance"]["affected_uavs"]
    assert c01["disturbance"]["affected_uavs"] == [1, 3]


@pytest.mark.parametrize("scenario_id", ["E3-A-01", "E3-C-01"])
def test_production_P0_and_P1_restore_the_planning_safety_contrast(scenario_id):
    registry = _yaml(CANDIDATE_REGISTRY)
    p0 = _runtime(registry, scenario_id, "P0_F0")
    p1 = _runtime(registry, scenario_id, "P1_F0")
    d0, d1 = p0["allocator_diagnostics"], p1["allocator_diagnostics"]
    assert d0["final_assignment"] == [2, 3, 0, 1]
    assert d1["final_assignment"] == [0, 1, 2, 3]
    assert d0["hard_violations"] == 2
    assert d1["hard_violations"] == 0
    assert d0["min_distance"] == pytest.approx(0.42748229992745784)
    assert d1["min_distance"] == pytest.approx(2.0)
    assert d0["margin_cost"] == pytest.approx(0.672365532501112)
    assert d1["margin_cost"] == pytest.approx(0.0)
    initial = p0["initial_positions_m"]
    assert all(math.dist(start, target) > 0 for start, target in zip(initial, p0["assigned_targets_m"]))
    assert all(math.dist(start, target) > 0 for start, target in zip(initial, p1["assigned_targets_m"]))


def test_all_24_assignments_confirm_unique_P0_and_global_P1():
    for path in (E3_DIR.parents[2] / "location_allocate", E3_DIR.parents[2] / "lfs_policy"):
        if str(path) not in sys.path:
            sys.path.insert(0, str(path))
    from location_allocate.policy_adapter import load_runtime_policy

    _, policy = load_runtime_policy(POLICY_PATH)
    safety = policy.resolve_safety(1.0)
    evaluator = policy.allocator_factory(safety.d_hard, safety.d_plan)
    initial = [[-3.0, -3.0, 3.0], [3.0, -3.0, 3.0], [-3.0, 3.0, 3.0], [3.0, 3.0, 3.0]]
    targets = [[float(value) for value in EXPECTED_TARGETS[index]] for index in range(1, 5)]
    rows = []
    for permutation in itertools.permutations(range(4)):
        metrics = evaluator.evaluate(initial, targets, permutation, 6.0)
        rows.append((permutation, metrics))
    minimum_distance = min(metrics.distance for _permutation, metrics in rows)
    distance_optima = [
        permutation for permutation, metrics in rows
        if abs(metrics.distance - minimum_distance) <= 1e-9
    ]
    global_lex = min(
        rows,
        key=lambda item: (
            item[1].hard_violations,
            item[1].margin_cost,
            item[1].distance,
        ),
    )
    assert distance_optima == [(2, 3, 0, 1)]
    assert global_lex[0] == (0, 1, 2, 3)


def test_minimum_jerk_static_separation_and_workspace_filters_pass():
    for path in (E3_DIR.parents[2] / "location_allocate", E3_DIR.parents[2] / "lfs_policy"):
        if str(path) not in sys.path:
            sys.path.insert(0, str(path))
    from location_allocate.motion_limits import minimum_jerk_peaks

    registry = _yaml(CANDIDATE_REGISTRY)
    targets = [[float(value) for value in EXPECTED_TARGETS[index]] for index in range(1, 5)]
    assert min(math.dist(a, b) for a, b in itertools.combinations(targets, 2)) == 2.0
    assert all(-15 <= x <= 15 and -10 <= y <= 35 and 0.5 <= z <= 15 for x, y, z in targets)
    for condition in ("P0_F0", "P1_F0"):
        runtime = _runtime(registry, "E3-A-01", condition)
        maximum = max(
            math.dist(start, target)
            for start, target in zip(
                runtime["initial_positions_m"], runtime["assigned_targets_m"]
            )
        )
        peaks = minimum_jerk_peaks(maximum, 6.0)
        assert peaks.velocity <= 5.0
        assert peaks.acceleration <= 5.0
        assert peaks.jerk <= 10.0


def test_unaffected_scenarios_and_population_are_preserved():
    v2 = _yaml(V2_REGISTRY)
    v3 = _yaml(CANDIDATE_REGISTRY)
    old, new = _scenario_map(v2), _scenario_map(v3)
    for scenario_id in ("E3-A-02", "E3-B-01", "E3-B-02", "E3-C-02"):
        assert old[scenario_id] == new[scenario_id]
    assert len(new) == 6
    assert v2["paired_seeds"] == v3["paired_seeds"]
    old_ids = {
        f"{scenario['scenario_id']}__{condition}__S{seed}"
        for scenario in v2["scenarios"]
        for condition in CONDITIONS
        for seed in v2["paired_seeds"]
    }
    new_ids = {
        f"{scenario['scenario_id']}__{condition}__S{seed}"
        for scenario in v3["scenarios"]
        for condition in CONDITIONS
        for seed in v3["paired_seeds"]
    }
    global_order = ORDER_PATH.read_text(encoding="utf-8").splitlines()
    assert len(old_ids) == len(new_ids) == 360
    assert old_ids == new_ids
    assert len(global_order) == 610
    assert {item for item in global_order if item.startswith("E3-")} == new_ids


def test_all_360_candidate_specs_compile_without_physical_execution():
    registry = _yaml(CANDIDATE_REGISTRY)
    count = 0
    for scenario in registry["scenarios"]:
        for condition in CONDITIONS:
            for seed in registry["paired_seeds"]:
                trial_id = f"{scenario['scenario_id']}__{condition}__S{seed}"
                runtime = build_runtime_spec(build_exact_spec(trial_id, registry=registry))
                assert len(runtime["profiles"]) == len(scenario["uav_ids"])
                count += 1
    assert count == 360
