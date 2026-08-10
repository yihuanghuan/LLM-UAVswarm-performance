import numpy as np

from location_allocate.safety_aware_allocator import SafetyAwareTopologyAllocator


def test_minimum_jerk_samples_start_and_end():
    allocator = SafetyAwareTopologyAllocator(sample_hz=20.0)
    initial = [[0.0, 0.0, 1.0]]
    targets = [[4.0, -2.0, 3.0]]

    samples = allocator.sample_nominal_trajectories(initial, targets, duration=2.0)

    assert samples.shape == (1, 41, 3)
    np.testing.assert_allclose(samples[0, 0], initial[0])
    np.testing.assert_allclose(samples[0, -1], targets[0])


def test_safety_cost_is_added_when_trajectories_get_too_close():
    allocator = SafetyAwareTopologyAllocator(
        sample_hz=20.0,
        d_safe=0.8,
        alpha=1.0,
        beta_xy=5.0,
        beta_prox=13.0,
        gamma=17.0,
    )
    initial = [[-1.0, 0.0, 0.0], [1.0, 0.0, 0.0]]
    targets = [[1.0, 0.0, 0.0], [-1.0, 0.0, 0.0]]

    metrics = allocator.evaluate(initial, targets, [0, 1], duration=3.0)

    assert metrics.min_distance < allocator.d_safe
    assert metrics.proximity_crossings == 1
    assert metrics.safety > 0.0
    assert metrics.total == metrics.distance + 13.0 + 17.0 * metrics.safety


def test_xy_crossing_is_penalized_separately_from_proximity_crossing():
    allocator = SafetyAwareTopologyAllocator(
        sample_hz=20.0,
        d_safe=1.0,
        beta_xy=7.0,
        beta_prox=11.0,
    )
    initial = [[-1.0, 0.0, 0.0], [1.0, 0.0, 10.0]]
    targets = [[1.0, 2.0, 0.0], [-1.0, 2.0, 10.0]]

    metrics = allocator.evaluate(initial, targets, [0, 1], duration=3.0)

    assert metrics.xy_crossings == 1
    assert metrics.proximity_crossings == 0
    assert metrics.safety == 0.0
    assert metrics.total == metrics.distance + 7.0


def test_legacy_beta_sets_both_crossing_penalties():
    allocator = SafetyAwareTopologyAllocator(sample_hz=20.0, d_safe=1.0, beta=6.0)
    initial = [[-1.0, 0.0, 0.0], [1.0, 0.0, 10.0]]
    targets = [[1.0, 2.0, 0.0], [-1.0, 2.0, 10.0]]

    metrics = allocator.evaluate(initial, targets, [0, 1], duration=3.0)

    assert allocator.beta_xy == 6.0
    assert allocator.beta_prox == 6.0
    assert metrics.total == metrics.distance + 6.0


def test_local_swap_refinement_reduces_unsafe_assignment_cost():
    allocator = SafetyAwareTopologyAllocator(
        sample_hz=20.0,
        d_safe=1.0,
        alpha=1.0,
        beta=20.0,
        gamma=20.0,
    )
    initial = [
        [-2.0, -2.0, 0.0],
        [-2.0, 0.0, 0.0],
        [-2.0, 2.0, 0.0],
    ]
    targets = [
        [-2.0, -2.0, 0.0],
        [-2.0, 0.0, 0.0],
        [0.0, -2.0, 0.0],
    ]
    hungarian_assignment = allocator._hungarian_assignment(initial, targets)
    hungarian_metrics = allocator.evaluate(
        initial,
        targets,
        hungarian_assignment,
        duration=4.0,
    )

    allocated, refined_metrics = allocator.allocate_with_metrics(
        initial,
        targets,
        duration=4.0,
    )

    assert refined_metrics.total < hungarian_metrics.total
    assert refined_metrics.proximity_crossings == 0
    assert allocated == [
        [-2.0, -2.0, 0.0],
        [0.0, -2.0, 0.0],
        [-2.0, 0.0, 0.0],
    ]


def test_allocate_keeps_result_order_aligned_with_uav_order():
    allocator = SafetyAwareTopologyAllocator()
    initial = [[0.0, 0.0, 0.0], [4.0, 0.0, 0.0]]
    targets = [[4.0, 0.0, 0.0], [0.0, 0.0, 0.0]]

    allocated = allocator.allocate(initial, targets, duration=3.0)

    assert allocated == [[0.0, 0.0, 0.0], [4.0, 0.0, 0.0]]


