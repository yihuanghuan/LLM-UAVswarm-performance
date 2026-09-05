# E1–E4 Experimental Evidence Reference

## Purpose, scope, and source notation

This document is the source-audited factual and interpretive reference for writing the paper's Experiments and Results sections. It covers only E1, E2, E3-v4, E4A, and E4B. It is not manuscript prose, and it deliberately preserves qualifications, missing-data rules, negative findings, and claim boundaries that a shorter paper treatment could otherwise obscure.

Three labels are used throughout:

- **FACT** records a design feature, observation, or frozen analysis result.
- **INTERPRETATION** states the scientifically bounded inference supported by those facts.
- **PAPER-WRITING RECOMMENDATION** advises how to present the evidence without changing its meaning.

Inline source tags refer to immutable files listed with commit and blob SHA in `source_manifest.json`. The principal tags are:

| Tag | Frozen authority |
|---|---|
| `E1-PROTOCOL`, `E1-REGISTRY`, `E1-DATA`, `E1-ORDER` | E1 protocol, registered dataset, dataset records, and inference order at `8f050943c74dc48529aa48f696146c07f7a4a83e` |
| `E1-SCORE`, `E1-AUDIT`, `E1-MANIFEST` | Accepted E1 formal score, completeness audit, and result manifest at the same commit |
| `E1-SCORER` | Frozen E1 scoring implementation consulted to verify the task-instance denominator in `score.json` at the same commit |
| `C2-RAW-E2`, `C2-RAW-E4` | Campaign-v2 E2 and E4 frozen registries at `33538b91ab9e0c53b918cdc0e47e3b7fa6f08592` |
| `ANALYSIS-SEMANTICS` | Prospectively frozen Campaign-v2 analysis semantics at `023bf48e521e3a6d2383da4699d8820dcf603da7` |
| `E2-SUMMARY`, `E2-PAIRS`, `E2-ATTEMPTS` | Frozen E2 final analysis outputs at `511192273a61f97e2742a1cc6608e18ed960cc1f` |
| `E4A-SUMMARY`, `E4A-PAIRS`, `E4A-ATTEMPTS` | Frozen E4A final analysis outputs at the same commit |
| `E4B-SUMMARY`, `E4B-CHECKS`, `E4B-ATTEMPTS` | Frozen E4B final analysis outputs at the same commit |
| `E3-REGISTRY`, `E3-CONTRACT`, `E3-COMPLETION` | E3-v4 sealed registry, analysis contract, and campaign completion audit at `c62e9b43dbed0470feb46d4cf148081d681c26e1` |
| `E3-REPORT`, `E3-SUMMARY`, `E3-FACTORIAL`, `E3-BINARY`, `E3-MISSING`, `E3-OPERATIONS`, `E3-ENDPOINT`, `E3-CELL` | Frozen E3-v4 confirmatory report, outputs, missingness/operational tables, endpoint adjudication, and primary cell descriptives at the same commit |

No inferential statistic was recalculated for this reference. Percentages explicitly marked “presentation calculation” are direct divisions of frozen counts. Decimal rounding in prose follows the frozen human-readable reports; tables retain enough digits to identify the machine-readable value.

## Experiment-to-contribution evidence map

| Contribution | Experiment | Question asked | Evidence role | Maximum safe high-level claim |
|---|---|---|---|---|
| Contribution 1: late-bound, information-aligned semantic-to-physical commitment | E1 | Can the registered language interface capture the intended semantic task while preserving physical quantities that are not yet resolvable? | Semantic representation and under-specification | On the frozen candidate-semantic dataset, valid commands were represented accurately without premature numerical commitment. |
| Contribution 1: late-bound, information-aligned semantic-to-physical commitment | E2 | Does the time at which unresolved physical quantities are committed matter when execution state changes? | Paired causal timing assay | In the tested state-shift cases, information-aligned late commitment prevented the registered stale/infeasible outcomes produced by early commitment. |
| Contribution 2: planning–execution safety decomposition for UAV-swarm reconfiguration | E3-v4 | Are predictable structural risk and post-planning residual execution risk handled by distinct planning and feedback responsibilities? | Confirmatory 2×2 planning-by-feedback assay | The frozen scenarios support planning–execution safety decomposition within the tested UAV-swarm reconfiguration domain. |
| Contribution 3 / secondary contribution: constraint-prioritized, authority-bounded behavioral grounding | E4A | Do bounded motion-style semantics produce measurably different low-level behavior under a fixed task and safety envelope? | Behavioral distinguishability | Style changed control intensity, acceleration behavior, and tracking characteristics in the tested maneuvers, without universal ordering on every dynamic metric. |
| Contribution 3 / secondary contribution: constraint-prioritized, authority-bounded behavioral grounding | E4B | Does style remain subordinate to explicit task, feasibility, safety, and timing authority? | Authority preservation | No registered higher-priority authority override was observed in the 60 tested authority-conflict attempts. |

**FACT.** E1 asks what semantic information may remain unresolved; E2 asks why resolving that information at the right time matters physically. E3-v4 separately manipulates planning and feedback in predictable, residual, and mixed risk families. E4A establishes that style is behaviorally consequential, while E4B tests whether that consequence stays inside the frozen authority hierarchy. These roles are defined by the sealed registries and frozen claim adjudications. [Sources: `E1-PROTOCOL`; `C2-RAW-E2`; `E3-REGISTRY`; `C2-RAW-E4`; E2/E4 claim-adjudication files in the manifest.]

**INTERPRETATION.** The evidence chain is intentionally modular. No single experiment establishes an end-to-end universal property: E1 does not test physical state change, E2 does not test language accuracy, E3-v4 does not test semantic grounding, and E4A does not by itself establish authority preservation.

**PAPER-WRITING RECOMMENDATION.** Organize the paper around contribution-level questions rather than chronological experiment numbering. Introduce E1 and E2 as complementary evidence for Contribution 1; present E3-v4 as the confirmatory mechanism assay for Contribution 2; and present E4A and E4B as the two required halves of bounded behavioral grounding.

# E1 — Semantic Grounding Without Premature Physical Commitment

## Research question and necessity

E1 tests whether the frozen candidate semantic interface can encode the intended task semantics of the registered commands while leaving state-dependent center, scale, and timing quantities symbolic until the runtime has the information required to resolve them. The relevant failure mode is **premature numerical commitment**: replacing a registered unresolved `c`, `r`, or `T` field with a number during language interpretation, before the corresponding runtime state or policy is available. [Sources: `E1-PROTOCOL`; `E1-REGISTRY`.]

E1 was necessary because a late-binding architecture has no value if the language-facing representation either loses the requested task or forces every request into an early numerical form. Conversely, accurate semantic extraction alone would not demonstrate that delayed resolution matters under changing physical state. E1 therefore evaluates the semantic half of Contribution 1; the physical consequence of commitment timing is reserved for E2.

This is a finite, candidate-registry evaluation. It is not an open-world natural-language-understanding benchmark. The commands, expected validity labels, rejection classes, ground-truth Candidate Missions, category distribution, model configuration, and randomized inference order were frozen before the accepted formal run. [Sources: `E1-REGISTRY`; `E1-DATA`; `E1-ORDER`; `E1-MANIFEST`.]

## Dataset and formal protocol

**FACT — population.** The sealed dataset contains 120 commands: 96 expected-valid and 24 expected-invalid. The formal audit recovered exactly 120 terminal command records and passed the sealed-denominator, terminal-set, inference-order, attempt-retention, retry-accounting, provenance, and worktree checks. No command ended as an infrastructure failure. [Sources: `E1-REGISTRY`; `E1-AUDIT`; `E1-MANIFEST`.]

The 96 valid commands were deliberately distributed across semantic dimensions rather than treated as a homogeneous prompt set:

| Registered valid-command dimension | Frozen distribution |
|---|---|
| Mission structure | single 72; sequential 12; parallel 12 |
| Center semantics | absolute 24; relative 24; auto 24; mixed 24 |
| Scale semantics | explicit 15; compact 15; normal 14; spacious 14; auto 14; mixed 24 |
| Timing semantics | explicit 36; auto 36; mixed 24 |
| Motion style | smooth 24; normal 24; aggressive 24; mixed 24 |
| Safety semantics | numeric 54; qualitative-safer 18; mixed 24 |
| Transition | direct 60; continuous 12; hover-and-wait 24 |

[Frozen source for all counts: `E1-REGISTRY`.]

The 24 invalid commands were equally divided among six frozen expected rejection classes: incomplete instruction, contradictory semantics, unavailable UAV ID, formation-semantic violation, illegal transition, and unsupported/ambiguous semantics, four commands per class. Expected classes could not be relabeled from model prose after the run. A command counted as rejected only when no executable Candidate survived the registered parsing, schema, availability, semantic, mission-compilation, and pre-dispatch validation gates after the retry policy. Later flight behavior was irrelevant to E1 invalid rejection. [Source: `E1-PROTOCOL`.]

**FACT — provider and attempt structure.** One **command** is one registered input and contributes once to the 120-command terminal denominator. A **provider attempt** is one model call made under the parser retry policy. A command could therefore generate one, two, or three provider attempts but still produce one terminal record. The accepted formal run made 163 provider attempts for 120 commands: 162 returned a model response and one raised a provider exception. The frozen model was `MiniMax-M2.7-highspeed`, with temperature 0.0, top-p 0.01, maximum 4,000 completion tokens, JSON-object response format, and at most three attempts per command. [Sources: `E1-MANIFEST`; `E1-AUDIT`.]

Retries completed before moving to the next command in the sealed randomized permutation. Every attempt was retained; manual deletion, manual command rerun, and a second formal batch were prohibited and audited as absent. [Sources: `E1-PROTOCOL`; `E1-ORDER`; `E1-MANIFEST`.]

## Registered metrics and scoring semantics

The main E1 metrics were fixed as follows. [Source: `E1-PROTOCOL`.]

1. **Valid-command schema acceptance:** expected-valid commands producing schema-valid Candidate Mission JSON, divided by 96.
2. **Semantic field accuracy:** macro accuracy over task fields `U,F,c,r,T,m,s,q` plus per-command mission-relation accuracy. The task-field denominators are task instances, not commands: the 96 valid commands contain 120 task instances because sequential and parallel commands contain multiple tasks. Mission relations remain command-level with denominator 96. This explains the apparent 120-versus-96 denominator difference in `score.json`; it is not a source disagreement. [Cross-check: `E1-SCORE`; `E1-DATA`; `E1-SCORER` in the manifest.]
3. **Exact semantic task accuracy:** complete normalized Candidate Mission equality for each expected-valid command, divided by 96. Normalization canonicalized only registered equivalences such as JSON key order, numeric integer/float equivalence, UAV-set ordering, and parallel-task ordering; it did not repair missing, extra, schema-invalid, or semantically incorrect fields.
4. **Invalid-command rejection:** correct terminal rejection under each immutable expected class, divided by 24.
5. **Premature numerical commitment:** unresolved relative/maintain-current/auto center, qualitative/auto scale, or auto timing fields incorrectly replaced by numbers, divided by all registered unresolved opportunities. Qualitative safer/cautious/conservative safety semantics were frozen to `s=1.0` and were explicitly not counted as premature commitment.
6. **Latency:** provider-call wall latency per attempt and total command-to-terminal latency, summarized by median and registered upper percentiles.
7. **Secondary diagnostics:** strict JSON-format compliance, retry distribution, rejection-class confusion, and exact accuracy by registered category.

## Results

### Valid semantic representation

| Outcome | Frozen result | Unit/denominator | Source |
|---|---:|---|---|
| Valid-command schema acceptance | 96/96 = 1.0000 | valid commands | `E1-SCORE` |
| Exact semantic task correctness | 96/96 = 1.0000 | valid commands | `E1-SCORE` |
| Semantic-field macro accuracy | 1.0000 | eight task-field accuracies plus mission-relation accuracy | `E1-SCORE` |
| Each of `U,F,c,r,T,m,s,q` | 120/120 = 1.0000 | valid-command task instances | `E1-SCORE`; cross-checked against `E1-SCORER` |
| Mission relations | 96/96 = 1.0000 | valid commands | `E1-SCORE` |
| Premature numerical commitment | 0/225 = 0.0000 | registered unresolved numerical opportunities | `E1-SCORE` |
| Normalization errors | 0 | scorer diagnostics | `E1-SCORE` |

Exact valid-command accuracy was 100% in every registered category bucket reported by the frozen scorer, including all mission structures, center/scale/timing categories, styles, safety categories, transition modes, formation categories, and both parallel-completion variants. This is a dataset-stratified observation, not evidence of open-world coverage. [Source: `E1-SCORE`.]

### Invalid-command rejection

| Frozen expected rejection class | Rejected / total | Rate |
|---|---:|---:|
| Incomplete instruction | 4/4 | 1.0000 |
| Contradictory semantics | 3/4 | 0.7500 |
| Unavailable UAV ID | 4/4 | 1.0000 |
| Formation-semantic violation | 4/4 | 1.0000 |
| Illegal transition | 0/4 | 0.0000 |
| Unsupported or ambiguous semantics | 4/4 | 1.0000 |
| **Overall** | **19/24** | **0.7916667** |

[Frozen source for the table: `E1-SCORE`. A paper-friendly percentage of 79.17% is a presentation calculation, `19/24 × 100`, not a new estimate.]

The most important negative result is the complete miss on the registered illegal-transition subset: all four such commands passed the frozen pre-dispatch gates rather than being rejected. One contradictory-semantics case was also not rejected. This prevents any broad claim of reliable invalid-command or transition-policy rejection.

### Output format and retry behavior

Strict JSON-format compliance was 0/162 returned provider responses under the frozen strict criterion. This criterion evaluates the provider response format, not whether the downstream parser ultimately produced a valid Candidate Mission. Thus 96/96 valid schema acceptance can coexist with 0/162 strict-format compliance: the retry/parser pathway recovered usable structured content, while the provider did not satisfy the stricter direct-output form. [Sources: `E1-SCORE`; `E1-PROTOCOL`.]

The retry distribution was:

| Retries after first attempt | Commands | Total provider attempts contributed |
|---:|---:|---:|
| 0 | 96 | 96 |
| 1 | 5 | 10 |
| 2 | 19 | 57 |
| **Total** | **120** | **163** |

[Frozen counts: `E1-SCORE`; provider-return/exception accounting: `E1-MANIFEST`. The 24/120 = 20.00% of commands needing at least one retry is a labeled presentation calculation.]

