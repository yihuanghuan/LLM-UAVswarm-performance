# IAPF acceleration feedforward update

## Summary

This change makes the IAPF repulsion vector affect both the position and
acceleration parts of the PX4 `TrajectorySetpoint`:

```text
p_ref_new = p_ref + iapf_position_gain * F_rep
a_ref_new = a_ref + iapf_accel_gain * F_rep
```

The acceleration contribution is bounded before it is published, so the
repulsion force cannot directly produce an excessive acceleration setpoint.

## Changed files

- `minisnap_LADRC/ladrc_controller/src/ladrc_position_controller_node.cpp`
  - Added ROS parameters for acceleration feedforward enablement, position
    gain, acceleration gain, and acceleration limit.
  - Replaced the hard-coded IAPF position gain with `iapf_position_gain`.
  - Added `iapf_accel_gain * F_rep` to the minimum-jerk acceleration reference.
  - Clamped the IAPF acceleration contribution to `iapf_accel_limit`.
  - Publishes acceleration in PX4 NED coordinates when
    `enable_iapf_accel_feedforward` is true:
    `NED.x = ENU.y`, `NED.y = ENU.x`, `NED.z = -ENU.z`.
- `minisnap_LADRC/ladrc_controller/config/ladrc_params.yaml`
  - Added defaults:
    - `enable_iapf_accel_feedforward: true`
    - `iapf_position_gain: 0.05`
    - `iapf_accel_gain: 0.3`
    - `iapf_accel_limit: 2.0`

## Compatibility notes

- When `enable_iapf_accel_feedforward` is false, acceleration remains
  `{NAN, NAN, NAN}` as before, preserving the original position-only PX4
  behavior.
- Hover-hold setpoints still use the default position-only path.
- `safety_factor <= 0.0` still disables IAPF by returning a zero repulsion
  vector.

## Verification

- Built the affected package:

```bash
source /opt/ros/humble/setup.bash
source /home/yihuang/learning/LLM_swarm_ws/install/setup.bash
colcon build --symlink-install --packages-select ladrc_controller
```

Result: `ladrc_controller` finished successfully. Colcon also reported the
known workspace-local `llm_env` NumPy example package-identification errors
while scanning the workspace, but they did not prevent the selected package
from building.

- Ran a PX4 Gazebo Classic single-vehicle simulation:

```bash
MicroXRCEAgent udp4 -p 8888
cd /home/yihuang/PX4-Autopilot
make px4_sitl gazebo-classic
```

The single PX4 instance exposed `/fmu/...` ROS 2 topics, so the controller was
started under `/uav1` with explicit single-instance remaps to `/fmu/...`.

The README single-vehicle command was then published to `/uav1/swarm_command`
with target `[3.0, 0.0, 3.0]`, duration `5.0`, and `safety_factor: 0.0`.

Observed result:

- The controller received odometry and entered `RUNNING_TRAJECTORY`.
- PX4 armed from the external command and detected takeoff.
- The controller received the swarm command and generated the minimum-jerk
  reference.
- `/fmu/in/trajectory_setpoint` contained finite acceleration values instead of
  `{NAN, NAN, NAN}`.
- `/uav1/status` reported `is_hover_stable: true` after reaching the target.
