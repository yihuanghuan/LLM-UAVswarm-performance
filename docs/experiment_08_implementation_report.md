# Experiment 08 implementation report

## Modification summary

- Added explicit `off`, Classic APF position, IAPF position, and IAPF dual
  execution modes.
- Added deterministic pairwise `id_order` escape, distance epsilon, position
  and acceleration norm limits, and neighbor freshness filtering.
- Added the `IAPFDebug` interface and per-UAV debug topic.
- Added fixed, distance Hungarian, and safety-aware assignment modes, including
  constrained grouped allocation evaluated over all cross-group UAV pairs.
- Added fixed scenarios, a reproducible ROS runner, batch protocol, analysis,
  statistical aggregation, plots, synthetic tests, and LFS artifact policy.
- Added typed ROS parameter-service updates for Humble, scenario-sized
  simulator supervision, and collision-safe three-stage automatic
  prepositioning with odometry-based convergence checks.

## Modes

| Method | Assignment | Avoidance |
|---|---|---|
| M0 | fixed or distance Hungarian | off |
| M1 | same as M0 | Classic APF position |
| M2 | same as M0 | IAPF position |
| M3 | same as M0 | IAPF position + acceleration |
| M4 | safety-aware | off |
| M5 | safety-aware | IAPF position + acceleration |

`avoidance_mode` takes precedence over the deprecated acceleration boolean.
Classic APF never receives an escape component or acceleration feedforward.

## Safety thresholds

The installed Iris model uses a 0.47 m square body collision box. Its furthest
horizontal collision extent comes from a rotor centered 0.22 m from the body
origin with a 0.128 m collision radius. The pairwise center envelope is
`2 × (0.22 + 0.128) = 0.696 m`; therefore this experiment records physical
collision events below `d_collision=0.70 m`. The remaining thresholds are
`d_violation=1.00 m`, `r_iapf=1.50 m`, and `d_assignment=2.00 m`.

## Result structure

Results are written to:

```text
experiments/results/experiments_08/<batch_id>/
├── batch_manifest.json
├── calibrated_parameters.json
├── raw/<scenario>/<condition>/trial_<N>_seed_<seed>/
├── summaries/
├── figures/
└── artifact_checksums.json
```

Each completed trial contains `run_metadata.json`, `odom.csv`,
`iapf_debug.csv`, `assignment.csv`, `mission_events.csv`, `pair_summary.csv`,
`trial_summary.csv`, and (unless disabled) `rosbag2/`.

## Commands

See `experiments/08-iapf/README.md` for build, validation, single-trial,
complete-batch, aggregation, plotting, and checksum commands.

## Verification status

- Baseline before modification: three packages built; six existing Python
  allocator tests passed.
- Current C++ IAPF core tests: six passed.
- Current allocator tests: nine passed.
- Current experiment analysis and aggregation tests: 15 passed.
- Synthetic edge-case validation: passed.
- Gazebo smoke:
  - `head_on/M0`: completed; the expected unsafe baseline produced two
    collision events and triggered the configured simulator-restart rule.
  - `head_on/M3`: completed in a fresh two-UAV simulator.
  - `dense_feasible/M3`: completed with eight UAVs, 1.700 m minimum distance,
    no collision or violation, and 0.252 m final formation error.
  - `dense_feasible/M5`: completed with eight UAVs, 1.719 m minimum distance,
    no collision or violation, and 0.253 m final formation error.
- Formal batch status is recorded after execution; unavailable or failed runs
  are never replaced with synthetic data.

## Known limitations

- APF/IAPF is heuristic and provides no formal collision-avoidance guarantee.
- Gazebo/PX4 process startup and real-time factor depend on host load.
- The current PX4 checkout may be dirty; its exact commit and dirty flag are
  captured per trial rather than modified by this experiment.
- Representative video generation requires an available capture backend; a
  missing backend is reported and does not fabricate video artifacts.
