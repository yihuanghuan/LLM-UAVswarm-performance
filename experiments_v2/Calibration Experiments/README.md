# Calibration Experiments

This tree is exclusively for parameter-selection scenarios and artifacts.
Calibration may use its registered scenarios and seeds to select values in
`docs/paper_parameter_freeze_ledger.md`.

Rules:

- Declare `dataset_class: calibration` in every result manifest.
- Register scenario IDs, exact seeds, sweep, acceptance rule and failure
  handling before execution.
- Keep raw logs, bags, per-trial metrics and failed/timeout trials; do not
  delete or silently rerun failures.
- Never copy calibration samples into a formal-evaluation aggregate.
- If a formal scenario or seed is viewed or used to choose a value, move it
  permanently into this calibration registry and replace it in the sealed
  formal registry.
- Legacy `exp/*` and pilot results are context only. They are not automatically
  members of this calibration set.

The directory order is C0-A, C0-B, C0-C, C0-D, C0-E, C0-F. Each C0
branch is created from the latest `paper/calibration`, while experimental code
and generated data remain on that C0 branch or in external artifact storage.
Only frozen parameter values and provenance return to `paper/calibration`.

Allocator numerical convergence is Supporting Method Verification, not a
Phase-0 calibration stage. It may verify the sealed allocator numerics but may
not select or retune them.

The canonical pre-registration for C0-A is
`experiments_v2/Calibration Experiments/C0-A-ladrc-motion-limits/legacy_campaign/CALIBRATION_PROTOCOL.md`.
