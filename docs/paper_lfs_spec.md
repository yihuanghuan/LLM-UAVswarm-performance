# Paper Candidate LFS Specification

This document is the authoritative semantic and architecture specification for
the Paper Candidate path. Architectural freeze does not imply that provisional
policy values are calibrated or paper-final.

## Formal representations

Candidate and Executable tasks preserve the same tuple:

```text
tau_candidate = (U,F,c,r,T,m,s,q)
tau_exec      = (U,F,c,r,T,m,s,q)
```

Candidate fields may contain unresolved semantic requests. Executable `c`, `r`
and `T` are resolved numeric values; `F`, `m`, `s` and `q` retain task semantics.
`ResolutionTrace`, assignment results, profiles and mission relations are not
members of either tuple.

The research interface is `schemas/paper_candidate_schema_v2.json`, with
`lfs_version=2.1`, prompt version `paper-candidate-en-v2`, and schema version
`paper-candidate-schema-v2`. Prompt and schema hashes are recorded for every
parse.

## Candidate field semantics

- `U`: unique participating UAV IDs, all present in the runtime availability
  set.
- `F`: structured descriptor: Circle, Line, Sphere, Triangle, or Polygon with
  explicit `sides>=4`.
- `c`: absolute world coordinate, relative world offset from the current task-U
  centroid, maintain-current-task-U-centroid, or auto. Auto deterministically
  selects the current task-U centroid.
- `r`: explicit, qualitative, or auto scale. Line uses adjacent spacing;
  Circle/Sphere use radius; Triangle uses circumradius; Polygon uses vertex
  circumradius. Qualitative and auto requests are resolved deterministically.
- `T`: explicit positive seconds or auto. Explicit feasible time is preserved;
  infeasible time is raised deterministically and traced.
- `m`: smooth, normal, or aggressive semantic style; omitted style canonically
  becomes normal. It never grants permission to violate feasibility or safety.
- `s`: numeric safety multiplier `>=1`. Non-numeric language such as “safer”
  does not invent a multiplier and produces `1.0`.
- `q`: exactly direct, continuous, or hover-and-wait with duration. Paper JSON
  has no standalone WaitNode. The Mission Compiler alone converts q to a
  completion event and an internal WaitSpec.

## Formation geometry

The deterministic convention is `paper-unit-geometry-v3`:

| Formation | Cardinality | Unit geometry and r |
|---|---:|---|
| Line | `N>=2` | Centered on world X; `r` is adjacent spacing |
| Circle | `N>=4` | Uniform circumference, first point world +X, counter-clockwise in XY; `r` is radius |
| Sphere | `N>=2` | Deterministic golden-angle ordering; `r` is sphere radius |
| Triangle | `N==3` | Equilateral vertices, first at world +X; `r` is circumradius |
| Polygon | `sides>=4`, `N>=sides` | Regular polygon with explicit sides; targets equally spaced along its perimeter; `r` is vertex circumradius |

Geometry is resolved strictly as Unit Geometry → Scale Resolution → Final
Geometry. Unit geometry provides `delta_F(N)`; the safety floor is
`r_safe=d_plan(s)/delta_F(N)`. Every final target must be inside the configured
AABB. Workspace pressure never permits shrinking below the safety floor.

## Mission and transition semantics

Mission nodes are ordered top-level TaskNodes or ParallelGroups. ParallelGroup
contains disjoint U sets and explicitly declares independent or synchronized
completion. No disjoint-U heuristic creates parallelism.

`continuous` is legal only on a top-level TaskNode with a following mission
node. It means that trajectory completion advances immediately without a
hover-stability gate or dwell; it does not promise nonzero velocity or a
physically non-stop transition. A terminal task and every task inside a
ParallelGroup must use direct or hover-and-wait.

Independent parallel tasks keep their own durations; completed UAVs hover at
their assigned goals while safety evaluation continues to `max(T_k)`.
Synchronized completion explicitly uses the maximum feasible group duration.

## Validation, resolution, and execution

```text
Natural Language → English Candidate parser
→ schema validation → static semantic validation
→ Mission Graph Compiler → FSM
→ ready task / ParallelGroup obtains one fresh immutable snapshot
→ runtime validation → center resolver
→ unit geometry → scale resolution → final geometry
→ T_plan → safety-aware allocator → T_exec
→ one safety recheck whenever T_exec != T_plan
→ Executable LFS + separate ResolutionTrace
→ Execution Profile → UAVExecutionCommand
```

Static validation owns IDs, task uniqueness, cardinality, parallel overlap,
q/mission legality and other state-independent checks. Runtime validation owns
fresh snapshot-dependent facts. Parallel tasks share one snapshot epoch.
`current_swarm_centroid` always means only the current task U.

`T_request` comes from Candidate, `T_plan` is allocator-only, and assignment
finalizes `T_exec`. `T_exec` is the sole duration source for Executable LFS,
Execution Profile and UAVExecutionCommand. Resolver, allocator and compiler
remain distinct modules.

`d_hard` is an invariant violation definition. `d_plan(s)` and IAPF soft
activation margins may increase with s. Planning scale uses `d_plan(s)`, never
`d_hard`.

## Frozen, provisional, and legacy boundaries

Frozen semantics include the two tuples, structured F/q, Candidate/Executable
separation, late binding, validation layers, ordered sequential/parallel
missions, task-U centroid, versioned English prompt/hash and fail-closed Paper
execution.

`lfs_policy.paper_current.yaml` remains runnable but its physical environment,
algorithm-calibration and future semantic-controller values retain their current
provisional/baseline status. See `paper_parameter_calibration.md`; no number is
made paper-final by this semantic freeze.

Legacy is entered only through `lfs_runtime_mode=legacy_v1`. Its implementation
lives under `location_allocate/legacy/`; compatibility shims preserve historical
imports. The compatibility schema is `schemas/legacy/lfs_schema_v1.json`.
Legacy keeps the Chinese numerical parser, task_sequences, historical
FormationGenerator behavior, Lineup/Free, `/uavN/odom`, UAVSwarmCommand and its
automatic disjoint-U grouping. Paper runtime imports none of these and Candidate
failure never falls back to legacy.

This specification does not claim that LADRC output drives the final PX4
setpoint, does not add velocity/jerk controller enforcement, and does not alter
Minimum-Jerk/LADRC/IAPF control synthesis.
