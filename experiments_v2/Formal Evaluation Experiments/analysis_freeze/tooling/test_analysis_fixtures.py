#!/usr/bin/env python3
"""Independent hand-check fixtures for formal-analysis-v1."""

from __future__ import annotations

import json
import math
from pathlib import Path
from types import SimpleNamespace as NS

import numpy as np
import pytest

from analysis_common import (EvidenceError, Series, acceleration_rise_time,
                             below_threshold_metrics, clip_series,
                             complete_interval_metric, normalize_series,
                             pooled_equal_uav_rms, synchronized_grid,
                             threshold_intervals, time_weighted_rms,
                             trapezoidal_integral)
from attempt_context import ProvenanceError, validate_attempt
from e4b_live_metric_extractor import evaluate_authority_case
from e5_live_metric_extractor import derive_physical_interval
from population_analysis import descriptive, paired_effect, population_result, prepare_e3, prepare_e4a
from rosbag_evidence import BagRecord


def test_duplicate_timestamp_rules() -> None:
    series = normalize_series([0, 1, 1, 2], [[0], [1], [1], [2]])
    assert series.t.tolist() == [0, 1, 2]
    assert series.dropped_duplicate_count == 1
    with pytest.raises(EvidenceError):
        normalize_series([0, 1, 1], [[0], [1], [1.1]])


def test_clip_boundary_interpolation_and_gap_fail_closed() -> None:
    series = normalize_series([0.0, 0.1, 0.2], [[0.0], [1.0], [2.0]])
    clipped, diagnostics = clip_series(series, 0.05, 0.15)
    assert clipped.t.tolist() == pytest.approx([0.05, 0.1, 0.15])
    assert clipped.value[:, 0].tolist() == pytest.approx([0.5, 1.0, 1.5])
    assert diagnostics["start_interpolated"] and diagnostics["end_interpolated"]
    with pytest.raises(EvidenceError):
        clip_series(normalize_series([0.0, 0.3], [[0], [1]]), 0.05, 0.25)


def test_known_three_uav_distance_minimum() -> None:
    series = {
        1: normalize_series([0, 1], [[0, 0, 0], [0, 0, 0]]),
        2: normalize_series([0, 1], [[3, 0, 0], [1, 0, 0]]),
        3: normalize_series([0, 1], [[0, 4, 0], [0, 4, 0]]),
    }
    grid, values, _ = synchronized_grid(series, 0, 1, max_gap_s=1.0)
    distances = {f"{i}-{j}": np.linalg.norm(values[i] - values[j], axis=1)
                 for i, j in ((1, 2), (1, 3), (2, 3))}
    assert min(float(np.min(value)) for value in distances.values()) == pytest.approx(1.0)
    assert grid[np.argmin(distances["1-2"])] == pytest.approx(1.0)


def test_e3_single_pair_event_and_exposure() -> None:
    result = below_threshold_metrics([0, 1, 2], {"1-2": [2, 1, 2]}, 1.5)
    assert result["hard_risk_event_count"] == 1
    assert result["hard_risk_exposure_duration"] == pytest.approx(1.0)
    assert result["any_pair_hard_risk_duration"] == pytest.approx(1.0)


def test_e3_leave_and_reenter_is_two_events() -> None:
    result = below_threshold_metrics([0, 1, 2, 3, 4], {"1-2": [2, 1, 2, 1, 2]}, 1.5)
    assert result["hard_risk_event_count"] == 2
    assert result["hard_risk_exposure_duration"] == pytest.approx(2.0)


def test_e3_overlapping_and_simultaneous_pairs_are_separate() -> None:
    result = below_threshold_metrics([0, 1, 2], {
        "1-2": [2, 1, 2], "1-3": [2, 1, 2], "2-3": [2, 2, 2]}, 1.5)
    assert result["hard_risk_event_count"] == 2
    assert result["hard_risk_exposure_duration"] == pytest.approx(2.0)
    assert result["any_pair_hard_risk_duration"] == pytest.approx(1.0)


def test_e3_exact_threshold_equality_is_outside() -> None:
    assert threshold_intervals([0, 1, 2], [1.5, 1.5, 1.5], 1.5) == []
    intervals = threshold_intervals([0, 1, 2], [1.5, 1.0, 1.5], 1.5)
    assert intervals == pytest.approx([(0.0, 2.0)])


def test_constant_and_linear_trapezoidal_integration() -> None:
    assert trapezoidal_integral([0, 1, 2], [3, 3, 3]) == pytest.approx(6.0)
    assert trapezoidal_integral([0, 1, 2], [0, 2, 4]) == pytest.approx(4.0)


