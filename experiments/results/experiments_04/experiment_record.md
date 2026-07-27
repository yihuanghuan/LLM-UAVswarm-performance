# Experiment 04 Execution Record

## Status

- Experiment: target-assignment baseline comparison
- Branch: `exp/04-assignment-baselines`
- Base: `gazebo-experiment-v1` (`df5c5bc9b7a1af695c41dea5744bcb546b7f0a47`)
- Status: completed successfully
- Result directory: `experiments/results/experiments_04`
- Final commit SHA: recorded in the final Git handoff after committing these artifacts

## Configuration

- Trials: 100 per scenario
- Scenarios: `small`, `medium`, `large`, `dense`, `crossing-prone`
- Methods: Random, Nearest Neighbor, Hungarian-Distance, Hungarian + crossing
  penalty, Hungarian + safety-aware local swap
- Master seed: `20260708`
- Nominal trajectory: Minimum Jerk, 8 s, 20 Hz
- Safety distance: 2 m
- Nominal arrival speed: 1 m/s
- Crossing-prone geometry: opposing X planes, reversed Y ordering, altitude
  levels from 2 m to 8 m, Gaussian position noise with 0.04 m standard deviation

The exact machine-readable configuration is in `run_config.json`.

## Commands

```bash
/home/yihuang/learning/LLM_swarm_ws/llm_env/bin/python \
  experiments/scripts/eval_assignment_offline.py \
  --trials 100 \
  --output-dir experiments/results/experiments_04 \
  --seed 20260708 \
  --duration 8 \
  --sample-hz 20 \
  --safety-distance 2 \
  --nominal-speed 1

/home/yihuang/learning/LLM_swarm_ws/llm_env/bin/python \
  experiments/scripts/analyze_assignment_offline.py \
  --input-dir experiments/results/experiments_04
```

## Validation

- Generated 2,500 method-level rows: 5 scenarios × 100 trials × 5 methods.
- Every scenario/method group contains exactly 100 rows.
- Every assignment is a valid target permutation.
- All recorded numeric metrics are finite and all compute times are non-negative.
- All ten files declared by `analysis_manifest.json` exist.
- Automated tests: 10 passed, covering experiment 04 and the runtime
  safety-aware allocator.

## Results and Interpretation

The complete aggregate values are in `table_assignment_baselines.md`; the
scenario-level values are in `assignment_summary.csv`.

- Hungarian-Distance produced the shortest mean path length (28.587 m).
- The crossing-penalty method removed all measured XY crossings, at a mean
  path length of 29.216 m.
- The complete safety-aware method reduced overall failed-assignment ratio
  from 0.722 to 0.702 relative to Hungarian-Distance, with mean path length
  increasing from 28.587 m to 29.308 m.
- In the small, medium, and large scenarios, the complete method increased
  mean minimum distance and reduced safety-violation samples relative to
  Hungarian-Distance.
- All dense trials failed the 2 m threshold because many initial positions
  were already inside that threshold; target reassignment cannot remove
  violations present at the first trajectory sample.
- In the altitude-layered crossing-prone scenario, removing XY projection
  crossings did not improve 3-D safety. The result demonstrates that a
  topological XY crossing metric and physical 3-D separation are distinct
  objectives and should not be interpreted interchangeably.

No weights or scenarios were retuned after observing the formal results.
