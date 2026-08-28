from __future__ import annotations

import copy
import math
from pathlib import Path
import sys

import pytest
import yaml

from e3_formal_backend import build_runtime_spec
from e3_protocol_v2_feasibility_audit import analytic_rows
from e3_trial_registry import (
    CONDITIONS,
    ORDER_PATH,
    PROTOCOL_PATH,
    PROTOCOL_SHA256,
    REGISTRY_PATH,
    REGISTRY_SHA256,
    build_exact_spec,
    canonical_sha256,
    load_registry,
    registered_trial_ids,
    scenario_index,
)


ROOT = Path(__file__).resolve().parents[4]
V1_PROTOCOL = PROTOCOL_PATH.with_name("E3_protocol_v1.yaml")
V1_REGISTRY = REGISTRY_PATH.with_name("e3_factorial_registry_v1.yaml")
V2_PROTOCOL = PROTOCOL_PATH.with_name("E3_protocol_v2.yaml")
V2_REGISTRY = REGISTRY_PATH.with_name("e3_factorial_registry_v2.yaml")


def _yaml(path):
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def _assigned_peaks(scenario, assignment_mode, duration):
    for path in (ROOT / "location_allocate", ROOT / "lfs_policy"):
        if str(path) not in sys.path:
            sys.path.insert(0, str(path))
    from location_allocate.motion_limits import minimum_jerk_peaks
    from location_allocate.policy_adapter import load_runtime_policy

    _, policy = load_runtime_policy(ROOT / "lfs_policy/config/lfs_policy.paper_current.yaml")
    safety = policy.resolve_safety(1.0)
    initial = [[float(x) for x in scenario["initial_positions_m"][u]] for u in scenario["uav_ids"]]
    targets = [[float(x) for x in scenario["ordered_targets_m"][u]] for u in scenario["uav_ids"]]
    allocator = policy.allocator_factory(safety.d_hard, safety.d_plan)
    assigned, _ = allocator.allocate_mode_with_metrics(
        initial, targets, duration, mode=assignment_mode
    )
    distance = max(math.dist(a, b) for a, b in zip(initial, assigned))
    return distance, minimum_jerk_peaks(distance, duration)


@pytest.mark.parametrize("scenario_id", ["E3-A-02", "E3-C-02"])
@pytest.mark.parametrize("assignment_mode", ["distance_hungarian", "safety_aware"])
def test_historical_8_second_configuration_is_infeasible(scenario_id, assignment_mode):
    scenario = {s["scenario_id"]: s for s in _yaml(V1_REGISTRY)["scenarios"]}[scenario_id]
    _distance, peaks = _assigned_peaks(scenario, assignment_mode, 8.0)
    assert peaks.velocity > 5.0


@pytest.mark.parametrize("scenario_id", ["E3-A-02", "E3-C-02"])
@pytest.mark.parametrize("assignment_mode", ["distance_hungarian", "safety_aware"])
def test_corrected_duration_satisfies_all_frozen_limits(scenario_id, assignment_mode):
    scenario = scenario_index()[scenario_id]
    distance, peaks = _assigned_peaks(scenario, assignment_mode, scenario["duration_s"])
    assert scenario["duration_s"] == 9.5
    assert peaks.velocity <= 5.0
    assert peaks.acceleration <= 5.0
    assert peaks.jerk <= 10.0
    if assignment_mode == "distance_hungarian":
        assert distance == pytest.approx(22.485281374238)
    else:
        assert distance == pytest.approx(24.61108749090042)


@pytest.mark.parametrize("scenario_id", ["E3-A-02", "E3-C-02"])
def test_duration_is_equal_across_all_factorial_cells(scenario_id):
    durations = {
        build_exact_spec(f"{scenario_id}__{condition}__S53101")["duration_s"]
        for condition in CONDITIONS
    }
    assert durations == {9.5}