def test_constant_and_linear_time_weighted_rms() -> None:
    assert time_weighted_rms([0, 1, 2], [3, 3, 3]) == pytest.approx(3.0)
    # Frozen trapezoids on squared samples: (0+.25)/2*.5 + (.25+1)/2*.5 = .375.
    assert time_weighted_rms([0, 0.5, 1], [0, 0.5, 1]) == pytest.approx(math.sqrt(0.375))


def test_e4a_rise_time_known_crossings() -> None:
    result = acceleration_rise_time([0, 1, 9, 10], [0, 1, 9, 10])
    assert result["valid"]
    assert result["t10"] == pytest.approx(1.0)
    assert result["t90"] == pytest.approx(9.0)
    assert result["value_s"] == pytest.approx(8.0)


def test_e4a_multipeak_uses_first_90_percent_of_global_peak() -> None:
    result = acceleration_rise_time([0, 1, 2, 3, 4], [0, 8, 0, 9, 10])
    assert result["peak"] == pytest.approx(10.0)
    assert result["t10"] == pytest.approx(0.125)
    assert result["t90"] == pytest.approx(3.0)
    assert result["value_s"] == pytest.approx(2.875)


def test_e4a_four_uav_aggregations() -> None:
    settling = [1, 2, 3, 4]
    effort = [2, 4, 6, 8]
    peak = [1, 2, 3, 4]
    rms = [1, 2, 3, 4]
    rise = [0.1, 0.2, 0.3, 0.4]
    tracking = [0.5, 1.0, 1.5, 2.0]
    assert max(settling) == 4
    assert np.mean(effort) == pytest.approx(5)
    assert np.mean(peak) == pytest.approx(2.5)
    assert pooled_equal_uav_rms(rms) == pytest.approx(math.sqrt(7.5))
    assert np.mean(rise) == pytest.approx(0.25)
    assert pooled_equal_uav_rms(tracking) == pytest.approx(math.sqrt(1.875))


def authority(scenario: str, t_exec: float, requested: dict, t_min: float | None,
              *, safety: bool = True, profile: bool = True) -> dict:
    return evaluate_authority_case(
        scenario=scenario, style="aggressive", t_exec=t_exec, requested=requested, t_min=t_min,
        feasibility_terms={"velocity": 1.5, "acceleration": 2.1, "jerk": 2.8},
        safety_ok=safety, profiles_ok=profile, physical_commands_ok=True)


@pytest.mark.parametrize("case", [
    authority("E4B-FEASIBLE-EXPLICIT-T", 4.0, {"mode": "explicit", "value_s": 4.0}, 2.8),
    authority("E4B-INFEASIBLE-EXPLICIT-T", 2.8, {"mode": "explicit", "value_s": 1.5}, 2.8),
    authority("E4B-AUTO-T", 3.0, {"mode": "auto"}, 2.8),
])
def test_e4b_valid_authority_cases(case: dict) -> None:
    assert all(item["pass"] is not False for item in case.values())


def test_e4b_unauthorized_safety_override() -> None:
    result = authority("E4B-SAFETY-ACTIVE", 6.0, {"mode": "explicit", "value_s": 6.0}, None,
                       safety=False)
    assert result["hard_safety_ownership_preserved"]["pass"] is False


def test_e4b_motion_limit_violation() -> None:
    result = authority("E4B-FEASIBLE-EXPLICIT-T", 4.0,
                       {"mode": "explicit", "value_s": 4.0}, 2.8, profile=False)
    assert result["motion_limits_and_controller_clamps_preserved"]["pass"] is False


def command(t: float, task_id: int, uav_id: int, group_id: int = 0) -> BagRecord:
    msg = NS(mission_id=1, task_id=task_id, group_id=group_id, uav_id=uav_id,
             target_pos=NS(x=float(uav_id), y=0.0, z=3.0))
    return BagRecord(f"/uav{uav_id}/execution_command", "test", t, t, msg)


def stable(t: float, uav_id: int) -> BagRecord:
    msg = NS(mission_id=1, uav_id=uav_id, is_hover_stable=True)
    return BagRecord(f"/uav{uav_id}/status", "test", t, t, msg)


def test_e5_sequential_interval_boundary() -> None:
    scenario = {"candidate_semantic_ground_truth": {"mission": {"nodes": [
        {"type": "task", "task": {"task_id": 1, "U": list(range(1, 9)), "q": {"mode": "continuous"}}},
        {"type": "task", "task": {"task_id": 2, "U": list(range(1, 9)),
                                    "q": {"mode": "hover-and-wait", "duration": 2}}},
    ]}}}
    records = [command(10, 1, i) for i in range(1, 9)] + [command(15, 2, i) for i in range(1, 9)]
    records += [stable(23 + i * 0.01, i) for i in range(1, 9)]
    result = derive_physical_interval(records, scenario)
    assert result["start"] == pytest.approx(10)
    assert result["end"] == pytest.approx(25.08)


