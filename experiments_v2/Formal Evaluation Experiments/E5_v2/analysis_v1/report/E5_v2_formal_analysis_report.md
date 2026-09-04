# E5-v2 formal analysis report

## Scope and frozen evidence

This is descriptive end-to-end integration evidence from the separately preregistered E5-v2 campaign. The source is commit 558def6238826460cb3f9323af445e8c299fb610. Exactly 60 registered attempts were consumed in the frozen order; all 60 were scientifically complete and no infrastructure failure, replacement, or additional sample occurred.

E5-v2 supplies no new causal evidence for C1, C2, or C3. It does not establish formal or asymptotic scalability, arbitrary-N generalization, linear or near-linear computational scaling, or real-time scaling guarantees. No inferential comparison across N was conducted.

## Overall results

All 60 registered attempts satisfied the frozen end-to-end mission-success criterion: 60/60 (100.0%; two-sided Wilson 95% CI 94.0–100.0%). This is observed success on the registered E5-v2 scenarios, not a universal reliability or safety guarantee.

| Endpoint | Result |
|---|---:|
| scientific completeness | 60/60 (100.0%; Wilson 95% CI 94.0–100.0%) |
| Candidate correctness | 60/60 (100.0%; Wilson 95% CI 94.0–100.0%) |
| resolver success | 60/60 (100.0%; Wilson 95% CI 94.0–100.0%) |
| mission completion | 60/60 (100.0%; Wilson 95% CI 94.0–100.0%) |
| mission success | 60/60 (100.0%; Wilson 95% CI 94.0–100.0%) |
| infrastructure failure | 0/60 (0.0%; Wilson 95% CI 0.0–6.0%) |
| failsafe | 0/60 (0.0%; Wilson 95% CI 0.0–6.0%) |
| hard failure | 0/60 (0.0%; Wilson 95% CI 0.0–6.0%) |

Continuous cells below are mean / median [min, max]; sample SD and IQR are retained in the machine-readable tables.

| Endpoint | Overall |
|---|---:|
| actual_d_min | 1.948 / 1.859 [1.593, 2.420] |
| tracking_rmse | 0.085 / 0.093 [0.023, 0.149] |
| final_error | 0.085 / 0.080 [0.019, 0.163] |
| completion_time | 11.138 / 12.628 [5.598, 15.041] |
| T_LLM | 19.172 / 16.425 [8.090, 84.644] |
| T_mission_execution | 11.953 / 14.518 [5.712, 18.615] |

## E5-v2A: feasible under-specified realization

All three prospectively feasible scenario families traversed the real semantic frontend, deterministic staged resolution, geometry, allocation, execution, safety, control, and mission-completion path in all five registered attempts.

| Scenario | Mission success | r_exec mean | T_exec mean | d_min mean | RMSE mean | final error mean | completion mean | T_LLM mean | T_mission mean |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| A1 — REL-COMPACT-CIRCLE | 5/5 (100.0%; Wilson 95% CI 56.6–100.0%) | 2.352 | 4.304 | 1.665 | 0.122 | 0.089 | 5.608 | 21.674 | 5.731 |
| A2 — MAINTAIN-NORMAL-LINE | 5/5 (100.0%; Wilson 95% CI 56.6–100.0%) | 2.250 | 6.398 | 1.799 | 0.132 | 0.155 | 7.607 | 17.548 | 7.712 |
| A3 — REL-SPACIOUS-SPHERE | 5/5 (100.0%; Wilson 95% CI 56.6–100.0%) | 3.721 | 4.939 | 2.370 | 0.105 | 0.105 | 6.617 | 21.244 | 6.729 |

Resolved center realization (component-wise mean [min, max]):

| Scenario | c_exec x | c_exec y | c_exec z |
|---|---:|---:|---:|
| A1 — REL-COMPACT-CIRCLE | 3.007 [3.003, 3.010] | 13.499 [13.494, 13.504] | 2.503 [2.501, 2.505] |
| A2 — MAINTAIN-NORMAL-LINE | 0.005 [0.003, 0.007] | 13.498 [13.496, 13.501] | 1.500 [1.498, 1.502] |
| A3 — REL-SPACIOUS-SPHERE | 0.005 [0.001, 0.008] | 13.498 [13.497, 13.499] | 6.501 [6.498, 6.506] |

All 15 E5-v2A attempts had exact Candidate correctness, resolver success, mission completion, and mission success. All 15 task-level c_exec, r_exec, and T_exec records matched their registered relative/maintain-current, qualitative, and automatic timing semantics.

A3 supports the bounded statement that qualitative spacious Sphere semantics are executable when their state-dependent physical realization lies inside the frozen workspace and safety envelope. It did not fix or rerun the distinct E5-v1 command.

## E5-v2B: larger-swarm demonstration

The same frozen command-to-control method was successfully demonstrated at N=8, N=12, and N=16 in the registered simulation scenarios. All 45 E5-v2B attempts were scientifically complete, Candidate-correct, resolver-successful, mission-complete, and mission-successful; each of the nine cells contributed exactly five attempts. N was not an isolated causal treatment: spawn extent, centroid, assignment geometry, displacement, qualitative realization, and auto timing co-varied under the frozen rules.

