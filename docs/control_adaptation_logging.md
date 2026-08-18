# Execution Profile and Control Adaptation Logging

The Paper Candidate path compiles motion style centrally. The controller does
not infer gains from distance or average speed.

## Current profile policy

```text
task_adaptation_type = identity
task_gain = 1.0
total_gain = style_gain
omega_c = baseline_omega_c * total_gain
omega_o = baseline_omega_o * total_gain
```

The current `paper-current-v7` development values are:

| style | style gain | omega_c | omega_o |
|---|---:|---|---|
| smooth | 0.8 | `[1.2,1.2,1.4]` | `[4,4,6]` |
| normal | 1.0 | `[1.5,1.5,1.75]` | `[5,5,7.5]` |
| aggressive | 1.1 | `[1.65,1.65,1.925]` | `[5.5,5.5,8.25]` |

All values remain inside the independent 0.75x–1.25x controller hard-clamp
envelope. These multipliers are provisional, not paper-final.

## Application path

`UAVExecutionCommand.profile` carries duration, style, compiled bandwidths,
motion limits, soft IAPF values, configuration ID, style gain, and task gain.
The controller rejects incomplete/non-finite values, clamps against injected
hard limits, and applies the accepted bandwidths to LSEF and LESO. Current
`smoothing_alpha=1.0` means immediate guarded application.

Legacy `UAVSwarmCommand.motion_style` remains record-only and restores the YAML
baseline; it never enters this semantic profile path.

## Runtime topics

`/uav{N}/control_adaptation` publishes
`uav_swarm_interfaces/msg/ControlAdaptationLog` with:

```text
mission_id, uav_id, motion_style
target_distance, duration, average_speed
gain_multiplier
omega_o_x/y/z, omega_c_x/y/z
peak_velocity, peak_acceleration
settling_time, tracking_rmse
```

The topic is published at the low-frequency metrics cadence. A CSV row is
written when the task first reaches stable hover, or before a later command
replaces it:

```text
logs/control_adaptation_log.csv
```

`/uav{N}/control_tracking_debug` provides control-rate nominal/safe references,
LADRC output, LESO z1/z2/z3, tracking error, position-derived velocity, and the
actual PX4 setpoint. `/uav{N}/trajectory_metrics` provides the analytic
Minimum-Jerk peaks and final task state.

## Verification

```bash
ros2 topic echo /uav1/control_adaptation
ros2 topic echo /uav1/control_tracking_debug
tail -f logs/control_adaptation_log.csv
```

For reproducible analysis, record all three topics plus
`/uav{N}/execution_command`; the semantic motion-style validation scripts under
`experiments/system_motion_style/` extract compiled/applied omega equality,
saturation, LESO peaks, tracking metrics, and LADRC→PX4 acceleration-link
consistency.
