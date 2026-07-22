# Experiment 01 Completion Record

## Status

- Experiment: LLM parsing reliability evaluation
- Status: completed successfully
- Branch: `exp/01-llm-parsing`
- Fixed base: `gazebo-experiment-v1`
- Base commit: `6c3496e7a42d7987751dc414396b3d9b11841721`
- Run ID: `minimax_m27_100x4`
- Model: `MiniMax-M2.7-highspeed`
- Result location: `experiments/results/experiments_01/minimax_m27_100x4`

The final commit SHA is the pushed branch tip and is recorded in the delivery message after Git creates it.

## Dataset and configuration

The fixed dataset contains 100 unique Chinese commands: 18 simple, 18 sequential,
18 grouped, 18 style-conditioned, 10 safety-conditioned, and 18 invalid/ambiguous.
Each valid command has formal LFS ground truth; invalid commands have an expected rejection category.

Each command was evaluated once with `plain_json`, `few_shot_json`, `lfs_schema`, and
`dense_waypoints`, producing 400 final sample rows. All methods used temperature 0,
top-p 0.01, JSON response mode, a 4000-token completion limit, and at most three attempts.
The complete prompts and their SHA-256 hashes are stored in `run_config.json`.

## Commands

```bash
python3 experiments/scripts/build_experiment_01_dataset.py

python3 experiments/scripts/eval_llm_parser.py \
  --run-id minimax_m27_100x4 \
  --method all \
  --workers 4

# Used after the MiniMax Token Plan was replenished. Existing successful rows were retained.
python3 experiments/scripts/eval_llm_parser.py \
  --run-id minimax_m27_100x4 \
  --method all \
  --workers 4 \
  --resume \
  --retry-api-errors

python3 experiments/scripts/analyze_llm_parser_experiment.py \
  --run-dir experiments/results/experiments_01/minimax_m27_100x4
```

## Primary results

| Method | JSON valid | Schema valid | Field accuracy | Exact task | Rejection accuracy | Mean latency (ms) |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| plain_json | 1.0000 | 0.8000 | 0.7157 | 0.5366 | 1.0000 | 29578.56 |
| few_shot_json | 1.0000 | 1.0000 | 0.9954 | 0.9634 | 0.8889 | 17062.41 |
| lfs_schema | 1.0000 | 1.0000 | 0.9593 | 0.7561 | 0.8889 | 16598.37 |
| dense_waypoints | 0.9800 | 0.9500 | 0.9360 | 0.7439 | 0.7222 | 45838.16 |

Accuracy fields exclude invalid/ambiguous commands; rejection accuracy uses only those commands.
Latency and token counts include retries. The full metric table is in `summary_by_method.csv`.

## Validation and provenance

- Final result rows: 400, exactly 100 per method, with no duplicate command/method keys.
- Raw API attempts: 635; every final row matches the last attempt session and retry count.
- Final infrastructure failure rate: 0%.
- An earlier Token Plan exhaustion is retained in `raw_attempts.jsonl`; those failed rows were
  removed from the final CSV and rerun after quota recovery.
- Unit and regression tests: 16 passed.
- Generated artifacts: Table 1, four PNG figures, four matching PDF figures, raw JSONL,
  normalized per-sample CSV, dataset snapshot, configuration, and analysis manifest.
