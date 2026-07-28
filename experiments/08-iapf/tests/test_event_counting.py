import numpy as np

from analysis_core import event_count, pair_metrics


def positions_from_distances(distances):
    first = np.zeros((len(distances), 3))
    second = np.column_stack([distances, np.zeros(len(distances)), np.zeros(len(distances))])
    return {1: first, 2: second}


def test_always_safe_and_exact_threshold_are_not_events():
    timeline = np.arange(5) * 0.05
    pairs, _ = pair_metrics(
        timeline, positions_from_distances(np.ones(5)), 0.7, 1.0)
    assert pairs[0].violation_event_count == 0
    assert pairs[0].violation_sample_count == 0


def test_one_continuous_violation_is_one_event():
    assert event_count([False, True, True, True, False]) == 1


def test_two_separated_violations_are_two_events():
    assert event_count([False, True, False, True, True]) == 2


def test_collision_and_violation_are_counted_separately():
    timeline = np.arange(6) * 0.05
    pairs, _ = pair_metrics(
        timeline,
        positions_from_distances(np.array([1.2, 0.9, 0.6, 0.6, 0.9, 1.2])),
        0.7, 1.0)
    assert pairs[0].collision_event_count == 1
    assert pairs[0].violation_event_count == 1
