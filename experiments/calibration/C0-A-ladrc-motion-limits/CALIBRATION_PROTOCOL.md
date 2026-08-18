# C0-A calibration protocol: LADRC baseline and motion limits

Protocol version: `C0-A-prereg-v1`

Dataset class: `calibration`

Pre-registered: 2026-08-18 (Asia/Shanghai)

Algorithm baseline: `paper-algorithm-freeze-v1` at
`56e8d2c8e59fc3513769e21910b7a20b2b43088d`

Starting policy: `paper-current-v7`

Execution status: **NOT STARTED**

This file defines the experiment before any C0-A trial is run or inspected.
Changing its sweep, scenarios, metrics, acceptance thresholds or selection rule
after execution begins requires a new protocol version plus a dated deviation
record; the original protocol must remain in history.

## Objective

Determine and freeze one dynamically safe baseline package for explicit PX4
acceleration-level Offboard execution:

- LADRC baseline `omega_c` and `omega_o` for x/y/z;
- shared `v_limit`, `a_limit`, and `j_limit`;
- minimum executable duration;
- LADRC/profile omega and motion hard clamps;
- duplicated physical controller caps listed as C0-A-owned in the parameter
  ledger.

C0-A establishes the unscaled baseline with `motion_style=normal`, for which
the architecture fixes `style_gain=1.0`. It uses explicit durations so the
provisional auto-duration style factors do not affect selection.

The current timing feasibility calculation is frozen as:

```text
T_min(d) = max(
  minimum_duration,
  1.875 d / v_limit,
  sqrt((10/sqrt(3)) d / a_limit),
  cbrt(60 d / j_limit)
)
```

The C++ reference remains the zero-end-velocity/acceleration quintic
Minimum-Jerk trajectory. LADRC consumes position, velocity and acceleration
references, then publishes its finite ENU acceleration command through PX4
`TrajectorySetpoint.acceleration` after ENU-to-NED conversion. Every C0-A run
must therefore pass `control_mode:=ladrc_acceleration` explicitly; the launch
default `px4_position` is a comparison baseline and is invalid for C0-A.

## Frozen inputs and prohibited changes

C0-A must verify the algorithm-freeze manifest before execution. It may not
modify:

- Candidate LFS, schema, prompt or parser;
- schema/static/runtime validation;
- deterministic resolver, mission graph or transition semantics;
- formation geometry equations or qualitative label semantics;
- allocator objective, search, aggregation or closest-approach mathematics;
- Minimum-Jerk mathematics or boundary conditions;
- Execution Profile mathematical structure or normal identity gain;
- LADRC/LESO/LSEF mathematics;
- IAPF formula, closing-speed gate, hysteresis, escape logic, modes or any
  C0-E-owned IAPF number;
- Safety Compiler structure, the meaning of `s`, or any C0-D-owned safety
  number;
- motion-style mapping or C0-F-owned style/auto-duration numbers;
- state-freshness, geometry, allocator-numerical, safety or IAPF parameters.

The controller rate (`50 Hz`), `b0_x/y/z=1.0`, startup state-machine values,
takeoff acceptance and hover-completion thresholds are frozen campaign inputs,
not C0-A sweep variables.

Use the frozen current values for all non-C0-A inputs. Use `s=1.0`,
`avoidance_mode=iapf_dual`, `iapf_escape_mode=id_order`, no injected wind or
disturbance, and collision-free lanes. An IAPF activation is recorded and
fails the intended no-interference scenario; it is not grounds to retune IAPF.

## Candidate sweep

The sweep is staged to avoid an unbounded full cross-product, but every stage
and survivor rule is fixed here. No range may be narrowed or expanded after
viewing C0-A outcomes.

### Stage A1 — controller baseline screening

Use the current motion limits `5/5/10`, `minimum_duration=0.5 s`, normal style,
and explicit `T=1.25*T_min`. Evaluate the Cartesian grid:

```text
omega_c baseline vector: [1.5, 1.5, 1.75]
omega_o baseline vector: [5.0, 5.0, 7.5]
omega_c vector multiplier: [0.67, 0.83, 1.00, 1.17, 1.33]
omega_o vector multiplier: [0.67, 0.83, 1.00, 1.17, 1.33]
```

