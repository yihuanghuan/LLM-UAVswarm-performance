# IAPF Position and Acceleration Integration

IAPF modifies the frozen Minimum-Jerk reference before LADRC:

```text
p_safe = p_MJ + clamp(iapf_position_gain * F_rep, position_limit)
a_safe = a_MJ + clamp(iapf_accel_gain * F_rep, acceleration_limit)
LADRC(p_safe, v_MJ, a_safe, measurement) -> acceleration command
```

Both offsets pass through the configured first-order filter. Acceleration
offset is present only in `iapf_dual`; other active modes use the position
offset alone.

## Current modes

`avoidance_mode` is the authoritative launch/runtime selector:

| mode | position offset | acceleration offset | velocity-aware escape |
|---|---|---|---|
| `off` | no | no | no |
| `classic_position` | yes | no | no |
| `iapf_position` | yes | no | yes |
| `iapf_dual` | yes | yes | yes |

The compatibility parameter `enable_iapf_accel_feedforward` is deprecated and
must not be set together with `avoidance_mode`.

## Controller-mode boundary

In `ladrc_acceleration` control mode, LADRC is the unique final translational
acceleration command; its finite ENU output is converted to NED and published
through `TrajectorySetpoint.acceleration`. In the `px4_position` comparison
mode, the safe position reference is published and acceleration feedforward is
included only for `iapf_dual`.

Current YAML defaults include `iapf_position_gain=0.05`,
`iapf_position_limit=0.50`, `iapf_accel_gain=0.30`, and
`iapf_accel_limit=2.00`. Candidate Execution Profile supplies the current soft
enter/exit distances and repulsion scale; controller hard safety parameters
remain independent guards.

This document describes the existing IAPF interface. The semantic motion-style
enablement does not change IAPF equations, modes, gains, or thresholds.