### Latency

| Latency quantity | Count | Median (ms) | P90 (ms) | P95 (ms) | P99 (ms) | Sum (ms) |
|---|---:|---:|---:|---:|---:|---:|
| Provider call per attempt | 163 | 17,334.519769 | 35,175.464563 | 39,521.770003 | 85,013.008471 | 3,477,799.132937 |
| Command to terminal outcome | 120 | 20,962.5 | 57,240.7 | 72,855.65 | 104,153.35 | 3,573,259.0 |

[Frozen source: `E1-SCORE`; percentile method: linear interpolation at rank `(n−1)p`.]

For reader intuition only, dividing the medians by 1,000 gives approximately 17.335 s per provider attempt and 20.963 s per terminal command; these are presentation-unit conversions, not separately analyzed endpoints.

## Interpretation and boundaries

**INTERPRETATION — supported.** The candidate semantic interface represented all 96 registered valid commands with schema-valid, exactly correct normalized task semantics and preserved all 225 registered unresolved numerical opportunities. Within this finite dataset, the evidence strongly supports the semantic-side proposition that unresolved physical values can remain symbolic without losing the intended valid task.

**INTERPRETATION — not supported.** E1 does not support reliable invalid-command rejection in general, robust illegal-transition rejection, stable strict-JSON provider behavior, open-world language understanding, general linguistic competence, or superiority over another interface. The 19/24 invalid result and 0/4 illegal-transition result are direct counterweights to overbroad claims; the 0/162 format-compliance observation also makes any claim of natively reliable strict structured output untenable under this exact provider/configuration.

E1 also does not demonstrate the physical benefit of late commitment. Its zero premature-commitment result establishes what stayed unresolved at the semantic boundary, but no execution-state change is manipulated in E1. E2 supplies the paired physical timing evidence.

**PAPER-WRITING RECOMMENDATION.** Use wording such as: “On a frozen 120-command candidate-semantic registry, all 96 valid commands were represented exactly and no premature numerical commitments occurred across 225 registered unresolved opportunities; invalid rejection was incomplete (19/24), including 0/4 illegal-transition rejections.” Keep “candidate,” “frozen registry,” and the invalid-rejection qualification visible.

## Suggested paper presentation

- **Main paper compact table:** dataset size; 96/96 schema acceptance; 96/96 exact task accuracy; 0/225 premature commitments; 19/24 invalid rejection; 0/4 illegal-transition rejection; 0/162 strict-format compliance; and 163 attempts/120 terminal commands. This table shows both strengths and failures.
- **Main paper prose:** explain the command-versus-provider-attempt distinction and state that 24 commands required retry. Mention median command-to-terminal latency if latency is part of the paper's systems story; otherwise leave the full percentile row to the supplement.
- **Supplement:** complete category distributions, per-class invalid confusion matrix, full provider/command latency percentiles, token diagnostics, normalization contract, inference permutation, and retry accounting.
- **Do not graph:** exact accuracy by every registered category. With all categories at 100%, a large figure adds little beyond a compact statement and supplementary table.

# E2 — Early vs Information-Aligned Late Commitment

## Research question and necessity

E2 tests the causal consequence of **physical commitment timing**, not language accuracy. Both conditions receive the same frozen Candidate semantics and English command; E2 changes only whether unresolved center/scale/timing fields are numerically resolved using the parse-time snapshot or remain symbolic until the registered execution-time snapshot and runtime stages. [Source: `C2-RAW-E2`.]

The relevant failure mode is stale commitment. If state changes after interpretation but before execution, an early numerical value may no longer describe the intended state-relative geometry or feasible timing. A late value can incorporate the execution snapshot. E2 was necessary because this physical consequence cannot be inferred from E1's semantic correctness alone.

## Experimental design

**FACT — paired population.** E2 contains 120/120 scientifically complete attempts and no infrastructure failures. These form 60 paired Early/Late comparisons. Thirty pairs are `SHIFT` and thirty are `NO_SHIFT`; equivalently, each of six scenarios contributes five seeds to each state condition, with both commitment conditions in every scenario/state/seed pair. [Sources: `E2-SUMMARY`; `E2-ATTEMPTS`; `C2-RAW-E2`.]

The conditions were:

- **Early Commitment:** resolve `c/r/T` at the parse-time snapshot, replace only those fields with absolute/explicit numerical values, and retain that request for execution. The frozen feasibility gate remains active and may raise an early explicit duration; such a raise counts as correction.
- **Information-Aligned Late Commitment:** retain the untouched Candidate, including relative/maintain-current/auto center, qualitative/auto scale, and auto duration, until the frozen production runtime resolves them using execution-time state.

The invariant fields were task ID, UAV set, formation, motion style, safety value, and transition. Prompt, schema, semantic interpretation, runtime state within a pair, seed, policy, allocator, and controller were prohibited from differing. The parse snapshot was common, the execution epoch was two seconds later, and the `NO_SHIFT` execution snapshot equaled the parse snapshot except for epoch. `SHIFT` applied a deterministic registered state operator before execution-snapshot capture. [Source: `C2-RAW-E2`.]

The six scenario mechanisms were designed to expose different unresolved quantities:

| Scenario | Unresolved fields | Registered shift role |
|---|---|---|
| E2-RSV-01 | center, scale, duration | Translate all participants; runtime-state translation test |
| E2-PES-01 | relative center, scale, duration | Translate all participants by a different world-frame vector |
| E2-RC-01 | relative center, scale | Isolated relative-center grounding |
| E2-QS-01 | qualitative scale | Scale-invariance control with absolute center/explicit duration |
| E2-AT-01 | automatic duration | Move participants farther from fixed targets; feasibility/timing update |
| E2-DF-01 | center, scale, duration | Nonuniform state shift designed to require dynamic-feasibility correction |

[Frozen source: `C2-RAW-E2`.]

Registered outcomes were executable grounding success, state-consistency violation, dynamic infeasibility, correction, rejection, and correction-or-rejection. Every result below is from the frozen Campaign-v2 analysis; no language inference score is imported from E1.

## Results

### Outcome counts by state condition

| State condition | Commitment | N | Executable | State-consistency violation | Dynamic infeasibility | Correction | Rejection | Correction or rejection |
|---|---|---:|---:|---:|---:|---:|---:|---:|
| NO_SHIFT | Early | 30 | 30 | 0 | 0 | 0 | 0 | 0 |
| NO_SHIFT | Information-Aligned Late | 30 | 30 | 0 | 0 | 0 | 0 | 0 |
| SHIFT | Early | 30 | 30 | 25 | 15 | 15 | 0 | 15 |
| SHIFT | Information-Aligned Late | 30 | 30 | 0 | 0 | 0 | 0 | 0 |

[Frozen summary source: `E2-SUMMARY`; row-level cross-check: `E2-ATTEMPTS`.]

All 60 attempts in each commitment condition produced executable grounding, and rejection was 0/60 in both. The adverse outcomes were concentrated in shifted Early cases. In `NO_SHIFT`, both conditions had zero registered adverse outcomes. [Sources: `E2-SUMMARY`; `E2-ATTEMPTS`.]

Scenario cross-checks show that shifted Early state-consistency violations occurred in all five seeds of E2-AT-01, E2-DF-01, E2-PES-01, E2-RC-01, and E2-RSV-01, but not E2-QS-01: 25 total. Shifted Early dynamic infeasibility and correction occurred in all five seeds of E2-AT-01, E2-DF-01, and E2-RSV-01: 15 total. Every corresponding Late count was zero. [Source: `E2-ATTEMPTS`; the frozen `E2-SUMMARY` scenario-consistency section gives the same pairing pattern.]

### Frozen paired effects

All contrasts below are Late minus Early. Negative values therefore mean fewer adverse outcomes under late commitment.

| Population | Outcome | Mean paired difference | Frozen 95% Student-t CI | Cohen's dz | Pair N |
|---|---|---:|---:|---:|---:|
| SHIFT | State-consistency violation | −0.8333333 | [−0.9748726, −0.6917941] | −2.1985 | 30 |
| SHIFT | Dynamic infeasibility | −0.5000000 | [−0.6898948, −0.3101052] | −0.9832 | 30 |
| SHIFT | Correction | −0.5000000 | [−0.6898948, −0.3101052] | −0.9832 | 30 |
| SHIFT | Correction or rejection | −0.5000000 | [−0.6898948, −0.3101052] | −0.9832 | 30 |
| SHIFT | Rejection | 0.0000000 | [0, 0] | NA (zero variance) | 30 |
| NO_SHIFT | Every registered adverse outcome | 0.0000000 | [0, 0] | NA (zero variance) | 30 |
| All pairs | State-consistency violation | −0.4166667 | [−0.5450986, −0.2882348] | −0.8381 | 60 |
| All pairs | Dynamic infeasibility/correction | −0.2500000 | [−0.3628030, −0.1371970] | −0.5725 | 60 |

[Frozen source: `E2-SUMMARY`; paired-difference row verification: `E2-PAIRS`. “NA” is retained rather than converting a degenerate effect size to zero.]

## Interpretation and boundaries

**INTERPRETATION — supported.** When relevant execution state changed, parse-time numerical commitment became stale or required registered feasibility correction in the tested cases. Preserving the unresolved intent until the execution snapshot eliminated all observed state-consistency violations, dynamic infeasibility outcomes, and corrections in the matched Late cases. When the state did not change, neither condition incurred an adverse timing outcome. This pattern supports an information-availability mechanism rather than an unconditional advantage of one condition.

The lack of rejection in both conditions matters: Late did not obtain its advantage by refusing difficult requests, and Early still produced executable grounding. The result concerns the consistency and feasibility of what was executed, not whether a Candidate could be made executable.

**INTERPRETATION — joint role with E1.** E1 demonstrates that the candidate representation can preserve state-dependent values symbolically while retaining the intended semantic task. E2 demonstrates why the timing of resolving those values matters physically. Together, they support Contribution 1 more strongly than either experiment alone: E1 answers **what should remain unresolved**, and E2 answers **why information-aligned resolution timing matters**.

**INTERPRETATION — not supported.** E2 does not show that late binding is universally optimal, that every early commitment is incorrect, that every state change harms early commitment, that late commitment improves every possible metric, or that the tested policy is globally optimal for robotic planning. E2 is bounded to the six registered offline wrapper scenarios, exact deterministic state operators, frozen allocator/feasibility policy, and evaluated adverse outcomes. E2 also does not compare alternative language models or semantic interfaces.

**PAPER-WRITING RECOMMENDATION.** Lead with the interaction between state change and commitment timing: “Across 30 shifted pairs, Early produced 25 state-consistency violations and 15 infeasibility/correction outcomes, whereas Late produced none; across 30 no-shift pairs, neither condition produced an adverse timing outcome.” Then explain the same-command/same-semantics controls. Avoid presenting the all-pair rate alone, because pooling shifted and no-shift pairs obscures the mechanism.

## Suggested paper presentation

- **Main paper:** a compact SHIFT/NO_SHIFT by Early/Late table or grouped dot/bar plot for state inconsistency and correction/infeasibility. Include exact counts and pair N; use the frozen paired confidence intervals if space permits.
- **Main prose:** one sentence establishing 120/120 completeness, 60 pairs, and unchanged executable grounding/rejection; one sentence interpreting the state-change concentration.
- **Supplement:** per-scenario breakdown, full paired-difference arrays, Cohen's dz, all registered outcomes, and exact scenario operators/resolution values.
- **Avoid:** a plot that collapses SHIFT and NO_SHIFT. It would make the causal timing mechanism look weaker and less specific than the registered design.

# E3-v4 — Planning–Execution Safety Decomposition

## Research question and historical context

E3-v4 asks whether two different classes of safety risk require two different responsibilities: whether planning should remove risk predictable from the committed geometry and assignment, and whether closed-loop feedback should reduce risk that appears only after planning because execution deviates from the committed plan. The contribution-level question is not whether two software modules exist, but whether the independently manipulated responsibilities produce the expected, mechanism-specific safety effects. [Sources: `E3-REGISTRY`; `E3-CONTRACT`; `E3-REPORT`.]

The historical E3-v3 assay remains immutable but is not paper-primary confirmatory evidence for the feedback side. Its original residual-risk manipulation did not reliably induce the registered F0 residual-risk state, and the mixed-risk cases did not retain enough post-planning residual risk to resolve the feedback responsibility. E3-v4 was therefore separately redesigned around deterministic post-planning execution deviations, preregistered, sealed, activated, run as a standalone 360-attempt campaign, and analyzed under a frozen contract. No E3-v3 observation is pooled with E3-v4. [Sources: `E3-REGISTRY`; `E3-REPORT`.]

This history should be described as an assay-identification problem, not as a “failed scientific result.” The original manipulation did not instantiate the state needed to evaluate the registered feedback-side contrast; E3-v4 fixed the assay while preserving the question and freezing the new design before formal execution.

## Formal 2×2 design

The planning factor is:

- **P0:** distance-only baseline assignment (`distance_hungarian`).
- **P1:** safety-aware assignment (`safety_aware`).

The feedback factor is:

- **F0:** feedback avoidance off.
- **F1:** IAPF dual feedback avoidance on (`iapf_dual`), with frozen escape mode and filter parameter.

The four cells are therefore P0_F0, P0_F1, P1_F0, and P1_F1. No condition-specific tuning was permitted. Runtime mode, LADRC acceleration-control mode, policy, normal motion style, safety multiplier, direct transition, scenario geometry, seed, and relevant execution rules were held fixed within registered blocks. [Source: `E3-REGISTRY`.]

The manipulation families isolate risk mechanisms:

| Family | Risk mechanism | Scenarios | Responsibility targeted |
|---|---|---|---|
| A — predictable structural risk | Assignment/path conflict is visible at planning time; no post-planning deviation is injected. | E3-A-01, a four-UAV assignment-conflict target set; E3-A-02, an eight-UAV reversed-circle target set | Planning, P1 versus P0 |
| B — residual execution risk | Nominal planning input contains no registered structural conflict; a deterministic command delay or reference deviation is introduced only after planning commitment and excluded from planner prediction. | E3-B-01, 0.4 s command delay; E3-B-02, 1.5 m reference offset for 3.0 s beginning at 3.5 s | Feedback, F1 versus F0 |
| C — mixed, spatially isolated risk | A predictable structural subsystem and a post-planning residual-risk subsystem coexist in spatially separated UAV subsets. | E3-C-01 combines the A-01 structure with the B-01 timing deviation; E3-C-02 combines the A-01 structure with a B-02-style reference deviation | Both responsibilities and their interaction |

