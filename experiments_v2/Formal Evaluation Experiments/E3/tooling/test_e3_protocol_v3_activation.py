from __future__ import annotations

import hashlib
import itertools
import json
import math
from pathlib import Path
import subprocess
import sys

import pytest
import yaml

import e3_trial_registry as registry_module
from e3_formal_backend import build_runtime_spec
from e3_trial_registry import (
    CONDITIONS,
    GLOBAL_REGISTRY_PATH,
    GLOBAL_REGISTRY_SHA256,
    ORDER_PATH,
    ORDER_SHA256,
    POLICY_PATH,
    PROTOCOL_PATH,
    PROTOCOL_SHA256,
    REGISTRY_PATH,
    REGISTRY_SHA256,
    E3Error,
    build_exact_spec,
    load_registry,
    registered_trial_ids,
    scenario_index,
)


E3_DIR = Path(__file__).resolve().parent.parent
FORMAL_DIR = E3_DIR.parent
REPO_ROOT = FORMAL_DIR.parents[1]
V1_PROTOCOL = FORMAL_DIR / "protocols" / "E3_protocol_v1.yaml"
V2_PROTOCOL = FORMAL_DIR / "protocols" / "E3_protocol_v2.yaml"
CANDIDATE_PROTOCOL = FORMAL_DIR / "protocols" / "E3_protocol_v3_candidate.yaml"
V1_REGISTRY = E3_DIR / "e3_factorial_registry_v1.yaml"
V2_REGISTRY = E3_DIR / "e3_factorial_registry_v2.yaml"
CANDIDATE_REGISTRY = E3_DIR / "e3_factorial_registry_v3_candidate.yaml"
DEMO_HARNESS = FORMAL_DIR / "formal_equivalent_demos/tooling/runtime_demo.py"
ACTIVE_AUDIT_SCRIPT = E3_DIR / "tooling/e3_protocol_v3_active_audit.py"
EXPECTED_TARGETS = {
    1: [-3, 4, 3],
    2: [3, 4, 3],
    3: [-2, 12, 3],
    4: [0, 12, 3],
}
HISTORICAL_HASHES = {
    V1_PROTOCOL: "68f134cbf41a5be30e83a0953daa1a8d74866939d0450f60ebb31298616f56d8",
    V2_PROTOCOL: "3b1177983058351a443395966fce92ddb91e990e10a1b9b10d44921d8b854ecf",
    CANDIDATE_PROTOCOL: "978063c29e591c0fa70c1c9b0fdb9a100c19fd9fb710964f9289c2369c9b621c",
    V1_REGISTRY: "48d66a07c744af4fad0f483ca24c72cf30dfbcaac9468e50ea3252ce6f76ea41",
    V2_REGISTRY: "f722d8a917ed6af57a3f75a79ef62720fdafb5835115a66d8e0582eb453d36a3",
    CANDIDATE_REGISTRY: "e09f7c159af5159f3e826986f14cc075c026e92067653fb18e6d9de0d0857ff3",
}


def _yaml(path):
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def _sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _runtime(scenario_id, condition):
    trial_id = f"{scenario_id}__{condition}__S53101"
    return build_runtime_spec(build_exact_spec(trial_id))


def test_active_v3_identity_and_hashes_are_authoritative():
    protocol, registry = _yaml(PROTOCOL_PATH), load_registry()
    assert PROTOCOL_PATH.name == "E3_protocol_v3.yaml"
    assert REGISTRY_PATH.name == "e3_factorial_registry_v3.yaml"
    assert protocol["protocol_id"] == "E3-planning-feedback-safety-factorial-v3"
    assert registry["registry_id"] == "E3-exact-factorial-v3"
    assert protocol["status"] == registry["status"] == "SEALED"
    assert protocol["active_authoritative_identity"] is True
    assert registry["active_authoritative_identity"] is True
    assert _sha(PROTOCOL_PATH) == PROTOCOL_SHA256
    assert _sha(REGISTRY_PATH) == REGISTRY_SHA256


def test_historical_v1_v2_and_reviewed_candidate_are_hash_stable():
    for path, expected in HISTORICAL_HASHES.items():
        assert _sha(path) == expected


def test_protocol_and_registry_hash_mismatch_fail_closed(monkeypatch):
    monkeypatch.setattr(registry_module, "PROTOCOL_SHA256", "0" * 64)
    with pytest.raises(E3Error, match="protocol hash mismatch"):
        registry_module.load_registry()
    monkeypatch.setattr(registry_module, "PROTOCOL_SHA256", PROTOCOL_SHA256)
    monkeypatch.setattr(registry_module, "REGISTRY_SHA256", "0" * 64)
    with pytest.raises(E3Error, match="registry hash mismatch"):
        registry_module.load_registry()


@pytest.mark.parametrize("scenario_id", ["E3-A-01", "E3-C-01"])
def test_active_A01_C01_recompute_reviewed_geometry_and_risk(scenario_id):
    scenario = scenario_index()[scenario_id]
    assert scenario["ordered_targets_m"] == EXPECTED_TARGETS
    p0, p1 = _runtime(scenario_id, "P0_F0"), _runtime(scenario_id, "P1_F0")
    d0, d1 = p0["allocator_diagnostics"], p1["allocator_diagnostics"]
    assert d0["final_assignment"] == [2, 3, 0, 1]
    assert d1["final_assignment"] == [0, 1, 2, 3]
    assert d0["hard_violations"] == 2
    assert d1["hard_violations"] == 0
    assert d0["min_distance"] == pytest.approx(0.42748229992745784)
    assert d1["min_distance"] == pytest.approx(2.0)
    assert all(
        math.dist(start, target) > 0
        for start, target in zip(p0["initial_positions_m"], p0["assigned_targets_m"])
    )
    assert all(
        math.dist(start, target) > 0
        for start, target in zip(p1["initial_positions_m"], p1["assigned_targets_m"])
    )