def test_assignment_modes_have_distinct_fixed_and_distance_behavior():
    allocator = SafetyAwareTopologyAllocator()
    initial = [[0.0, 0.0, 0.0], [4.0, 0.0, 0.0]]
    targets = [[4.0, 0.0, 0.0], [0.0, 0.0, 0.0]]

    fixed, _ = allocator.allocate_mode_with_metrics(
        initial, targets, mode="fixed")
    distance, _ = allocator.allocate_mode_with_metrics(
        initial, targets, mode="distance_hungarian")

    assert fixed == targets
    assert distance == initial


def test_grouped_allocator_preserves_group_ownership_and_scores_cross_group_pairs():
    allocator = SafetyAwareTopologyAllocator(d_safe=1.0, beta=20.0, gamma=20.0)
    groups = [
        {
            "uav_ids": [1, 2],
            "initial": [[-2.0, -0.5, 2.0], [-2.0, 0.5, 2.0]],
            "targets": [[2.0, 0.5, 2.0], [2.0, -0.5, 2.0]],
        },
        {
            "uav_ids": [3, 4],
            "initial": [[-0.5, -2.0, 2.0], [0.5, -2.0, 2.0]],
            "targets": [[0.5, 2.0, 2.0], [-0.5, 2.0, 2.0]],
        },
    ]

    allocated, metrics = allocator.allocate_grouped(
        groups, duration=5.0, mode="safety_aware")

    assert {tuple(point) for point in allocated[0]} == {
        tuple(point) for point in groups[0]["targets"]}
    assert {tuple(point) for point in allocated[1]} == {
        tuple(point) for point in groups[1]["targets"]}
    assert metrics.min_distance < 1.0


def test_grouped_allocator_rejects_duplicate_uav_ids():
    allocator = SafetyAwareTopologyAllocator()
    groups = [
        {"uav_ids": [1], "initial": [[0, 0, 0]], "targets": [[1, 0, 0]]},
        {"uav_ids": [1], "initial": [[0, 1, 0]], "targets": [[1, 1, 0]]},
    ]
    with np.testing.assert_raises(ValueError):
        allocator.allocate_grouped(groups, duration=3.0)


def test_variable_duration_trajectory_holds_early_finisher_at_goal():
    allocator = SafetyAwareTopologyAllocator(sample_hz=10.0)
    trajectories = allocator.sample_nominal_trajectories_variable(
        [[0.0, 0.0, 0.0], [0.0, 2.0, 0.0]],
        [[1.0, 0.0, 0.0], [4.0, 2.0, 0.0]],
        durations=[1.0, 3.0],
    )

    assert trajectories.shape == (2, 31, 3)
    assert trajectories[0, 10:].tolist() == [[1.0, 0.0, 0.0]] * 21
    assert trajectories[1, -1].tolist() == [4.0, 2.0, 0.0]


def test_grouped_allocator_accepts_independent_group_durations():
    allocator = SafetyAwareTopologyAllocator(sample_hz=10.0)
    groups = [
        {
            "uav_ids": [1, 2],
            "initial": [[0.0, 0.0, 0.0], [0.0, 2.0, 0.0]],
            "targets": [[2.0, 0.0, 0.0], [2.0, 2.0, 0.0]],
        },
        {
            "uav_ids": [3, 4],
            "initial": [[0.0, 4.0, 0.0], [0.0, 6.0, 0.0]],
            "targets": [[4.0, 4.0, 0.0], [4.0, 6.0, 0.0]],
        },
    ]

    allocated, metrics = allocator.allocate_grouped(
        groups, durations=[1.0, 3.0], mode="distance_hungarian"
    )

    assert len(allocated) == 2
    assert metrics.min_distance > 0.0


def test_grouped_allocator_keeps_legacy_scalar_duration_api():
    allocator = SafetyAwareTopologyAllocator()
    groups = [{
        "uav_ids": [1, 2],
        "initial": [[0.0, 0.0, 0.0], [0.0, 2.0, 0.0]],
        "targets": [[2.0, 0.0, 0.0], [2.0, 2.0, 0.0]],
    }]

    allocated, _ = allocator.allocate_grouped(groups, duration=2.0)

    assert len(allocated[0]) == 2
