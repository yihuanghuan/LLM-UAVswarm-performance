"""Compatibility tests for the isolated historical allocator."""

import numpy as np

from location_allocate.legacy.weighted_sum_allocator import (
    LegacyWeightedSumAllocator,
)
from location_allocate.safety_aware_allocator import (
    SafetyAwareTopologyAllocator,
)


def test_legacy_weighted_sum_remains_outside_paper_allocator():
    assert not issubclass(
        LegacyWeightedSumAllocator, SafetyAwareTopologyAllocator
    )
    allocator = LegacyWeightedSumAllocator(
        d_safe=1.0,
        alpha=1.0,
        beta_xy=7.0,
        beta_prox=11.0,
        gamma=1.0,
    )
    result = allocator.evaluate(
        [[-1.0, 0.0, 0.0], [1.0, 0.0, 10.0]],
        [[1.0, 2.0, 0.0], [-1.0, 2.0, 10.0]],
        [0, 1],
        duration=3.0,
    )

    assert result.xy_crossings == 1
    assert result.proximity_crossings == 0
    assert result.total == result.distance + 7.0


def test_legacy_offline_evaluator_numpy_inputs_remain_supported():
    allocator = LegacyWeightedSumAllocator(d_safe=1.0)

    allocated, metrics = allocator.allocate_with_metrics(
        np.asarray([[-1.0, 0.0, 0.0], [1.0, 0.0, 0.0]]),
        np.asarray([[1.0, 1.0, 0.0], [-1.0, 1.0, 0.0]]),
        duration=3.0,
    )

    assert len(allocated) == 2
    assert metrics == allocator.last_metrics