def test_active_geometry_exhaustively_recomputes_unique_P0_and_global_P1():
    root = Path(__file__).resolve().parents[4]
    for path in (root / "location_allocate", root / "lfs_policy"):
        if str(path) not in sys.path:
            sys.path.insert(0, str(path))
    from location_allocate.motion_limits import minimum_jerk_peaks
    from location_allocate.policy_adapter import load_runtime_policy

    _, policy = load_runtime_policy(POLICY_PATH)
    safety = policy.resolve_safety(1.0)
    evaluator = policy.allocator_factory(safety.d_hard, safety.d_plan)
    scenario = scenario_index()["E3-A-01"]
    initial = [[float(v) for v in scenario["initial_positions_m"][uid]] for uid in scenario["uav_ids"]]
    targets = [[float(v) for v in scenario["ordered_targets_m"][uid]] for uid in scenario["uav_ids"]]
    rows = []
    for permutation in itertools.permutations(range(4)):
        metrics = evaluator.evaluate(initial, targets, permutation, scenario["duration_s"])
        maximum = max(math.dist(initial[i], targets[permutation[i]]) for i in range(4))
        peaks = minimum_jerk_peaks(maximum, scenario["duration_s"])
        rows.append((permutation, metrics, peaks))
    minimum_distance = min(metrics.distance for _perm, metrics, _peaks in rows)
    distance_optima = [
        perm for perm, metrics, _peaks in rows
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
    for permutation in (distance_optima[0], global_lex[0]):
        row = next(item for item in rows if item[0] == permutation)
        assert row[2].velocity <= 5.0
        assert row[2].acceleration <= 5.0
        assert row[2].jerk <= 10.0


def test_A02_C02_duration_and_derived_timing_remain_corrected():
    for scenario_id in ("E3-A-02", "E3-C-02"):
        for condition in CONDITIONS:
            spec = build_exact_spec(f"{scenario_id}__{condition}__S53101")
            assert spec["duration_s"] == 9.5
            assert spec["scoring"]["end_offset_s"] == 11.5
            assert spec["timeout_after_t0_s"] == 15.5


def test_B_scenarios_are_scientifically_unchanged_from_v2():
    v2 = {item["scenario_id"]: item for item in _yaml(V2_REGISTRY)["scenarios"]}
    active = scenario_index()
    assert active["E3-B-01"] == v2["E3-B-01"]
    assert active["E3-B-02"] == v2["E3-B-02"]


def test_population_global_registry_and_order_are_unchanged():
    ids = registered_trial_ids()
    assert len(ids) == len(set(ids)) == 360
    assert len(scenario_index()) == 6
    assert len(load_registry()["paired_seeds"]) == 15
    order = ORDER_PATH.read_text(encoding="utf-8").splitlines()
    assert len(order) == 610
    assert {item for item in order if item.startswith("E3-")} == set(ids)
    assert _sha(ORDER_PATH) == ORDER_SHA256
    assert _sha(GLOBAL_REGISTRY_PATH) == GLOBAL_REGISTRY_SHA256


def test_resolved_hashes_and_all_360_active_specs_compile(tmp_path):
    json_output = tmp_path / "active-audit.json"
    markdown_output = tmp_path / "active-audit.md"
    completed = subprocess.run(
        [
            sys.executable,
            str(ACTIVE_AUDIT_SCRIPT),
            "--json-output", str(json_output),
            "--markdown-output", str(markdown_output),
        ],
        cwd=REPO_ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr
    audit = json.loads(json_output.read_text(encoding="utf-8"))
    assert audit["status"] == "PASS"
    assert audit["production_compile_validation"] == {
        "checked": 360,
        "fail_count": 0,
        "failures": [],
        "pass_count": 360,
    }


@pytest.mark.parametrize(
    "trial_id",
    [
        "E3-A-01__P0_F0__S53101", "E3-A-01__P1_F0__S53101",
        "E3-A-02__P0_F0__S53101", "E3-A-02__P1_F0__S53101",
        "E3-C-01__P0_F0__S53101", "E3-C-01__P1_F0__S53101",
        "E3-C-02__P0_F0__S53101", "E3-C-02__P1_F0__S53101",
    ],
)
def test_demo_harness_classes_reconstruct_compile_only_with_nonformal_labels(trial_id):
    spec = dict(build_exact_spec(trial_id))
    spec["dataset_class"] = "engineering_validation"
    runtime = build_runtime_spec(spec)
    assert runtime["dataset_class"] == "engineering_validation"
    assert runtime["trial_id"] == trial_id
    harness_source = DEMO_HARNESS.read_text(encoding="utf-8")
    assert '"dataset_class": "engineering_validation"' in harness_source
    assert '"accepted_formal_result": False' in harness_source
    assert '"result_notice": NOTICE' in harness_source
    assert '"formal_cursor_consumed": False' in harness_source