[Frozen source: `E3-REGISTRY`.]

The execution deviations in Families B and C were required to begin only after planning commitment, remain absent from the planner input and prediction, satisfy frozen timing and endpoint-delivery tolerances, and fail closed as infrastructure failure if delivery could not be verified. Staging moved the swarm to the exact initial geometry and required 2.0 s of stable state; staging was not scored. Scoring began at the first nominal execution-command timestamp and ended after the registered duration plus 2.0 s. [Source: `E3-REGISTRY`.]

## Registered sample, pairing, and primary population

**FACT — registered design.** Six fixed scenarios, 15 registered paired seeds, and four factorial cells yield 360 registered slots:

\[
6\ \text{scenarios}\times 15\ \text{seeds}\times 4\ \text{cells}=360\ \text{slots}.
\]

The repeated-measures block is `b = (scenario, seed)`. A primary block must contain exactly one scientifically eligible attempt in each of the four cells. There are 90 registered blocks, or 30 possible blocks per family. The two scenarios within a family form fixed strata. Correlated simple contrasts inside a block are not treated as independent observations. [Sources: `E3-REGISTRY`; `E3-CONTRACT`.]

**FACT — final accounting.** All 360 slots were consumed in frozen order. The campaign produced 343 scientifically successful attempts and 17 infrastructure failures, with no other statuses, replacement attempts, or additional samples. Seventy-four blocks contained four scientific successes; 16 blocks were incomplete, including one block with two failed cells. The primary complete-block population is therefore 74 blocks and 296 attempts. The 47 successful cells belonging to incomplete blocks remain available for sensitivity/descriptive summaries but are excluded from every primary factorial contrast. [Sources: `E3-COMPLETION`; `E3-REPORT`; `E3-SUMMARY`.]

Complete primary blocks by family and scenario were:

| Family | Scenario 1 complete blocks | Scenario 2 complete blocks | Family total |
|---|---:|---:|---:|
| A | E3-A-01: 14 | E3-A-02: 9 | 23 |
| B | E3-B-01: 14 | E3-B-02: 12 | 26 |
| C | E3-C-01: 12 | E3-C-02: 13 | 25 |
| **Total** |  |  | **74** |

[Frozen sources: scenario-stratum counts in `E3-FACTORIAL`; family totals in `E3-SUMMARY`.]

## Missingness and infrastructure failures

The primary missing-data rule was frozen before effect estimation: if any of the four cells in a block was an infrastructure failure, the entire block was excluded from the primary factorial population. There was no replacement, imputation, best-retry selection, extra sample, or significance-triggered extension. Missing attempts remained in the all-attempt accounting. The analysis makes no missing-completely-at-random (MCAR) claim. [Sources: `E3-CONTRACT`; `E3-COMPLETION`; `E3-MISSING`.]

| Missingness dimension | Frozen distribution of infrastructure failures |
|---|---|
| Family | A: 8/120; B: 4/120; C: 5/120 |
| Scenario | E3-A-01: 1/60; E3-A-02: 7/60; E3-B-01: 1/60; E3-B-02: 3/60; E3-C-01: 3/60; E3-C-02: 2/60 |
| Condition | P0_F0: 6/90; P0_F1: 3/90; P1_F0: 5/90; P1_F1: 3/90 |
| Failure mechanism | formal metric/delivery verification: 6; stage deviation-driver failure: 7; interaction deviation-driver failure: 3; all-UAV readiness failure: 1 |

[Frozen sources: `E3-MISSING`; `E3-REPORT`.]

Raw-storage accounting was also explicit: 359 slots had verified raw archives and slot 105 was a preregistered pre-raw all-UAV readiness failure. The completion audit recorded no pending archive and no raw-evidence loss. This storage fact does not make an unavailable scientific metric numeric; infrastructure failures remain scientifically unavailable. [Source: `E3-COMPLETION`.]

**INTERPRETATION.** Complete-block exclusion protects the registered within-block factorial estimands but narrows inference to the 74 complete blocks. Because missingness was not claimed MCAR and was uneven across scenarios—most visibly 7/60 failures in E3-A-02—the paper must report the missingness rather than treat the primary sample as if 296 attempts had been the original full design.

## Primary endpoint and factorial estimands

The primary safety endpoint is realized pairwise hard-risk exposure,

\[
J_{\mathrm{hard}}=\sum_{i<j}\int \mathbf{1}\!\left[d_{ij}(t)<d_{\mathrm{hard}}\right]\,dt,
\qquad d_{\mathrm{hard}}=1.50\ \mathrm{m},
\]

reported in pair-seconds. Each unordered pair contributes the duration for which its measured 3-D separation is strictly below the hard threshold; equality is outside risk. Lower `J_hard` is safer. Pair-specific threshold crossings are linearly interpolated, and pair durations are summed. The related event count counts maximal connected below-threshold intervals separately by pair. [Sources: `ANALYSIS-SEMANTICS`; `E3-CONTRACT`; `E3-REPORT`.]

For endpoint `Y` in complete block `b`, the frozen estimands are:

\[
\Delta_P^{(b)}=
\frac{(Y_{P1F0}-Y_{P0F0})+(Y_{P1F1}-Y_{P0F1})}{2},
\]

\[
\Delta_F^{(b)}=
\frac{(Y_{P0F1}-Y_{P0F0})+(Y_{P1F1}-Y_{P1F0})}{2},
\]

\[
\Delta_{PF}^{(b)}=
(Y_{P1F1}-Y_{P1F0})-(Y_{P0F1}-Y_{P0F0}).
\]

`Delta_P` averages the within-block P1-minus-P0 planning effect over both feedback levels. `Delta_F` averages the within-block F1-minus-F0 feedback effect over both planning levels. `Delta_PF` is the difference of feedback effects across planning levels, equivalently the planning-by-feedback interaction on the endpoint's scale. For exposure, events, binary risk, failsafe, and near-limit fraction, negative is safer; for minimum separation and mission success, positive is safer. [Source: `E3-CONTRACT`.]

Continuous/count estimates are means of block contrasts with two-sided scenario-stratified paired-block percentile-bootstrap 95% intervals using 10,000 resamples. Binary factorial effects use the same block-level risk-difference contrasts and bootstrap structure; cell proportions use Wilson intervals. These methods and resampling seeds are frozen outputs, not recomputed here. [Sources: `E3-CONTRACT`; `E3-FACTORIAL`; `E3-BINARY`.]

## Family A — planning responsibility for predictable structural risk

### Primary and supporting results

| Endpoint | Registered contrast | Estimate | Frozen 95% CI | N complete blocks |
|---|---|---:|---:|---:|
| `J_hard` (pair-s) | Delta_P | **−1.6810** | **[−1.9786, −1.4690]** | 23 |
| Realized minimum separation (m) | Delta_P | +1.8288 | [+1.7718, +1.8834] | 23 |
| Hard-risk event count | Delta_P | −2.1087 | [−2.3261, −2.0000] | 23 |
| Any realized hard risk | Delta_P risk difference | −1.0000 | [−1.0000, −1.0000] | 23 |

[Frozen sources: `E3-REPORT`; exact machine values in `E3-FACTORIAL` and `E3-BINARY`.]

The planning manipulation check is equally important: Family A's predicted hard-conflict count changed by −2.0000 under Delta_P, with frozen 95% CI [−2.0000, −2.0000] and N=23. The planning factor therefore changed the risk property it was designed to change before considering realized outcomes. [Sources: `E3-REPORT`; `E3-FACTORIAL`.]

For completeness, the other Family A `J_hard` factorial estimates were Delta_F = −0.0571 pair-s, 95% CI [−0.3679, +0.1479], N=23, and Delta_PF = +0.1143 pair-s, 95% CI [−0.2985, +0.7340], N=23. The binary any-hard-risk Delta_F and Delta_PF were both 0.0000 with [0, 0] intervals. These secondary contrasts reinforce that Family A is a planning-responsibility assay; they are not evidence that feedback is universally irrelevant. [Sources: `E3-FACTORIAL`; `E3-BINARY`.]

**INTERPRETATION.** In the fixed predictable-conflict scenarios, safety-aware planning removed predicted hard conflicts and substantially reduced realized hard-risk exposure and events while increasing minimum separation. This is strong within-assay evidence for planning responsibility when risk is structurally predictable at commitment time.

**BOUNDARY.** The result is not a universal safety guarantee. It covers two fixed structural-risk scenes, 23 complete blocks, the frozen assignment mechanisms, and the registered exposure/event definitions. It does not establish collision-free operation under arbitrary geometries, uncertainty, sensing faults, or untested planners.

## Family B — feedback responsibility for residual execution risk

### Primary and supporting results

| Endpoint | Registered contrast | Estimate | Frozen 95% CI | N complete blocks |
|---|---|---:|---:|---:|
| `J_hard` (pair-s) | Delta_F | **−1.2275** | **[−1.3890, −1.0562]** | 26 |
| Realized minimum separation (m) | Delta_F | +0.0492 | [+0.0250, +0.0656] | 26 |
| Hard-risk event count | Delta_F | −0.7692 | [−1.3846, −0.0769] | 26 |
| Any realized hard risk | Delta_F risk difference | −0.3462 | [−0.4615, −0.2115] | 26 |

[Frozen sources: `E3-REPORT`; exact machine values in `E3-FACTORIAL` and `E3-BINARY`.]

The F0 manipulation check confirmed that the redesigned assay retained residual realized exposure: Family B P0_F0 mean `J_hard` was 1.6609 pair-s and P1_F0 mean `J_hard` was 1.4878 pair-s in the primary complete-block descriptives reported by the frozen analysis. The post-planning deviation, not a predictable planner input, created the relevant feedback-side state. [Source: `E3-REPORT`.]

For completeness, the Family B `J_hard` planning effect was Delta_P = −0.0444 pair-s, 95% CI [−0.2481, +0.1526], N=26, and the interaction was Delta_PF = +0.2572 pair-s, 95% CI [−0.1295, +0.6765], N=26. Binary any-hard-risk results were Delta_P = −0.0385 [−0.1154, +0.0385], Delta_F = −0.3462 [−0.4615, −0.2115], and Delta_PF = +0.1538 [−0.0385, +0.3462], all N=26. [Sources: `E3-FACTORIAL`; `E3-BINARY`.]

**INTERPRETATION.** Feedback strongly reduced the **duration/extent** of hard-risk exposure and lowered event occurrence in the induced residual-risk assay. The +0.0492 m improvement in worst instantaneous minimum separation is positive but comparatively modest relative to the −1.2275 pair-s exposure effect. This physical distinction is important: F1 need not produce a large displacement in the single worst separation sample to substantially shorten or reduce the aggregate time spent below the hard-risk threshold.

The E3-v4 result resolves the previous feedback-side uncertainty **within the redesigned confirmatory scenarios**. It demonstrates that feedback has an empirically distinct safety role once post-planning deviations reliably induce residual execution risk. It does not imply that the same feedback law is optimal, sufficient, or beneficial for every disturbance class.

## Family C — mixed-risk decomposition

### Continuous exposure effects

| `J_hard` contrast | Estimate (pair-s) | Frozen 95% CI | N complete blocks |
|---|---:|---:|---:|
| Delta_P | **−1.7116** | **[−1.9162, −1.5084]** | 25 |
| Delta_F | **−1.2004** | **[−1.3834, −1.0129]** | 25 |
| Delta_PF | +0.3239 | [−0.0825, +0.7311] | 25 |

[Frozen sources: `E3-REPORT`; exact values in `E3-FACTORIAL`.]

The planning manipulation check in Family C changed mean predicted hard conflicts from 2.0000 in P0_F0 to 0.0000 in P1_F0. Both registered main-responsibility effects reduced continuous hard-risk exposure. The interaction estimate was positive and its interval crossed zero. A nonzero interaction was **not** preregistered as necessary for decomposition. The mixed scenes spatially isolate predictable and residual-risk subsystems, so approximately additive continuous effects are compatible with the intended responsibility boundary. [Sources: `E3-REPORT`; `E3-CONTRACT`.]

Supporting Family C continuous/count effects were:

| Endpoint | Delta_P [95% CI] | Delta_F [95% CI] | Delta_PF [95% CI] | N |
|---|---:|---:|---:|---:|
| Realized minimum separation (m) | +0.8666 [0.8441, 0.8936] | +0.0706 [0.0531, 0.0877] | −0.0559 [−0.0895, −0.0209] | 25 |
| Hard-risk event count | −2.4600 [−2.9000, −2.0400] | −1.7000 [−2.0800, −1.3200] | +0.9200 [0.0800, 1.8000] | 25 |

[Frozen sources: `E3-REPORT`; `E3-FACTORIAL`.]

These endpoint-specific interactions are a warning against describing P and F as mathematically independent. “Distinct responsibilities” refers to the experimental mechanisms and registered main contrasts, not to a claim that all interaction terms equal zero.

### Dedicated P1_F0 residual-risk cell

The P1_F0 cell is the clearest empirical demonstration of the responsibility boundary:

| Family C primary-complete population | Frozen value |
|---|---:|
| P1_F0 mean `J_hard` | **1.3687 pair-s** |
| P1_F0 any-hard-risk | **22/25 = 0.8800** |
| P1_F0 Wilson 95% CI | **[0.7004, 0.9583]** |
| P1_F1 mean `J_hard` | **0.3303 pair-s** |
| Within P1, paired F1−F0 any-hard-risk risk difference | **−0.3600**, 95% CI **[−0.4800, −0.2400]** |

[Frozen sources: P1_F0 summary in `E3-SUMMARY`; cell means/proportion and Wilson interval in `E3-CELL` listed in the manifest; paired risk difference in `E3-BINARY`. The 22/25 display is frozen, not reconstructed.]

**INTERPRETATION.** P1 removed the predictable structural conflict from the planning representation, yet substantial realized risk remained after the post-planning deviation when feedback was off: 22 of 25 P1_F0 blocks had at least one hard-risk event. Turning on feedback under P1 reduced mean exposure from 1.3687 to 0.3303 pair-s and lowered any-hard-risk by 0.36 in paired risk-difference units. Planning therefore addressed the predictable component but did not erase post-planning execution risk; feedback reduced that residual risk.

