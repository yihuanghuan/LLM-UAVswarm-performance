# E5-v2 remaining-endpoint mapping audit

## Result

`PASS`

This audit used only artifacts present at the pre-slot-1 tooling freeze
`9276cbe1dcff8299d3edcd73e10cc3a686b2441c`. No slot-1 scientific metric value
was computed or viewed. `J_hard` is outside this audit and is governed by the
separate human endpoint-availability adjudication.

Of 22 remaining endpoints, 17 have an exact prospective mapping, five are
prospectively requested only when observable and are unavailable, and none
requires further semantic adjudication.

| Endpoint | Mapping | Frozen semantics / availability |
|---|---|---|
| Candidate correctness | `EXACT_MAPPING_CONFIRMED` | Canonical-JSON equality between the real frontend Candidate and registered Candidate ground truth; NA if no Candidate. |
| Resolver success | `EXACT_MAPPING_CONFIRMED` | Valid Candidate, complete resolved trace, and no unresolved task rejection. |
| Scientific completeness | `EXACT_MAPPING_CONFIRMED` | No infrastructure failure, valid Candidate, evidence-valid scientific terminal; false for raw evidence loss. |
| Infrastructure failure | `EXACT_MAPPING_CONFIRMED` | Any pre-command startup/spawn/controller/readiness/raw-recorder failure. The v1 readiness-only implementation omission for a post-readiness pre-command recorder failure requires an infrastructure-only alignment. |
| Mission completion | `EXACT_MAPPING_CONFIRMED` | Production runtime returns after all registered completion semantics are met. |
| Mission success | `EXACT_MAPPING_CONFIRMED` | Conjunction of every frozen success requirement, including independent `actual d_min >= 1.50 m`. |
| Actual `d_min` | `EXACT_MAPPING_CONFIRMED` | Minimum synchronized Euclidean pair distance over the scored interval, with the frozen 0.20 s interpolation-gap rule. |
| Tracking RMSE | `EXACT_MAPPING_CONFIRMED` | Duration-weighted 3-D error RMSE across available UAV/time coverage; gaps over 0.20 s omitted. |
| Final error | `EXACT_MAPPING_CONFIRMED` | Maximum latest per-UAV 3-D tracking-error norm in the scored interval. |
| Completion time | `EXACT_MAPPING_CONFIRMED` | First all-UAV stable completion terminal minus first dispatch timestamp. |
| Failsafe | `EXACT_MAPPING_CONFIRMED` | Any failsafe, unintended disarm, or offboard loss over registered UAVs and scored time. |
| Hard failure | `EXACT_MAPPING_CONFIRMED` | Cleanup error or post-resolution non-timeout hard runtime/component terminal error. |
| Resolved `c_exec` | `EXACT_MAPPING_CONFIRMED` | `resolved_center` from frozen resolver trace, per task. |
| Resolved `r_exec` | `EXACT_MAPPING_CONFIRMED` | `r_exec` from frozen resolver trace, per task. |
| Resolved `T_exec` | `EXACT_MAPPING_CONFIRMED` | `t_exec` from frozen resolver trace, per task. |
| `T_LLM` | `EXACT_MAPPING_CONFIRMED` | Monotonic elapsed time around the real frozen semantic frontend invocation. |
| `T_validation` | `PREREGISTERED_BUT_UNAVAILABLE` | No independent pre-slot-1 timestamp; retrospective splitting is prohibited. |
| `T_state_resolution` | `PREREGISTERED_BUT_UNAVAILABLE` | No independent pre-slot-1 timestamp; retrospective splitting is prohibited. |
| `T_geometry` | `PREREGISTERED_BUT_UNAVAILABLE` | No independent pre-slot-1 timestamp; retrospective splitting is prohibited. |
| `T_allocator` | `PREREGISTERED_BUT_UNAVAILABLE` | No independent pre-slot-1 timestamp; retrospective splitting is prohibited. |
| `T_profile` | `PREREGISTERED_BUT_UNAVAILABLE` | No independent pre-slot-1 timestamp; retrospective splitting is prohibited. |
| `T_mission_execution` | `EXACT_MAPPING_CONFIRMED` | Monotonic elapsed time around the complete production runtime call; it is not reported as deterministic compute-only latency. |

The machine-readable audit records the mathematical or Boolean semantics, unit,
interval, aggregation, availability condition, exact prospective authority, and
implementation source for every endpoint.

No endpoint other than adjudicated `J_hard` has semantic ambiguity. The five
unavailable latency components follow the already frozen “when observable”
rule and receive NA rather than zero.
