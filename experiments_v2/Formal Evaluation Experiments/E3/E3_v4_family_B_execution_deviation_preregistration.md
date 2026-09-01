# E3-v4 Family-B deterministic execution-deviation preregistration

Status: `FROZEN_BEFORE_PHYSICAL_SCREENING`

This document and
`E3_v4_family_B_execution_deviation_grid.yaml` preregister the complete finite
Family-B screening before any attempt using these mechanisms.  They supersede
the wrench assay only for future E3-v4 design.  All wrench-path evidence remains
immutable pilot history.

## Scientific manipulations

### B-01: execution timing deviation

Four UAVs execute parallel 8 m translations.  Pair 2-3 is nominally separated
by exactly 2.0 m: `sqrt(3) m` longitudinally and `1.0 m` laterally.  UAV3 is the
leading member.  Allocation and profile compilation complete before dispatch.
UAVs 1, 2, and 4 receive their committed commands at the reference command
time; UAV3 receives the same committed target and profile after a registered
0.4, 0.5, or 0.6 s ROS-time delay.  No target ownership or planner input changes.

The grid brackets the legacy 0.6 s prior while preferring smaller deviations.
The ideal minimum-jerk execution counterfactual predicts pair-2-3 minima of
1.402455, 1.278746, and 1.172025 m respectively.  These values justify assay
sensitivity but are not physical qualification results.

### B-02: execution reference deviation

Six UAVs contract from a 5.0 m circle to a 2.4 m circle with identity ownership.
At 3.5 s after the accepted nominal command, UAV3 receives a new validated
execution command.  Its endpoint is the original committed minimum-jerk
reference at 6.5 s plus a registered world-x offset.  At 6.5 s it receives a
new validated reset command to the original committed target.  The offset grid
is 1.2, 1.5, and 1.8 m; the interval is fixed at 3.0 s and the overall mission at
10.0 s.

This is an external reference-command deviation through the already frozen
`UAVExecutionCommand` interface.  It is not the removed legacy dynamic
controller-parameter hook.  The 10 s duration and 3 s interval make both the
bias and reset minimum-jerk segments comply analytically with the frozen 5 m/s,
5 m/s2, and 10 m/s3 component limits.  Ideal pair-2-3 endpoint distances are
1.811440, 1.511440, and 1.211440 m; the finite grid therefore includes a likely
floor cell, a threshold-bracketing cell, and a non-catastrophic risk cell.

## Offline planning gate

The frozen-policy audit is
`E3_v4_family_B_execution_deviation_offline_audit.json`.  It records:

- B-01 P0/P1 assignments `[0,1,2,3]`, predicted hard violations 0, and
  predicted `d_min = 2.000000 m` (within numerical tolerance);
- B-02 P0/P1 assignments `[0,1,2,3,4,5]`, predicted hard violations 0, and
  predicted `d_min = 2.400000 m`;
- identical P0/P1 assignments for each geometry;
- all B-02 deviation/reset segments inside frozen motion limits;
- exact expansion of the 60-attempt order.

Thus neither scene is a Family-A planning manipulation.  The physical grid may
start only while this audit is `PASS`.

## Fail-closed delivery evidence

Every attempt uses ROS simulation time (`use_sim_time=true`).  Wall time is only
an infrastructure watchdog.

For B-01 the retained bag must contain exactly one nominal command per UAV,
common header times for reference UAVs, the delayed command header, and
controller `command_accepted` events.  The achieved delay must be within 0.05 s
of registration.

For B-02 the retained bag must contain the nominal generation, exactly one bias
generation, and exactly one reset generation.  Unique mission IDs distinguish
them.  Exact targets/durations, activation and reset timing, controller
acceptance, bias-generation `ControlTrackingDebug` samples reaching the
registered endpoint within 0.15 m, and reset-generation debug samples are all
required.  The registered start/duration tolerance is 0.05 s.

Both mechanisms publish an experiment-only planning-commitment ledger event,
containing the already resolved assignment and runtime-spec hash, before the
first nominal command.  Missing or inconsistent delivery evidence makes an
attempt `INFRASTRUCTURE_FAILURE`; it cannot enter continuous scientific metrics.

## Finite population and selection

Screening uses only qualification seeds
`[69707,69912,68907,67442,64654]` under `P0_F0` and `P1_F0`.  F1 is refused by
the harness.  Candidate order is three increasing B-01 delays followed by three
increasing B-02 offsets; within a cell P0 precedes P1 and seed order is as shown.
The canonical expanded-order SHA-256 is
`f95192b7391085d8ae92a592ce31dd2e92fdc530683babba8766237c80838fc7`.

A cell must meet every registered gate.  In each planning mode at least 3/5
seeds must have nonzero intended-pair hard-risk events and exposure.  At least
4/5 must be mission-successful, no attempt may be catastrophic (`d_min <= 0.25
m`), no systematic failsafe is allowed, and acceleration-limit-near samples may
not occupy 20% or more of scored control-debug samples.  B-02 must have zero
pre-activation hard events.  Unrelated-pair risk cannot qualify a cell.

If multiple cells for one mechanism qualify, choose the smallest delay or
offset, then lexical candidate ID.  F1 response is unavailable and forbidden as
a selection input.  If no cell qualifies, freeze the finite-grid failure and
stop before any amendment.

Infrastructure retries, if required, are append-only `retry-rN` attempts.  No
scientific attempt is overwritten or replaced.  This grid produces no formal
result and consumes no formal cursor.

At freeze time:

```text
F1_attempt_count = 0
formal_attempt_count = 0
production_method_changed = false
```
