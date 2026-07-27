# Experiment 02 Completion Record

## Status

- Experiment: LFS intermediate representation ablation
- Status: completed successfully
- Branch: `exp/02-lfs-ablation`
- Fixed base: `gazebo-experiment-v1`
- Base commit: `df5c5bc9b7a1af695c41dea5744bcb546b7f0a47`
- Run ID: `minimax_m27_100x4`
- Model: `MiniMax-M2.7-highspeed`
- Result location: `experiments/results/experiments_02/minimax_m27_100x4`
- Final pushed commit SHA: recorded in the delivery message after Git creates the commit

## Dataset and protocol

The fixed dataset contains 100 unique Chinese commands. Primary metrics use 82 valid commands;
18 invalid or ambiguous commands are evaluated separately for correct rejection and false execution.
Each command was independently evaluated once with all four methods, producing 400 final rows.
All methods used temperature 0, top-p 0.01, JSON response mode, and at most three attempts.

## Commands

```bash
source ~/learning/LLM_swarm_ws/llm_env/bin/activate
source /opt/ros/humble/setup.bash
source ~/learning/LLM_swarm_ws/install/setup.bash
python3 experiments/scripts/eval_lfs_ablation.py --run-id minimax_m27_100x4 --method all --workers 4
python3 experiments/scripts/analyze_lfs_ablation.py --run-dir experiments/results/experiments_02/minimax_m27_100x4
```

## Primary results

| Method | Executable | Mean retries | Invalid UAV | Invalid formation | Missing field | Compilation |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Direct waypoint | 1.0000 | 0.0488 | 0.0000 | 0.0169 | 0.0000 | 1.0000 |
| Task JSON (no schema) | 0.9878 | 0.0000 | 0.0000 | 0.0169 | 0.0000 | 0.9878 |
| LFS + schema | 1.0000 | 0.0000 | 0.0000 | 0.0085 | 0.0000 | 1.0000 |
| LFS + schema + semantic | 1.0000 | 0.0000 | 0.0000 | 0.0000 | 0.0000 | 1.0000 |

## Validation

- Final result rows: 400, exactly 100 per method, with no duplicate command/method keys.
- Valid-command rows: 82 per method; invalid-command rows: 18 per method.
- API infrastructure failures: 0.
- Existing experiment data was not overwritten.