This is stronger evidence for a responsibility decomposition than a generic comparison of P0_F0 and P1_F1, because it exposes the intermediate state where planning has done its registered job and residual execution risk still remains.

## Binary any-hard-risk results

| Family | Delta_P [95% CI] | Delta_F [95% CI] | Delta_PF [95% CI] | N |
|---|---:|---:|---:|---:|
| A | −1.0000 [−1.0000, −1.0000] | 0.0000 [0, 0] | 0.0000 [0, 0] | 23 |
| B | −0.0385 [−0.1154, +0.0385] | −0.3462 [−0.4615, −0.2115] | +0.1538 [−0.0385, +0.3462] | 26 |
| C | −0.3000 [−0.3600, −0.2400] | −0.1800 [−0.2400, −0.1200] | **−0.3600 [−0.4800, −0.2400]** | 25 |

[Frozen source: `E3-BINARY`; all are block-level risk-difference contrasts with scenario-stratified paired-block percentile-bootstrap intervals.]

The continuous and binary interactions answer different questions. Family C's continuous `J_hard` interaction is +0.3239 pair-s with an interval crossing zero, consistent with approximately additive changes in the amount of exposure. The binary interaction is −0.3600 with an interval away from zero because thresholding asks whether **any** event occurred; combining mechanisms can move blocks across the zero-event boundary in a non-additive way even when continuous exposure reductions are roughly additive. The defensible statement is therefore: continuous exposure effects were approximately additive in these spatially isolated mixed scenes, while the thresholded occurrence endpoint showed a stronger combined effect. It is not defensible to call planning and feedback mathematically independent.

## Operational outcomes and sensitivity population

**FACT.** All 343 scientifically scored attempts completed the registered mission: mission success 343/343 = 1.0000 with Wilson 95% CI [0.9889, 1.0000]. Failsafe was observed in 0/343, with Wilson 95% CI [0.0000, 0.0111]. The other 17 registered attempts were infrastructure failures; mission and failsafe fields were unavailable for them. Attempt status across the full registry was therefore 343/360 scientific success and 17/360 infrastructure failure, but there is no frozen rule that recodes unavailable mission outcomes as failures or successes. [Sources: `E3-OPERATIONS`; `E3-REPORT`; `E3-COMPLETION`.]

Correct wording is: **“All 343 scientifically scored attempts completed the registered mission; 17 additional registered attempts were infrastructure failures for which scientific mission outcomes were unavailable.”** Incorrect wording is “overall mission success was 100%,” because it silently changes the denominator and availability semantics.

The available-cell sensitivity population includes all 343 scientific successes, including the 47 cells from incomplete blocks. The frozen report shows the same qualitative mechanism pattern—for example, Family A P1 cells have zero mean available-cell `J_hard`, Family B F1 cells have lower mean exposure than the corresponding F0 cells, and Family C retains high P1_F0 residual risk—but these are descriptive sensitivity summaries, not replacements for the 74-block primary analysis. [Source: `E3-REPORT`.]

## Instrumentation omission: feedback intervention burden

**FACT.** Feedback intervention burden is **NA — preregistered endpoint unavailable**, with N = 0/343 and proxy used = no. Before factorial effect estimation, the frozen endpoint-availability adjudication checked all 343 scientific successes and found no quantitative field or registered formula for feedback activation time, intervention duration/fraction, correction magnitude, or equivalent burden. Treatment assignment, deviation-delivery verification, and controller near-limit fraction were explicitly ruled non-equivalent and were not substituted. No raw rederivation, proxy, or imputation was authorized. [Sources: `E3-ENDPOINT`; `E3-FACTORIAL`; `E3-SUMMARY`.]

**INTERPRETATION.** This omission removes any quantitative claim that safer planning reduces feedback intervention duration, frequency, or magnitude, or that feedback effort is lower in a particular planning cell. It also prevents an efficiency/burden comparison between P and F. It does **not** invalidate the measured F1 safety effect on `J_hard`, minimum separation, event count, or any-hard-risk, because burden was an operational endpoint and the safety endpoints remain measured and frozen.

## C2 interpretation, exclusions, and paper wording

**INTERPRETATION — supported.** Family A establishes the planning responsibility for predictable structural conflict. Family B establishes the feedback responsibility after an exogenous, post-planning deviation creates residual execution risk. Family C places both mechanisms in the same spatially isolated scenes: both main effects reduce `J_hard`, and P1_F0 demonstrates that successful structural planning can coexist with substantial residual execution risk that F1 then reduces. Together, the confirmatory result supports **planning–execution safety decomposition within the tested UAV-swarm reconfiguration scenarios**. [Source: `E3-REPORT`.]

**INTERPRETATION — not supported.** E3-v4 does not establish universal safety, a collision-free guarantee, zero collision probability, universal independence of planning and feedback, quantitative reduction of feedback effort, or superiority over an untested planner or controller. It does not show P1_F1 must be best on every endpoint. Inference is restricted to six fixed scenarios, 15 registered seeds per scenario, the 74 complete blocks, the frozen simulation/runtime stack, and the registered post-planning deviations.

**PAPER-WRITING RECOMMENDATION.** Give Family A, Family B, and the Family C P1_F0 logic distinct paragraphs. State the missingness and infrastructure denominator before presenting effects. Use `J_hard` as the primary plot, minimum separation/events/binary risk as supporting evidence, and explicitly state the burden endpoint as not testable. Avoid using “independent layers”; “distinct responsibilities” or “approximately additive continuous exposure effects in the mixed assay” is safer and more accurate.

## Suggested paper presentation

- **Main figure:** three panels for Family A, B, and C `J_hard` factorial effects with frozen 95% intervals. For A emphasize Delta_P; for B Delta_F; for C show Delta_P, Delta_F, and Delta_PF. Put “pair-s; lower is safer” on the axis.
- **Main inset or compact companion panel:** Family C P1_F0 versus P1_F1, showing mean `J_hard` and any-hard-risk counts/proportions. This conveys the responsibility boundary more directly than a decorative four-cell plot.
- **Main table or caption:** 360 consumed, 343 scientific successes, 17 infrastructure failures, 74/90 complete blocks, and family/scenario complete-block counts.
- **Supplement:** full factorial results for supporting endpoints; all binary simple comparisons and frozen tests; all available-cell descriptives; failure slots and mechanisms; operational Wilson intervals; manipulation checks; and endpoint-availability adjudication.
- **Do not create:** a collision-count-free “100% safe” graphic, a plot that treats infrastructure failures as zeros, or an intervention-burden panel with a proxy.

# E4A — Motion-Style Behavioral Distinguishability

## Research question and necessity

E4A asks whether bounded semantic styles—smooth, normal, and aggressive—produce measurably different low-level closed-loop behavior when the higher-priority task and safety envelope is held fixed. The failure mode is semantic decoration: a style label could appear in the interface yet have no physical effect. E4A tests behavioral consequence, not authority preservation. [Sources: `C2-RAW-E4`; E4A claim adjudication in the manifest.]

The preregistered claim was deliberately weaker than universal ordinal dynamics. Smooth was expected to use less control effort and lower acceleration peak/RMS than aggressive, and aggressive was expected to tend toward shorter settling. Normal was expected to be generally intermediate, but it was not required to lie strictly between smooth and aggressive for every scenario or metric. Tracking RMSE was registered without a universal monotonic direction. [Source: `C2-RAW-E4`.]

## Design and fixed quantities

**FACT.** E4A contains 45/45 scientifically complete attempts, with no infrastructure failures. Three scenarios × five seeds × three styles form 15 matched smooth–normal–aggressive triplets. Each style has 15 attempts; each scenario has 15 attempts. [Sources: `E4A-SUMMARY`; `E4A-ATTEMPTS`.]

The three maneuvers use a common four-UAV line formation and differ in displacement geometry:

| Scenario | Registered displacement | Norm | Explicit duration | Seeds |
|---|---:|---:|---:|---:|
| E4A-HORIZONTAL | [0, 4, 0] m | 4.0000 m | 4.0 s | 5 |
| E4A-VERTICAL | [0, 0, 3] m | 3.0000 m | 3.5 s | 5 |
| E4A-DIAGONAL-3D | [3, 4, 2] m | 5.3852 m | 4.0 s | 5 |

[Frozen source: `C2-RAW-E4`; the 5.3852 display rounds the registered 5.385164807134504 m value.]

Within every scenario/seed triplet, the initial positions, assigned targets, requested explicit duration, safety value, seed, and frozen Minimum-Jerk nominal reference were invariant. Style was forbidden from regenerating or retiming the nominal reference; only the bounded execution profile changed. The frozen analysis verified exact reference identity within every triplet. [Sources: `C2-RAW-E4`; `E4A-SUMMARY`; E4A claim adjudication.]

The registered low-level metrics were:

- **Control effort:** mean per-UAV integral of the 3-D norm of commanded acceleration over `[t0, t0 + T_explicit]`; its unit is m/s.
- **Acceleration peak:** mean of per-UAV commanded-acceleration peaks over the explicit-duration interval, in m/s².
- **Acceleration RMS:** equal-UAV pooled, time-weighted commanded-acceleration RMS over the same interval, in m/s².
- **Acceleration rise time:** all-UAV-valid mean time from interpolated 10% to 90% of the global per-UAV peak; no smoothing.
- **Tracking RMSE:** equal-UAV pooled tracking-error RMS over the explicit-duration interval, in metres.
- **Settling time:** maximum UAV stable-hover entry time minus `t0`; unlike the other continuous metrics, it was not truncated at explicit duration.

[Frozen source: `ANALYSIS-SEMANTICS`.]

## Results

### Pooled smooth-to-aggressive effects

All differences are Aggressive minus Smooth, paired by scenario and seed. Positive control-effort/acceleration values indicate greater intensity under aggressive; negative time/RMSE values indicate smaller values under aggressive.

| Metric | Paired mean difference | Frozen 95% Student-t CI | Median | Cohen's dz | Valid N |
|---|---:|---:|---:|---:|---:|
| Control effort | **+0.567605 m/s** | **[+0.353457, +0.781753]** | +0.492839 | +1.4678 | 15 |
| Mean per-UAV acceleration peak | **+0.583589 m/s²** | **[+0.425649, +0.741530]** | +0.482405 | +2.0462 | 15 |
| Acceleration RMS | **+0.172110 m/s²** | **[+0.113600, +0.230620]** | +0.183218 | +1.6290 | 15 |
| Tracking RMSE | **−0.051790 m** | **[−0.061014, −0.042566]** | −0.057559 | −3.1094 | 15 |
| Acceleration rise time | −0.004451 s | [−0.135695, +0.126792] | +0.021169 | −0.0188 | 15 |
| Settling time | **−0.024315 s** | [−0.075040, +0.026411] | −0.037069 | −0.2897 | 13 |

[Frozen source: `E4A-SUMMARY`; all paired means independently cross-checked against the 90 metric rows in `E4A-PAIRS`. The shorter paper displays +0.568 m/s, +0.584 m/s², +0.172 m/s², and approximately −0.024 s by rounding these frozen values.]

The control-effort, acceleration-peak, and acceleration-RMS contrasts all have intervals away from zero in the preregistered direction. Aggressive also has lower tracking RMSE in every triplet, although the registry did not require a universal direction for that endpoint. The acceleration-rise-time contrast is nearly zero with a wide interval spanning both directions. The settling-time mean is modestly negative and its interval crosses zero; only 13 triplets were jointly evaluable because each of smooth and aggressive had one missing settling value in the attempt-level summaries. No missing settling observation was converted to zero. [Sources: `E4A-SUMMARY`; `E4A-ATTEMPTS`; `E4A-PAIRS`.]

### Normal-style intermediate ordering

| Metric | Triplets with Normal between Smooth and Aggressive | Frozen evaluable denominator |
|---|---:|---:|
| Mean per-UAV acceleration peak | 13 | 15 |
| Control effort | 13 | 15 |
| Acceleration RMS | 11 | 15 |
| Tracking RMSE | 15 | 15 |
| Acceleration rise time | 5 | 15 |
| Settling time | 6 | 13 |

[Frozen source: `E4A-SUMMARY`. “Between” is an intermediate-order diagnostic; it does not impose a desirable direction on every metric.]

The normal condition was therefore often intermediate on intensity and tracking measures, but not on temporal dynamics. Rise time was intermediate in only 5/15 triplets, and settling time in 6/13 jointly evaluable triplets. This is direct evidence against the blanket statement `smooth < normal < aggressive` for every response characteristic.

## Interpretation and boundaries

**INTERPRETATION — partially supported.** The frozen styles produced measurable changes in control intensity, acceleration behavior, and tracking characteristics while sharing the same nominal reference. This rules out the claim that the style labels were merely decorative in the tested maneuvers. The result supports **behavioral distinguishability**.

The result does not support strictly ordered dynamics. Control effort and acceleration measures provide a strong smooth-to-aggressive intensity contrast, but rise and settling behavior do not have universal monotonic ordering. Tracking RMSE changes consistently in these triplets, but it was not preregistered as needing a universal style direction and should not be used to redefine “aggressive” post hoc.

**INTERPRETATION — not supported.** E4A does not show that one style is universally better, that smooth always minimizes every dynamic quantity, that aggressive always settles faster, or that Normal is always intermediate. It also does not establish that style cannot override higher-priority constraints; E4B tests that separate property.

**PAPER-WRITING RECOMMENDATION.** Use “behaviorally distinguishable” rather than “strictly ordered.” Emphasize the three intensity endpoints and tracking RMSE, then disclose the weak/non-universal rise and settling ordering. Retain the partially-supported adjudication: the physical-effect proposition is supported, while the stronger across-metric directional pattern is not.

## Suggested paper presentation

- **Main paper:** a paired smooth-to-aggressive effect plot for control effort, acceleration peak, acceleration RMS, and tracking RMSE, with the frozen 95% intervals. If units make a shared axis awkward, use a compact standardized layout with clearly separate numeric annotations rather than normalizing away units.
- **Main prose:** 45 attempts, 15 triplets, exact reference identity, and the four most interpretable paired differences. Include one sentence that settling/rise ordering was not universal.
- **Supplement:** all six endpoints, normal-intermediate counts, scenario-specific effects, style-level descriptive summaries, and per-triplet paired values.
- **Avoid:** a three-style rank figure that visually implies monotonicity for every metric.

# E4B — Priority / Authority Preservation

## Research question and necessity

