"""Tests for the experiment 04 offline assignment pipeline."""

from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path

import numpy as np


REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPTS_DIR = REPO_ROOT / "experiments" / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

import analyze_assignment_offline as analysis  # noqa: E402
import eval_assignment_offline as experiment  # noqa: E402


def allocator_factory(**kwargs: object):
    return experiment.make_allocator(
        20.0,
        2.0,
        crossing_only=bool(kwargs.get("crossing_only", False)),
    )


def test_all_five_baselines_return_permutations():
    initial, targets = experiment.generate_scenario(
        "medium",
        trial_id=3,
        rng=np.random.default_rng(1234),
    )
    for index, method in enumerate(experiment.METHODS):
        assignment, elapsed = experiment.compute_assignment(
            method,
            initial,
            targets,
            duration=8.0,
            rng=np.random.default_rng(100 + index),
            allocator_factory=allocator_factory,
        )
        assert sorted(assignment) == list(range(len(initial)))
        assert elapsed >= 0.0


def test_crossing_prone_geometry_exercises_crossing_penalty():
    initial, targets = experiment.generate_scenario(
        "crossing-prone",
        trial_id=0,
        rng=np.random.default_rng(7),
    )
    distance_assignment = experiment.hungarian_assignment(initial, targets)
    crossing_assignment, _ = experiment.compute_assignment(
        "hungarian_crossing_penalty",
        initial,
        targets,
        duration=8.0,
        rng=np.random.default_rng(7),
        allocator_factory=allocator_factory,
    )
    evaluator = allocator_factory()
    distance_metrics = evaluator.evaluate(initial, targets, distance_assignment, 8.0)
    crossing_metrics = evaluator.evaluate(initial, targets, crossing_assignment, 8.0)

    assert distance_metrics.xy_crossings > 0
    assert crossing_metrics.xy_crossings < distance_metrics.xy_crossings


def test_violation_count_failure_and_arrival_variance():
    initial = np.asarray([[-1.0, 0.0, 3.0], [1.0, 0.0, 3.0]])
    targets = np.asarray([[1.0, 0.0, 3.0], [-1.0, 0.0, 3.0]])
    metrics = experiment.evaluate_assignment(
        allocator_factory(),
        initial,
        targets,
        assignment=[0, 1],
        duration=1.0,
        safety_distance=0.5,
        nominal_speed=1.0,
    )
    assert metrics.safety_violation_count > 0
    assert metrics.failed_assignment == 1
    assert metrics.arrival_time_variance == 0.0

    unequal_targets = np.asarray([[1.0, 0.0, 3.0], [-3.0, 0.0, 3.0]])
    unequal = experiment.evaluate_assignment(
        allocator_factory(),
        initial,
        unequal_targets,
        assignment=[0, 1],
        duration=1.0,
        safety_distance=0.5,
        nominal_speed=1.0,
    )
    assert unequal.arrival_time_variance > 0.0


def test_end_to_end_small_run_and_analysis(tmp_path):
    output_dir = tmp_path / "experiments_04"
    args = argparse.Namespace(
        trials=1,
        output_dir=str(output_dir),
        seed=20260708,
        duration=8.0,
        sample_hz=20.0,
        safety_distance=2.0,
        nominal_speed=1.0,
        scenarios=list(experiment.SCENARIOS),
    )
    actual_dir = experiment.run_experiment(args)
    manifest = analysis.analyze(actual_dir)

    with (actual_dir / "assignment_trials.csv").open(newline="", encoding="utf-8") as handle:
        trial_rows = list(csv.DictReader(handle))
    with (actual_dir / "assignment_summary.csv").open(newline="", encoding="utf-8") as handle:
        summary_rows = list(csv.DictReader(handle))

    assert len(trial_rows) == len(experiment.SCENARIOS) * len(experiment.METHODS)
    assert len(summary_rows) == (len(experiment.SCENARIOS) + 1) * len(experiment.METHODS)
    assert int(manifest["row_count"]) == 25
    assert {row["method"] for row in trial_rows} == set(experiment.METHODS)
    for row in trial_rows:
        assignment = json.loads(row["assignment"])
        assert sorted(assignment) == list(range(int(row["num_uav"])))

    expected = [
        "table_assignment_baselines.md",
        "fig_min_distance_boxplot.png",
        "fig_crossing_count_bar.pdf",
        "fig_path_safety_pareto.png",
        "fig_qualitative_crossing_prone.pdf",
        "analysis_manifest.json",
    ]
    assert all((actual_dir / name).is_file() for name in expected)
