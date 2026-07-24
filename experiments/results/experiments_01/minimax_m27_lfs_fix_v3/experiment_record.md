# Experiment 01 LFS Accuracy Fix Record

## Status

- Experiment: selective LFS accuracy regression rerun
- Status: completed successfully
- Branch: `exp/01-llm-parsing`
- Fixed base: `gazebo-experiment-v1`
- Base commit: `6c3496e7a42d7987751dc414396b3d9b11841721`
- Original experiment commit: `ba7fb3dca0e1b5de934eb90e52fd549a978b07ec`
- Baseline run: `minimax_m27_100x4`
- Rerun ID: `minimax_m27_lfs_fix_v3`
- Model: `MiniMax-M2.7-highspeed`
- Result location: `experiments/results/experiments_01/minimax_m27_lfs_fix_v3`

The original 400-row result set was used read-only and remains unchanged.

## Scope

The rerun contains the 20 commands affected by the LFS changes:

- all 18 sequential commands (`sequential_01` through `sequential_18`);
- `simple_18`, which previously emitted the non-canonical `Lineup` formation;
- `style_18`, which previously coupled aggressive motion style to the safety factor.

Only `lfs_schema` was rerun. The dataset snapshot, exact prompt and its SHA-256,
model configuration, normalized result rows, and raw API responses are retained in this directory.

## Changes under test

- Deterministic compiler defaults for `m` and `s`.
- Deterministic transition derivation for `q` from task dependencies and UAV overlap.
- `depends_on` support in the formal LFS schema.
- Canonical `Lineup` to `Line` normalization.
- Safety-factor grounding so motion style cannot modify safety.
- Rejection of duplicate tasks created only by motion-style changes.
- LFS few-shot examples for serial dependency, style grounding, and mapping
  “第一阶段/第二阶段” styles to already established tasks.
- Validation feedback on retry and robust extraction of JSON after model reasoning text.

## Commands

```bash
python3 experiments/scripts/eval_llm_parser.py \
  --run-id minimax_m27_lfs_fix_v3 \
  --method lfs_schema \
  --workers 4 \
  --sample-id simple_18 \
  --sample-id sequential_01 --sample-id sequential_02 --sample-id sequential_03 \
  --sample-id sequential_04 --sample-id sequential_05 --sample-id sequential_06 \
  --sample-id sequential_07 --sample-id sequential_08 --sample-id sequential_09 \
  --sample-id sequential_10 --sample-id sequential_11 --sample-id sequential_12 \
  --sample-id sequential_13 --sample-id sequential_14 --sample-id sequential_15 \
  --sample-id sequential_16 --sample-id sequential_17 --sample-id sequential_18 \
  --sample-id style_18

python3 experiments/scripts/compare_lfs_fix.py \
  --baseline-csv experiments/results/experiments_01/minimax_m27_100x4/sample_results.csv \
  --rerun-csv experiments/results/experiments_01/minimax_m27_lfs_fix_v3/sample_results.csv \
  --output-dir experiments/results/experiments_01/minimax_m27_lfs_fix_v3
```

## Results

| Scope | Count | Before field | After field | Before exact | After exact | Before trigger | After trigger |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| All affected | 20 | 0.8333 | 1.0000 | 0.0000 | 1.0000 | 0.3667 | 1.0000 |
| Sequential | 18 | 0.8287 | 1.0000 | 0.0000 | 1.0000 | 0.2963 | 1.0000 |
| Simple (`simple_18`) | 1 | 0.8750 | 1.0000 | 0.0000 | 1.0000 | 1.0000 | 1.0000 |
| Style (`style_18`) | 1 | 0.8750 | 1.0000 | 0.0000 | 1.0000 | 1.0000 | 1.0000 |

All 20 final rows are JSON-valid, schema-valid, compiler-successful, exact matches.
Safety-factor error is zero for every valid task. The run used 20 API attempts with no retry
and contains no API or semantic error.

## Validation

- Rerun rows: 20, with 20 unique command IDs and only the `lfs_schema` method.
- Raw API attempts: 20.
- Unit and regression tests: 22 passed.
- Python syntax compilation: passed.
- Git whitespace validation: passed.
- Full before/after data: `lfs_fix_comparison.csv`.
