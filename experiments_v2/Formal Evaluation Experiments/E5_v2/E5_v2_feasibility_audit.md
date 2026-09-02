# E5-v2 deterministic feasibility audit

Result: `E5_V2_FEASIBILITY_AUDIT = PASS`.

This is prospective design analysis only: no LLM call, Gazebo run, formal trial, or accepted formal result was created. It asks only whether each frozen Candidate has a legal physical realization; it does not rank candidates by expected ease or success.

## Selected cells

| Candidate | N | state model | feasible | c_exec | r_exec | T_exec | predicted d_min | J_hard |
|---|---:|---|---|---|---|---|---|---:|
| A1-CIRCLE-COMPACT-REL-3-0-1 | 8 | cold_start_spawn | true | `[[3.0, 13.5, 1.83]]` | `[2.3518133367774783]` | `[4.304510783326148]` | 1.752179166 | 0 |
| A1-CIRCLE-COMPACT-REL-3-0-1 | 8 | nominal_post_readiness | true | `[[3.0, 13.5, 2.5]]` | `[2.3518133367774783]` | `[4.304510783326148]` | 1.752179166 | 0 |
| A2-LINE-NORMAL-MAINTAIN | 8 | cold_start_spawn | true | `[[0.0, 13.5, 0.83]]` | `[2.25]` | `[6.3984375]` | 1.800000000 | 0 |
| A2-LINE-NORMAL-MAINTAIN | 8 | nominal_post_readiness | true | `[[0.0, 13.5, 1.5]]` | `[2.25]` | `[6.3984375]` | 1.800000000 | 0 |
| A3-SPHERE-SPACIOUS-REL-0-0-5 | 8 | cold_start_spawn | true | `[[0.0, 13.5, 5.83]]` | `[3.7205877811845802]` | `[4.938973772794869]` | 2.407048532 | 0 |
| A3-SPHERE-SPACIOUS-REL-0-0-5 | 8 | nominal_post_readiness | true | `[[0.0, 13.5, 6.5]]` | `[3.7205877811845802]` | `[4.938973772794868]` | 2.407048532 | 0 |
| B-S1-CIRCLE-ABS-R6-T14 | 8 | cold_start_spawn | true | `[[0.0, 18.0, 4.0]]` | `[6.0]` | `[14.0]` | 1.996737196 | 0 |
| B-S1-CIRCLE-ABS-R6-T14 | 8 | nominal_post_readiness | true | `[[0.0, 18.0, 4.0]]` | `[6.0]` | `[14.0]` | 1.996737196 | 0 |
| B-S1-CIRCLE-ABS-R6-T14 | 12 | cold_start_spawn | true | `[[0.0, 18.0, 4.0]]` | `[6.0]` | `[14.0]` | 1.857773847 | 0 |
| B-S1-CIRCLE-ABS-R6-T14 | 12 | nominal_post_readiness | true | `[[0.0, 18.0, 4.0]]` | `[6.0]` | `[14.0]` | 1.834583397 | 0 |
| B-S1-CIRCLE-ABS-R6-T14 | 16 | cold_start_spawn | true | `[[0.0, 18.0, 4.0]]` | `[6.0]` | `[14.0]` | 1.806203497 | 0 |
| B-S1-CIRCLE-ABS-R6-T14 | 16 | nominal_post_readiness | true | `[[0.0, 18.0, 4.0]]` | `[6.0]` | `[14.0]` | 1.852704076 | 0 |
| B-S2-CIRCLE-NORMAL-MAINTAIN | 8 | cold_start_spawn | true | `[[0.0, 13.5, 0.83]]` | `[2.9397666709718475]` | `[4.636306819923606]` | 2.090812326 | 0 |
| B-S2-CIRCLE-NORMAL-MAINTAIN | 8 | nominal_post_readiness | true | `[[0.0, 13.5, 1.5]]` | `[2.9397666709718475]` | `[4.636306819923606]` | 2.090812326 | 0 |
| B-S2-CIRCLE-NORMAL-MAINTAIN | 12 | cold_start_spawn | true | `[[0.0, 19.5, 0.83]]` | `[4.346666218300812]` | `[6.298395030192372]` | 1.765097529 | 0 |
| B-S2-CIRCLE-NORMAL-MAINTAIN | 12 | nominal_post_readiness | true | `[[0.0, 19.5, 1.5]]` | `[4.346666218300812]` | `[6.298395030192372]` | 1.765097529 | 0 |
| B-S2-CIRCLE-NORMAL-MAINTAIN | 16 | cold_start_spawn | true | `[[0.0, 25.5, 0.83]]` | `[5.766559757418396]` | `[9.198291840393043]` | 1.741119697 | 0 |
| B-S2-CIRCLE-NORMAL-MAINTAIN | 16 | nominal_post_readiness | true | `[[0.0, 25.5, 1.5]]` | `[5.766559757418396]` | `[9.198291840393043]` | 1.741119697 | 0 |
| B-S3-PARALLEL-TWO-CIRCLES | 8 | cold_start_spawn | true | `[[-6.0, 18.0, 4.0], [6.0, 18.0, 4.0]]` | `[3.0, 3.0]` | `[14.0, 14.0]` | 2.400000000 | 0 |
| B-S3-PARALLEL-TWO-CIRCLES | 8 | nominal_post_readiness | true | `[[-6.0, 18.0, 4.0], [6.0, 18.0, 4.0]]` | `[3.0, 3.0]` | `[14.0, 14.0]` | 2.400000000 | 0 |
| B-S3-PARALLEL-TWO-CIRCLES | 12 | cold_start_spawn | true | `[[-6.0, 18.0, 4.0], [6.0, 18.0, 4.0]]` | `[3.0, 3.0]` | `[14.0, 14.0]` | 1.879565644 | 0 |
| B-S3-PARALLEL-TWO-CIRCLES | 12 | nominal_post_readiness | true | `[[-6.0, 18.0, 4.0], [6.0, 18.0, 4.0]]` | `[3.0, 3.0]` | `[14.0, 14.0]` | 1.879565644 | 0 |
| B-S3-PARALLEL-TWO-CIRCLES | 16 | cold_start_spawn | true | `[[-6.0, 18.0, 4.0], [6.0, 18.0, 4.0]]` | `[3.0, 3.0]` | `[14.0, 14.0]` | 2.121320344 | 0 |
| B-S3-PARALLEL-TWO-CIRCLES | 16 | nominal_post_readiness | true | `[[-6.0, 18.0, 4.0], [6.0, 18.0, 4.0]]` | `[3.0, 3.0]` | `[14.0, 14.0]` | 2.121320344 | 0 |