def test_e5_parallel_synchronized_interval_boundary() -> None:
    scenario = {"candidate_semantic_ground_truth": {"mission": {"nodes": [{
        "type": "parallel", "completion_mode": "synchronized", "tasks": [
            {"task_id": 1, "U": [1, 2, 3, 4], "q": {"mode": "direct"}},
            {"task_id": 2, "U": [5, 6, 7, 8], "q": {"mode": "direct"}},
        ]}]}}}
    records = [command(5, 1 if i <= 4 else 2, i, 1) for i in range(1, 9)]
    records += [stable(12 + i * 0.01, i) for i in range(1, 9)]
    result = derive_physical_interval(records, scenario)
    assert result["start"] == pytest.approx(5)
    assert result["end"] == pytest.approx(12.08)


@pytest.mark.parametrize("observed_start,observed_end,valid", [
    (None, None, False),       # failure before physical start
    (0.0, 4.0, False),        # mid-window failure
    (0.0, 10.0, True),        # later failure after complete metric evidence
])
def test_failure_interval_policy(observed_start: float | None, observed_end: float | None,
                                 valid: bool) -> None:
    result = complete_interval_metric(7.0, 0.0, 10.0, observed_start, observed_end,
                                      partial_value=3.0, partial_reason="fixture_failure")
    assert result["valid"] is valid
    if not valid:
        assert result["value"] is None and result["partial_observed_value"] == 3.0


def test_missing_completion_final_error_is_na() -> None:
    result = complete_interval_metric(1.0, 0, 10, 0, 9, partial_value=2.0,
                                      partial_reason="terminal completion absent")
    assert result["value"] is None


def test_infrastructure_failure_keeps_earlier_latency_numeric() -> None:
    provider = complete_interval_metric(2.5, 0, 2.5, 0, 2.5)
    physical = complete_interval_metric(9, 3, 13, None, None, partial_reason="infrastructure failure")
    assert provider["value"] == pytest.approx(2.5)
    assert physical["value"] is None


def test_descriptive_and_paired_effect_known_answers() -> None:
    summary = descriptive([1, 2, 3, None])
    assert summary["valid_N"] == 3 and summary["NA_N"] == 1
    assert summary["mean"] == pytest.approx(2)
    paired = paired_effect([1, 2, 3], [2, 4, 6])
    assert paired["paired_differences"] == pytest.approx([1, 2, 3])
    assert paired["cohen_dz"] == pytest.approx(2.0)


def test_e3_population_pairing_fails_missing_cell() -> None:
    records = [{"experiment": "E3", "trial_id": f"E3-A-01__{condition}__S53101",
                "demo_instance_id": condition} for condition in ("P0_F0", "P0_F1", "P1_F0")]
    with pytest.raises(EvidenceError):
        prepare_e3(records, strict_complete_factorial=True)


def test_e4a_reference_identity_mismatch_fails_closed() -> None:
    records = []
    for style, identity in (("smooth", "a" * 64), ("normal", "a" * 64), ("aggressive", "b" * 64)):
        records.append({"experiment": "E4A", "trial_id": f"E4A-HORIZONTAL__{style}__S54101",
                        "metrics": {"reference_identity": {"validated": True, "sha256": identity}}})
    result = prepare_e4a(records, strict_style_triplets=False)
    assert result["reference_identity_mismatches"]
    with pytest.raises(EvidenceError):
        prepare_e4a(records, strict_style_triplets=True)


def test_formal_population_gate_rejects_incomplete_membership() -> None:
    with pytest.raises(EvidenceError):
        population_result([], require_exact_registered_population=True)


def test_provenance_mismatch_fails_closed(tmp_path: Path) -> None:
    manifest = {
        "family": "E3", "dataset_class": "formal_evaluation", "accepted_formal_result": False,
        "result_notice": "NOT_FORMAL_RESULT", "formal_cursor_consumed": False,
        "registered_trial_id": "x", "execution_spec": {"trial_id": "x"},
        "runtime_provenance": {"status": "PASS"}, "same_backend_as_formal_adapter": True,
    }
    (tmp_path / "raw").mkdir()
    (tmp_path / "demo_manifest.json").write_text(json.dumps(manifest))
    (tmp_path / "raw/runtime_spec.json").write_text(json.dumps({
        "trial_id": "x", "runtime_spec_type": "E3_registered_physical_runtime_spec_v3"}))
    with pytest.raises(ProvenanceError):
        validate_attempt(tmp_path, "E3")
