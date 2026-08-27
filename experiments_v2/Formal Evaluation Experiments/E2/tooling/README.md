# E2 commitment-timing tooling

This directory contains experiment-only tooling for the sealed E2 protocol. It
loads `candidate_ground_truth` and the exact registered snapshots, uses the
sealed `e2_commitment_wrapper.py`, and invokes the frozen production
`resolve_execution_task` implementation. It does not call an LLM, Gazebo, PX4,
ROS, or any controller, and it does not publish commands.

The runner currently exposes synthetic validation only. It deliberately has no
formal-result mode and always writes all of these labels:

```text
dataset_class: synthetic_validation
accepted_formal_result: false
NOT_FORMAL_RESULT
```

Run provenance and tests from the repository root:

```bash
PYTHONPATH="location_allocate:lfs_policy:experiments_v2/Formal Evaluation Experiments/harness:experiments_v2/Formal Evaluation Experiments/E2/tooling" \
  python3 "experiments_v2/Formal Evaluation Experiments/E2/tooling/e2_provenance.py"

PYTHONPATH="location_allocate:lfs_policy:experiments_v2/Formal Evaluation Experiments/harness:experiments_v2/Formal Evaluation Experiments/E2/tooling" \
  python3 -m pytest -q \
  "experiments_v2/Formal Evaluation Experiments/harness/test_e2_commitment_wrapper.py" \
  "experiments_v2/Formal Evaluation Experiments/E2/tooling/test_e2_tooling.py"
```

Run the complete 120-attempt dry run:

```bash
PYTHONPATH="location_allocate:lfs_policy:experiments_v2/Formal Evaluation Experiments/harness:experiments_v2/Formal Evaluation Experiments/E2/tooling" \
  python3 "experiments_v2/Formal Evaluation Experiments/E2/tooling/e2_runner.py" \
  --synthetic-validation --run-id RUN_ID
```

The output is created exclusively beneath
`E2/results/synthetic-validation/RUN_ID/`. It contains a provenance manifest,
120-file append-only hash-chained raw journal, offline score, deterministic
replay report, offline audit, result manifest, and file hash manifest.

The dry-run sequence is an E2-only filter of the immutable globally interleaved
E2–E5 order. This filtering exists only for Stage A/B validation and is not
claimed to be the formal execution order. The runner does not modify the order
or consume its formal cursor.

Offline rescoring and auditing are available independently:

```bash
PYTHONPATH="location_allocate:lfs_policy:experiments_v2/Formal Evaluation Experiments/harness:experiments_v2/Formal Evaluation Experiments/E2/tooling" \
  python3 "experiments_v2/Formal Evaluation Experiments/E2/tooling/e2_scorer.py" RUN_DIR

PYTHONPATH="location_allocate:lfs_policy:experiments_v2/Formal Evaluation Experiments/harness:experiments_v2/Formal Evaluation Experiments/E2/tooling" \
  python3 "experiments_v2/Formal Evaluation Experiments/E2/tooling/e2_audit.py" RUN_DIR
```

Synthetic scores are tooling diagnostics only and must not be interpreted as
paper evidence or used for tuning.