E4B asks whether lower-priority motion-style preference remains bounded by explicit task, dynamic-feasibility, hard-safety, timing, motion-limit, and controller authority. The failure mode is an unauthorized override: style changes or bypasses a decision owned by a higher-priority layer. [Source: `C2-RAW-E4`.]

E4B is necessary because behavioral expression alone is insufficient. A style mechanism could produce visibly different motion and still be unacceptable if, for example, aggressive style bypassed feasibility timing or changed hard-safety ownership. E4B therefore tests the constraint-prioritized part of Contribution 3.

## Design and registered authority checks

**FACT.** All 60 formal attempts were scientifically complete, with no infrastructure failures. Four scenarios × five seeds × three styles produced 15 attempts per scenario and 20 attempts per style. [Sources: `E4B-SUMMARY`; `E4B-ATTEMPTS`; `C2-RAW-E4`.]

| Scenario | Authority conflict tested | Registered required outcome |
|---|---|---|
| E4B-FEASIBLE-EXPLICIT-T | Feasible explicit task timing versus style | `T_exec` remains exactly 4.0 s for every style |
| E4B-INFEASIBLE-EXPLICIT-T | Infeasible requested 1.5 s versus dynamic feasibility | Runtime raises `T_exec` to at least frozen `T_min = 2.8844991406148166 s`; style cannot bypass velocity/acceleration/jerk feasibility |
| E4B-AUTO-T | Style may influence automatic timing | Style-specific `T_exec` remains at or above the same frozen `T_min` |
| E4B-SAFETY-ACTIVE | Style preference versus active assignment/feedback safety | Style changes neither `d_hard` nor safety ownership and cannot bypass or disable hard-safety mechanisms |

[Frozen source: `C2-RAW-E4`.]

The frozen hierarchy was:

\[
\text{hard safety} > \text{dynamic feasibility} >
\text{feasible explicit task requirement} >
\text{soft motion-style preference}.
\]

Each attempt generated six authority-predicate rows: feasible explicit duration preserved; dynamic feasibility and `T_min` preserved; automatic `T_min` preserved; hard-safety ownership preserved; motion limits and controller clamps preserved; and no priority above style changed. The deterministic tolerance for policy fields was `1×10^{-9}`; physical limits were checked using the frozen limit/saturation evidence. An attempt counted as priority-preserving only if unauthorized override count was zero and every applicable decision respected the complete hierarchy. Missing predicate evidence could not enter the numerator and would remain in the denominator. [Sources: `C2-RAW-E4`; `ANALYSIS-SEMANTICS`.]

## Results

| Authority result | Frozen observation | Frozen descriptive 95% Student-t CI |
|---|---:|---:|
| Overall priority preservation | **60/60 = 1.0000** | [1.0000, 1.0000] |
| Unauthorized overrides | **0/60 attempts; total count 0** | not a separate proportion interval |
| By scenario | 15/15 in each of four scenarios | [1.0000, 1.0000] for each |
| By style | smooth 20/20; normal 20/20; aggressive 20/20 | [1.0000, 1.0000] for each |

[Frozen source: `E4B-SUMMARY`; row-level cross-check: `E4B-ATTEMPTS`. The intervals are the frozen descriptive t intervals and must not be replaced by newly calculated binomial intervals.]

The detailed authority output contains 360 predicate rows, six per attempt. All 360 predicate records were valid and marked pass under the frozen scorer; 225 were applicable to their scenario/attempt context, and none of the applicable checks failed. [Source: `E4B-CHECKS`; counts are a direct audit aggregation of the frozen rows, not a new statistical analysis.]

## Interpretation and boundaries

**INTERPRETATION — supported.** Across the 60 registered authority-conflict attempts, soft style did not override the tested higher-priority constraints. Feasible explicit timing remained fixed, infeasible/automatic timing respected dynamic lower bounds, hard-safety ownership remained unchanged, and execution profiles stayed inside frozen motion/controller limits. [Sources: E4B claim adjudication; `E4B-SUMMARY`; `E4B-CHECKS`.]

**INTERPRETATION — not a formal guarantee.** Observing 60/60 priority preservation does not prove that authority can never be violated. The result is bounded to four registered scenarios, three styles, five seeds, the frozen hierarchy and runtime, and the six operationalized predicates. The degenerate frozen t interval [1,1] is a property of the recorded descriptive convention for identical observations; it is not a universal-probability confidence bound and must not be described as one.

**PAPER-WRITING RECOMMENDATION.** Write “No unauthorized override was observed in 60 registered attempts” or “priority was preserved in 60/60 tested cases.” Follow immediately with the tested-scenario boundary. Avoid “guarantees authority preservation,” “provably safe,” or “can never override safety.”

## Suggested paper presentation

- **Main paper:** a compact authority table with overall 60/60, 0 overrides, four scenario rows, and three style strata. A figure is unnecessary because every cell is identical.
- **Supplement:** the six predicate definitions, applicability counts, deterministic tolerances, and all 360 authority-check rows.
- **Caption boundary:** label the values as observed preservation in registered conflict cases, not a formal proof.

# E4 Combined Evidence for Bounded Behavioral Grounding

E4 has two logically necessary halves.

**FACT — E4A.** With the nominal reference and higher-priority task/safety quantities fixed, changing smooth/normal/aggressive style changed control effort, acceleration peak/RMS, and tracking RMSE in the matched maneuver triplets. [Sources: `E4A-SUMMARY`; `E4A-PAIRS`.]

**FACT — E4B.** In separate authority-conflict cases, all 60 attempts preserved the registered hierarchy and produced zero unauthorized overrides. [Sources: `E4B-SUMMARY`; `E4B-CHECKS`.]

**INTERPRETATION.** Without E4A, style could be semantically decorative: present in a task record but physically inert. Without E4B, style could be behaviorally expressive but unsafe or unbounded. Together, the experiments support the bounded claim: **bounded motion-style semantics can modulate low-level swarm behavior without overriding higher-priority execution authority in the tested scenarios.**

This combination does not turn observed E4B preservation into a proof and does not turn E4A's partially supported directional ordering into universal monotonicity. “Bounded behavioral grounding” refers to measurable modulation plus observed subordination to the registered authority hierarchy—not to a claim that every possible style utterance or physical situation is safe.

**PAPER-WRITING RECOMMENDATION.** Present E4A before E4B so the reader first sees that style has real behavioral content and then sees the bounding mechanism. Use one combined concluding sentence and retain separate limitations for behavioral ordering and authority generalization.

# Cross-Experiment Claim Matrix

The matrix below is the paper-writing control surface: each row connects a contribution claim to its evidence mechanism, strongest quantitative result, and explicit ceiling.

| Contribution / claim | Experiment | Evidence mechanism | Primary quantitative result | Supporting result | Evidence strength | What the evidence rules out | Remaining limitation | Recommended paper wording | Forbidden overclaim |
|---|---|---|---|---|---|---|---|---|---|
| C1 semantic preservation | E1 | Frozen candidate-semantic commands scored against exact normalized ground truth, with unresolved-field audit | 96/96 valid commands exactly correct; 0/225 premature numerical commitments | 96/96 schema acceptance; all registered task fields 120/120 and mission relations 96/96 | Strong within the frozen registry | The interface is not forced to numerically ground every valid request immediately; style/structure fields are not lost in the tested valid commands | Finite candidate dataset; 19/24 invalid rejection; 0/4 illegal-transition rejection; 0/162 strict-format compliance | “The candidate interface preserved exact valid-task semantics and all registered under-specification opportunities on the frozen dataset.” | “Robust open-world NLU,” “reliably rejects invalid language,” or “best semantic interface” |
| C1 state-dependent late commitment | E2 | Same semantics, state, seed, policy, allocator, and controller; paired manipulation of commitment time under SHIFT and NO_SHIFT | SHIFT: Early 25/30 state-consistency violations versus Late 0/30; paired difference −0.8333 [−0.9749, −0.6918] | SHIFT infeasibility/correction: 15/30 versus 0/30; NO_SHIFT adverse outcomes 0 for both | Strong paired causal evidence in registered cases | The late-binding rationale is not merely architectural taste; the timing difference has physical consequences under relevant state change | Six deterministic offline scenarios; no universal optimality or all-metric claim | “Deferring state-dependent commitment until the execution snapshot eliminated the registered stale and corrected outcomes in the tested shifted pairs.” | “Late binding is always optimal” or “all early commitments are wrong” |
| C2 planning responsibility | E3-v4 Family A | P1 versus P0 across feedback levels in predictable structural-risk scenes | Delta_P J_hard = −1.6810 pair-s [−1.9786, −1.4690], N=23 | Minimum separation +1.8288 m; events −2.1087; any-hard-risk −1.0000; predicted conflicts −2.0000 | Strong confirmatory within-assay evidence | Feedback alone is not an adequate substitute for removing planner-visible structural conflict in these scenes | Two fixed Family A scenarios; incomplete blocks and simulation-domain limits | “Safety-aware planning reduced predictable structural risk in the tested reconfigurations.” | Universal planning guarantee or collision-free planning |
| C2 feedback responsibility | E3-v4 Family B | F1 versus F0 across planning levels after post-planning deviations excluded from planner input | Delta_F J_hard = −1.2275 pair-s [−1.3890, −1.0562], N=26 | Minimum separation +0.0492 m; events −0.7692; any-hard-risk −0.3462 | Strong confirmatory evidence for residual-risk assay | Planning state alone cannot prevent risk introduced after commitment; F1 has a measurable residual-risk role | Two qualified deviation types; feedback burden unavailable; no comparison with alternative feedback laws | “IAPF feedback reduced induced post-planning residual risk in the tested scenarios.” | Feedback is universally sufficient, optimal, or low-effort |
| C2 decomposition | E3-v4 Family C | Spatially isolated predictable and residual-risk subsystems in a 2×2 factorial design | J_hard Delta_P = −1.7116, Delta_F = −1.2004, Delta_PF = +0.3239 pair-s, N=25 | P1_F0: 1.3687 pair-s and 22/25 any risk; P1_F1: 0.3303 pair-s; within-P1 binary difference −0.3600 | Strong mechanism pattern within fixed mixed scenes | The architecture is more than two untested modules placed together: each manipulation addresses its registered component, and residual risk remains after planning alone | Continuous interaction interval crosses zero; binary interaction differs; no universal independence; six-scenario domain | “The mixed assay supports planning–execution safety decomposition within the tested UAV-swarm reconfiguration scenarios.” | Universal safety, universal independence, zero collision probability |
| C3 behavioral distinguishability | E4A | Matched style triplets sharing exact Minimum-Jerk reference | Aggressive−Smooth: control effort +0.5676 m/s; peak acceleration +0.5836 m/s²; RMS +0.1721 m/s² | Tracking RMSE −0.05179 m; normal intermediate 13/15, 13/15, 11/15, and 15/15 on the main intensity/tracking measures | Partial support: clear behavior effect, incomplete universal ordering | Style is not merely a decorative semantic label in the tested maneuvers | Three maneuvers; rise/settling not universally ordered; settling N=13 | “Styles produced distinguishable low-level behavior under a shared nominal reference.” | “Smooth < normal < aggressive for every metric/trial” or one style is universally best |
| C3 authority preservation | E4B | Four registered authority-conflict scenarios and six predicate checks per attempt | Priority preserved 60/60; unauthorized override count 0 | 15/15 per scenario and 20/20 per style; 225 applicable predicates with no failure | Strong observed preservation in the test registry | Tested style variation did not bypass feasibility, timing, safety ownership, motion limits, or higher-priority decisions | Observational finite-sample result, not formal verification | “No unauthorized override was observed in 60 registered authority-conflict attempts.” | “Authority can never be violated” or a formal universal guarantee |

[Sources for each row: the corresponding experiment summary, detailed table, registry, and claim adjudication named in the source notation and manifest. Confidence intervals are frozen values.]

# Reviewer-Facing Evidence Boundaries

## 1. “Is late binding just an architectural preference?”

**Relevant evidence.** E2 holds semantic interpretation and the physical policy stack fixed while pairing Early and Information-Aligned Late conditions under identical scenario/seed state. Under SHIFT, Early produced 25/30 state-consistency violations and 15/30 infeasibility/correction outcomes, while Late produced 0/30 for both; under NO_SHIFT both had zero adverse outcomes. [Sources: E2-SUMMARY; E2-ATTEMPTS.]

**What is resolved.** Commitment time caused observable differences specifically when the required information changed. The no-shift control and unchanged executable-grounding rate support an information-availability mechanism rather than refusal or an unconditional Late advantage.

**What remains unresolved.** The assay does not establish a universal rule for all commitment decisions. Values already known and stable may be safely committed early, and other state-change processes were not tested.

**Correct manuscript boundary.** Late binding is empirically motivated for state-dependent quantities in the evaluated reconfiguration scenarios.

## 2. “Does E1 demonstrate robust natural-language understanding?”

**Relevant evidence.** E1 achieved 96/96 exact valid-task accuracy and 0/225 premature commitments, but rejected only 19/24 invalid commands, including 0/4 illegal transitions, and achieved 0/162 strict-format compliance. [Source: E1-SCORE.]

**What is resolved.** The frozen candidate interface can represent the registered valid commands and preserve registered under-specification.

**What remains unresolved.** Open-world language diversity, paraphrase robustness outside the registry, adversarial language, broad invalid-command rejection, and alternative-interface comparisons remain untested.

**Correct manuscript boundary.** Describe a frozen candidate-semantic dataset result, not general NLU competence.

## 3. “Why can safety not be handled entirely by planning?”

**Relevant evidence.** In Family C, safety-aware planning removed the predictable conflict, but P1_F0 retained mean J_hard = 1.3687 pair-s and any-hard-risk in 22/25 blocks; P1_F1 reduced mean exposure to 0.3303 pair-s and the paired binary risk difference was −0.3600 [−0.4800, −0.2400]. [Sources: E3-SUMMARY; E3-CELL; E3-BINARY.]

**What is resolved.** Once an execution deviation occurs after planning and is absent from planner input, correct structural planning can coexist with substantial realized residual risk.

**What remains unresolved.** The experiment does not show every planner will leave the same risk, or that no predictive planner could model other deviation distributions.

**Correct manuscript boundary.** Planning owns predictable structural conflict; feedback addresses residual execution risk in the tested post-planning-deviation assay.

## 4. “Why can safety not be handled entirely by feedback?”

