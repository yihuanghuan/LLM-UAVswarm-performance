# E2--E5 sealed global campaign infrastructure

CURRENT FORMAL CAMPAIGN STATUS: **NOT_READY**

E3, E4A, E4B, and E5 do not yet have pinned validated runners. Passing these
infrastructure tests does not authorize cursor #1. This directory provides only
`synthetic_validation`; every generated record is labeled
`accepted_formal_result: false` and `NOT_FORMAL_RESULT`.

## Authority and execution boundary

`simulation_trial_order_v1.txt` is the sole 610-attempt order authority. The
dispatcher derives position `k + 1` only from the retained append-only suite
journal, then routes exactly that trial. It has no API for “next E2”, next
available runner, skipping an unavailable family, replacement seeds, or
re-running a retained registered trial. Success and retained failure both
advance by one position. A failure never replaces its journaled attempt.

Each adapter must implement:

```python
run_exact_trial(trial_id, campaign_context) -> retained_attempt_descriptor
```

The adapter must execute only the supplied ID, must not select another trial or
alter suite state, and must atomically retain an immutable artifact before
returning its status, relative path, SHA-256, commit, and source provenance.
Only the dispatcher may append the suite journal.

The journal uses `000001-attempt.json`, ... with a SHA-256 chain. Startup
validates the exact sealed prefix and every retained artifact. An artifact
without its journal entry, any partial temporary file, a gap, duplicate,
reorder, replacement, hash mismatch, or concurrent dispatcher causes a
fail-closed stop for explicit recovery. Artifacts are published and fsynced
before the corresponding journal record is atomically published and fsynced.

## Synthetic rehearsal

From the repository root:

```bash
PYTHONPATH="experiments_v2/Formal Evaluation Experiments/campaign" \
  python3 -m pytest -q \
  "experiments_v2/Formal Evaluation Experiments/campaign/test_campaign_infrastructure.py"

PYTHONPATH="experiments_v2/Formal Evaluation Experiments/campaign" \
  python3 "experiments_v2/Formal Evaluation Experiments/campaign/campaign_provenance.py"

PYTHONPATH="experiments_v2/Formal Evaluation Experiments/campaign" \
  python3 "experiments_v2/Formal Evaluation Experiments/campaign/synthetic_rehearsal.py" \
  --synthetic-validation --run-id RUN_ID

PYTHONPATH="experiments_v2/Formal Evaluation Experiments/campaign" \
  python3 "experiments_v2/Formal Evaluation Experiments/campaign/campaign_audit.py" \
  "experiments_v2/Formal Evaluation Experiments/campaign/results/synthetic-validation/RUN_ID"
```

The rehearsal invokes deterministic mock adapters, never E2/E3/E4/E5
scientific tooling. Results exist only beneath
`campaign/results/synthetic-validation/<run-id>/`; no formal campaign directory
or cursor is created or consumed.

## Formal launch gate

Formal launch remains fail closed until all of the following are independently
recorded: E2 READY, E3 READY, E4A READY, E4B READY, E5 READY, global
infrastructure PASS, complete 610-attempt synthetic rehearsal PASS, and all
provenance checks PASS. A later, separately approved launch mechanism must also
provide formal-capable exact-trial adapters; this synthetic dispatcher contains
no accepted-formal-result mode.

The runner registry truthfully pins the validated E2 Stage-B synthetic head as
its interface reference and leaves E3/E4A/E4B/E5 unpinned and `NOT_READY`.

## Scientific interpretation

The global order is data-collection order only. Analysis remains separate:
E2 supports C1, E3 supports C2, E4A/E4B support C3, and E5 provides integration
evidence. The infrastructure does not define or report a 610-trial overall
scientific success rate and does not replace any preregistered primary metric.