This is a 25-package Cartesian grid. The independent vector multipliers retain
the current x/y symmetry and z-axis anisotropy without searching thousands of
per-axis combinations. `control_frequency=50 Hz` and `b0_x/y/z=1.0` remain
fixed.

Screen on scenarios `C0A-S-HX-3`, `C0A-S-VU-2`, and `C0A-S-DIAG-1` with the
first three registered seeds. A candidate survives only if all hard acceptance
criteria pass in all nine trials. Rank survivors using the selection rule
below and carry the best five distinct baseline packages to A1 confirmation on
the complete single-UAV scenario set with all five seeds. If fewer than five
survive, confirm every survivor; if none survive, C0-A reports
`NO_ACCEPTABLE_CONFIGURATION` and stops without changing parameters.

### Stage A2 — motion envelope and minimum duration

Hold the winning A1 baseline fixed. Evaluate the Cartesian grid:

```text
v/a/j package (m/s, m/s^2, m/s^3):
  [3.0, 3.0, 6.0]
  [4.0, 4.0, 8.0]
  [5.0, 5.0, 10.0]
  [4.0, 3.0, 8.0]
  [5.0, 4.0, 8.0]
  [5.0, 4.0, 10.0]
minimum_duration_s: [0.50, 0.75, 1.00]
explicit_duration_multiplier: [1.00, 1.15, 1.30]
```

For each displacement, compute `T_min` with the candidate envelope, then use
the registered explicit multiplier. Do not let auto style timing enter this
stage. Screen all candidates on `C0A-S-HX-3`, `C0A-S-HX-6`, `C0A-S-VU-2`,
`C0A-S-VD-1`, and `C0A-S-DIAG-2` with the first three seeds. Confirm the best
five hard-passing envelopes over the complete single-UAV set and all five
seeds. Apply the same zero-survivor stop rule as A1.

### Stage A3 — hard clamps and duplicated controller values

This stage does not retune the A1/A2 winner. It validates the smallest guard
envelope that covers the selected baseline, observed repeat variability and
the predeclared future style-gain admissible interval `[0.75, 1.20]`:

```text
omega envelope candidates (baseline multipliers):
  [0.70, 1.20], [0.70, 1.25], [0.75, 1.25], [0.75, 1.30]
motion clamp multiplier candidates relative to selected v/a/j:
  [1.00, 1.05, 1.10]
```

Select the tightest candidate covering `[0.75,1.20]` and every accepted
profile without runtime clamping. Motion hard clamps default to exactly the
selected shared limits; use `1.05` or `1.10` only if quantization/transport
roundoff produces a false clamp, and document that evidence. Reconcile paper
policy limits with controller YAML (`max_velocity`, per-axis acceleration
caps); no duplicated runtime value may contradict the selected envelope.

The frozen hover/takeoff envelope is used for mission acceptance but is never
changed. If it prevents every otherwise stable candidate from completing,
C0-A reports `NO_ACCEPTABLE_CONFIGURATION` rather than opening an unregistered
sweep.

## Calibration scenarios

All scenario IDs below are calibration-only and must never be reused as final
paper evaluation scenarios. Coordinates are world ENU metres and must remain
inside the current workspace AABB. The nominal start after takeoff is
`[0, 0, 3]`; reset simulation state before every trial.

| ID | UAVs | Displacement(s) | Purpose |
|---|---:|---|---|
| `C0A-S-HX-1` | 1 | `[+1,0,0]`, `[-1,0,0]` | short horizontal/reversal |
| `C0A-S-HX-3` | 1 | `[+3,0,0]`, `[-3,0,0]` | medium horizontal |
| `C0A-S-HX-6` | 1 | `[+6,0,0]`, `[-6,0,0]` | long horizontal |
| `C0A-S-HY-3` | 1 | `[0,+3,0]`, `[0,-3,0]` | orthogonal horizontal |
| `C0A-S-VU-2` | 1 | `[0,0,+2]` | climb |
| `C0A-S-VD-1` | 1 | `[0,0,-1]` | descent with altitude margin |
| `C0A-S-DIAG-1` | 1 | `[+2,+2,+1]` | moderate 3-D diagonal |
| `C0A-S-DIAG-2` | 1 | `[-3,+2,+2]` | mixed-sign 3-D diagonal |
| `C0A-M-4` | 4 | starts `[-4,3i,3]`, targets `[+4,3i,3]`, `i=1..4` | four-UAV scheduling/control scaling in separated parallel lanes |
| `C0A-M-8` | 8 | starts `[-4,3i,3]`, targets `[+4,3i,3]`, `i=1..8` | eight-UAV scheduling/control scaling in separated parallel lanes |

