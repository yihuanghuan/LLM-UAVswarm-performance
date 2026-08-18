# Formal Evaluation Experiments

This tree is exclusively for sealed paper-final evaluation scenarios and
artifacts. It must not be used until all C0 calibrations are complete and an
immutable paper-final tag has been created.

Rules:

- Declare `dataset_class: formal_evaluation` in every result manifest.
- Seal scenario definitions and seeds before the first accepted formal run.
- Formal scenarios, seeds, partial results and aggregate statistics may not be
  used to select, reject or revise parameters.
- If any formal scenario or seed influences tuning, permanently remove it from
  this set, register it as calibration data, and replace it before restarting
  formal evaluation.
- Store formal raw data and metrics separately from calibration and legacy
  data; never pool their statistics.
- Every result must identify the immutable paper-final tag, Git commit, policy
  hash, scenario-registry version, scenario ID, seed and environment manifest.
- Old `exp/*` results are `legacy_pilot`, not members of this formal dataset.

Formal branches must be siblings created independently from the same
paper-final tag. Instrumentation may observe or record but must not change Full
Method runtime semantics or frozen parameter values.
