# C0-A calibration protocol: LADRC baseline and motion limits

Protocol version: `C0-A-prereg-v3`

Dataset class: `calibration`

Amendment class: `post-outcome metric-definition amendment`

Authorized: 2026-08-20 (Asia/Shanghai)

Algorithm baseline: `paper-algorithm-freeze-v1` at
`56e8d2c8e59fc3513769e21910b7a20b2b43088d`

Starting policy: `paper-current-v7`

Execution status at protocol freeze: **NOT STARTED**

## Amendment disclosure and preserved history

C0-A-prereg-v3 is a post-outcome metric-definition amendment.

The amendment is motivated solely by the construct-validity failure documented
in `metric_validity_audit/METRIC_VALIDITY_AUDIT.md`: the prereg-v2 raw,
mean-centered sign-change count is dominated by small-amplitude hover/control
chatter and does not validly implement an independent hard veto on physical
closed-loop oscillation. It is not motivated by candidate ranking or a desire
to increase the pass rate.

All v1 and v2 records remain historical evidence. In particular,
`C0-A-prereg-v2 = NO_ACCEPTABLE_CONFIGURATION`, its 300 formal trials, frozen
thresholds, results, manifests and audit artifacts are not reclassified,
deleted or overwritten.

V3-B is formally adopted. Relative to v2, v3 changes only:

1. raw mean-centered ZERO_CROSSINGS is recorded as a diagnostic and has no
   hard-veto, survivor, ranking, tie-break or final-selection authority;
2. v3 uses the new registered seeds below because v2 outcomes were inspected;
3. v3 trial IDs, schedule, manifests and artifacts use the v3 namespace.

No other acceptance threshold, selection priority, candidate, scenario,
algorithm, parameter range or failure semantic changes.

## Objective and prohibited changes

Select and, only after complete 1/4/8-UAV validation, freeze:

- LADRC baseline `omega_c` and `omega_o` for x/y/z;
- shared `v_limit`, `a_limit`, `j_limit` and `minimum_duration`;
- omega hard clamps, motion hard clamps and duplicated physical controller
  caps owned by C0-A.

The v2 objective, timing equation, execution path and frozen non-C0-A inputs
are incorporated unchanged. The campaign must use `motion_style=normal`,
`style_gain=1.0`, `s=1.0`, `control_mode=ladrc_acceleration`, explicit duration,
`avoidance_mode=iapf_dual`, `iapf_escape_mode=id_order`, 50 Hz control and
`b0=[1,1,1]`.

The campaign may not modify LADRC/LESO/LSEF, Minimum Jerk, the PX4 acceleration
path, Candidate LFS, Resolver, Geometry, Allocator, Execution Profile
mathematics, IAPF, Safety Compiler, motion-style mapping, any candidate range,
or any scenario definition.

## Fixed candidate stages

### A1 screening and confirmation

Use baseline vectors:

```text
omega_c baseline = [1.5, 1.5, 1.75]
omega_o baseline = [5.0, 5.0, 7.5]
omega_c multiplier = [0.67, 0.83, 1.00, 1.17, 1.33]
omega_o multiplier = [0.67, 0.83, 1.00, 1.17, 1.33]
```

Screen the complete 25-package Cartesian grid. Use motion limits `5/5/10`,
`minimum_duration=0.5 s`, and explicit `T=1.25*T_min`. The registered cases
are `C0A-S-HX-3:POS_X_3`, `C0A-S-HX-3:NEG_X_3`,
`C0A-S-VU-2:POS_Z_2`, and `C0A-S-DIAG-1:POS_X2_Y2_Z1` with all three
screening seeds: exactly `25 x 4 x 3 = 300` trials.

A candidate survives only if all 12 trials pass every v3 hard criterion.
Confirm the best five survivors (or all if fewer than five) over the complete
12-case single-UAV registry with all five confirmation seeds. If no candidate
survives a screening or confirmation gate, report
`NO_ACCEPTABLE_CONFIGURATION` and stop without changing the protocol.

### A2 screening and confirmation

Hold the A1 winner fixed. Evaluate the unchanged Cartesian grid:

```text
v/a/j packages =
  [3,3,6], [4,4,8], [5,5,10], [4,3,8], [5,4,8], [5,4,10]
minimum_duration = [0.50, 0.75, 1.00] s
duration stress multiplier = [1.00, 1.15, 1.30]
```

The duration multiplier is a test condition, not a candidate parameter.
Screen and confirm using exactly the v2 registered cases and staged counts.
Select only `v_limit`, `a_limit`, `j_limit`, and `minimum_duration`; do not
retune A1.

