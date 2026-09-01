# E3-v4 Family-B staging-gate correction

Status: `FROZEN_BEFORE_FURTHER_RETRY`

This record concerns experiment-only verification. It does not alter a scene,
candidate grid, seed, planner, controller, IAPF parameter, safety threshold, or
production runtime semantic.

The original two B-02 seed-69912 records showed a wrong realized staging
geometry that the first qualification harness did not fail closed on. Commit
`f5bf61b893aeef85a5c0fa5911444c0e8df75af1` therefore added an independent
global-position gate before interaction execution.

The first append-only retry of `B02-REF-O1p5 / P0_F0 / 69912` was retained as
an infrastructure failure. Its final recorded global positions were all within
approximately 0.02 m of the six registered staging targets. The added gate
nevertheless rejected the stage because it also compared the instantaneous,
unfiltered `/swarm_state` twist against 0.30 m/s. Those raw values ranged from
approximately 0.29 to 0.41 m/s. This duplicates neither the signal nor the
hysteresis used by the frozen controller's authoritative `is_hover_stable`
state: the controller uses filtered position-derived velocity with frozen
0.30 m/s enter and 0.40 m/s exit thresholds.

The corrected experiment-only gate therefore requires, continuously for the
already registered two seconds:

1. every UAV's independently recorded global position is within 0.30 m of its
   registered staging target;
2. every frozen controller reports the matching staging mission,
   `is_hover_stable=true`, and `failsafe=false`.

Raw global speeds remain recorded in the stage result for audit, but are not
used as a second, semantically inconsistent controller-stability test. The
failed retry remains immutable. Subsequent retries use the same registered
candidate, condition, and seed and are append-only.

F1 attempts: 0. Formal attempts: 0.
