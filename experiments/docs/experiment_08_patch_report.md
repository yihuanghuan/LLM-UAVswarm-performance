# Experiment 08 patch implementation report

## Engineering changes

The shared IAPF implementation now uses relative velocity and closing speed,
pairwise-opposite deterministic escape directions, 1.50/1.65 m hysteresis,
and a 0.20 low-pass filter. Freshness, epsilon protection, position and
acceleration limits, and structured debug output remain enabled. The debug
stream additionally records closing speed, hysteresis state, and active
neighbor count.

Experiment-only controller parameters inject a temporary reference hold or
reference bias. Their defaults are inert and they are confined to
`exp/08-iapf`. Command delay is implemented by the deterministic runner.

## Scenarios and matrix

V2 adds two nominally safe scenarios, three execution-deviation scenarios,
and two exchangeable assignment scenarios. `head_on`, `vertical`,
`grouped_reconfiguration`, and `dense_infeasible` are retained only as
stress/failure-boundary cases. Fixed-identity scenarios now always resolve to
fixed assignment, even when a method uses safety-aware assignment elsewhere.

The v2 formal matrix is 40 non-intrusive + 60 fallback + 80 complement + 40
stress + 10 position-only ablation = 230 trials. A 27-arm, one-seed pilot is
run first. All paired comparisons reuse the same seed.

## Metrics and statistics

The analysis adds completion time, activation event count, intervention
latency, unnecessary intervention rate, paired minimum-distance improvement,
paired risk reduction, and fallback rescue rate. Planned continuous
comparisons use Wilcoxon signed-rank tests and paired-median 10,000-sample
bootstrap confidence intervals. Paired mission outcomes use exact McNemar
tests.

## Result preservation

The original formal batch was moved without modification to
`v1_original/formal/exp08-formal-20260728`. The 15 prior smoke batches are
classified under `v1_original/smoke_runs`. New pilot and formal batches are
written under `v2_patch/pilot` and `v2_patch/formal`, respectively.

Run commands are documented in `experiments/08-iapf/README.md`.
