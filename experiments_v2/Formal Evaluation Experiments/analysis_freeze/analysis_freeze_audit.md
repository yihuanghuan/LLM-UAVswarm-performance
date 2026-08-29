# Formal Analysis v1 Freeze Audit

Verdict: `ANALYSIS_FREEZE_COMPLETE_READY_FOR_CAMPAIGN_V2_FREEZE`

Campaign v2 was not created or started. Campaign v1 was not resumed. No formal attempt, provider call, PX4/Gazebo run, protocol change, scientific retuning, or demo-outcome-driven rule selection occurred.

## Semantics identity and ambiguity closure

`analysis_semantics_v1` is frozen as `formal-analysis-semantics-v1`, SHA-256 `f19440262a96d784177e5367e8de2a2ec50b7b6ca5b229d4a6d09816408c0db3`. Every formerly blocking definition is recorded as `HUMAN_APPROVED_PROSPECTIVE_ANALYSIS_DECISION`, approved before Campaign-v2 outcomes existed.

All eight A2 decision groups are closed: E3 pair-specific risk events; E4A acceleration rise time; E4A interval; E4A swarm aggregation; E5 physical mission boundary; E5 tracking/final-error/IAPF aggregation; E5 latency stage boundaries; and common partial/failure/NA policy.

**Unresolved A2 issues: 0.**

A1 is frozen to authoritative header time, deterministic duplicate rejection, exact clipping, piecewise-linear boundary/pair synchronization and threshold crossings, trapezoidal integration, time-weighted RMS, zero-order-held Boolean state, no smoothing, and a fail-closed 0.20 s maximum gap derived from the 50 Hz controller plus its frozen neighbor-staleness contract. Descriptive conventions are sample SD, linear quartiles, a two-sided 95% Student-t mean interval, and paired Cohen dz; no inferential test was selected from demo data.

## Analysis contract and extractors

| Family | Frozen outputs | Raw authority and interval | Aggregation / failure behavior |
|---|---|---|---|
| E2 | grounding success, state-consistency violation, dynamic infeasibility, correction/rejection | Existing offline resolution trace and frozen flags | Existing scorer preserved byte-for-byte; exact population and all-attempt denominators |
| E3 v3 | actual/predicted d-min, pair events/exposure/union, success, IAPF time/delta integrals, reference deviation integral/RMS | Global ENU swarm state, recorded allocator result, IAPF/tracking/status/event signals; `t0` to `t0 + exact duration + 2 s` | Pair-seconds for primary exposure; per-pair/UAV diagnostics; complete evidence required |
| E4A | settling, effort, acceleration peak/RMS/rise, tracking RMSE | Interaction command, LADRC output, tracking error, stable-hover state; continuous window `[t0,t0+T_explicit]` | Frozen max/mean/equal-UAV RMS rules; all-UAV rise validity; paired reference hash fails closed |
| E4B | six predicates, override count, priority preservation | Exact authority trace, compiled profiles, physically published profiles | Every predicate retained; missing evidence cannot enter numerator; every attempt remains in denominator |
| E5 | all-attempt success, tracking, final error, d-min, IAPF burdens, seven latency stages | Provider/language record, graph, dispatch commands, global positions, controller signals; first command to graph-derived terminal completion | Equal-UAV tracking, mean/max final error, summed IAPF burden; incomplete physical metrics are `NA`; earlier complete latency remains numeric |

The schema-only synthetic validators retain their historical identities. New scientific extractors are explicitly named `e3_live_metric_extractor.py`, `e4a_live_metric_extractor.py`, `e4b_live_metric_extractor.py`, and `e5_live_metric_extractor.py`.

## Independent validation

Twenty-nine independent hand-check tests pass. They cover known 3-D distances, single/re-entered/overlapping/simultaneous pair events, exact-threshold equality, constant/linear trapezoids and RMS, global-peak 10–90% rise time including multi-peak signals, four-UAV aggregation, all E4B authority cases, sequential/parallel E5 terminal boundaries, five failure/partial-evidence classes, reference identity, exact population membership, and provenance mismatch fail-closed behavior.

Existing regressions also pass: E2 20/20, E3 57/57, E4A 21/21, E4B 23/23, and E5 26/26. E3/E4/E5 tests were run at the recorded execution-code commits; this avoids false failures from old provenance scripts whose pre-demo allowlist intentionally treats later committed demo evidence or `.gitattributes` as a source-tree change. The live extractors independently hash-gate the current sealed protocols, registries, and policy.

## Non-formal demo replay

All 29 retained physical attempts were analyzed twice. Canonical outputs were byte-identical on both passes and all 29 validate against the frozen result schema. Replay summary SHA-256 is `443a07b26afcac9c99b309bbd1817b285e04cc3eb48b5b4521f227ca9d1c7e0c`.

The 25 resolved registered paths contain 23 complete physical extraction records and two expected E5 frozen-method failures. Those two retain numeric completed semantic/service-stage evidence and all-attempt failure outcomes, while physical continuous metrics correctly remain `NA`. All 12 resolved E3 records, all 3 E4A records, and all 5 E4B records have the evidence required by their applicable metrics. The four superseded pre-fix attempts remain separately represented as incomplete, partial, or provenance-fail-closed history; none was deleted or overwritten.

Every replay output is labelled `dataset_class=engineering_validation`, `accepted_formal_result=false`, `scientific_use=analysis_tool_validation_only`, and `NOT_FORMAL_RESULT`. No demo effect size, ordering, or paper conclusion was interpreted.

## Population readiness

E3 formal input must exactly match all 360 registered IDs and every P0/P1 × F0/F1 cell; missing or duplicate cells fail. E4A must exactly match 45 IDs and shared reference identities across each style triplet. E4B and E5 exact-population gates require 60 and 25 IDs respectively. E4B Priority-Preservation and E5 success always retain all attempts in their denominators. Continuous summaries explicitly report valid N and NA N, and partial diagnostics never enter primary contrasts.

Descriptive and paired-effect infrastructure provides mean, sample SD, median, IQR, valid/NA N, paired differences, 95% mean CIs, and Cohen dz. No post-hoc filtering or significance-driven method selection is implemented.

## Frozen tooling identity

Branch: `formal/analysis-v1`  
Tooling source commit: `5546e2b673e3368574c2118ecc1943fab382f745`  
Bundle files: 17  
`formal-analysis-v1` bundle SHA-256: `9210245b12a108447cf03715ca6fd90e6ad3bf85fcab7a61e4dcfc6e5ac545b4`

The bundle manifest pins the semantics, schemas, shared numeric/rosbag/provenance utilities, four extractors, population preparation, replay tooling, fixtures, bundle builder, and preserved E2 scorer dependency. Population output records every consumed attempt-result hash.

## Campaign protection

Final protection check passed: Campaign v1 still has exactly journal #1/#2, accepted count 2, no #3, unchanged cursor, launcher manifest SHA-256 `dd5ed80049b138d4e97c82ce556ed306efbc6e4b2a369f7616be0ff101f332d1`, and byte-map SHA-256 `29a6539e4b6b4372e0adc98bc5b45b4a8a40c20c3f23f244460e45695d14ba37`.

`ANALYSIS_FREEZE_COMPLETE_READY_FOR_CAMPAIGN_V2_FREEZE`
