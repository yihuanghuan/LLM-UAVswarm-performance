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
    allocator = SafetyAwareTopologyAllocator(sample_hz=20.0, d_safe=0.8)
    initial = [[-1.0, 0.0, 0.0], [1.0, 0.0, 0.0]]
    targets = [[1.0, 0.0, 0.0], [-1.0, 0.0, 0.0]]

    metrics = allocator.evaluate(initial, targets, [0, 1], duration=3.0)

    assert metrics.min_distance < allocator.d_safe
    assert metrics.proximity_crossings == 1
    assert metrics.safety > 0.0


def test_xy_crossing_is_tracked_separately_from_proximity_crossing():
    allocator = SafetyAwareTopologyAllocator(sample_hz=20.0, d_safe=1.0)
    initial = [[-1.0, 0.0, 0.0], [1.0, 0.0, 10.0]]
    targets = [[1.0, 2.0, 0.0], [-1.0, 2.0, 10.0]]

    metrics = allocator.evaluate(initial, targets, [0, 1], duration=3.0)

    assert metrics.xy_crossings == 1
    assert metrics.proximity_crossings == 0
    assert metrics.safety == 0.0


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
