# Pre-v1 Analysis Contract Audit

Status: `BLOCKED_A2_PREIMPLEMENTATION`

This audit was performed before implementing any live-data extractor. It uses only sealed/active protocols, authoritative registries, existing frozen scorer/validator code, controller message/runtime definitions, and calibration analysis code. No demo outcome was used to choose a metric rule.

## Authoritative identities

| Experiment | Protocol / registry | SHA-256 |
|---|---|---|
| E2 | `E2_protocol_v1.yaml` | `9ea7234db111b69cccb72315eed26e4abf117955eb20a2d593f2d854ea0b40e3` |
| E2 | `e2_scenario_registry_v1.yaml` | `8215a5d8248c946c480ca4c8cb41e2afac28e6021c9f308a068580da69369bae` |
| E3 | active `E3_protocol_v3.yaml` | `2eea03e2bb33aa1c10c1ae104b965f909690f00c8caee4446291faf2c9893013` |
| E3 | active `e3_factorial_registry_v3.yaml` | `b56344c6cd257e99851523d640d9a89d6def994884877e2303d8fab836e0faf2` |
| E4 | `E4_protocol_v1.yaml` | `5a7eeb923aebcfb068827c6513a37e856dc8d6f05166a4b84775b33572bd83d0` |
| E4 | `e4_motion_style_registry_v1.yaml` | `48779a6667759955dd7dab2d8509f61a5439cca51a4bf98fcb48b6d17c499f95` |
| E5 | `E5_protocol_v1.yaml` | `116002154cd2395b6a9f55d7c1aae6e0a2c42440f0ceaa827a1a8cb02828319c` |
| E5 | `e5_end_to_end_registry_v1.yaml` | `9bb6bc9b46b5211c50c8f2e29bd434235424beb2bb0fc36ec857a3298d89511e` |
| Global | seed/failure registry | `90313d33793940489edde631d397564378ae54fe3cfddf438e4a895d6132254d` |

E3 v3 activation commit `16de9c7ffd83b67925fc5817f33665727ccbb75f` is an ancestor of the audit base. E3 duration, geometry, P0/P1/F0/F1 semantics, seeds, and ordering were not modified.

## Analysis contract

| Experiment | Metric | Status | Frozen definition and raw authority | Interval / aggregation / failure contract | Determination |
|---|---|---|---|---|---|
| E2 | executable grounding success | Primary | Valid executable mission grounded at registered execution snapshot; authoritative offline resolution trace and frozen Boolean flag. | All-attempt rate; 120 registered attempts; every failure retained. | Fully determined; preserve existing `e2_scorer.py`. |
| E2 | state consistency violation rate | Primary | Executable c/r/T inconsistent with registered execution snapshot; offline trace and Boolean flag. | All-attempt rate, paired by scenario/seed/snapshots. | Fully determined. |
| E2 | dynamic infeasibility rate | Primary | Requested timing or geometry infeasible under frozen policy; offline trace and Boolean flag. | All-attempt rate. | Fully determined. |
| E2 | correction/rejection rates | Primary plus separate diagnostics | Traced deterministic correction or terminal rejection; report combined and separately. | All-attempt rates. | Fully determined. |
| E3 | actual_d_min | Primary | Minimum measured pairwise 3-D distance; actual per-UAV position. | `t0` through `t0 + duration + 2 s`; per-pair diagnostics. | Formula A0; timestamp alignment/boundary convention A1. |
| E3 | predicted_d_min | Primary | Allocator prediction retained before execution; recorded assignment and provenance. | Pre-dispatch scalar; never recompute from actual trajectory. | Fully determined A0. |
| E3 | hard-risk exposure | Primary | Actual distance below frozen `d_hard=1.50 m`. | Same E3 scored interval; pairwise and total exposure. | Threshold A0; continuous-time crossing/integration convention A1. |
| E3 | hard-risk event count | Primary | Protocol says count events below `d_hard`. | Same scored interval; all attempts retained. | **A2 unresolved:** event unit/merging semantics are not frozen. |
| E3 | mission_success | Primary | All required tasks complete within `t0 + duration + 6 s` and no hard failure; explicit completion and failure events. | Boolean; failures retained in denominator. | Fully determined A0 if registered task-event mapping is present. |
| E3 | IAPF activation time | Primary | Authoritative per-UAV `iapf_active`. | Same scored interval; per-UAV and sum over UAVs. | Signal/aggregation A0; transition timing A1. |
| E3 | integral_delta_p / integral_delta_a | Primary | Integral of Euclidean norm of authoritative IAPF delta-p / delta-a. | Same scored interval; per-UAV plus registered swarm sum. | Formula A0; integration/boundary convention A1. |
| E3 | trajectory_deviation | Primary | Nominal-vs-safe-reference 3-D distance, not tracking error; integral and RMS. | Same scored interval. | Formula A0; integration/RMS time weighting A1. |
| E4A | settling_time | Primary | Task-command time to controller stable-hover entry under the existing completion state. | Start is execution command; stable-hover state is logged. | Per-UAV signal is determined; **A2 unresolved** swarm aggregation and common scored interval. |
| E4A | control_effort | Primary | Time integral of norm of commanded LADRC acceleration. | Protocol says “scored interval” but E4 protocol/registry does not freeze its exact end. | **A2 unresolved.** |
| E4A | acceleration_response | Primary | Peak, RMS, and rise-time summary of commanded acceleration. | Per-UAV/swarm aggregation not specified. | Peak/RMS formula is mechanical after interval choice; **rise-time definition is A2 unresolved.** |
| E4A | tracking_RMSE | Primary | RMS 3-D distance between safe reference and measured position. | Exact interval and swarm weighting are not frozen. | **A2 unresolved.** |
| E4A | reference identity | Analysis provenance check | Same initial positions, assigned targets, explicit T, seed, and Minimum-Jerk nominal reference across styles; only authorized profile differs. | Fail closed on any mismatch. | Fully determined A0. |
| E4B | unauthorized_override_count | Primary | Count the six complete frozen authority predicates with `1e-9` deterministic-field tolerance and logged saturation predicate for measured limits. | One Boolean result per predicate; all attempts retained. | Fully determined A0. |
| E4B | Priority-Preservation Rate | Primary | Zero unauthorized overrides and complete hierarchy respected. | Overall and by scenario/style; denominator is all retained E4B attempts. | Fully determined A0. |
| E5 | all-attempt mission success | Primary | Every registered task accepted/dispatched/completed before timeout, no listed hard failure, and actual d_min at least 1.50 m. | Every attempted run, including retained infrastructure failures, remains in denominator. | Boolean/denominator determined; depends on unresolved d_min interval. |
| E5 | tracking_RMSE | Primary | RMS 3-D safe-reference to measured-position distance, per UAV and pooled only with declared weighting. | “Scored mission”; weighting not declared by protocol or registry. | **A2 unresolved.** |
| E5 | final_error | Primary | Per-UAV 3-D error at terminal completion and mission aggregate. | Terminal completion differs by mission graph; aggregate operator unspecified. | **A2 unresolved.** |
| E5 | actual_d_min | Primary | Minimum measured pairwise 3-D distance over entire scored mission. | Exact scored-mission start/end are not frozen. | **A2 unresolved.** |
| E5 | iapf_burden | Primary | Activation time plus integral norm delta-p and delta-a. | Exact mission interval and swarm aggregation are not frozen. | Formula A0; **interval/aggregation A2 unresolved.** |
| E5 | latency_decomposition | Primary | LLM inference, parse/validation, snapshot wait, resolution, allocation, dispatch, physical execution. | Required stage boundary timestamps are not defined in sealed text. Missing stages must not be fabricated. | **A2 unresolved.** |

