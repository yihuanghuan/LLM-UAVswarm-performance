# Paper Safety-Aware Topology Assignment

The Paper Candidate path uses Hungarian distance initialization followed by
pairwise local refinement. A swap is accepted only when it improves the true
lexicographic score

```text
(hard_violation_count, planning_margin_cost, total_distance)
```

where a pair is a hard violation when its synchronized nominal 3-D distance is
below `d_hard`, and its planning-margin cost is

```text
max(0, (d_plan - d_min) / d_plan)^2
```

for `0 < d_hard <= d_plan`. Equal-progress Minimum-Jerk motions use an analytic
3-D closest-approach solution. Independent-duration ParallelGroup motions use
numerical Minimum-Jerk evaluation on a shared clock, with completed vehicles
held at their targets. The Paper policy's `sample_hz` affects only that
variable-duration numerical evaluation; equal-progress analytic closest
approach is independent of the sampling rate. `comparison_tolerance` is only a
floating-point tolerance for lexicographic comparison, not an objective weight.

XY segment crossings remain available as diagnostics, but are not part of the
Paper optimization objective. The historical weighted-sum implementation is
isolated in `location_allocate.legacy.weighted_sum_allocator` for explicit
legacy replay and historical offline experiments.

This algorithm is a local refinement and does not claim a global optimum or a
collision-free guarantee. Final assignments are revalidated under final
execution timing before profiles are compiled.
