# C0-B freeze audit

## Scope and immutable inputs

- Calibration execution/base commit: `17f0c1ec62b8d5554c575af5754861b59d70eabc`
- Original C0-B result commit: `e7e67bea4a4a07ac5d131376863dc80c1418d1df`
- C0-A frozen policy SHA-256: `1ac009c4da6636fe4a3fcd8492fe9957e22bba94412e005a3555dd5985a5d325`
- Combined C0-B measurement CSV SHA-256: `6c664405a1e1bcc13cbf0ba5a51cd89e7a4900c381a45ba1c36cddeb16486261`
- C0-B campaign configuration SHA-256: `d590611cf47de3aec49d325035746dc9a4b0b4306203ca6c4811d977529b9b5d`
- Finalized C0-B policy SHA-256: `fdc7b3fd038ae623699eaefd131028d53a259c22507b320c2775369c23594884`
- Downstream canonical policy SHA-256: `65bc31a4a231b5fe520f9e33a8be219e15088824a9cc988120e9dcc22721d058`

The manifest's `git_commit` is intentionally the commit used for calibration
execution/freeze generation.  It is not a claim that the generated result
artifact was committed at that SHA; the later artifact commit is recorded
above explicitly.

## Final policy decision

The campaign measurement CSV is preserved unchanged.  Its state-age and
snapshot-skew P99 plus the fixed 10 ms margin justify the frozen values
`state_timeout_ms=22.080` and `snapshot_skew_threshold_ms=22.043`.

Planner waiting was re-evaluated from the preserved real combined dataset
with those frozen predicates, rather than the former provisional
500 ms / 150 ms predicates.  The replay contains 3,658 complete snapshots;
each was immediately acceptable, so P99 planner wait is 0 ms.  Applying the
same fixed 10 ms margin retains `planner_wait_timeout_ms=10.000`.  The
replay records are `corrected_planner_wait_measurements.csv` and
`corrected_planner_wait_summary.yaml`.

## Downstream consumption and verification

`lfs_policy.paper_current.yaml` is now configuration
`paper-current-v8-c0-b-frozen`, with state freshness in seconds and
`parameter_status` explicitly marking C0-A motion/LADRC and C0-B freshness as
frozen.  All later calibration values remain marked provisional.  The policy
adapter regression asserts these values after the policy is loaded.

The runtime deadline regression verifies immediate acceptance, acceptance
after a transient wait, and rejection when the deadline expires.  The runtime
uses no more than `min(0.05, remaining_time)` per spin, so it does not
intentionally exceed the configured freshness wait deadline.
