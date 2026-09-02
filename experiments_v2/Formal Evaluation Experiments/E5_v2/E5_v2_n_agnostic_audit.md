# E5-v2 N-agnostic method audit

`E5_V2_N_AGNOSTIC_METHOD_AUDIT = PASS`

The frozen production method at `paper-final-sim-v3` / `6cf402debf23851b1eff3edc6f3ab49eae7127c4` does not encode an exactly-eight-agent scientific method. N=12 and N=16 require no change to Candidate semantics, center/scale/timing resolution, formation algorithms, allocator objective, safety thresholds, IAPF parameters/topology, LADRC parameters, Minimum-Jerk semantics, execution profiles, mission relations, or priority hierarchy.

## Inspected subsystems

| Component | Principal path | Fixed-N finding | Classification | E5-v2 action |
|---|---|---|---|---|
| Candidate runtime/schema | `schemas/paper_candidate_schema_v2.json`; `candidate_mission_runtime.py`; `paper_lfs_validator.py` | U has no maximum; formation cardinality only | none, N-agnostic | none |
| Availability/IDs | `location_allocate.py`; `validation_common.py` | default IDs stop at 10, parameter is dynamic | experiment/infrastructure | pass registered IDs explicitly |
| State snapshot | `state_snapshot.py`; `paper_runtime.py` | keyed/iterated by requested IDs | none, N-agnostic | none |
| Center resolution | `lfs_resolver.py` | centroid uses `len(U)` | none, N-agnostic | none |
| Geometry | `formation_geometry.py` | Line/Circle/Polygon/Sphere generate `count` slots | none, N-agnostic | none |
| Qualitative scale | `formation_geometry.py`; frozen policy | scale legitimately changes with geometry `delta_min(N)` | none, N-agnostic | retain exact frozen mapping |
| Allocator | `safety_aware_allocator.py` | Nx3/Hungarian/pairwise/group ranges are dynamic | none, N-agnostic | retain exact objective |
| Assignment/commands | `late_resolution.py`; `execution_command_builder.py` | per-input permutation/profile/command | none, N-agnostic | none |
| Minimum-Jerk/profile | `timing_resolution.py`; `execution_profile_compiler.py`; controller header | max assigned displacement and per-UAV compilation | none, N-agnostic | retain exact limits/rules |
| IAPF | `ladrc_position_controller_node.cpp`; `iapf_core.cpp` | vector/map of configured neighbors | none, N-agnostic | retain exact parameters |
| LADRC launch/namespaces | `swarm_launch.py`; `ladrc_params.yaml` | defaults stop at 10, launch input is dynamic | experiment/infrastructure | supply IDs; no production edit |
| PX4 naming/spawn | `swarm_launch.py`; PX4 `sitl_multiple_run.sh` | `/px4_i`, ports, offsets and `-n` are arithmetic; max 255 | experiment/infrastructure | supply N=8/12/16 |
| Sequential/parallel runtime | `mission_compiler.py`; `mission_executor.py`; `paper_runtime.py`; `late_resolution.py` | iterates nodes/tasks/groups/U | none, N-agnostic | none |
| Safety diagnostics | `late_resolution.py`; allocator; message schemas | pairs, dynamics and neighbors are dynamic | none, N-agnostic | dynamic collection only |
| Readiness | legacy readiness scripts | CLI default 1..8, gate itself iterates CLI IDs | experiment/infrastructure | E5-v2-local wrapper |
| Closed calibration/legacy harnesses | C0-D/C0-E and `experiments-legacy/system_8uav` | literal eight-UAV commands/topics | experiment/infrastructure | leave immutable, do not reuse |
| Old E5-v1 registry | authoritative registry at `33538b…` | availability is intentionally 1..8 | experiment registry | leave byte-immutable |

## Hard-coded assumptions found

The apparent fixed-size assumptions are infrastructure-only:

- `location_allocate.py` and `swarm_launch.py` default to IDs 1–10. The actual ROS parameter parser, publishers, subscribers, namespaces, neighbor lists, resolver, and allocator accept the explicit 1–16 list.
- closed eight-UAV calibration/legacy launchers and collectors contain literal lists or defaults for 1–8;
- the old E5-v1 registry intentionally freezes 1–8.

E5-v2 does not edit those closed artifacts or any production source. Its experiment-local launch/readiness/logging layer must derive every ID, namespace, process expectation, and topic from the registered `uav_ids` list.

No class-A method-semantic N=8 assumption was found. Therefore `BLOCKED_AT_E5_V2_METHOD_SCALING_SEMANTICS` is not triggered.