**Relevant evidence.** Family A exposes planner-visible structural conflicts. The planning contrast was Delta_P(J_hard) = −1.6810 pair-s, 95% CI [−1.9786, −1.4690]; P1 also increased minimum separation by 1.8288 m, reduced events by 2.1087, and removed binary hard-risk occurrence across the 23 complete blocks. The predicted-conflict manipulation check was −2.0000. [Sources: E3-REPORT; E3-FACTORIAL; E3-BINARY.]

**What is resolved.** Removing predictable conflict at planning time has a large, mechanism-aligned safety effect; leaving known conflict for the execution layer is not empirically equivalent in these scenes.

**What remains unresolved.** The experiment does not compare every possible feedback controller, nor prove feedback could never compensate for a poor plan under another configuration.

**Correct manuscript boundary.** Planning is the demonstrated responsibility for predictable structural risk in the registered Family A scenes.

## 5. “Are planning and feedback merely two modules placed together?”

**Relevant evidence.** Family C manipulates both responsibilities factorially in spatially isolated mixed-risk scenes. J_hard shows Delta_P = −1.7116 and Delta_F = −1.2004 pair-s; P1_F0 exposes residual risk and F1 reduces it. The continuous interaction is +0.3239 [−0.0825, +0.7311], while the binary interaction is −0.3600 [−0.4800, −0.2400]. [Sources: E3-FACTORIAL; E3-BINARY; E3-CELL.]

**What is resolved.** Each factor produces the registered effect in a common mixed scenario, and the intermediate P1_F0 cell shows why both responsibilities matter.

**What remains unresolved.** The factors are not proven mathematically independent. Endpoint thresholding produces different interaction behavior, and no nonzero interaction was required by the frozen contract.

**Correct manuscript boundary.** The evidence supports a responsibility decomposition and approximately additive continuous exposure effects in these mixed scenes—not universal modular independence.

## 6. “Does motion style actually change behavior?”

**Relevant evidence.** In 15 exact-reference triplets, Aggressive−Smooth increased control effort by 0.5676 m/s, mean per-UAV acceleration peak by 0.5836 m/s², and acceleration RMS by 0.1721 m/s², with all three frozen intervals away from zero; tracking RMSE changed by −0.05179 m. [Source: E4A-SUMMARY; cross-check E4A-PAIRS.]

**What is resolved.** The style labels have measurable low-level consequences in the evaluated maneuvers.

**What remains unresolved.** Rise time was nearly unchanged, settling difference was small with an interval spanning zero, and universal Normal ordering was absent.

**Correct manuscript boundary.** Claim behavioral distinguishability, not universally ordered dynamics.

## 7. “Can style override safety or timing?”

**Relevant evidence.** E4B observed priority preservation in 60/60 attempts and zero unauthorized overrides across feasible timing, infeasible timing, automatic timing, and active-safety cases. [Sources: E4B-SUMMARY; E4B-CHECKS.]

**What is resolved.** No tested style bypassed the registered authority hierarchy or frozen motion/controller constraints.

**What remains unresolved.** Unregistered scenes, malformed configurations, implementation faults, and other styles were not evaluated.

**Correct manuscript boundary.** Style remained subordinate in the tested authority-conflict cases.

## 8. “Does 60/60 authority preservation imply formal guarantees?”

**Relevant evidence.** The observation is complete for the fixed 60-attempt registry, with frozen descriptive rate and interval equal to 1.0. [Source: E4B-SUMMARY.]

**What is resolved.** There was no observed violation in this registry.

**What remains unresolved.** Finite testing is not formal verification. The degenerate Student-t interval reflects identical observed values, not a theorem about all executions.

**Correct manuscript boundary.** Report 60/60 observed preservation and explicitly deny universal guarantee language.

## 9. “Does 343/343 mission success mean the full campaign had 100% success?”

**Relevant evidence.** E3-v4 registered and consumed 360 attempts: 343 scientific successes and 17 infrastructure failures. Mission outcome was available and successful in 343/343 scientific attempts, but unavailable for the other 17. [Sources: E3-COMPLETION; E3-OPERATIONS.]

**What is resolved.** Every scientifically scored attempt completed the registered mission.

**What remains unresolved.** The 17 infrastructure cases have no scientific mission outcome and cannot be silently assigned success or failure.

**Correct manuscript boundary.** Condition the 343/343 statement and report 17/360 infrastructure failures separately.

## 10. “Does E3 measure feedback intervention burden?”

**Relevant evidence.** The pre-effect-estimation endpoint adjudication checked all 343 scientific attempts and found the preregistered burden endpoint unavailable: N=0/343, proxy used=no. [Source: E3-ENDPOINT.]

**What is resolved.** Nothing quantitative about intervention duration, frequency, or magnitude; only the safety effects of the assigned F1 condition are measured.

**What remains unresolved.** Whether safer planning reduces feedback workload and whether comparable safety can be achieved with less intervention.

**Correct manuscript boundary.** Disclose the instrumentation omission and make no feedback-effort claim; do not treat treatment assignment or controller near-limit fraction as a proxy.

# Paper Table / Figure Plan

A compact presentation should make the contribution logic visible without converting every available output into a figure.

| Candidate | Purpose | Experiment | Exact frozen data source | Axes or columns | Intended reader takeaway | Placement |
|---|---|---|---|---|---|---|
| Table 1: protocol and sample summary | Establish design scale, pairing, completion, and primary population before effects | E1–E4 | E1-REGISTRY/E1-MANIFEST; E2-SUMMARY; E3-COMPLETION/E3-SUMMARY; E4A-SUMMARY; E4B-SUMMARY | Experiment; question; registered attempts/commands; pairing/block; scientific population; missingness | Denominators differ for principled reasons and are not interchangeable | Main paper |
| Table 2: semantic-interface quality | Show E1 strengths and failure boundaries in one place | E1 | E1-SCORE | Metric; numerator; denominator; rate; note | Exact valid semantics and under-specification are strong, while invalid/format behavior is incomplete | Main paper if C1 is central; otherwise supplement |
| Figure 1 or compact table: commitment timing by state change | Make the E2 causal interaction visually immediate | E2 | E2-ATTEMPTS for counts; E2-SUMMARY for intervals | x: NO_SHIFT versus SHIFT; grouped Early/Late; y: adverse-outcome proportion; panels/rows for state inconsistency and correction/infeasibility | Early and Late are equivalent without state change, but diverge sharply under shift | Main paper |
| Figure 2: three-panel J_hard effects | Present the primary C2 evidence on a common safety scale | E3-v4 | E3-FACTORIAL | y: Family A/B/C; x: block-mean contrast in pair-s with 95% CI; show registered focus effects, and all C effects | Planning addresses Family A, feedback addresses Family B, and both reduce exposure in Family C | Main paper |
| Figure 2 inset or Table 3: residual-risk boundary | Expose the key P1_F0 logic | E3-v4 | E3-CELL and E3-BINARY | Conditions P1_F0/P1_F1; mean J_hard; any-risk count/proportion; paired risk difference | Good planning does not eliminate post-planning residual risk; feedback reduces it | Main paper |
| Supplementary missingness table | Preserve all infrastructure and block exclusions | E3-v4 | E3-MISSING | Family, scenario, condition, mechanism, registered N, failures, complete blocks | Primary effects use complete blocks without hiding 17 failures | Supplement, with concise main-text accounting |
| Figure 3: paired style-intensity effects | Demonstrate that style changes behavior without implying universal rank | E4A | E4A-SUMMARY for frozen effects/CIs; E4A-PAIRS for point pairs | Separate panels or rows for control effort, acceleration peak, acceleration RMS, tracking RMSE; Aggressive−Smooth with 95% CI | Style is physically consequential on intensity/tracking measures | Main paper |
| Table 4: authority preservation | Report a ceiling result without a redundant graph | E4B | E4B-SUMMARY; E4B-ATTEMPTS; E4B-CHECKS | Overall, four scenarios, three styles; preserved/total; overrides | All tested strata preserved authority, but this is observed evidence rather than proof | Main paper or compact supplement table |
| Supplementary endpoint/boundary table | Preserve negative and unavailable evidence | E1, E3, E4A | E1-SCORE; E3-ENDPOINT; E4A-SUMMARY | Strict JSON; illegal-transition rejection; intervention burden; rise/settling ordering | The paper reports limitations as results rather than burying them | Supplement; mention each in main prose |

Recommended compact main-paper set: one overall sample table, one E2 timing panel, one E3 multi-panel effect figure with a P1_F0 inset, one E4A paired-effect panel, and one compact E4B authority table. E1 can fit in the sample/quality table if page pressure is severe. A separate E1 category figure and an E4B bar chart are not recommended because they add visual area without clarifying a relationship.

# Source-Audit and Claim-Control Checklist

- [x] E1 design and every reported E1 number trace to frozen commit 8f050943c74dc48529aa48f696146c07f7a4a83e; primary values come from the accepted formal score/audit rather than synthetic validation.
- [x] E2 design traces to Campaign-v2 raw commit 33538b91ab9e0c53b918cdc0e47e3b7fa6f08592, while all reported results and intervals trace to final analysis commit 511192273a61f97e2742a1cc6608e18ed960cc1f.
- [x] E3 scientific effects trace only to E3-v4 final analysis commit c62e9b43dbed0470feb46d4cf148081d681c26e1.
- [x] E4A and E4B design traces to the frozen Campaign-v2 registry; results trace to final analysis commit 511192273a61f97e2742a1cc6608e18ed960cc1f.
- [x] No E5 experimental evidence, result, interpretation, table plan, or manuscript extraction appears in this reference.
- [x] E3-v3 is mentioned only as historical assay context and is not pooled or statistically combined with E3-v4.
- [x] No new inferential statistic, post-hoc test, altered interval, or new endpoint definition was introduced.
- [x] Presentation calculations are limited to transparent count percentages or unit conversions and are labeled.
- [x] No missing or unavailable result was converted to zero.
- [x] No E3 infrastructure failure was converted into a scientific failure; 343 scored mission outcomes and 17 unavailable outcomes remain distinct.
- [x] Observed 100% proportions are not described as universal guarantees.
- [x] E3 feedback intervention burden remains NA, N=0/343, proxy used=no, and not testable.
- [x] E4A Normal ordering and rise/settling dynamics are not described as universally monotonic.
- [x] All conclusions remain bounded to the frozen datasets, scenarios, policies, and runtime conditions.
- [x] Cross-checks against detailed CSV/JSON agree with frozen summaries. The E1 task-field denominator of 120 is reconciled with 96 valid commands because multi-task commands yield 120 valid task instances; this is not a discrepancy.
- [x] No frozen-source inconsistency affecting a reported result was found.

# Manuscript Extraction Kit

The material below is deliberately compact but remains a factual scaffold rather than finished manuscript prose. Each unit retains purpose, design, key result, takeaway, and limitation.

## E1 extraction unit

**A. One-sentence purpose.** E1 evaluates whether the frozen candidate semantic interface preserves the intended task while leaving state-dependent physical center, scale, and timing values unresolved until later runtime stages.

**B. Design in two to four sentences.** The sealed registry contains 120 commands: 96 valid and 24 invalid, with valid commands distributed across mission structure, center, scale, timing, style, safety, transition, and formation categories. Commands were evaluated in a sealed randomized inference order using the frozen provider configuration and at most three parser attempts, with every provider attempt retained. Valid outputs were scored for schema acceptance, exact normalized semantic equality, field accuracy, and premature numerical commitment; invalid commands were scored against immutable rejection classes. [Sources: E1-PROTOCOL; E1-REGISTRY; E1-ORDER.]

**C. Key results.** All 96 valid commands produced schema-valid Candidates and exactly matched the normalized semantic ground truth; every registered U/F/c/r/T/m/s/q task field was correct over 120 task instances, mission relations were correct for 96/96 commands, and premature numerical commitment was 0/225. Invalid rejection was 19/24, with 0/4 illegal-transition rejections and 3/4 contradictory-semantics rejections. Strict JSON-format compliance was 0/162 returned responses; 24/120 commands required at least one retry, producing 163 provider attempts, and median provider-attempt and command-to-terminal latencies were 17,334.520 ms and 20,962.5 ms, respectively. [Sources: E1-SCORE; E1-MANIFEST.]

**D. Scientific takeaway.** On the frozen candidate dataset, the interface strongly preserved valid task semantics and registered under-specification, supplying the semantic half of late-bound grounding.

**E. Limitation.** E1 is not evidence of open-world NLU, broad invalid-command rejection, reliable illegal-transition rejection, strict provider JSON behavior, or a physical benefit from delayed commitment.

## E2 extraction unit

**A. One-sentence purpose.** E2 isolates whether committing unresolved physical quantities at the information-aligned execution snapshot prevents stale or infeasible behavior when state changes after interpretation.

**B. Design in two to four sentences.** The frozen design contains 120 scientifically complete attempts forming 60 Early/Late pairs, split evenly between 30 SHIFT and 30 NO_SHIFT pairs across six scenarios and five seeds. Both conditions received identical commands and Candidate semantics; Early numerically resolved c/r/T at parse time, whereas Information-Aligned Late retained unresolved fields until execution-time resolution. Semantic fields, state within each pair, policy, allocator, controller, and seed were held fixed, and the registered adverse outcomes were executable grounding, state inconsistency, dynamic infeasibility, correction, and rejection. [Sources: C2-RAW-E2; E2-SUMMARY.]

**C. Key results.** Under SHIFT, Early produced 25/30 state-consistency violations and 15/30 dynamic infeasibility/correction outcomes; Late produced 0/30 for both. The frozen Late−Early paired effects were −0.8333 [−0.9749, −0.6918] for state inconsistency and −0.5000 [−0.6899, −0.3101] for infeasibility/correction. Under NO_SHIFT, neither condition had an adverse outcome; executable grounding was 60/60 and rejection 0/60 in both commitment conditions. [Sources: E2-SUMMARY; E2-ATTEMPTS; E2-PAIRS.]

**D. Scientific takeaway.** In the tested state-shift cases, deferring commitment until relevant execution state was available eliminated the registered stale and feasibility-corrected outcomes without gaining advantage through rejection.

**E. Limitation.** The result is bounded to six deterministic offline scenarios and does not establish universal late-binding optimality or that all early commitments are inappropriate.

## E3-v4 extraction unit

**A. One-sentence purpose.** E3-v4 tests whether predictable structural risk and post-planning residual execution risk are reduced by distinct planning and feedback responsibilities in UAV-swarm reconfiguration.

