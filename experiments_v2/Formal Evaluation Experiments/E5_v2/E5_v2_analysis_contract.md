# E5-v2 prospective analysis contract

Status: frozen candidate contract for human review. This contract is created before any E5-v2 formal outcome and cannot be revised in response to outcomes.

## Scope

E5-v2 is descriptive end-to-end integration evidence. It does not test C1, C2, or C3, and does not establish formal/asymptotic scalability or arbitrary-N generalization. No hypothesis requires larger N to be worse, equal, or better.

## Population and denominators

The registered population is exactly 60 cold-start attempts in the frozen order: E5-v2A 15 and E5-v2B 45.

- **All-attempt denominator:** every registered attempt, including semantic, resolver, planning, execution, controller/PX4, and infrastructure failures. A failed attempt consumes its order slot and seed.
- **Scientific-complete denominator:** attempts for which the registered scientific pipeline could be evaluated through its defined scientific terminal result, reported separately from the all-attempt denominator.
- **Infrastructure outcomes:** classified separately and retained in the all-attempt denominator. They are never silently discarded, retried for replacement, or converted to scientific failures/successes.

No failed seed is replaced. No best attempt is selected. A formal attempt is never rerun merely because it failed.

## Outcome classification

Each attempt records separate stage outcomes for semantic frontend, Candidate schema/semantic validation, resolver, planning, mission execution, control/PX4, scientific mission result, and infrastructure result.

Mission success requires all registered tasks to be accepted/dispatched and reach their registered completion event before timeout, no hard component/infrastructure failure, no failsafe/unintended disarm, and observed `d_min >= d_hard = 1.50 m` over the scored mission.

Unavailable continuous measurements are `NA` with an explicit reason/stage. They are not set to zero and are excluded only from that metric's continuous summary; the attempt remains in binary/all-attempt summaries.

## Reporting strata

Report without pooling:

- substudy: E5-v2A versus E5-v2B;
- E5-v2A scenario A1/A2/A3;
- E5-v2B task family SIMPLE/UNDER_SPECIFIED/COMPOSITIONAL;
- E5-v2B swarm size N=8/12/16;
- each E5-v2B N×family cell.

Old E5-v1 and new E5-v2 never share a success-rate denominator. Historical E5-v1 results may be described only as a separate registry with distinct scientific inputs.

## Binary summaries

For all-attempt mission success, scientific completeness, infrastructure failure, resolver success, Candidate correctness, mission completion, failsafe, and hard failure, report numerator/denominator and proportion. Where an interval is useful, report a two-sided Wilson 95% confidence interval with z=1.959963984540054 and no continuity correction. An interval is descriptive, not a scale hypothesis test.

## Continuous summaries

For each metric and reporting stratum, report available N, mean, median, sample SD (NA for N<2), IQR (Q3−Q1), and optionally min/max. Never impute zero for an infrastructure failure or an unavailable stage.

E5-v2A continuous outcomes include resolved `c_exec`, `r_exec`, `T_exec`, actual `d_min`, `J_hard`, tracking RMSE, final error, completion time, and available latency decomposition. Each resolved value is audited against frozen state semantics, qualitative policy, workspace, safety geometry, and dynamic feasibility.

E5-v2B continuous outcomes include `d_min`, `J_hard`, tracking RMSE, final error, completion time, and deterministic-stage runtimes by N/family. Report validation, state resolution, geometry, allocator, and execution-profile compilation latency only when observable without a method-semantic change. LLM latency is separate from deterministic runtime.

## Interpretation boundary

Allowed wording is limited to observed operation for tested sizes, for example: “Deterministic pipeline runtime increased with swarm size but remained operational for the tested N,” if the data support it. Prohibited claims include linear/near-linear scalability, real-time scalability, arbitrary-N scaling, or universal swarm-size generalization.
