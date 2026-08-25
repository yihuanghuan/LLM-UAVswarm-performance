# C0-E IAPF component freeze report

## Decision

C0-E is frozen and accepted. The final policy is threshold T1,
repulsion C_M025, and filter D_A020. It passed the unchanged production loader,
the locked 20-run confirmation, and the three deferred C0-D integration
smokes. The first integrated C0-D+C0-E canonical policy is
`paper-current-v10-c0-e-frozen`.

The actual starting commit for this continuation was
`be203117071dec3453e4c0ff5e536706de28101e`. The candidate was locked before
confirmation in `candidate_lock.yaml`; no parameter was retuned afterward.

## Runtime and scene gate

The minimum harness uses the production Candidate path:

`location_allocate.candidate_dispatch -> UAVFormationNode -> PaperMissionRuntime`

All paper trials ran with `ladrc_acceleration`. The five independent
calibration scenes passed their semantic gate (5/5): genuine closing behavior
for S1/S2, vertical relative motion for S3, dense local interaction for S4,
and positive separating behavior for S5. Every scored start was above the
frozen `d_hard=1.50 m` threshold. Staging was excluded from metrics.

## Lexicographic calibration

Selection order was fixed as safety violation, mission failure, trajectory
deviation, then tracking cost. No weighted score was used.

### Stage B: threshold and hysteresis

| Candidate | enter / exit (m) | Valid trials | Hard violations | Mission failures | Integrated position modulation | Integrated acceleration modulation |
|---|---:|---:|---:|---:|---:|---:|
| T1 | 1.60 / 1.70 | 8 | 0 | 0 | 0.450559 | 2.703477 |
| T2 | 1.65 / 1.75 | 8 | 0 | 0 | 0.854515 | 5.127237 |
| T3 | 1.65 / 1.80 | 5 | 1 | 0 | 0.302287 | 1.813794 |
| T4 | 1.70 / 1.80 | 8 | 0 | 0 | 1.532334 | 9.194172 |

T3 was eliminated by its S1 safety violation (`min distance=1.496881 m`).
Among safe, mission-successful candidates, T1 had the least trajectory
deviation and was locked for later stages. Two incomplete infrastructure
attempts are retained separately in `screening_excluded_attempts.csv` and do
not participate in this table or selection.

### Stage C: repulsion mapping

Threshold T1 remained locked while `repulsion_base=1.00` and only the
preregistered margin varied.

| Candidate | margin | Valid trials | Hard violations | Mission failures | Integrated position modulation | Integrated acceleration modulation |
|---|---:|---:|---:|---:|---:|---:|
| C_M0125 | 0.125 | 6 | 1 | 0 | 0.579297 | 3.475895 |
| C_M025 | 0.25 | 6 | 0 | 0 | 0.612860 | 3.677270 |
| C_M050 | 0.50 | 6 | 0 | 0 | 0.696140 | 4.176949 |

C_M0125 was eliminated by its S1/s=2 violation
(`min distance=1.497651 m`). C_M025 and C_M050 were safe and mission
successful; C_M025 had the lower trajectory deviation and was locked.

### Stage D: filter

Threshold T1 and repulsion C_M025 remained locked.

| Candidate | alpha | Valid trials | Hard violations | Mission failures | Integrated position modulation | Integrated acceleration modulation |
|---|---:|---:|---:|---:|---:|---:|
| D_A010 | 0.10 | 6 | 0 | 0 | 0.629183 | 3.775325 |
| D_A020 | 0.20 | 6 | 0 | 0 | 0.608889 | 3.653435 |
| D_A030 | 0.30 | 6 | 0 | 0 | 0.625581 | 3.753555 |

All three candidates were safe and mission successful. D_A020 had the lowest
integrated position and acceleration modulation and was locked.

## Remaining C0-E numerics and clamps

Minimum-change validation retained the inherited numerics unchanged:
repulsion gain 25.0, `id_order` escape mode, escape gain 0.05, distance epsilon
0.10 m, position modulation gain/limit 0.05/0.50 m, and acceleration
modulation gain/limit 0.30/2.00 m/s^2. There was no persistent stall, chatter,
clamp activity, or acceleration saturation requiring another allowed change.

Coverage clamps derived over `s in [1,2]` are:

- `iapf_enter_min=1.60 m`
- `iapf_enter_max=1.7000000000000002 m` (exact binary-expression coverage)
- `iapf_exit_max=1.90 m`
- `iapf_repulsion_max=1.25`

These bounds passed the unchanged loader; no inequality was weakened.

## Locked confirmation

The exact locked policy SHA-256 was
`fbd2747711ffd05c70541c69af17818030f74f6cbdbd97f3349afa66310d62e7`.
All 20 required trials passed (S1--S5 x s={1,2} x two cold starts):

- hard violations/exposure: 0 / 0.0 s
- mission failures, stalls, timeouts: 0, 0, 0
- chatter toggles and clamp activity: 0, 0
- minimum pairwise distance: 1.503510 m
- maximum tracking RMSE: 0.073350 m
- maximum final error: 0.102631 m

The raw confirmation manifests retain the actually recorded seed label and
the README explains its non-operational difference from the preregistered
confirmation label. No confirmation data was used for retuning.

## Deferred C0-D integration closure

After confirmation, exactly three locked-policy integration smokes ran:

| Smoke | UAVs | s | Result |
|---|---:|---:|---|
| compact | 8 | 1 | PASS |
| crossing-prone | 8 | 1 | PASS |
| normal/spacious | 8 | 2 | PASS |

Each used authoritative C0-D (`d_hard=1.50 m`, `d_plan_base=1.80 m`,
`s_min=1`, `s_max=2`), the locked C0-E policy, Candidate dispatch,
PaperMissionRuntime readiness, and LADRC acceleration control. The old v9
smokes are not counted as these results.

## Frozen upstream invariants

C0-A motion limits, C0-B freshness predicates, and C0-C geometry are unchanged.
C0-D is exactly the authoritative hard-anchored linear mapping
`d_plan(s)=1.50+0.30*s`. In particular, C0-B remains
`state_timeout=0.02208 s`, `snapshot_skew=0.022043 s`,
`fresh_state_wait_timeout=0.010 s`, and
`allow_receive_time_fallback=false`.

The C0-C experimental prewarm helper is not an operational dependency. C0-F
values remain provisional. C0-F and formal E1--E6 experiments were not
started.