### A3 validation

Hold the A1/A2 winners fixed and validate the unchanged grid:

```text
omega envelope = [0.70,1.20], [0.70,1.25], [0.75,1.25], [0.75,1.30]
motion clamp multiplier = [1.00, 1.05, 1.10]
```

Run all 12 clamp pairs on the four registered A3 displacement cases with all
five confirmation seeds: 240 trials. Select the tightest eligible hard-passing
guard envelope under the unchanged v2 rule. A3 may not reopen A1 or A2.

### Scale validation

Validate the fixed A1/A2/A3 package in order on `C0A-M-1`, `C0A-M-4`, then
`C0A-M-8`, five trials each. All UAVs use the same +8 m lane displacement,
normal style, `s=1`, `ladrc_acceleration` and `T=1.25*T_min(D=8 m)`. This stage
does not tune parameters. Every trial at all three scales must pass before C0-A
can freeze.

## Seeds and immutable schedule

```text
screening seeds = [43001, 43002, 43003]
confirmation/A3/scale seeds = [43001, 43002, 43003, 43004, 43005]
trial ordering seed = 43999
```

Generate `trial_order_v3.json` before execution with one
`random.Random(43999)` stream. Shuffle each stage block in protocol order;
within scale validation retain M-1/M-4/M-8 condition order and shuffle only
the five seeds per condition. The immutable potential counts are:

| Stage | Potential entries |
|---|---:|
| A1_SCREENING | 300 |
| A1_CONFIRMATION | 300 maximum |
| A2_SCREENING | 1134 |
| A2_CONFIRMATION | 900 maximum |
| A3_VALIDATION | 240 |
| SCALE_VALIDATION | 15 |

Total potential entries: 2889. Confirmation activates only the registered top
five survivor rank slots; inactive slots are not trials and not failures.

## Metrics and v3 hard criteria

Record every v2 metric using the same implementation and windows. In
particular, continue to record the raw diagnostic field
`post_trajectory_zero_crossings_per_axis`, computed as sign changes after
centering each 5 s post-trajectory axis on its own sample mean.

`raw_zero_crossings` is diagnostic only. It does not decide PASS/FAIL,
survival, ranking, tie-break or final parameter selection.

Every applicable trial must satisfy all unchanged v2 hard criteria:

1. mission success; no PX4 failsafe, Offboard loss, unintended disarm, startup
   failure, command rejection, process crash or non-finite setpoint/observer;
2. terminal post-trajectory RMS `<=0.25 m`, per-axis peak-to-peak
   `<=0.60 m`, and last/first RMS ratio `<=1.0`;
3. analytic reference peaks within candidate v/a/j limits to tolerance `1e-9`
   and no profile clamp;
4. per-axis acceleration saturation ratio `<=2%` and achieved control-loop
   rate within `[47.5,52.5] Hz`;
5. absolute roll and pitch peaks each `<=30 deg`;
6. tracking RMSE `<=0.50 m`, maximum tracking error `<=1.00 m`, final error
   `<=0.40 m`;
7. finite command jerk P99.5 `<=1.5*j_limit`;
8. in multi-UAV validation, minimum separation `>=1.0 m`, no IAPF activation,
   and success for every UAV.

Infrastructure, timeout and missing-data failures retain the v2 fail-closed
denominator rules. A formal trial ID is never overwritten or replaced.

## Selection rule

Filter complete candidates by all v3 hard criteria, then apply the unchanged
v2 lexicographic priority after deleting ZERO_CROSSINGS from the stability
tuple:

1. lowest worst-case post RMS, then P2P, then last/first ratio, then largest
   safety/attitude margin;
2. lowest attitude and command-jerk ratios;
3. lowest worst-case and P95 acceleration saturation;
4. lowest worst-case/median tracking RMSE, maximum error and final error;
5. lower acceleration, jerk, velocity and omega bandwidth, then longer
   minimum duration and narrower eligible guard envelope;
6. lexicographically smallest serialized parameter tuple for an exact tie.

No weighted score, v2 ranking, crossing count, manual shortlist or
post-outcome threshold adjustment is permitted.

## Freeze authorization

Only a complete A1/A2/A3 and 1/4/8-UAV PASS authorizes a clean C0-A-owned
parameter update on `paper/calibration`, provenance and ledger update, policy
hash, and tag `paper-cal-C0A-v1`. Otherwise every C0-A row remains
`PROVISIONAL`, no tag is created, and `READY_FOR_C0_B=NO`.

C0-B is outside this protocol and must not start.