## Ambiguity classification

### A0 — mechanically implied

- Euclidean 3-D distances and vector norms.
- E3 scored start/end and timeout derived from exact registered spec.
- E3 recorded allocator prediction, explicit completion/failure predicates, and v3-only hash gate.
- E4A paired reference-identity invariants.
- E4B six authority predicates, hierarchy, tolerance, and all-attempt rate.
- E2 existing flags, grouping, denominators, and complete-population checks.
- Global rule that every attempt is retained and replacement/sample extension is forbidden.

### A1 — conventional choices requiring a future semantics document

- Monotonic timestamp normalization and deterministic duplicate handling.
- Piecewise-linear boundary interpolation and threshold crossing.
- Trapezoidal integration and time-weighted RMS.
- Coverage and maximum-gap fail-closed criteria.

Repository search found related calibration implementations, including a fixed 0.02 s interpolation grid and transition counting in C0-F. Those are not sufficient authority to silently freeze formal E3/E4/E5 semantics; they may be cited as prior art after the A2 decisions are reviewed.

### A2 — unresolved and blocking

1. **E3 hard-risk event identity:** per-pair events versus the union of any-pair exposure; handling simultaneous/overlapping pairs; merging at exact-threshold or brief re-crossings. The sealed E3 text only says “count”.
2. **E4A acceleration rise time:** no frozen baseline/final fraction, 10–90% convention, scalar norm versus component rule, or multi-peak selection exists. Repository-wide search found no implementation outside the protocol phrase.
3. **E4A scored interval:** no exact end is frozen for control effort, acceleration response, or tracking RMSE.
4. **E4A swarm aggregation:** sum/mean/max/pooled weighting is not specified for attempt-level reporting.
5. **E5 scored mission boundaries:** command submission, first dispatch, first execution command, and terminal mission event are distinct and the protocol does not select exact boundaries for physical metrics.
6. **E5 pooled weighting and mission aggregate:** tracking sample/UAV weighting and final-error aggregation are explicitly required but not defined.
7. **E5 latency stage boundaries:** exact timestamp pairs and overlap rules are not frozen for the seven named components.
8. **Common partial/failure metric policy:** global rules retain failures, but do not freeze when partially observed continuous metrics are reported versus `NA`; numeric zero is forbidden unless actually measured.

These choices can change attempt metrics, condition contrasts, or population summaries. They cannot be selected from demo outcomes.

## Extractor and population validation

Not started, as required by the A2 STOP rule. No live extractor, synthetic fixture, demo replay, result aggregation, analysis bundle, or `formal-analysis-v1` identity was created. Existing E2 scoring was inspected but not modified.

Mechanically determined future grouping keys are recorded but not implemented: E3 `(scenario, seed, P, F)` complete four-cell pairing; E4 `(scenario/geometry, seed, style, explicit/auto/authority class)`; E5 all registered attempts including method and infrastructure failures.

## Campaign protection

Pre- and post-audit Campaign v1 fingerprints passed and are byte-identical: journal exactly #1/#2, accepted formal attempts 2, no #3, launcher commit unchanged, launcher manifest SHA-256 `dd5ed80049b138d4e97c82ce556ed306efbc6e4b2a369f7616be0ff101f332d1`, complete file-map SHA-256 `29a6539e4b6b4372e0adc98bc5b45b4a8a40c20c3f23f244460e45695d14ba37`.

## Required human decisions

Human review must add or approve prospective, outcome-independent definitions for all eight A2 items above. Only then may a new analysis implementation branch freeze A1 conventions, implement extractors and fixtures, replay non-formal demos, and generate an immutable tooling bundle.

`BLOCKED_ANALYSIS_FREEZE`
