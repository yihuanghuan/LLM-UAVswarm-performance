# E3-v4 frozen analysis contract

Status: `FROZEN_BEFORE_FORMAL_RESULTS`

This contract applies only to the standalone 360-attempt E3-v4 confirmatory
campaign. Qualification/pilot data, E3-v3 historical data, infrastructure
retries, and incomplete four-cell blocks are excluded from primary effect
estimation. They remain retained and are reported separately.

## Experimental unit and primary population

The repeated-measures block is (b=(scenario, seed)). A primary block must
contain exactly one scientifically eligible attempt in each registered cell
P0_F0, P0_F1, P1_F0, and P1_F1. The primary population is all complete
four-cell blocks. The two scenarios within each family and all 15 paired seeds
are retained; no result-dependent scene/seed exclusion is permitted.

An infrastructure failure remains in the all-attempt denominator and journal
but contributes no continuous scientific metric. There are no replacement
seeds, no outcome imputation, no best-retry selection, and no
significance-triggered extension. If a registered block is incomplete, it is
excluded as a whole from primary factorial contrasts and included in a
missingness table with reason. Available-cell descriptive summaries and an
all-attempt mission/failure analysis are mandatory sensitivity reports, not
substitutes for the primary block population.

## Block-level factorial estimands

For every registered endpoint (Y), calculate within each complete block:

\[
\Delta_P^{(b)} = \frac{(P1F0-P0F0)+(P1F1-P0F1)}{2},
\]

\[
\Delta_F^{(b)} = \frac{(P0F1-P0F0)+(P1F1-P1F0)}{2},
\]

\[
\Delta_{PF}^{(b)}=(P1F1-P1F0)-(P0F1-P0F0).
\]

The two correlated simple contrasts inside a block are never stacked as
independent observations. Family-level inference uses 30 possible blocks
(2 fixed scenarios x 15 seeds), stratified by scenario.

## Registered endpoints

Primary safety endpoint: realized hard-risk exposure (J_{hard}), expressed
as pair-seconds; lower is safer. Key supporting endpoints are realized minimum
3-D separation (higher is safer), hard-risk event count (lower), and binary
any-realized-hard-risk (lower). Predicted minimum separation and predicted
hard-conflict count are planning/manipulation-check endpoints. Mission success,
failsafe, controller near-limit fraction, and feedback intervention burden are
reported as operational/burden endpoints and cannot replace a safety endpoint.

Current frozen thresholds and interpolation/event semantics are used without
change: (d_{hard}=1.50\) m, (d_{plan}=1.80\) m, and the registered E3
continuous-time pairwise metric implementation.

## Family hypotheses and manipulation checks

- Family A tests planning responsibility. P1 should lower predicted structural
  conflicts and realized hard risk relative to P0. In F1 cells, feedback
  intervention burden should also be lower after safer planning.
- Family B tests feedback responsibility only after the frozen qualification
  established F0 residual risk. F1-vs-F0 effects are evaluated for exposure,
  events, and minimum distance, with intervention burden reported. A null or
  harmful F1 effect is retained as valid negative evidence.
- Family C tests decomposition. P0 has registered predictable structural risk;
  P1 removes that nominal component; P1_F0 must be reported as the residual
  execution-risk cell. The interaction and responsibility decomposition are
  primary interpretations. P1_F1 is not required to be globally best on every
  metric.

Formal manipulation checks are descriptive and do not authorize post-result
scene deletion or retuning. Delivery-invalid attempts are infrastructure
failures under the preregistered fail-closed semantics.

## Confidence intervals, tests, and effect sizes

All intervals are two-sided 95% intervals; directional hypotheses are
interpreted from signed estimates and intervals, not converted to one-sided
tests. For continuous/count block contrasts, report the mean block contrast,
median, paired standardized effect (d_z=\bar\Delta/s_\Delta) when variance is
nonzero, and a scenario-stratified paired-block percentile bootstrap interval
with 10,000 resamples. Seeds are resampled with replacement within each fixed
scenario; all four cells travel together. The bootstrap RNG seed is the first
64 bits of SHA-256 of `E3-v4-analysis-bootstrap-v1|family|endpoint|contrast`.

For binary endpoints, compute the same block-level factorial contrasts on
0/1 outcomes and use the same stratified paired-block bootstrap for risk-
difference contrasts. Cell proportions use Wilson score intervals. Registered
two-cell paired binary summaries use the exact McNemar test plus paired risk
difference. Ordinary Student-t proportion confidence intervals are forbidden
as paper-primary binary intervals.

Report raw estimates and intervals for all registered endpoints. The primary
confirmatory endpoint within each family is (J_{hard}). Supporting endpoint
p-values, if shown, use Holm adjustment within family; effect estimates and
confidence intervals are never suppressed by significance.

## Audit invariants

```text
registry_sha256 = 80ddbb8701f1c7feb84ae64a7985f233742f522c1204131ab4dd6d09960bd79b
formal_seed_registry_sha256 = 665600871ad3fb6cff324ab3ef9144b0d84b42acc19505283679b6ae01586841
formal_order_sha256 = 60ee30a7100b53c4964e3f9f086ff3d137fb41282eebc4439760bf17f033b39b
F1_qualification_attempt_count = 0
formal_attempt_count_at_freeze = 0
```
