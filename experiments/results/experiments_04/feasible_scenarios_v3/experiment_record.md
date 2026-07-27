# Experiment 04 Feasible-Scenario Revision

## Status and Configuration

- Branch: `exp/04-assignment-baselines`
- Base experiment: 100 trials × 5 scenarios × 5 methods
- Result status: final revised dataset
- Master seed: `20260708`
- Nominal trajectory: Minimum Jerk, 8 s, 20 Hz
- Endpoint feasibility: minimum pairwise distance ≥ 2.1 m
- Primary safety-margin threshold: 2.0 m
- Secondary critical threshold: 1.5 m
- Dense target: 8-point circle with radius 3.2 m
- Crossing-prone target: 5 UAVs on opposing, reversed Y/Z layers

The original dataset and the 2.8 m dense-radius pilot remain in sibling
directories and were not overwritten.

## Commands

```bash
/home/yihuang/learning/LLM_swarm_ws/llm_env/bin/python \
  experiments/scripts/eval_assignment_offline.py \
  --trials 100 \
  --output-dir experiments/results/experiments_04/feasible_scenarios_v3 \
  --seed 20260708 \
  --duration 8 \
  --sample-hz 20 \
  --safety-distance 2 \
  --critical-distance 1.5 \
  --scenario-min-distance 2.1 \
  --nominal-speed 1

/home/yihuang/learning/LLM_swarm_ws/llm_env/bin/python \
  experiments/scripts/analyze_assignment_offline.py \
  --input-dir experiments/results/experiments_04/feasible_scenarios_v3
```

## Main Results

Compared with Hungarian-Distance, the complete safety-aware method:

- reduced overall 2 m safety-margin failure ratio from 0.372 to 0.240;
- reduced overall 1.5 m critical failure ratio from 0.038 to 0.006;
- increased mean minimum distance from 2.362 m to 2.460 m;
- reduced mean safety-violation samples from 42.152 to 18.920;
- increased mean total path length from 22.930 m to 23.031 m.

For `small`, `medium`, and `large`, the complete method's safety-margin
failure ratios were 0.01, 0.01, and 0.06, respectively, and its critical
failure ratio was zero in all three scenarios.

The feasible dense scenario remains a deliberate stress case. Its primary
failure ratio decreased from 0.55 to 0.50 and its critical failure ratio from
0.03 to 0.02. The crossing-prone scenario decreased from 1.00 to 0.62 at the
2 m margin; neither method had material critical failures there.

No allocator weights were changed. The failure-rate improvement comes from
removing unavoidable endpoint violations and separating the configured 2 m
safety margin from the 1.5 m severe-violation indicator.