### Nine registered N × family cells

| Cell | Success | d_min mean | RMSE mean | final error mean | completion mean | T_LLM mean | T_mission mean |
|---|---:|---:|---:|---:|---:|---:|---:|
| N8 SIMPLE | 5/5 (100.0%; Wilson 95% CI 56.6–100.0%) | 1.996 | 0.024 | 0.024 | 15.035 | 11.249 | 15.082 |
| N8 UNDER_SPECIFIED | 5/5 (100.0%; Wilson 95% CI 56.6–100.0%) | 2.058 | 0.131 | 0.058 | 5.871 | 12.726 | 5.972 |
| N8 COMPOSITIONAL | 5/5 (100.0%; Wilson 95% CI 56.6–100.0%) | 2.405 | 0.038 | 0.036 | 15.030 | 28.963 | 15.091 |
| N12 SIMPLE | 5/5 (100.0%; Wilson 95% CI 56.6–100.0%) | 1.835 | 0.028 | 0.032 | 15.037 | 12.372 | 15.678 |
| N12 UNDER_SPECIFIED | 5/5 (100.0%; Wilson 95% CI 56.6–100.0%) | 1.764 | 0.141 | 0.144 | 7.505 | 13.380 | 8.491 |
| N12 COMPOSITIONAL | 5/5 (100.0%; Wilson 95% CI 56.6–100.0%) | 1.865 | 0.054 | 0.071 | 15.035 | 25.885 | 15.190 |
| N16 SIMPLE | 5/5 (100.0%; Wilson 95% CI 56.6–100.0%) | 1.823 | 0.042 | 0.046 | 15.038 | 12.554 | 18.059 |
| N16 UNDER_SPECIFIED | 5/5 (100.0%; Wilson 95% CI 56.6–100.0%) | 1.714 | 0.118 | 0.155 | 10.235 | 17.807 | 13.241 |
| N16 COMPOSITIONAL | 5/5 (100.0%; Wilson 95% CI 56.6–100.0%) | 2.082 | 0.082 | 0.107 | 15.038 | 34.661 | 16.455 |

### Descriptive summaries by N

| N | Registered | Success | d_min mean | RMSE mean | final error mean | completion mean |
|---:|---:|---:|---:|---:|---:|---:|
| 8 | 15 | 15/15 (100.0%; Wilson 95% CI 79.6–100.0%) | 2.153 | 0.064 | 0.039 | 11.979 |
| 12 | 15 | 15/15 (100.0%; Wilson 95% CI 79.6–100.0%) | 1.821 | 0.075 | 0.082 | 12.526 |
| 16 | 15 | 15/15 (100.0%; Wilson 95% CI 79.6–100.0%) | 1.873 | 0.081 | 0.103 | 13.437 |

### Descriptive summaries by task family

| Family | Registered | Success | d_min mean | RMSE mean | final error mean | completion mean |
|---|---:|---:|---:|---:|---:|---:|
| SIMPLE | 15 | 15/15 (100.0%; Wilson 95% CI 79.6–100.0%) | 1.885 | 0.031 | 0.034 | 15.037 |
| UNDER_SPECIFIED | 15 | 15/15 (100.0%; Wilson 95% CI 79.6–100.0%) | 1.845 | 0.130 | 0.119 | 7.870 |
| COMPOSITIONAL | 15 | 15/15 (100.0%; Wilson 95% CI 79.6–100.0%) | 2.117 | 0.058 | 0.072 | 15.034 |

### UNDER_SPECIFIED physical realization by N

The semantic structure was held constant across N; the frozen state/cardinality-dependent rules legitimately produced different centers, scale, and automatic timing.

| N | c_exec mean [x,y,z] | r_exec mean | T_exec mean | semantic audit |
|---:|---:|---:|---:|---:|
| 8 | [0.005, 13.499, 1.501] | 2.940 | 4.638 | PASS |
| 12 | [0.006, 19.499, 1.500] | 4.347 | 6.296 | PASS |
| 16 | [0.009, 25.502, 1.501] | 5.767 | 9.195 | PASS |

Observed physical and timing quantities varied with the associated N-dependent mission realization. These descriptive differences are not causal N effects or performance-scaling estimates.

## Endpoint availability

J_hard is NA / NOT ANALYZED for 0/60 available observations. Its frozen status is PREREGISTERED_ENDPOINT_UNAVAILABLE_DUE_TO_SEMANTIC_AMBIGUITY. No replacement, proxy, raw-data rederivation, or zero imputation was used. Mission success independently retained the frozen actual d_min >= 1.50 m rule.

The preregistered latency components T_validation, T_state_resolution, T_geometry, T_allocator, and T_profile are unavailable in 60/60 attempts and remain NA. T_LLM and T_mission_execution are available in 60/60 and are summarized descriptively; they were not combined into a scaling metric.

## Tooling-amendment governance