def test_population_and_global_order_are_preserved():
    v1 = _yaml(V1_REGISTRY)
    v2 = load_registry()
    assert len(v1["scenarios"]) == len(v2["scenarios"]) == 6
    assert v1["paired_seeds"] == v2["paired_seeds"]
    v1_ids = [
        f"{scenario['scenario_id']}__{condition}__S{seed}"
        for scenario in v1["scenarios"]
        for condition in CONDITIONS
        for seed in v1["paired_seeds"]
    ]
    v2_ids = registered_trial_ids()
    assert len(v2_ids) == len(set(v2_ids)) == 360
    assert set(v1_ids) == set(v2_ids)
    global_e3_order = [
        item for item in ORDER_PATH.read_text(encoding="utf-8").splitlines()
        if item.startswith("E3-")
    ]
    assert len(global_e3_order) == 360
    assert set(global_e3_order) == set(v2_ids)


def test_v1_v2_are_preserved_and_v3_hashes_are_authoritative():
    import hashlib

    assert hashlib.sha256(V1_PROTOCOL.read_bytes()).hexdigest() == (
        "68f134cbf41a5be30e83a0953daa1a8d74866939d0450f60ebb31298616f56d8"
    )
    assert hashlib.sha256(V1_REGISTRY.read_bytes()).hexdigest() == (
        "48d66a07c744af4fad0f483ca24c72cf30dfbcaac9468e50ea3252ce6f76ea41"
    )
    assert hashlib.sha256(V2_PROTOCOL.read_bytes()).hexdigest() == (
        "3b1177983058351a443395966fce92ddb91e990e10a1b9b10d44921d8b854ecf"
    )
    assert hashlib.sha256(V2_REGISTRY.read_bytes()).hexdigest() == (
        "f722d8a917ed6af57a3f75a79ef62720fdafb5835115a66d8e0582eb453d36a3"
    )
    assert hashlib.sha256(PROTOCOL_PATH.read_bytes()).hexdigest() == PROTOCOL_SHA256
    assert hashlib.sha256(REGISTRY_PATH.read_bytes()).hexdigest() == REGISTRY_SHA256


def test_corrected_exact_spec_hashes_cover_derived_timing():
    spec = build_exact_spec("E3-A-02__P1_F1__S53101")
    scenario = scenario_index()["E3-A-02"]
    assert spec["registered_input_hash"] == canonical_sha256({
        "scenario": scenario,
        "condition": "P1_F1",
        "seed": 53101,
    })
    expected = copy.deepcopy(spec)
    resolved_hash = expected.pop("resolved_execution_spec_hash")
    assert resolved_hash == canonical_sha256(expected)


def test_unaffected_scenarios_are_semantically_identical():
    v1 = {s["scenario_id"]: s for s in _yaml(V1_REGISTRY)["scenarios"]}
    v2 = {s["scenario_id"]: s for s in _yaml(V2_REGISTRY)["scenarios"]}
    for scenario_id in ("E3-A-01", "E3-B-01", "E3-B-02", "E3-C-01"):
        assert v2[scenario_id] == v1[scenario_id]
    for scenario_id in ("E3-A-02", "E3-C-02"):
        old = copy.deepcopy(v1[scenario_id])
        new = copy.deepcopy(v2[scenario_id])
        old.pop("duration_s")
        new.pop("duration_s")
        old.pop("command_text_for_manifest")
        new.pop("command_text_for_manifest")
        assert new == old


@pytest.mark.parametrize("scenario_id", ["E3-A-02", "E3-C-02"])
@pytest.mark.parametrize("condition", CONDITIONS)
def test_exact_spec_timing_derives_mechanically(scenario_id, condition):
    spec = build_exact_spec(f"{scenario_id}__{condition}__S53101")
    assert spec["spec_type"] == "E3_exact_execution_spec_v3"
    assert spec["duration_s"] == 9.5
    assert spec["scoring"]["end_offset_s"] == 11.5
    assert spec["timeout_after_t0_s"] == 15.5


def test_all_24_cells_are_analytically_feasible_and_compile():
    rows = analytic_rows()
    assert len(rows) == 24
    assert all(row["feasibility"] == "PASS" for row in rows)
    for row in rows:
        trial_id = f"{row['scenario_id']}__{row['condition']}__S53101"
        runtime = build_runtime_spec(build_exact_spec(trial_id))
        assert runtime["runtime_spec_type"] == "E3_registered_physical_runtime_spec_v3"
        assert len(runtime["profiles"]) in (4, 8)