All selected target geometries lie inside the frozen workspace, each target set respects its frozen d_plan geometry floor, the frozen allocator returns an assignment with no predicted d_hard violation, and final Minimum-Jerk profiles respect the frozen motion limits.

## Non-selected design candidates

| Candidate | N | state model | feasible | deterministic disposition |
|---|---:|---|---|---|
| R-A3-OLD-LIKE-SPHERE-SPACIOUS-REL-3-0-1 | 8 | cold_start_spawn | false | workspace scale limit conflicts with d_plan(s) or requested scale |
| R-A3-OLD-LIKE-SPHERE-SPACIOUS-REL-3-0-1 | 8 | nominal_post_readiness | false | workspace scale limit conflicts with d_plan(s) or requested scale |
| R-A1-CIRCLE-COMPACT-REL-14-0-0 | 8 | cold_start_spawn | false | workspace scale limit conflicts with d_plan(s) or requested scale |
| R-A1-CIRCLE-COMPACT-REL-14-0-0 | 8 | nominal_post_readiness | false | workspace scale limit conflicts with d_plan(s) or requested scale |
| R-B-S2-SPHERE-NORMAL-MAINTAIN | 8 | cold_start_spawn | false | workspace scale limit conflicts with d_plan(s) or requested scale |
| R-B-S2-SPHERE-NORMAL-MAINTAIN | 8 | nominal_post_readiness | false | workspace scale limit conflicts with d_plan(s) or requested scale |
| R-B-S2-SPHERE-NORMAL-MAINTAIN | 12 | cold_start_spawn | false | workspace scale limit conflicts with d_plan(s) or requested scale |
| R-B-S2-SPHERE-NORMAL-MAINTAIN | 12 | nominal_post_readiness | false | workspace scale limit conflicts with d_plan(s) or requested scale |
| R-B-S2-SPHERE-NORMAL-MAINTAIN | 16 | cold_start_spawn | false | workspace scale limit conflicts with d_plan(s) or requested scale |
| R-B-S2-SPHERE-NORMAL-MAINTAIN | 16 | nominal_post_readiness | false | workspace scale limit conflicts with d_plan(s) or requested scale |
| R-B-S1-CIRCLE-ABS-R6-T10 | 8 | cold_start_spawn | true | physically admissible but excluded by the predeclared coverage/selection rule |
| R-B-S1-CIRCLE-ABS-R6-T10 | 8 | nominal_post_readiness | true | physically admissible but excluded by the predeclared coverage/selection rule |
| R-B-S1-CIRCLE-ABS-R6-T10 | 12 | cold_start_spawn | true | physically admissible but excluded by the predeclared coverage/selection rule |
| R-B-S1-CIRCLE-ABS-R6-T10 | 12 | nominal_post_readiness | true | physically admissible but excluded by the predeclared coverage/selection rule |
| R-B-S1-CIRCLE-ABS-R6-T10 | 16 | cold_start_spawn | true | physically admissible but excluded by the predeclared coverage/selection rule |
| R-B-S1-CIRCLE-ABS-R6-T10 | 16 | nominal_post_readiness | true | physically admissible but excluded by the predeclared coverage/selection rule |
| R-B-S3-PARALLEL-CLOSE-CENTERS | 8 | cold_start_spawn | false | parallel nominal trajectory violates d_hard |
| R-B-S3-PARALLEL-CLOSE-CENTERS | 8 | nominal_post_readiness | false | parallel nominal trajectory violates d_hard |
| R-B-S3-PARALLEL-CLOSE-CENTERS | 12 | cold_start_spawn | false | parallel nominal trajectory violates d_hard |
| R-B-S3-PARALLEL-CLOSE-CENTERS | 12 | nominal_post_readiness | false | parallel nominal trajectory violates d_hard |
| R-B-S3-PARALLEL-CLOSE-CENTERS | 16 | cold_start_spawn | false | parallel nominal trajectory violates d_hard |
| R-B-S3-PARALLEL-CLOSE-CENTERS | 16 | nominal_post_readiness | false | parallel nominal trajectory violates d_hard |

The old-like low Sphere and edge-shifted Circle fail closed at frozen workspace/scale gates. The close-center parallel composition fails at the frozen d_hard gate. The T=10 S1 candidate is physically admissible but was not selected because its conservative N=16 planning duration is corrected, whereas the predeclared S1 rule takes the first duration unchanged at every deterministic gate.
