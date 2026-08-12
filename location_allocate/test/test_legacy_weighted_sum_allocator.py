"""Compatibility tests for the isolated historical allocator."""

from location_allocate.legacy.weighted_sum_allocator import (
    LegacyWeightedSumAllocator,
)


def test_legacy_weighted_sum_remains_outside_paper_allocator():
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