Each signed displacement is a separate trial. After A1/A2 selection, validate
the single-UAV winner at 1 UAV, then `C0A-M-4`, then `C0A-M-8`. Scale
validation uses the same per-UAV displacement, explicit duration and frozen
parameters; it is validation, not another parameter-selection stage. A 4- or
8-UAV failure prevents freezing and cannot be used to reopen the sweep.

No scenario from a later formal registry may be substituted. If a future
formal scenario is accidentally run or inspected during C0-A, it must be
permanently reclassified as calibration data.

## Repetitions, seeds and ordering

- Screening stages: three repetitions, seeds `41001`, `41002`, `41003`.
- Confirmation and 1/4/8-UAV validation: five repetitions, seeds `41001`,
  `41002`, `41003`, `41004`, `41005`.
- Set the PX4/Gazebo/randomized scenario seed wherever supported and record
  each effective seed. If the simulator component is deterministic or ignores
  a seed, still retain the repetition and mark that component
  `seed_not_supported`; repetitions capture reset and scheduling variability.
- Generate a deterministic randomized trial order from seed `41999`, save the
  resulting order before execution, and never reorder after seeing results.
- Start every trial from a clean simulator/PX4/controller process and the
  registered initial state. Do not reuse observer or filter state.

## Metrics and computation

Compute per-UAV values first, then per-trial worst case and aggregate
distributions. Preserve the raw time series needed to reproduce every metric.

| Metric | Definition |
|---|---|
| Tracking RMSE | 3-D norm error between measured position and the nominal Minimum-Jerk reference over `[0,T]`; also report per axis. |
| Maximum tracking error | Maximum 3-D nominal-reference error over `[0,T]`. |
| Final error | Target-to-measured 3-D error at first stable-hover confirmation, or at timeout for failures. |
| Peak velocity | Peak measured 3-D speed and analytic/reference peak (`1.875 d/T`). |
| Peak acceleration | Peak LADRC command and finite-difference measured acceleration; report per axis and norm. |
| Peak jerk/reference jerk | Peak finite-difference LADRC-command jerk and analytic reference peak (`60d/T^3`); also report 99.5th percentile command jerk to expose isolated differentiation spikes. |
| Acceleration saturation ratio | Fraction of active trajectory samples at the applied acceleration limit (within 1% of the limit), per axis and any-axis. |
| Roll/pitch peak | Maximum absolute PX4 roll and pitch during active trajectory plus 2 s settling. |
| Mission success | Startup reaches READY, command is accepted, trajectory finishes and stable hover is confirmed before timeout. |
| Stability/oscillation indicator | Post-trajectory 5 s position-error RMS, peak-to-peak error, zero-crossing count per axis after demeaning, and ratio of RMS in the last 2 s to the first 2 s. |
| PX4 failsafe | Any asserted failsafe, loss of Offboard/armed state, rejected/non-finite setpoint or startup FAILED transition. |

Also record actual duration, arrival-time error, control-loop achieved rate,
missed/deadline samples, IAPF activation, minimum inter-UAV distance, profile
clamp flags, observer states, process exit status and resource utilization.

## Hard acceptance criteria

A candidate passes only if every applicable confirmation and scale-validation
trial satisfies all of the following:

1. `mission_success=true`; zero PX4 failsafes, non-finite values, process
   crashes, command rejections, unintended disarms or Offboard losses.
2. No persistent/growing oscillation: post-trajectory RMS error `<=0.25 m`,
   peak-to-peak error `<=0.60 m`, last/first 2 s RMS ratio `<=1.0`, and no more
   than six demeaned error zero crossings on any axis in the 5 s window.
