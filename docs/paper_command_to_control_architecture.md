# Paper Command-to-Control Architecture

This is the current entry point for the Paper Candidate implementation. The
architecture and the C0-A through C0-F policy calibration are frozen.

## Canonical path

```text
English natural language
→ versioned Candidate Mission: tau=(U,F,c,r,T,m,s,q)
→ schema/static validation → Mission Graph/FSM
→ fresh runtime snapshot → late resolution and final geometry
→ T_plan → lexicographic safety-aware allocation → T_exec
→ Executable LFS + separate ResolutionTrace
→ Execution Profile / Safety Compiler
→ UAVExecutionCommand
→ controller finite checks, hard clamps, profile application
→ Minimum-Jerk nominal reference → IAPF safe reference
→ LESO/LSEF LADRC → PX4 acceleration setpoint → inner loops
```

The last LADRC/PX4 edge is active only when launch selects
`control_mode:=ladrc_acceleration`; the launch default `px4_position` remains a
comparison baseline. Candidate failure never falls back to legacy.

## Motion-style contract

`m` is resolved without reinterpretation and copied into Executable LFS. For
the current style-only study:

```text
task_adaptation_type = identity
task_gain = 1.0

omega_c = baseline_omega_c * style_gain
omega_o = baseline_omega_o * style_gain
```

The C0-F frozen values are:

| style | style gain | auto-T factor |
|---|---:|---:|
| smooth | 0.80 | 1.30 |
| normal | 1.00 | 1.15 |
| aggressive | 1.10 | 1.10 |

The baseline bandwidths are `omega_c=[1.5,1.5,1.75]` and
`omega_o=[5,5,7.5]`. Hard clamps are a separate 0.75x–1.25x safety envelope,
so all three normal profiles pass unchanged while out-of-family profiles are
bounded. The controller's current `smoothing_alpha=1.0` means guarded atomic
application; it is not a multi-cycle ramp.

## Timing and priority

For a dynamically feasible explicit duration, all styles preserve the exact
requested `T`; identical start, target, geometry and T therefore produce the
same Minimum-Jerk nominal trajectory. For `T=auto`, the final duration is
`T_min * auto_style_factor`, never below `T_min`.

The enforced priority is:

```text
hard safety > dynamic feasibility > feasible explicit T > motion style
```

Style cannot change `d_hard`, `d_plan`, the allocator objective, motion limits,
Minimum-Jerk mathematics, LADRC mathematics, the PX4 interface, or IAPF core.

## Safety-factor contract

`s` has one meaning: task-level safety preference / safety-margin multiplier.
Late resolution compiles it once into the planning-layer `d_plan` and the
runtime-layer IAPF enter distance, exit distance, and repulsion scale.
`d_violation` (`d_hard`) remains a system-level fixed threshold. The controller
only validates, clamps, and applies these values; IAPF core does not receive or
multiply by `s`. See [paper_safety_factor.md](paper_safety_factor.md) for the
current frozen formulas and values.

## Controller application and observability

`UAVExecutionCommand.profile` is validated and clamped before use. Accepted
bandwidths call `setControllerBandwidth()` and `setObserverBandwidth()`, which
update LSEF gains and LESO observer gains. In LADRC acceleration mode, the
resulting finite output is transformed ENU→NED and published as the PX4
acceleration setpoint. `ControlAdaptationLog`, `ControlTrackingDebug`,
`TrajectoryMetrics`, and `ResolutionTrace` expose the compiled/applied profile,
analytic trajectory peaks, LESO states, saturation, tracking, and final PX4
setpoint.

## Status

Targeted unit, controller, and Gazebo validation supports:

```text
semantic motion-style architecture: frozen
parameter calibration: C0-A through C0-F frozen
```

The frozen C0-F artifact records style gain `0.8/1.0/1.1`, auto factor
`1.30/1.15/1.10`, and `smoothing_alpha=1.0`. Its locked candidate and
confirmation evidence, rather than earlier development trials, are the current
parameter provenance. See `paper_parameter_calibration.md` and the C0-F freeze
artifact.

## Authoritative documentation map

- `README.md`: build, launch, interfaces, and repository navigation.
- `paper_lfs_spec.md`: Candidate/Executable semantics and frozen boundaries.
- `paper_candidate_runtime.md`: production runtime and ROS interfaces.
- `paper_parameter_calibration.md`: current value and freeze provenance.
- `safety_aware_topology_assignment.md`: allocator objective and safety gates.
- `paper_safety_factor.md`: frozen `s` semantics and cross-layer mapping.
- `minimum_jerk_trajectory_metrics.md`: trajectory equations and metrics.
- `control_adaptation_logging.md`: current profile/control observability.
- `iapf_*.md`: current IAPF behavior and experiment tooling; IAPF is outside
  this motion-style calibration change.
- `experiments/docs/experiments_01.md` through `experiments_11.md` and
  `experiments/docs/requirements.md`: formal experiment protocols.
- `experiments/results/*` retained final reports: formal result summaries and
  their raw-data indexes, not debugging diaries.