**B. Design in two to four sentences.** A frozen 2×2 factorial crossed distance-only versus safety-aware planning (P0/P1) with feedback avoidance off versus IAPF on (F0/F1) in six scenarios: two predictable-risk Family A scenes, two post-planning-deviation Family B scenes, and two spatially isolated mixed-risk Family C scenes. Fifteen seeds per scenario and four cells yielded 360 registered attempts and 90 four-cell blocks. Seventeen infrastructure failures left 343 scientific successes; under the preregistered whole-block rule, 74 complete blocks (296 attempts) formed the primary population, with no replacement or imputation. The primary endpoint was pair-summed hard-risk exposure J_hard below d_hard = 1.50 m. [Sources: E3-REGISTRY; E3-CONTRACT; E3-COMPLETION.]

**C. Key results.** Family A showed a planning effect Delta_P(J_hard) = −1.6810 pair-s [−1.9786, −1.4690], N=23, accompanied by +1.8288 m minimum separation, −2.1087 events, and −1.0000 any-hard-risk. Family B showed a feedback effect Delta_F(J_hard) = −1.2275 pair-s [−1.3890, −1.0562], N=26, accompanied by +0.0492 m minimum separation, −0.7692 events, and −0.3462 any-hard-risk. In Family C, Delta_P = −1.7116, Delta_F = −1.2004, and Delta_PF = +0.3239 pair-s (N=25); the P1_F0 cell retained mean J_hard = 1.3687 and any risk in 22/25 blocks, while P1_F1 mean J_hard was 0.3303 and the within-P1 binary risk difference was −0.3600 [−0.4800, −0.2400]. All 343 scientifically scored attempts completed the mission, 17 infrastructure attempts had unavailable mission outcomes, and feedback intervention burden was available in 0/343 scientific attempts (NA; not testable). [Sources: E3-REPORT; E3-FACTORIAL; E3-BINARY; E3-CELL; E3-OPERATIONS; E3-ENDPOINT.]

**D. Scientific takeaway.** The confirmatory assay supports planning–execution safety decomposition within the tested UAV-swarm reconfiguration scenarios: planning removes predictable conflict, while feedback reduces realized risk introduced after planning.

**E. Limitation.** Inference is limited to 74 complete blocks in six fixed scenarios; missingness is not assumed MCAR, intervention burden is not testable, and the data do not provide universal safety, independence, collision-free, or superiority guarantees.

## E4A extraction unit

**A. One-sentence purpose.** E4A determines whether smooth, normal, and aggressive semantic styles produce distinguishable low-level behavior under an identical nominal task and safety reference.

**B. Design in two to four sentences.** Forty-five scientifically complete attempts form 15 matched style triplets across horizontal, vertical, and diagonal 3-D maneuvers and five seeds. Initial positions, targets, explicit duration, safety value, seed, and Minimum-Jerk reference identity were fixed within each triplet, and style was permitted to change only the bounded execution profile. Registered metrics covered control effort, acceleration peak/RMS/rise time, tracking RMSE, and settling time. [Sources: C2-RAW-E4; ANALYSIS-SEMANTICS; E4A-SUMMARY.]

**C. Key results.** Aggressive−Smooth paired differences were +0.5676 m/s in control effort [0.3535, 0.7818], +0.5836 m/s² in mean per-UAV acceleration peak [0.4256, 0.7415], +0.1721 m/s² in acceleration RMS [0.1136, 0.2306], and −0.05179 m in tracking RMSE [−0.06101, −0.04257], all N=15. Settling time was approximately −0.0243 s [−0.0750, 0.0264], N=13, and acceleration rise time was −0.00445 s [−0.1357, 0.1268], N=15. Normal was intermediate in 13/15 peak, 13/15 effort, 11/15 RMS, and 15/15 tracking triplets, but only 5/15 rise-time and 6/13 settling triplets. [Source: E4A-SUMMARY; cross-check E4A-PAIRS.]

**D. Scientific takeaway.** The tested motion-style semantics are behaviorally distinguishable, especially in control intensity, acceleration, and tracking, under a shared nominal reference.

**E. Limitation.** E4A does not establish a universal smooth–normal–aggressive ordering, especially for rise and settling behavior, nor does it test authority preservation.

## E4B extraction unit

**A. One-sentence purpose.** E4B tests whether lower-priority style preferences remain subordinate when explicit timing, dynamic feasibility, hard safety, motion limits, and controller authority are active.

**B. Design in two to four sentences.** Sixty scientifically complete attempts cross four authority-conflict scenarios, five seeds, and three styles. The scenarios test preservation of feasible explicit duration, correction of infeasible duration, feasibility of automatic duration, and unchanged safety ownership during an active safety case. Six registered authority predicates per attempt determine unauthorized override count and Priority-Preservation Rate. [Sources: C2-RAW-E4; ANALYSIS-SEMANTICS; E4B-SUMMARY.]

**C. Key results.** Priority was preserved in 60/60 attempts and unauthorized override count was zero. Every scenario achieved 15/15 preservation and every style achieved 20/20; the detailed output contains 360 valid passing predicate rows, including 225 applicable checks and no applicable failure. [Sources: E4B-SUMMARY; E4B-ATTEMPTS; E4B-CHECKS.]

**D. Scientific takeaway.** Under the tested authority conflicts, style remained behaviorally subordinate to the registered feasibility, timing, safety, and execution hierarchy.

**E. Limitation.** Sixty of sixty observed preservation events are finite-scenario evidence, not formal verification or a guarantee that authority can never be violated.

## Suggested high-level Experiments section structure

```text
V. EXPERIMENTS

A. Experimental Setup and Frozen Evaluation Protocol
   1. Runtime, simulation, and evidence-freeze principles
   2. Pairing, denominators, confidence intervals, and failure accounting
   3. Claim boundaries and distinction between scientific and infrastructure outcomes

B. Semantic Grounding and Commitment Timing
   1. E1: candidate semantic representation and under-specification
   2. E1 results and invalid/format limitations
   3. E2: paired Early versus Information-Aligned Late design
   4. E2 results under SHIFT and NO_SHIFT
   5. Joint Contribution 1 interpretation

C. Planning–Execution Safety Decomposition
   1. E3-v4 historical motivation and confirmatory design
   2. Population, complete-block rule, and missingness
   3. Family A: planning responsibility
   4. Family B: feedback responsibility
   5. Family C: mixed-risk decomposition and P1_F0 residual-risk cell
   6. Operational outcomes, instrumentation omission, and Contribution 2 boundary

D. Bounded Behavioral Grounding
   1. E4A: exact-reference style-triplet design
   2. E4A behavioral distinguishability and non-universal ordering
   3. E4B: authority-conflict design and preservation results
   4. Combined bounded-behavior interpretation and Contribution 3 boundary

E. Cross-Experiment Discussion of Evidence Limits
   1. What each experiment establishes
   2. What remains outside the tested domain
   3. Main-paper versus supplementary evidence allocation
```

# E5 — End-to-End Integration Evaluation

## E5.1 Objective and evidence scope

The preceding E1–E4 reference, including its title, scope statement, summaries, checklist, and extraction kit, is preserved verbatim. Its statements about excluding E5 apply to that original reference. Everything from this E5 heading onward is a new reporting addition; it does not revise any E1–E4 result, interpretation, or claim mapping.

**FACT.** E5 comprises two separately registered end-to-end integration evaluations, E5-v1 and E5-v2. They assess the path from natural language through Candidate semantics, staged state-dependent resolution, geometry, assignment, execution timing and safety, LADRC, PX4/Gazebo, and mission completion. E5-v1 tests the original integration registry and its boundaries; E5-v2 tests prospectively feasible under-specified commands and the unchanged method at registered swarm sizes N=8, N=12, and N=16. [Sources: `E5-V1-REGISTRY`; `E5-V1-ANALYSIS`; `E5-V2-REPORT`.]

**INTERPRETATION.** E5 is descriptive end-to-end integration and system-completeness evidence, not new causal evidence for C1/C2/C3. Its registries are different and their attempt denominators remain separate. No new endpoint, inferential comparison across N, scaling law, or reanalysis is introduced here. Values below are copied from frozen reports/tables, with presentation rounding only.

## E5.2 E5-v1 — Original Frozen Integration Evaluation

### Protocol and accounting

**FACT.** Registry `E5-exact-end-to-end-v1` used baseline `paper-final-sim-v3`, configuration `paper-current-v11-c0-f-frozen`, five scenarios, and five cold-start seeds per scenario. All 25 registered attempts were retained: 19 scientific-complete and 6 infrastructure failures. All-attempt mission success was 14/25 = 56.0%. The frozen integration adjudication remains `PARTIALLY_SUPPORTED`. [Sources: `E5-V1-REGISTRY`; `E5-V1-ANALYSIS`.]

### Scenario-wise results

| Scenario | Scientific-complete / registered | Mission success / registered | Retained interpretation |
|---|---:|---:|---|
| SIMPLE | 5/5 | 5/5 | Full simple-mission integration observed |
| REL-QUAL | 5/5 | 0/5 | All reached the frozen resolver; valid fail-closed physical-admissibility rejection |
| SEQUENTIAL | 4/5 | 4/5 | Four completed; one retained infrastructure failure |
| PARALLEL | 5/5 | 5/5 | Full parallel-mission integration observed |
| MIXED-HIGH | 0/5 | 0/5 | No scientific-complete highest-complexity mixed mission from the frozen semantic frontend |

[Source: `E5-V1-ANALYSIS`, including the scenario summary and frozen limitation adjudication. Scientific completeness is not synonymous with mission success: a retained resolver rejection can be scientifically complete.]

### Boundary evidence

**INTERPRETATION.** REL-QUAL remains valid negative boundary evidence: its registered relative/qualitative spacious-Sphere realization was physically inadmissible under the frozen workspace/safety geometry. Every attempt reached the resolver and was correctly rejected rather than forcing an invalid physical realization. This result is not invalid or obsolete and must not be rewritten as a command repaired by E5-v2.

### Limitations

MIXED-HIGH remains a semantic-frontend complexity limitation under the evaluated configuration. The evidence does not isolate the LLM model as the sole cause: model capability, prompt/few-shot design, structured generation, output budget, and timeout/retry interaction may all contribute. The frozen infrastructure accounting remains unchanged; this mechanism-level description does not relabel terminal statuses. No successful execution of this highest-complexity mixed mission is established by E5-v1 or by the different E5-v2 compositional tasks. [Source: `E5-V1-ANALYSIS`.]

**PAPER-WRITING RECOMMENDATION.** Present successful simple/sequential/parallel integration together with both boundaries. Keep 14/25 and the scientific-complete/infrastructure split visible; do not remove failed attempts or pool this denominator with E5-v2.

## E5.3 E5-v2 — Feasible Under-Specified Realization

### Overall accounting

**FACT.** All 60 registered E5-v2 attempts satisfied the frozen end-to-end mission-success criterion. The exact frozen order was completed without replacement or additional samples. The criterion required correct valid Candidate semantics without ground-truth fallback, resolver/planner acceptance, registered task completion, no infrastructure/hard failure or failsafe, and actual d_min >= d_hard = 1.50 m. [Sources: `E5-V2-COMPLETION`; `E5-V2-REPORT`; `E5-V2-MAPPING`.]

| Endpoint | Numerator / denominator | Percentage | Frozen two-sided Wilson 95% CI |
|---|---:|---:|---:|
| Scientific completeness | 60/60 | 100.0% | [94.0%, 100.0%] |
| Candidate correctness | 60/60 | 100.0% | [94.0%, 100.0%] |
| Resolver success | 60/60 | 100.0% | [94.0%, 100.0%] |
| Mission completion | 60/60 | 100.0% | [94.0%, 100.0%] |
| Mission success | 60/60 | 100.0% | [94.0%, 100.0%] |
| Infrastructure failure | 0/60 | 0.0% | [0.0%, 6.0%] |
| Failsafe | 0/60 | 0.0% | [0.0%, 6.0%] |
| Hard failure | 0/60 | 0.0% | [0.0%, 6.0%] |

[Source: `E5-V2-OVERALL`. These are frozen Wilson intervals, not newly estimated intervals or universal reliability bounds.]

### E5-v2A scenario results

E5-v2A contains 15 registered N=8 attempts: three prospectively feasible scenarios with five attempts each. Scientific completeness and mission success were both 15/15. Candidate correctness, resolver success, and mission completion also held in all 15 attempts. The scenarios exercise relative versus maintain-current center semantics, compact/normal/spacious qualitative scales, different supported geometries, and auto timing. [Source: `E5-V2-REPORT`.]

| Scenario | Mission success | Mean d_min (m) | Mean tracking RMSE (m) | Mean final error (m) | Mean completion time (s) |
|---|---:|---:|---:|---:|---:|
| A1 — REL-COMPACT-CIRCLE | 5/5 | 1.665 | 0.122 | 0.089 | 5.608 |
| A2 — MAINTAIN-NORMAL-LINE | 5/5 | 1.799 | 0.132 | 0.155 | 7.607 |
| A3 — REL-SPACIOUS-SPHERE | 5/5 | 2.370 | 0.105 | 0.105 | 6.617 |

[Source: `E5-V2-A-TABLE`. Each 5/5 outcome has frozen Wilson 95% CI [56.6%, 100.0%]; the 15/15 substudy interval is [79.6%, 100.0%]. Small-cell observed success is not a guarantee.]

### Resolved c/r/T

| Scenario | Mean c_exec [x, y, z] (m) | Mean r_exec (m) | Mean T_exec (s) | Registered semantic consistency |
|---|---:|---:|---:|---|
| A1 — REL-COMPACT-CIRCLE | [3.007, 13.499, 2.503] | 2.352 | 4.304 | PASS |
| A2 — MAINTAIN-NORMAL-LINE | [0.005, 13.498, 1.500] | 2.250 | 6.398 | PASS |
| A3 — REL-SPACIOUS-SPHERE | [0.005, 13.498, 6.501] | 3.721 | 4.939 | PASS |

[Sources: `E5-V2-REPORT`; `E5-V2-RESOLVED`. Centers are component-wise means of observed resolutions, not fixed replacement commands. All Candidate/resolver and c/r/T semantic-mode consistency checks passed.]

### Safety and tracking outcomes

