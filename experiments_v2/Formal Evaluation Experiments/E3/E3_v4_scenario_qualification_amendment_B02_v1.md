# E3-v4 scenario qualification amendment — B-02 v1

```yaml
classification: qualification_protocol_amendment_after_preregistered_finite_grid_exhaustion

reason: >-
  B-02 v1 disturbance-only grid exhausted without valid target-pair residual risk;
  analytic geometry review shows that vertical-risk assay requires a horizontal
  projection below d_hard while preserving nominal 3-D safety.

production_method_changed: false
F1_used_for_selection: false
formal_results_generated: false
```

This is the single human-authorized versioned B-02 qualification amendment. It does
not delete, overwrite, or weaken the original qualification contract or the blocked
Family-B report. It adds exactly one finite external-condition search for B-02.
B-01 is frozen and will not be rerun or retuned. Production code, policy, controller,
allocator, IAPF, thresholds, execution profile, and runtime semantics remain frozen.

## Analytic geometry family

For `h in {1.0, 1.1, 1.2} m`, the registered affected-pair vertical separation is

\[
z_{sep}(h)=\sqrt{2.0^2-h^2}.
\]

With vertical midpoint `z_c=3.0 m`, UAV2 and UAV3 are placed at y coordinates
`-h/2,+h/2` and z coordinates `3-z_sep/2,3+z_sep/2`. UAV1/UAV4 are at
`[0,-4,3]` and `[0,+4,3]`. Every target is the corresponding initial point plus
`[8,0,0] m`. Consequently `d_xy,23=h<1.5 m` while nominal `d_23=2.0 m`.
Pure vertical compression can therefore enter the hard-risk region without inserting
nominal structural risk.

The exact coordinates and their full precision are frozen in
`E3_v4_B02_amendment_v1_grid.yaml`. No coordinate may change in response to a pilot.
Before physical execution, both production planning modes must select a nominally
safe assignment with zero predicted hard violations, predicted minimum 2.0 m, and
frozen motion-limit feasibility. Any failure is
`BLOCKED_ANALYTIC_TEMPLATE_INCOMPATIBILITY`.

## Finite 9-cell screening grid

The only disturbance profiles are pure world-z inward rectangular forces on UAV2 and
UAV3, zero torque, onset 2.0 s, and duration 1.5 s:

| Profile | Per-UAV magnitude | Per-UAV impulse |
|---|---:|---:|
| F2p0 | 2.0 N | 3.0 N·s |
| F3p0 | 3.0 N | 4.5 N·s |
| F4p0 | 4.0 N | 6.0 N·s |

The Cartesian product of three geometries and three profiles is exactly nine stable
candidate IDs. No other magnitude, duration, onset, or geometry is permitted.
Each cell uses both P0_F0/P1_F0 and the five existing screening seeds, for at most 90
scientific screening attempts. All attempts are append-only. Infrastructure retries
retain the same seed and use explicit retry suffixes.

## Gates and selection

Both planning modes must have zero predicted hard violations and no structural-risk
distinction. In each mode, event prevalence must be 1–4/5 with positive `J_hard`.
Every qualifying event must involve pair 2–3 and begin after disturbance onset.
Recoverability, contact, failsafe, `d_min > 0.25 m`, mission stability, and coverage
rules remain those of the original contract.

All nine cells are screened before selection. Among candidates passing every gate,
selection is lexicographic: minimum force impulse, then maximum h, then lexical ID.
No F1 observation is permitted.

## Unseen F0-only holdout

The five holdout seeds are frozen before screening in
`E3_v4_B02_holdout_qualification_seeds.yaml`. They are disjoint from screening and
E3-v3 formal seeds and are never formal-eligible. The harness must refuse them until
a separately committed screening-selection freeze names exactly one candidate.
That candidate then receives ten F0-only holdout attempts.

The holdout must independently pass the same prevalence, exposure, causal-pair, and
recoverability gates. Failure yields `BLOCKED_AT_E3_B02_HOLDOUT_FAILURE`; no second
screening candidate may be selected. If no screening cell passes, the outcome is
`BLOCKED_AT_E3_B02_AMENDMENT_V1_EXHAUSTED`. No second amendment is authorized.