Slot 1 was physically executed exactly once under tooling bundle v1 (422d82b593ba927dffaee3c14bcf8b6996304a8ae302cdc525ab3c525b786ecb). A post-run packaging blocker occurred after complete raw evidence had been preserved. The transaction was recovered without rerunning the mission under recovery bundle 29eb7421d2095ba88e60df0ed224ad035348b534cb57877a32d967bd933027bb. Slots 2–60 used amended execution bundle v2 (2800b1a4540ffde75573f5ea7bf580b415302d5c4d86f0ab86898c69f7b02572). The scientific method and protocol did not change, but instrumentation was not byte-identical across all attempts; slot 1 remains in the all-attempt denominator.

## Relationship to E5-v1

E5-v1 is a separately frozen historical registry. Its REL-QUAL condition remained 0/5 mission success because the registered spacious-Sphere realization violated frozen geometry/workspace constraints, and its MIXED-HIGH frontend limitation remains. E5-v2 was independently preregistered to study prospectively feasible under-specified positive integration tasks and to add N=12/N=16 demonstrations. Their success percentages are neither pooled nor presented as before/after improvement.

## Claim-boundary table

| Question | Evidence | Supported interpretation | Unsupported interpretation |
|---|---|---|---|
| Feasible under-specified realization | 15/15 E5-v2A attempts completed with confirmed Candidate/resolver and c/r/T semantics | Prospectively feasible relative/qualitative/auto commands completed the full pipeline in the registered scenarios | Arbitrary under-specified commands will always be feasible |
| Physical boundary handling | Feasible E5-v2A plus immutable inadmissible E5-v1 REL-QUAL | The frozen resolver may instantiate a feasible request or reject a physically inadmissible one | All qualitative semantics are executable in every workspace/state |
| Larger-swarm demonstration | All 45 E5-v2B attempts across N=8/12/16 and S1/S2/S3 | The same frozen method operated at N=8/12/16 in the tested simulation missions | Formal scalability, arbitrary N, or asymptotic performance |
| Reliability | 60/60 met the frozen end-to-end success rule | Success was observed in all registered E5-v2 attempts | Universal 100% reliability |
| Safety | All successful attempts had actual d_min >= 1.50 m | The registered hard-distance criterion was satisfied in these attempts | Continuous J_hard exposure or universal collision-avoidance guarantee |

## Paper-facing evidence extraction

### Strongest quantitative facts

1. All 60/60 attempts met mission success (Wilson 95% CI 94.0–100.0%).
2. Scientific completeness was 60/60 and infrastructure failures were 0/60.
3. Candidate correctness, resolver success, and mission completion were each 60/60.
4. E5-v2A achieved 15/15 mission success across three distinct feasible relative/qualitative/auto scenarios.
5. All 15 E5-v2A and all 75 total task-level resolved c/r/T records passed semantic-mode consistency checks.
6. E5-v2B achieved 45/45 mission success, with 5/5 in every one of the nine N × task-family cells.
7. Overall actual d_min was mean 1.948 m (range 1.593–2.420 m).
8. Overall tracking RMSE was mean 0.085 m and final error mean 0.085 m.
9. Completion time averaged 11.138 s; T_LLM averaged 19.172 s and T_mission_execution 11.953 s.
10. J_hard and five decomposed deterministic latency components remained unavailable in 0/60 observations by frozen adjudication/mapping.

### Recommended compact E5 results paragraph

In the separately preregistered E5-v2 integration campaign, all 60 registered attempts satisfied the frozen end-to-end mission-success criterion (100%; Wilson 95% CI 94.0–100.0%). This included 15/15 prospectively feasible under-specified attempts spanning relative or maintain-current centers, qualitative scales, and automatic duration, and 45/45 scale-demonstration attempts with 5/5 successes in every N=8, N=12, and N=16 by SIMPLE, UNDER_SPECIFIED, and COMPOSITIONAL cell. Candidate correctness, resolver success, and mission completion were each observed in 60/60 attempts. The same frozen command-to-control pipeline was therefore demonstrated in the registered scenarios at all three swarm sizes; this is descriptive integration evidence and does not establish formal or asymptotic scalability or arbitrary-N generalization.

### Recommended main-paper table

Report registered N, scientific completeness, mission success with Wilson CI, Candidate correctness, resolver success, actual d_min, tracking RMSE, final error, and completion time for overall E5-v2, E5-v2A scenarios, and the nine E5-v2B N × family cells.

### Recommended supplementary results

Include the per-attempt table, full binary and continuous summaries (N, mean, median, sample SD, IQR, min/max), all c_exec/r_exec/T_exec task records, endpoint availability, exact frozen hashes, and mixed-tooling provenance.

### Explicit limitations and prohibited overclaims

Do not infer new C1/C2/C3 evidence; formal/asymptotic/linear/real-time scalability; arbitrary-N generalization; universal reliability; guaranteed collision avoidance; causal N effects; or continuous hard-risk exposure. Do not pool E5-v1 and E5-v2 or describe E5-v2 as fixing E5-v1. J_hard and the five unavailable latency components must remain NA.