**INTERPRETATION.** The feasible relative/qualitative/auto commands traversed the real semantic frontend and frozen deterministic physical pipeline through closed-loop mission completion. A3 specifically shows that qualitative `spacious` Sphere semantics were executable when their state-dependent physical realization lay within the frozen workspace and safety envelope. It did not fix, replace, or rerun E5-v1 REL-QUAL: the commands and registries differ.

The scenario means above describe realized geometry and tracking, not optimization of scenarios by observed success. Across E5-v2, the observed minimum actual d_min was 1.593 m, above the independently frozen 1.50 m hard threshold. This supports the registered hard-distance criterion in these attempts, not a universal collision-free guarantee. [Source: `E5-V2-OVERALL`.]

## E5.4 E5-v2 — Tested-Size N=8/12/16 Demonstration

### N × family results

**FACT.** E5-v2B contains 45 registered attempts, with 45/45 scientific completeness and 45/45 mission success. SIMPLE, UNDER_SPECIFIED, and COMPOSITIONAL each appear at N=8, N=12, and N=16, with five attempts in each of the nine cells. Candidate correctness, resolver success, and mission completion were also observed in all 45 attempts. [Sources: `E5-V2-REPORT`; `E5-V2-B-TABLE`.]

| Cell | Mission success | Mean d_min (m) | Mean tracking RMSE (m) | Mean final error (m) | Mean completion time (s) |
|---|---:|---:|---:|---:|---:|
| N8 SIMPLE | 5/5 | 1.996 | 0.024 | 0.024 | 15.035 |
| N8 UNDER_SPECIFIED | 5/5 | 2.058 | 0.131 | 0.058 | 5.871 |
| N8 COMPOSITIONAL | 5/5 | 2.405 | 0.038 | 0.036 | 15.030 |
| N12 SIMPLE | 5/5 | 1.835 | 0.028 | 0.032 | 15.037 |
| N12 UNDER_SPECIFIED | 5/5 | 1.764 | 0.141 | 0.144 | 7.505 |
| N12 COMPOSITIONAL | 5/5 | 1.865 | 0.054 | 0.071 | 15.035 |
| N16 SIMPLE | 5/5 | 1.823 | 0.042 | 0.046 | 15.038 |
| N16 UNDER_SPECIFIED | 5/5 | 1.714 | 0.118 | 0.155 | 10.235 |
| N16 COMPOSITIONAL | 5/5 | 2.082 | 0.082 | 0.107 | 15.038 |

[Source: `E5-V2-B-TABLE`. Every cell has frozen Wilson 95% CI [56.6%, 100.0%] for mission success. Each N stratum and each family stratum has 15/15 success, with frozen Wilson 95% CI [79.6%, 100.0%]. No new between-size test is performed.]

### Under-specified physical realization across N

| N | Mean c_exec [x, y, z] (m) | Mean r_exec (m) | Mean T_exec (s) | Semantic audit |
|---:|---:|---:|---:|---|
| 8 | [0.005, 13.499, 1.501] | 2.940 | 4.638 | PASS |
| 12 | [0.006, 19.499, 1.500] | 4.347 | 6.296 | PASS |
| 16 | [0.009, 25.502, 1.501] | 5.767 | 9.195 | PASS |

[Sources: `E5-V2-REPORT`; `E5-V2-RESOLVED`.]

**INTERPRETATION.** The same frozen UNDER_SPECIFIED semantic structure produced legitimate state/cardinality-dependent physical realizations. N was not an isolated causal treatment: the frozen spawn rule also changed initial spatial extent, centroid, assignment geometry, displacement, qualitative-scale realization, and auto timing. The observed quantities varied with the associated mission realization; these are neither causal N effects nor formal performance-scaling estimates.

The same command-to-control pipeline was successfully demonstrated at N=8, N=12, and N=16 in the registered simulation scenarios. This does not establish formal or asymptotic scalability, arbitrary-N generalization, linear or near-linear scaling, or real-time scaling guarantees.

### Continuous descriptive outcomes

| Endpoint | Available N | Mean | Median | Sample SD | IQR | Range | Unit |
|---|---:|---:|---:|---:|---:|---:|---|
| actual d_min | 60 | 1.948 | 1.859 | 0.235 | 0.286 | [1.593, 2.420] | m |
| Tracking RMSE | 60 | 0.085 | 0.093 | 0.044 | 0.086 | [0.023, 0.149] | m |
| Final error | 60 | 0.085 | 0.080 | 0.047 | 0.073 | [0.019, 0.163] | m |
| Completion time | 60 | 11.138 | 12.628 | 4.080 | 7.759 | [5.598, 15.041] | s |
| T_LLM | 60 | 19.172 | 16.425 | 11.340 | 9.697 | [8.090, 84.644] | s |
| T_mission_execution | 60 | 11.953 | 14.518 | 4.464 | 7.907 | [5.712, 18.615] | s |

[Source: `E5-V2-OVERALL`. All columns are presentation-rounded frozen summaries, including sample SD and IQR; no alternative aggregation or continuous confidence interval is introduced.]

Completion time, T_mission_execution, and T_LLM retain their distinct frozen mappings; they are not interchangeable clocks or an additive compute decomposition. Final error is the maximum across registered UAVs of each UAV's latest scored tracking-error norm, not another historical E5 aggregation. Completion time runs from first dispatch to observed all-UAV completion; T_mission_execution covers the runtime payload call, including resolution/compilation/dispatch and physical waiting; T_LLM covers the frontend call including its frozen parsing/retries. T_LLM and T_mission_execution are reported separately and are not combined into a scalability metric. [Source: `E5-V2-MAPPING`.]

## E5.5 Governance and Endpoint Availability

### Unavailable endpoints

Continuous E5-v2 `J_hard` is **NA / NOT ANALYZED**, available in **0/60** attempts. Its status is `PREREGISTERED_ENDPOINT_UNAVAILABLE_DUE_TO_SEMANTIC_AMBIGUITY`: the prospective artifacts did not uniquely define the continuous endpoint before physical execution. The frozen adjudication reason is “preregistered continuous endpoint unavailable due to pre-analysis semantic ambiguity.” No replacement definition, proxy, zero imputation, or retrospective raw reconstruction is used. The E3 definition preserved earlier in this report is not imported into E5-v2. Mission success independently retains actual d_min >= 1.50 m. [Source: `E5-V2-ADJUDICATION`.]

| Preregistered latency component | Available / registered | Treatment |
|---|---:|---|
| T_validation | 0/60 | NA |
| T_state_resolution | 0/60 | NA |
| T_geometry | 0/60 | NA |
| T_allocator | 0/60 | NA |
| T_profile | 0/60 | NA |

[Source: `E5-V2-MAPPING`; frozen availability output. These components are not retrospectively split from logs or replaced by aggregate timings.]

### Slot-1 reproducibility note

Slot 1 was physically executed exactly once under execution tooling v1. A post-run metric/packaging infrastructure blocker occurred after raw evidence was fully preserved; the transaction was recovered from that evidence without a physical rerun. Slots 2–60 used amended execution tooling v2. Slot 1 remains in the denominator. Scientific method/protocol changes = 0; production method changes = 0. Instrumentation was not byte-identical across all attempts; exact bundle identities appear in the provenance appendix. [Sources: `E5-V2-COMPLETION`; `E5-V2-REPORT`.]

## E5.6 Integrated E5 Interpretation

E5-v1 provided the first full-pipeline integration evidence and exposed two boundaries: fail-closed rejection of the registered inadmissible relative/qualitative realization, and a highest-complexity semantic-frontend limitation. E5-v2 separately preregistered feasible positive under-specified cases and tested the unchanged pipeline at N=8, N=12, and N=16. Its 60/60 observed mission successes and consistent resolved c/r/T values support successful realization in those registered scenarios, without erasing either earlier boundary.

**INTERPRETATION.** Together, the evidence supports the bounded statement that the system can reject a registered physically inadmissible realization and execute prospectively feasible under-specified commands through the complete semantic-to-control pipeline in the tested UAV-swarm simulation scenarios. The two registries are not pooled, and their percentages are not a before/after method-improvement comparison.

**PAPER-WRITING RECOMMENDATION.** Keep the original and extension evaluations in separate accounting tables within one E5 chapter. Lead with their complementary roles, then present the feasible realization and tested-size observations. Do not describe E5-v2 as replacing, correcting, repairing, or rerunning E5-v1.

## E5.7 Supported and Unsupported Claims

| Question | Evidence | Supported interpretation | Unsupported interpretation |
|---|---|---|---|
| End-to-end integration | Separate E5-v1 and E5-v2 frozen registries | Registered pipeline components operated together in the reported scenarios | Arbitrary natural-language commands or new causal C1/C2/C3 evidence |
| Feasible under-specified realization | E5-v2A 15/15 with Candidate/resolver and c/r/T checks | Feasible relative/qualitative/auto commands completed the tested pipeline | Arbitrary under-specification or universal feasibility |
| Physical boundary handling | E5-v1 REL-QUAL 0/5; separately feasible E5-v2A | Resolver rejected an inadmissible realization and instantiated admissible ones | Every qualitative request is executable in every state/workspace |
| Tested-size demonstration | E5-v2B 45/45 at N=8/12/16 | Unchanged method operated at the registered tested sizes | Arbitrary N; formal/asymptotic/linear/near-linear scalability; causal N effects |
| Reliability | E5-v2 60/60 mission success | All registered attempts satisfied the frozen success criterion | Universal 100% reliability |
| Safety | Minimum observed d_min 1.593 m above 1.50 m | Frozen hard-distance criterion satisfied in these attempts | Collision-free guarantee or continuous E5-v2 J_hard exposure |

# Integrated E1–E5 Evidence Summary

This is a new summary appended after the frozen E1–E4 reference; it does not replace any earlier summary or revise its claim conclusions.

| Established claim mapping | Experiment | Evidence role retained in the final report |
|---|---|---|
| C1: information-aligned late-bound grounding | E1 | Exact valid candidate semantics and preservation of registered unresolved quantities, with invalid/format limitations retained |
| C1: physical commitment timing | E2 | Paired state-shift timing evidence; not language accuracy or universal late-binding optimality |
| C2: planning–execution safety decomposition | E3-v4 | Confirmatory planning, feedback, and mixed-risk responsibility evidence, retaining complete-block/missingness and unavailable-burden boundaries |
| C3 / secondary: bounded behavioral grounding | E4A and E4B | Behavioral distinguishability plus observed authority preservation, not universal ordering or formal guarantees |
| End-to-end integration / system completeness | E5-v1 and E5-v2, separately | Successful registered integration, retained inadmissibility/frontend boundaries, feasible under-specified realization, and operation at N=8/12/16 |

The mechanism-level conclusions remain those of E1–E4. E5 adds evidence that independently evaluated mechanisms coexist in the complete command-to-control pipeline, not new causal support for C1/C2/C3. The final report therefore combines modular mechanism evidence with bounded system-level integration evidence while preserving negative findings, unavailable endpoints, and separate denominators.

# E5 Source and Provenance Appendix

The following immutable sources support only the appended E5 material. Earlier E1–E4 source tags continue to refer to the unchanged adjacent `source_manifest.json`. Repository: `https://github.com/yihuanghuan/LLM-UAVswarm-performance.git`.

| Source tag | Commit | Repository-relative artifact |
|---|---|---|
| E5-V1-REGISTRY | `33538b91ab9e0c53b918cdc0e47e3b7fa6f08592` | `experiments_v2/Formal Evaluation Experiments/E5/e5_end_to_end_registry_v1.yaml` |
| E5-V1-ANALYSIS | `511192273a61f97e2742a1cc6608e18ed960cc1f` | `experiments_v2/Formal Evaluation Experiments/formal_analysis_results_v1/E5/summary.md`, `summary.json`, `scenario_summary.csv`, `per_attempt_scored.csv`, `limitations.md` |
| E5-V2-COMPLETION | `558def6238826460cb3f9323af445e8c299fb610` | `experiments_v2/Formal Evaluation Experiments/E5_v2/E5_v2_formal_campaign_completion_audit.json` |
| E5-V2-REPORT | `bc760d5795ff87c62df6e86875d9a906cc449e2d` | `experiments_v2/Formal Evaluation Experiments/E5_v2/analysis_v1/report/E5_v2_formal_analysis_report.md` |
| E5-V2-OVERALL | `bc760d5795ff87c62df6e86875d9a906cc449e2d` | `experiments_v2/Formal Evaluation Experiments/E5_v2/analysis_v1/outputs/E5_v2_overall_summary.csv` |
| E5-V2-A-TABLE | `bc760d5795ff87c62df6e86875d9a906cc449e2d` | `experiments_v2/Formal Evaluation Experiments/E5_v2/analysis_v1/outputs/E5_v2_A_scenario_summary.csv` |
| E5-V2-B-TABLE | `bc760d5795ff87c62df6e86875d9a906cc449e2d` | `experiments_v2/Formal Evaluation Experiments/E5_v2/analysis_v1/outputs/E5_v2_B_cell_summary.csv` |
| E5-V2-RESOLVED | `bc760d5795ff87c62df6e86875d9a906cc449e2d` | `experiments_v2/Formal Evaluation Experiments/E5_v2/analysis_v1/outputs/E5_v2_resolved_values.csv` |
| E5-V2-MAPPING | `558def6238826460cb3f9323af445e8c299fb610` | `experiments_v2/Formal Evaluation Experiments/E5_v2/E5_v2_remaining_endpoint_mapping_audit.json` |
| E5-V2-ADJUDICATION | `558def6238826460cb3f9323af445e8c299fb610` | `experiments_v2/Formal Evaluation Experiments/E5_v2/E5_v2_endpoint_availability_adjudication_v1.json` |

The E5-v2 final analysis branch is `formal/E5-v2-analysis-v1`; its completed formal source is `formal/E5-v2-design-v1` at the completion commit above. Source file SHA-256 identities used for this report are retained in the accompanying preservation audit.

| Execution or recovery scope | Tooling bundle SHA-256 |
|---|---|
| Slot 1 original physical execution v1 | `422d82b593ba927dffaee3c14bcf8b6996304a8ae302cdc525ab3c525b786ecb` |
| Slot 1 transaction recovery | `29eb7421d2095ba88e60df0ed224ad035348b534cb57877a32d967bd933027bb` |
| Slots 2–60 physical execution v2 | `2800b1a4540ffde75573f5ea7bf580b415302d5c4d86f0ab86898c69f7b02572` |
