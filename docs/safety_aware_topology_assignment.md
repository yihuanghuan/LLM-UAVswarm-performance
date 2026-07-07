# Safety-Aware Topology Assignment Changes

## Summary

This update upgrades the scheduler assignment layer from distance-only
Hungarian matching to safety-aware topology refinement.

The runtime ROS contract is unchanged: `location_allocate.py` still publishes
the same `UAVSwarmCommand` messages to `/uav{N}/swarm_command`.

## What Changed

- Added `location_allocate.safety_aware_allocator`.
- Kept Hungarian assignment as the initial solution.
- Added Minimum Jerk nominal trajectory sampling:
  - default sample rate: `20 Hz`
  - trajectory progress: `10t^3 - 15t^4 + 6t^5`
- Added assignment metrics:
  - total flight distance
  - XY segment crossing count
  - spatiotemporal proximity crossing count
  - safety penalty when sampled pairwise distance is below `d_safe`
  - minimum sampled pairwise distance
- Added local pairwise target swap refinement until no lower-cost swap exists.
- Logged the final assignment cost breakdown before publishing goals.

Default cost weights:

```text
J_total = alpha * J_dist
        + beta_xy * J_xy_cross
        + beta_prox * J_proximity_cross
        + gamma * J_safety
alpha = 1.0
beta_xy = 10.0
beta_prox = 10.0
gamma = 1.0
d_safe = 2.0 m
epsilon = 1e-3
```

`beta` remains accepted as a compatibility shortcut and sets both crossing
weights when `beta_xy` and `beta_prox` are not provided.

## Validation

Local checks performed:

```bash
python3 -m py_compile \
  location_allocate/location_allocate/safety_aware_allocator.py \
  location_allocate/location_allocate/location_allocate.py \
  location_allocate/test/test_safety_aware_allocator.py

PYTHONPATH=location_allocate \
  /home/yihuang/learning/LLM_swarm_ws/llm_env/bin/python \
  -m pytest -q -p no:launch_testing \
  location_allocate/test/test_safety_aware_allocator.py

source /opt/ros/humble/setup.bash
source /home/yihuang/learning/LLM_swarm_ws/install/setup.bash
colcon build --symlink-install --packages-select location_allocate
```

Results:

- Syntax check passed.
- Safety-aware allocator tests passed: `5 passed`.
- `location_allocate` colcon build finished successfully.

Note: colcon printed package-identification errors while scanning the
workspace-local `llm_env` numpy test examples because `Cython` is not installed
there. The selected `location_allocate` package still built successfully.

## Git

Functional implementation commit:

```text
d5aa9a3 Add safety-aware topology assignment
```
