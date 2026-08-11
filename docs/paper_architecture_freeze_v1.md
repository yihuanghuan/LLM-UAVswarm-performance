# Paper Architecture Freeze v1

## Paper-frozen

- Candidate and Executable tasks both use `tau=(U,F,c,r,T,m,s,q)`; trace and mission relations remain separate.
- Candidate schema version is `paper-candidate-schema-v1`; supported formations are Circle, Line, Sphere, Triangle, and Polygon.
- The English prompt is `paper-candidate-en-v1`; prompt and schema hashes are recorded for every parse.
- Mission Graph Compiler exclusively interprets q and ParallelGroup completion mode.
- Sequential tasks resolve after predecessors complete; a ParallelGroup uses one immutable fresh `/uavN/swarm_state` snapshot.
- State is `nav_msgs/Odometry`, world/global ENU position and velocity, with a valid source timestamp.
- `current_swarm_centroid`, maintain, relative resolution and allocation starts use only the current task U.
- Geometry order is Unit Geometry → Scale Resolution → Final Geometry. `r_safe=d_plan(s)/delta_F(N)`.
- Timing is split into T_request, T_plan and T_exec. T_exec is the sole executable/profile/message duration. Any representable T difference triggers exactly one final safety re-evaluation.
- `d_hard` is invariant. Soft distances use `d_x(s)=d_hard+s(d_x_base-d_hard)`. Parallel d_plan aggregation is max.
- Parallel completion defaults to independent; synchronized is explicit only.
- New execution uses UAVExecutionCommand; Candidate failure never falls back to legacy.

Geometry convention `paper-unit-geometry-v1`: Line is centered on world X in increasing order. Circle/Polygon/Triangle begin at world +X and proceed counter-clockwise in world XY. Triangle has exactly three vertices. Sphere retains deterministic golden-angle ordering.

## Baseline-frozen but revisitable with semantic LADRC

- smooth/normal/aggressive style gains are all 1.
- task gain is 1 through identity adaptation.
- smoothing alpha is 1.0 (direct application).

These values define a neutral baseline, not the final semantic-controller contribution.

## Provisional parameters

Workspace AABB, state timeout/skew/wait timeout, nominal spacing, qualitative multiplier values, d_hard/d_plan/IAPF numeric baselines, s_max, velocity/acceleration/jerk limits, minimum duration, auto-T style factors, allocator weights/sample rate and all future semantic-controller adaptation values require calibration. See `paper_parameter_calibration.md`.

At current s=1, requested minimum spacings are 1.6/2.0/2.5 m for compact/normal/spacious; d_plan=2.0 m produces final spacings 2.0/2.0/2.5 m. Compact is therefore explicitly reported as safety-clamped to normal.

## Legacy-only

- v1 numerical LFS, task_sequences and the Chinese prompt.
- Historical FormationGenerator behavior, including Triangle/Polygon circle reuse.
- Lineup and Free.
- UAVSwarmCommand and `/uavN/odom : geometry_msgs/Point` compatibility.
- Disjoint-UAV automatic parallel grouping and historical allocator adapters.

Legacy is entered only through `lfs_runtime_mode=legacy_v1`. Existing public wrappers remain available.

## Deliberately unfinished

LADRC output is not newly connected to the PX4 final control synthesis. Minimum-Jerk/LADRC/IAPF composition, semantic LADRC redesign, velocity/jerk controller enforcement, and Experiment 07 redesign are outside this freeze.