3. Analytic reference peaks do not exceed selected `v/a/j` limits (numerical
   tolerance `1e-9`), and applied profiles incur no omega/motion hard clamp.
4. Acceleration saturation ratio `<=2%` on every axis and trial; measured
   control-loop rate stays within `±5%` of its candidate value.
5. Peak absolute roll and pitch are each `<=30 deg`.
6. Tracking RMSE `<=0.50 m`, maximum nominal-reference tracking error
   `<=1.00 m`, and final error `<=0.40 m`.
7. In multi-UAV validation, minimum separation remains `>=d_hard=1.0 m`, no
   registered lane produces an IAPF activation, and all UAVs succeed.

Peak command jerk is reported and ranked but is not alone a hard failure
because the frozen feedback controller can create non-reference transients.
Any non-finite jerk or a 99.5th-percentile command jerk above `1.5*j_limit` is
a hard failure. These thresholds may not be relaxed after results are viewed.

## Selection and tie-breaking rule

Filter candidates by the hard acceptance criteria. Rank only complete,
hard-passing candidates in this lexicographic order:

1. stability and safety: lowest worst-case post-trajectory oscillation tuple,
   then largest minimum safety/attitude margin;
2. dynamic feasibility: lowest worst-case roll/pitch and command-jerk ratios;
3. low saturation: lowest worst-case acceleration saturation ratio, followed
   by lower 95th-percentile ratio;
4. tracking: lowest worst-case RMSE, then aggregate median RMSE, maximum error
   and final error;
5. conservative/simple package: lower `a_limit`, lower `j_limit`, lower
   `v_limit`, lower omega bandwidth norm, longer minimum duration, then
   narrower guard envelope, in that order;
6. if still exactly tied at stored metric precision, choose the
   lexicographically smallest serialized parameter tuple and report the tie.

No weighted score may replace this ordering. A configuration near an
instability or attitude/saturation boundary cannot win merely by having lower
RMSE. If no candidate passes, report failure and leave every C0-A ledger row
`PROVISIONAL`; do not create an unregistered follow-up sweep.

## Failure, timeout and missing-data handling

- A trial-level wall-clock timeout is `120 s` from process-ready start.
- Startup must reach READY within the frozen `60 s` startup timeout.
- After command acceptance, stable hover must occur by
  `max(T + 20 s, 3T)`. The earliest applicable deadline causes failure.
- A crash, startup failure, PX4 failsafe, missing mandatory topic, corrupt bag,
  rejected profile, non-finite metric, unintended IAPF activation or metric
  extraction error is a failed trial, not missing-at-random data.
- Failed and timed-out trials remain in `raw/` and in aggregate denominators.
  They are never deleted or replaced. A diagnostic rerun receives a new trial
  ID and cannot replace the original selection record.
- If infrastructure failure affects all candidates in the same scheduled
  block, stop the campaign, preserve the block, and issue a protocol deviation
  before resuming. Do not label candidate-specific failures as infrastructure.
- Partial candidate results cannot be ranked. A candidate with any failed
  required repetition fails hard acceptance.

## Required outputs

At completion, the C0-A branch must contain or reference immutable storage for:

```text
experiments/calibration/C0-A-ladrc-motion-limits/
├── CALIBRATION_PROTOCOL.md
├── CALIBRATION_RESULT.md
├── manifest.json
├── raw/
├── metrics/
├── figures/
└── scripts/
```

`manifest.json` must include protocol hash, algorithm tag/commit, C0 branch and
commit, dirty-worktree flag, policy/config hashes, PX4/ROS/Gazebo versions,
host/environment details, scenario-registry hash, complete scheduled trial
list, seeds, command lines, start/end timestamps, output hashes and failure
status. `CALIBRATION_RESULT.md` must apply the selection rule without changing
it, list all rejected candidates and failures, and identify the one selected
package or `NO_ACCEPTABLE_CONFIGURATION`.

Only a clean parameter/provenance commit may return to `paper/calibration`.
Raw data, figures, sweep/debug code and calibration-only launch changes remain
on `cal/C0-A-ladrc-motion-limits` or immutable artifact storage. Successful
freeze updates the owned ledger rows and creates a new immutable checkpoint
tag; this protocol itself does not freeze any provisional value.
