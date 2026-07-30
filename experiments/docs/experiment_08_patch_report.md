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

## V2 completion record

- Branch: `exp/08-iapf`
- Fixed baseline: `gazebo-experiment-v1`
  (`df5c5bc9b7a1af695c41dea5744bcb546b7f0a47`)
- Shared algorithm revision on `main`:
  `aa4ce3a214ce54172fe1c8b56a1e7d6aace7d4c8`
- Shared algorithm merge on this experiment branch:
  `d1206dbec8ec72de9092d5f000c386475f926962`
- Formal execution revision:
  `5d58572b494f5fa994d83a1f9473227fe7ac470c`
- Formal artifact commit:
  `52b306d858069d33ecef0c80def2bf6b7b415d98`
- Experiment configuration:
  `experiments/08-iapf/config/experiment_defaults.yaml`,
  `experiments/08-iapf/config/methods.yaml`, and
  `experiments/08-iapf/config/scenarios/`
- Pilot data:
  `experiments/results/experiments_08/v2_patch/pilot/`
- Formal data:
  `experiments/results/experiments_08/v2_patch/formal/exp08-v2-formal-20260730/`
- Formal command:
  `/usr/bin/python3 -u experiments/08-iapf/scripts/run_batch.py
  --batch-id exp08-v2-formal-20260730 --phase formal --manage-sim --resume`
- Post-processing: `aggregate_trials.py`, `plot_iapf_results.py`, and
  `checksum_results.py`, using the formal data directory above.
- Completion status: successful; all 230 planned formal trials are present,
  with no missing or unexpected trial keys. The result set contains five
  summary CSV files, seven PNG/PDF figure pairs, and a verified 2,416-entry
  artifact checksum manifest.

The auxiliary `exp08-v2-formal-20260729` directory records the failed
background startup. `exp08-v2-formal-validation-20260730` records an
interrupted dry-run validation. Pilot attempts and tuning batches remain
separate under `v2_patch/pilot`; none of these auxiliary directories is
included in the 230-trial formal aggregate.
