# E2 — Commitment timing

Population: 120/120 scientific-complete attempts, comprising 60 paired Early/Late comparisons.

Both conditions achieved executable grounding in 60/60 attempts. Under `NO_SHIFT`, neither condition had an adverse primary outcome. Under `SHIFT`, Early Commitment produced 25/30 state-consistency violations and 15/30 dynamic infeasibility/correction outcomes; Information-Aligned Late Commitment produced 0/30 for each. Rejection was 0/60 in both conditions.

The adverse timing effect is therefore concentrated exactly where registered execution-time information changes, while remaining visible across the frozen scenario breakdown recorded in `summary.json`. Paired differences, Student-t uncertainty intervals, and Cohen's dz are reported in the machine-readable summary; degenerate all-zero contrasts correctly have no defined dz.

Verdict: `C1_COMMITMENT_TIMING: SUPPORTED`.

Maximum defensible wording: In the frozen paired E2 setting, premature numerical commitment caused state-inconsistent or feasibility-corrected behavior when execution-time state changed, whereas preserving unresolved intent until the registered execution snapshot eliminated those adverse outcomes; the conditions were equivalent when the state did not change.
