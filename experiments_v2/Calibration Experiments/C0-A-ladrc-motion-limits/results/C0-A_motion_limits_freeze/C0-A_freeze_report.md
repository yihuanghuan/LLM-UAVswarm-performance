# C0-A Freeze Confirmation

## Status

- Stage C mission-success trials: **36/36**.
- Saturation: **zero in all trials**.
- Freeze status: **FROZEN**.

The policy is a validated execution-policy candidate, not an optimised controller configuration.

## Final frozen parameters

- velocity limit: 5.0 m/s
- acceleration limit: 5.0 m/s²
- jerk limit: 10.0 m/s³
- LADRC omega_c: [1.5, 1.5, 1.75]
- LADRC omega_o: [5.0, 5.0, 7.5]

## Stage C validation statistics

Format: mean / standard deviation / minimum / maximum.

| Metric | Result |
|---|---:|
| Tracking RMSE (m) | 0.1017 / 0.0410 / 0.0267 / 0.1573 |
| Final error (m) | 0.0135 / 0.0048 / 0.0034 / 0.0212 |
| Settling time (s) | 4.3517 / 0.7482 / 3.2799 / 5.3792 |
| Peak velocity (m/s) | 1.9399 / 0.8291 / 0.6920 / 3.2174 |
| Peak acceleration (m/s²) | 2.9733 / 0.5551 / 1.6163 / 4.3084 |
| Saturation ratio | 0.0000 / 0.0000 / 0.0000 / 0.0000 |

Analytic/reference jerk is retained in each trial's `runtime_metrics.per_uav[0].analytic_reference_peaks.jerk`; it is 5.12 m/s³ for the diagonal reference profile and remains below the selected 10 m/s³ limit.

## Reproducibility

- Git commit: `6c2fdaa4f5d0a735183e3b224d6aca2eab898455`
- Configuration hash: `60a3528020b3fd84013850faab3ca24625bd1d74be4c77a19be3fc885b82f75a`
- Baseline config SHA-256: `e98033b5cac3e79122f0813a93bcc779cf9902da65cb4ec45c6b8b77660fb932`
- Sweep config SHA-256: `a4cedf2012231de2a0ce46cef9c5c8e49087ef3265abbadab664e187679656df`
- Seed root: `20260821`; per-trial seeds and specifications are in `stage_c_plan.csv` and `trials/*/trial_spec.json`.

## Calibration timeline

1. Stage A screening — fixed LADRC baseline across short, medium, and long x/y/z/diagonal scenarios; screening passed.
2. Stage A repeatability — 36/36 trials succeeded with zero saturation.
3. Stage B bounded OAT sweep — all 27 stress trials succeeded; the non-boundary 5/5/10 candidate was selected.
4. Stage C confirmation — 36/36 mission-success trials and zero saturation with that candidate.

## Diagnostic review

- `C_selected_validation_medium_diagonal_r1`: `COMMAND_JERK_P99_5`. This is retained from the legacy command finite-difference diagnostic; it is not the analytic/reference jerk used by C0-A.

The diagnostic is retained for audit but is not a C0-A hard failure: jerk feasibility uses the analytic/reference trajectory profile.
## Conclusion

Stage C passes. The frozen artifact defines the validated execution policy for subsequent formal experiments.
