# E3-v4 scenario qualification contract

Status: FROZEN BEFORE E3-v4 QUALIFICATION RESULTS

Purpose: qualify external conditions that make the Planning x Feedback factorial a
valid test of C2. Qualification establishes manipulation validity; it must not select
conditions that make the feedback treatment look effective.

## Frozen governance boundary

The production baseline, policy, allocator algorithms, IAPF equations and parameters,
LADRC, Minimum Jerk, motion limits, thresholds (`d_hard = 1.5 m`, `d_plan = 1.8 m`),
state-freshness rules, safety-factor mapping, execution profile, and runtime semantics
are frozen. Qualification may change only exact initial/target geometry and the
experiment-only disturbance vector, magnitude, duration, onset, affected UAVs, and
instrumentation needed to retain evidence.

E3-v3 registries, raw results, manifests, journals, hashes, analysis, and trial order
are immutable historical evidence. E3-v4 is a new confirmatory experiment.

## Feedback-off information firewall

Scenario qualification permits exactly `P0_F0` and `P1_F0`. The qualification harness
must reject `P0_F1`, `P1_F1`, `F1`, `iapf_dual`, or any other feedback-on request before
physical startup. No F1 qualification artifact may be created, opened for comparison,
or used in candidate selection. Candidate selection uses only the criteria below.

The first F1 execution for a frozen E3-v4 scene is reserved for the later formal
campaign, after registry, formal seeds, order, analysis contract, and preflight have
all been frozen. Historical E3-v3 F1 observations are not candidate-selection inputs.

## Qualification population and prevalence

A separate seed registry will freeze five qualification seeds before the candidate
grid is executed. These seeds are disjoint from E3-v3 formal seeds and from the future
E3-v4 formal seeds. For every physically evaluated candidate, all retained attempts
remain append-only pilot/calibration evidence.

The qualification population is the five registered seeds under each required F0
planning mode. Infrastructure failures remain retained and separately classified;
they do not become scientific outcomes, are never replaced by a different seed, and
cannot be hidden. A repeated execution after infrastructure repair, if needed, uses
the same seed and receives an explicit retry suffix while preserving the failed row.

The preregistered non-floor/non-ceiling interval is 20%--80%, inclusive: 1--4 of five
scientific-complete attempts must contain at least one registered hard-risk event.
This interval is used because five independent pilot seeds yield exact 20 percentage
point resolution while excluding both 0/5 and 5/5. It is fixed before new pilot
results. The selected candidate is the first candidate in the frozen search order
that passes every applicable rule; it is not the candidate with the largest effect.

## Common measured endpoints

For every attempt, retain nominal `predicted_d_min`, predicted hard-violation count,
actual `d_min` with pair and timestamp, hard-risk event count, pair-seconds exposure
`J_hard`, any-pair hard-risk duration, disturbance arm/application timing, affected-UAV
position/velocity response, mission completion, failsafe/contact evidence, and control
stability diagnostics. Metrics use the frozen E3-v3 definitions unless an explicitly
versioned instrumentation-only extractor adds provenance fields without changing a
production signal or endpoint definition.

A hard-risk event requires `actual_d_min < d_hard`; threshold equality is not an event.
Nonzero event prevalence must be accompanied by positive aggregate `J_hard` and at
least one event-attempt with positive `J_hard`.

## Family B gates

Each B candidate must pass all of the following under both P0_F0 and P1_F0.

1. **B-Q1 nominal safety.** The disturbance-free allocator prediction has zero hard
   violations and `predicted_d_min > 1.5 m`.
2. **B-Q2 planning is not the manipulation.** P0 and P1 have the same predicted-hard
   outcome (zero), no assignment-dependent structural conflict, and predicted minima
   that agree to numerical tolerance (`1e-9 m`).
3. **B-Q3 residual realized risk.** Event prevalence is 1--4/5 in each planning mode,
   and aggregate `J_hard > 0` in each planning mode.
4. **B-Q4 recoverability.** At least 4/5 scientific-complete attempts in each mode
   complete the registered mission without failsafe, loss of control, vehicle-ground
   contact, or controller-saturation-dominated termination. No attempt may have
   `actual_d_min <= 0.25 m` or a registered vehicle-vehicle contact. The 80% event
   ceiling is independently enforced.
5. **B-Q5 causal alignment.** At least one hard-risk event must involve the registered
   affected pair and begin no earlier than disturbance onset. A candidate whose only
   event is an unrelated nominal pair is rejected.

B-01 remains a horizontal/lateral physical mode and B-02 remains a vertical physical
mode. Search order is magnitude, duration, onset, then geometry. Analytic geometric
screening may reject a stimulus-only candidate without physical execution when the
force axis leaves an orthogonal pair separation greater than `d_hard`; that rejection,
calculation, and candidate identity must be retained. Geometry may be changed only
after all earlier applicable candidates in the frozen grid have failed or have such a
registered analytic impossibility certificate.

## Family C gates

Each C candidate must satisfy:

1. **C-Q1 P0 structural risk.** P0 has at least one predicted hard violation or a
   registry-defined predicted structural-risk endpoint.
2. **C-Q2 P1 structural mitigation.** For the identical ordered target set, P1 removes
   all predicted hard violations, has `predicted_d_min > 1.5 m`, and improves the
   structural endpoint relative to P0.
3. **C-Q3 residual persistence after planning.** P1_F0 has event prevalence 1--4/5,
   positive aggregate `J_hard`, and at least one affected-pair event beginning no
   earlier than disturbance onset.
4. **C-Q4 recoverability.** P1_F0 satisfies the B-Q4 stability/contact rules. P0_F0
   structural events are reported but are not used to tune disturbance strength.
5. **C-Q5 geometry preservation.** C-01 retains the v3 offset-trapezoid ordered target
   set and C-02 retains the v3 reversed-circle ordered target set unless a separately
   documented protocol inconsistency makes that impossible. The disturbance is
   directed at a nominally safe P1 pair using only prediction, never F1 response.

## Candidate progression and stopping

The exact finite candidate grid, geometry fallback variants, order, and qualification
seeds must be committed before the first new physical pilot. Every candidate receives
one of: `PASS`, `REJECT_FLOOR`, `REJECT_CEILING`, `REJECT_CAUSAL_ALIGNMENT`,
`REJECT_STABILITY`, `REJECT_NOMINAL_STRUCTURE`, `REJECT_ANALYTIC_IMPOSSIBILITY`, or
`INCOMPLETE_INFRASTRUCTURE`, with retained evidence and reason.

Work proceeds B-01, B-02, C-01, C-02, then A compatibility validation. Search stops at
the first full pass for each scene. It must not continue to seek a more favorable F1
effect. If the finite grid cannot produce qualified, recoverable residual risk without
changing production semantics, work stops with the required `BLOCKED` declaration.

## Family A compatibility-only validation

A-01 and A-02 retain their v3 initial geometry, ordered targets, duration, and zero
disturbance. Under the v4 tooling, validation checks registry legality, frozen motion
feasibility, zero-force loading parity, and preservation of the P0/P1 predicted
structural distinction. No redesign is permitted for aesthetics or effect size.

## Freeze gate

After all six scenes qualify, the report and candidate registry must enumerate every
accepted and rejected candidate without F1 results. Only then may new disjoint formal
seeds, a standalone deterministic 360-attempt order, an append-only journal contract,
the four-cell block analysis contract, and final preflight be frozen. Passing this
contract authorizes preparation only; it does not authorize a formal attempt.
