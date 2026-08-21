# C0-A-prereg-v3 DRAFT

> **DRAFT ONLY — NOT PREREGISTERED, NOT EXECUTABLE, NO TRIALS STARTED**

C0-A-prereg-v3 is a post-outcome metric-definition amendment.

The amendment is motivated by a documented construct-validity problem in
the prereg-v2 raw zero-crossing metric, not by candidate ranking or the desire
to increase the pass rate.

All v2 trials and the v2 NO_ACCEPTABLE_CONFIGURATION result remain preserved.

## Status and exclusions

- Draft status: `AWAITING_REVIEW`
- Formal v3 trials started: `false`
- v3 trial count: `0`
- v3 schedule: `NOT GENERATED`
- Parameter candidate changes: `NONE`
- Algorithm changes: `NONE`
- Other hard-criterion changes: `NONE`
- C0-A parameter freeze: `NONE`
- C0-B activation: `NO`

This draft cannot authorize a campaign.  It must first receive an independent
noise-floor input, a choice between V3-A and V3-B, a complete protocol audit,
and explicit approval.

## Preserved v2 history

`C0-A-prereg-v2` remains formally concluded as
`NO_ACCEPTABLE_CONFIGURATION`: 300/300 A1 screening trials, 26 trial passes,
274 trial failures and zero survivors.  No v2 record, threshold, selection
decision, or denominator is reinterpreted by this draft.

The diagnostic evidence and Outcome B rationale are in
`metric_validity_audit/METRIC_VALIDITY_AUDIT.md`.

## Scope of the possible amendment

Only the operational definition and role of terminal zero crossings is under
review.  The following remain unchanged unless a separate, explicit protocol
amendment is later justified:

- post-window RMS `<=0.25 m`;
- peak-to-peak `<=0.60 m`;
- last/first RMS ratio `<=1.0`;
- tracking RMSE, maximum error and final error thresholds;
- command jerk, saturation, attitude, rate and mission/safety criteria;
- all A1 candidates, scenarios, seeds and selection rules;
- LADRC, Minimum Jerk, IAPF, compiler, allocator, LFS and PX4 control logic.

## Candidate-independent measurement-floor prerequisite

No numeric deadband is proposed from the v2 candidate outcomes.  Before this
draft can become a preregistration, conduct a separate
`calibration_diagnostic` stationary-hover characterization:

1. Use one fixed development baseline declared before data collection.
2. Issue no displacement task; hold a fixed target in the calibration world.
3. Use independently declared reset seeds and trial IDs with
   `diagnostic=true`; they cannot replace any v2 trial.
4. Record position/odometry and control debug at the production rates over a
   fixed terminal window long enough to characterize low-frequency drift.
5. Estimate per-axis measurement resolution, stationary residual distribution,
   P99 absolute hover-noise excursion and timestamp quality.
6. Define each physical deadband `delta_a` from measurement resolution + the
   independently measured P99 noise excursion + a predeclared engineering
   margin.
7. Freeze the formula and numeric `delta_a` before generating a v3 candidate
   schedule.  Do not inspect how any delta changes v2 survivor counts.

The v2 terminal windows may motivate this characterization but may not set the
deadband because they contain the candidate responses under audit.

## Proposed target-relative hysteretic crossing primitive

For axis `a`, use target-relative error without centering on the evaluated
window:

```text
e_a(t) = p_a(t) - p_a,target
```

Given an independently established `delta_a > 0`, define a three-region state:

```text
positive: e_a > +delta_a
neutral:  |e_a| <= delta_a
negative: e_a < -delta_a
```

An effective crossing is counted only after the state completes a transition
from positive to negative or negative to positive.  Samples in the neutral
region neither create a crossing nor erase the last non-neutral state.  This
implements a physical amplitude requirement and hysteresis; it does not simply
raise the allowed raw crossing count.

If the independent hover study shows that raw position noise remains material
outside this band, a fixed low-pass step may precede the state machine.  Its
filter type, sample-rate treatment, cutoff/alpha, initialization and edge
handling must be fixed from the independent noise characterization—not from
candidate pass rates.

## V3-A — deadbanded crossing remains a hard criterion

Under V3-A, the target-relative hysteretic count remains a hard stability
criterion.  The permitted count and per-axis aggregation must be justified in
physical terms and frozen before v3 data collection.  Retaining the v2 count
limit may be considered only after verifying that the new event represents a
full physically meaningful excursion; no outcome-driven search over count
limits is allowed.

Advantages:

- preserves an explicit veto on repeated, meaningful oscillations;
- adds amplitude semantics absent from v2;
- remains directly auditable on a trace.

Risks:

- a count threshold still compresses amplitude, damping and frequency into one
  integer;
- short windows yield coarse counts;
- threshold justification remains a separate construct-validity obligation.

## V3-B — crossing is secondary stability evidence

Under V3-B, hard stability continues to be determined primarily by the
unchanged post RMS, P2P and last/first ratio criteria.  The target-relative
deadbanded/hysteretic crossing count is retained as a reported secondary
metric and deterministic tie-break/diagnostic, not an independent hard veto.

Advantages:

- RMS and P2P encode physical amplitude, while last/first encodes growth;
- avoids allowing arbitrarily small high-frequency sign chatter to dominate
  the hard decision;
- still exposes repeated meaningful excursions for review.

Risks:

- a genuine bounded limit cycle might satisfy the existing amplitude limits;
- removing an independent crossing veto requires an explicit scientific
  rationale and review, not merely better pass rates.

## Draft assessment

V3-B is more directly aligned with the physical construct “bounded and
non-growing terminal response,” while V3-A offers a conservative extra veto
after the crossing primitive has physical amplitude semantics.  This draft
does **not** choose between them.  Selection must be made before v3 execution
using the intended physical construct and independent hover characterization,
never by comparing survivor counts.

## Conditions required before any v3 execution

- independent hover/noise characterization completed and archived;
- numeric deadband/filter definition frozen from that characterization;
- V3-A or V3-B explicitly selected and justified;
- full v3 protocol and deterministic schedule generated;
- algorithm-freeze and ownership gates PASS;
- executable-protocol audit reports zero ambiguity;
- explicit user review and authorization.

Until then:

```text
READY_TO_RUN_C0_A_V3 = NO
READY_FOR_C0_B = NO
```
