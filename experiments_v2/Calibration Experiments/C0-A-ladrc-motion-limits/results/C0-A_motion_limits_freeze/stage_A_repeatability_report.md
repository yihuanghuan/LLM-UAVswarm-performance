# C0-A Stage A — Repeatability Confirmation

All trials use the fixed LADRC baseline and unchanged motion limits. This report is a feasibility/reproducibility check, not controller tuning.

## Trial outcome

- Completed trials: 36/36
- Success rate: 36/36
- Failure cases: 0
- Saturation remains zero: yes

## Aggregate metrics

- Tracking RMSE (m): mean 0.1022; std 0.0403; max 0.1490; min 0.0288
- Final error (m): mean 0.0128; std 0.0053; max 0.0261; min 0.0055
- Settling time (s): mean 4.3533; std 0.7427; max 5.3594; min 3.2793
- Peak velocity (m/s): mean 1.9387; std 0.8252; max 3.1958; min 0.6858
- Peak acceleration (m/s²): mean 2.8159; std 0.5917; max 3.9947; min 1.5846
- Saturation ratio (): mean 0.0000; std 0.0000; max 0.0000; min 0.0000

## Worst-case scenario

- long_y (A_baseline_long_y_r3): tracking RMSE 0.1490 m; final error 0.0171 m; settling time 5.2994 s.

## Repeatability assessment

- Per-scenario tracking-RMSE and final-error spread threshold: 0.20 m.
- Tracking metrics repeatable: yes.
- Stage A repeatability: PASS.

## Failure or completeness issues

- None.
