# C0-A Stage A — Controller Baseline Validation

This is a single-repeat screening pass with fixed LADRC parameters and fixed motion limits; it is not gain tuning or a policy freeze.

## Coverage

- Planned/executed cases: 12/12
- Distances: short, medium, long.
- Directions: x, y, z, diagonal.
- Repetitions completed: 1 per case (repeatability remains pending).

## Outcome

- Successes: 12/12
- Failures: 0
- Stage A screening: PASS
- Stage B readiness: acceptable for a bounded initial sweep; three-repeat confirmation is still required before any freeze.

## Metric statistics

- Tracking RMSE (m): mean 0.1022; max 0.1490; min 0.0288
- Final position error (m): mean 0.0141; max 0.0226; min 0.0074
- Settling time (s): mean 4.3527; max 5.3594; min 3.2992
- Peak velocity (m/s): mean 1.9244; max 3.1918; min 0.6858
- Peak acceleration (m/s²): mean 2.8438; max 3.9947; min 1.6011
- Peak jerk (m/s³): mean 54.1785; max 108.1521; min 28.8604
- Saturation ratio: mean 0.0000; max 0.0000; min 0.0000
- Velocity-limit utilization: mean 0.3849; max 0.6384; min 0.1372
- Acceleration-limit utilization: mean 0.5688; max 0.7989; min 0.3202
- Jerk-limit utilization: mean 5.4179; max 10.8152; min 2.8860

Jerk utilization is diagnostic only: it is an unfiltered second finite difference of PX4 measured velocity and therefore includes estimator/sample noise. It is not used as a Stage A pass/fail condition; analytic reference jerk remains separately bounded by the compiled profile.

## Worst-case scenario

- long_x (A_baseline_long_x_r1): tracking RMSE 0.1490 m; final error 0.0124 m; saturation 0.0000.

## Failure cases

- None.
