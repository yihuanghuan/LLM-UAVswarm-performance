# E3-v4 formal confirmatory analysis

This report implements the frozen standalone E3-v4 analysis. Signed effects are retained: negative values are safer for exposure/events/risk/failsafe/near-limit endpoints, while positive values are safer for minimum separation and mission success.

## 1. Frozen provenance

Integrity gate: **PASS**. The immutable campaign source is `f61c8c174eb4ca836a54af999189550a2bf46f34` (`experiment: freeze E3-v4 formal campaign completion audit`). Analysis ran on `formal/E3-v4-analysis-v1`, whose merge base is the immutable source. No path outside `analysis_v4/` changed relative to that source.

The contract correctly retains the candidate registry hash `80ddbb8701f1c7feb84ae64a7985f233742f522c1204131ab4dd6d09960bd79b`. Human activation repinned the sealed registry to `2b3dccc2ad27cf317029c2b7b014bca3a8b28fc8c0a196fd4c2e5abe0be9d4b7` while candidate and sealed scientific payload hashes were both `43a4805a5c9bd881fc3cc8ff0785bbf3436a5fbbffc38596d05e985b88a896e0` (`candidate_vs_sealed_scientific_payload_equivalent: true`; scientific protocol changes: 0). This is valid provenance, not an inconsistency.

Activated execution tooling bundle: `78cb5dbc374983c64752433fa1c62c4990903b03b5b813f0248f13105eb074bf`. Frozen thresholds are d_hard=1.50 m and d_plan=1.80 m.

## 2. Campaign/population audit

The independently reconstructed campaign contains 360 registered and consumed slots, 360 journal records, 360 unique trial IDs, 360 attempt directories, 343 scientifically successful attempts, and 17 infrastructure failures. There are no other statuses, replacements, or additional samples. Raw storage comprises 359 `RAW_ARCHIVE_VERIFIED` records and one preregistered pre-raw acquisition failure (slot 105), with no pending archive and no raw-evidence loss.

## 3. Missingness report

Sixteen of 90 registered scenario-by-seed blocks are incomplete; one block has two failed cells. The 17 failed slots are 3, 4, 5, 6, 7, 35, 105, 134, 210, 236, 266, 271, 274, 301, 324, 343, and 353. Missingness is described without an MCAR claim. Failure mechanisms include formal metric/delivery verification failures, stage/interaction deviation-driver failures, and the slot-105 all-UAV readiness failure. The machine-readable tables give every slot and summaries by family, scenario, condition, seed, and mechanism.

| Dimension | Distribution of 17 infrastructure failures |
|---|---|
| Family | A: 8; B: 4; C: 5 |
| Scenario | E3-A-01: 1; E3-A-02: 7; E3-B-01: 1; E3-B-02: 3; E3-C-01: 3; E3-C-02: 2 |
| Condition | P0_F0: 6; P0_F1: 3; P1_F0: 5; P1_F1: 3 |
| Mechanism | metric/delivery verification: 6; stage deviation driver: 7; interaction deviation driver: 3; all-UAV readiness: 1 |

## 4. Primary block population

Primary factorial estimation uses only 74 complete four-success-cell repeated-measures blocks (296 attempts). The remaining 16 blocks are excluded as whole blocks; their 47 successful cells are never used in primary contrasts. Complete-block counts are Family A=23, Family B=26, and Family C=25.

## 5. Metric mapping

| Endpoint | Authoritative formal-attempt JSON field/path | Analysis encoding |
|---|---|---|
| `j_hard_pair_s` | `metrics.realized.hard_risk_exposure_pair_s` | stored numeric/boolean value |
| `realized_min_separation_m` | `metrics.realized.d_min_m` | stored numeric/boolean value |
| `hard_risk_event_count` | `metrics.realized.hard_risk_event_count` | stored numeric/boolean value |
| `predicted_min_separation_m` | `metrics.predicted.d_min_m` | stored numeric/boolean value |
| `predicted_hard_conflict_count` | `metrics.predicted.hard_violations` | stored numeric/boolean value |
| `controller_near_limit_fraction` | `metrics.stability.near_acceleration_limit_sample_fraction` | stored numeric/boolean value |
| `any_realized_hard_risk` | `metrics.realized.hard_risk_event_count` | int(hard_risk_event_count > 0) |
| `mission_success` | `metrics.stability.mission_success` | stored numeric/boolean value |
| `failsafe_seen` | `metrics.stability.failsafe_seen` | stored numeric/boolean value |
| `feedback_intervention_burden` | `Unavailable in frozen instrumentation` | N=0/343; no proxy |

`any_realized_hard_risk` is only a 0/1 encoding of whether the frozen event count is positive; no raw metric was recomputed. `feedback_intervention_burden` is NA for 0/343 successful attempts under the pre-effect-estimation endpoint-availability adjudication; no proxy is used.

## 6. Family A results

The primary J_hard `Delta_P` estimate is -1.6810 (95% CI -1.9786 to -1.4690; N=23). Supporting estimates are realized minimum separation 1.8288 (95% CI 1.7718 to 1.8834; N=23), hard-risk event count -2.1087 (95% CI -2.3261 to -2.0000; N=23), and any-hard-risk risk difference -1.0000 (95% CI -1.0000 to -1.0000; N=23).

## 7. Family B results

The primary J_hard `Delta_F` estimate is -1.2275 (95% CI -1.3890 to -1.0562; N=26). Supporting estimates are realized minimum separation 0.0492 (95% CI 0.0250 to 0.0656; N=26), hard-risk event count -0.7692 (95% CI -1.3846 to -0.0769; N=26), and any-hard-risk risk difference -0.3462 (95% CI -0.4615 to -0.2115; N=26).

## 8. Family C results

For J_hard, Delta_P is -1.7116 (95% CI -1.9162 to -1.5084; N=25), Delta_F is -1.2004 (95% CI -1.3834 to -1.0129; N=25), and Delta_PF is 0.3239 (95% CI -0.0825 to 0.7311; N=25). The P1_F0 residual-risk cell has mean J_hard=1.3687 pair-s and any-hard-risk 22/25=0.8800 (N=25). Under P1, F1 reduced mean exposure to 0.3303 pair-s; the paired simple F1-minus-F0 point difference was -1.0384 pair-s. Thus planning removed the predictable component but did not eliminate residual execution risk, which feedback then reduced. P1_F1 is not treated as obligatorily best on every endpoint.

## 9. Primary J_hard factorial estimates

| Family | Contrast | Mean block contrast | 95% CI | N | d_z |
|---|---:|---:|---:|---:|---:|
| A | Delta_P | -1.6810 | -1.9786 to -1.4690 | 23 | -1.7011 |
| A | Delta_F | -0.0571 | -0.3679 to 0.1479 | 23 | -0.0830 |
| A | Delta_PF | 0.1143 | -0.2985 to 0.7340 | 23 | 0.0830 |
| B | Delta_P | -0.0444 | -0.2481 to 0.1526 | 26 | -0.0831 |
| B | Delta_F | -1.2275 | -1.3890 to -1.0562 | 26 | -1.3022 |
| B | Delta_PF | 0.2572 | -0.1295 to 0.6765 | 26 | 0.2368 |
| C | Delta_P | -1.7116 | -1.9162 to -1.5084 | 25 | -3.0229 |
| C | Delta_F | -1.2004 | -1.3834 to -1.0129 | 25 | -1.4283 |
| C | Delta_PF | 0.3239 | -0.0825 to 0.7311 | 25 | 0.3002 |

## 10. Supporting safety endpoints

| Family | Registered focus | Realized d_min | Hard-event count |
|---|---|---:|---:|
| A | Delta_P | 1.8288 (95% CI 1.7718 to 1.8834; N=23) | -2.1087 (95% CI -2.3261 to -2.0000; N=23) |
| B | Delta_F | 0.0492 (95% CI 0.0250 to 0.0656; N=26) | -0.7692 (95% CI -1.3846 to -0.0769; N=26) |
| C | Delta_P | 0.8666 (95% CI 0.8441 to 0.8936; N=25) | -2.4600 (95% CI -2.9000 to -2.0400; N=25) |
| C | Delta_F | 0.0706 (95% CI 0.0531 to 0.0877; N=25) | -1.7000 (95% CI -2.0800 to -1.3200; N=25) |
| C | Delta_PF | -0.0559 (95% CI -0.0895 to -0.0209; N=25) | 0.9200 (95% CI 0.0800 to 1.8000; N=25) |

## 11. Binary endpoint results

| Family | Contrast | Any-hard-risk risk difference | 95% CI | N |
|---|---|---:|---:|---:|
| A | Delta_P | -1.0000 | -1.0000 to -1.0000 | 23 |
| A | Delta_F | 0.0000 | 0.0000 to 0.0000 | 23 |
| A | Delta_PF | 0.0000 | 0.0000 to 0.0000 | 23 |
| B | Delta_P | -0.0385 | -0.1154 to 0.0385 | 26 |
| B | Delta_F | -0.3462 | -0.4615 to -0.2115 | 26 |
| B | Delta_PF | 0.1538 | -0.0385 to 0.3462 | 26 |
| C | Delta_P | -0.3000 | -0.3600 to -0.2400 | 25 |
| C | Delta_F | -0.1800 | -0.2400 to -0.1200 | 25 |
| C | Delta_PF | -0.3600 | -0.4800 to -0.2400 | 25 |

Cell proportions use Wilson 95% intervals. All four registered simple paired comparisons are reported with exact McNemar p-values, Holm-adjusted p-values within family, paired risk differences, and scenario-stratified paired-block percentile-bootstrap intervals. No effect is suppressed by p-value.

## 12. Manipulation checks

Family A's planning manipulation changed predicted hard-conflict count by -2.0000 (95% CI -2.0000 to -2.0000; N=23) for Delta_P. Family B F0 retained residual realized exposure descriptively (P0_F0 mean=1.6609, P1_F0 mean=1.4878 pair-s). Family C's predictable component changed from mean predicted conflicts 2.0000 in P0_F0 to 0.0000 in P1_F0; realized P1_F0 residual exposure is reported above. These checks do not authorize exclusions or retuning.

## 13. Available-cell sensitivity

The available-cell dataset includes all 343 scientifically successful attempts, including 47 successful cells from incomplete blocks. It is descriptive/sensitivity-only and does not replace the 74-block primary analysis.

| Family | Condition | J_hard mean (N) | Any-hard-risk proportion (Wilson 95% CI) |
|---|---|---:|---:|
| A | P0_F0 | 1.7326 (25) | 25/25=1.0000 (0.8668 to 1.0000) |
| A | P0_F1 | 1.8816 (29) | 29/29=1.0000 (0.8830 to 1.0000) |
| A | P1_F0 | 0.0000 (30) | 0/30=0.0000 (0.0000 to 0.1135) |
| A | P1_F1 | 0.0000 (28) | 0/28=0.0000 (0.0000 to 0.1206) |
| B | P0_F0 | 1.5977 (30) | 30/30=1.0000 (0.8865 to 1.0000) |
| B | P0_F1 | 0.3212 (29) | 18/29=0.6207 (0.4400 to 0.7731) |
| B | P1_F0 | 1.4731 (27) | 24/27=0.8889 (0.7194 to 0.9615) |
| B | P1_F1 | 0.4033 (30) | 19/30=0.6333 (0.4551 to 0.7813) |
| C | P0_F0 | 3.2304 (29) | 29/29=1.0000 (0.8830 to 1.0000) |
| C | P0_F1 | 1.8832 (29) | 29/29=1.0000 (0.8830 to 1.0000) |
| C | P1_F0 | 1.3961 (28) | 25/28=0.8929 (0.7280 to 0.9629) |
| C | P1_F1 | 0.3285 (29) | 15/29=0.5172 (0.3443 to 0.6861) |

## 14. All-attempt operational sensitivity

Attempt status was successful for 343/360 and infrastructure failure for 17/360. Among the 343 scientifically scored attempts, mission success was 343/343 (1.0000; Wilson 95% CI 0.9889 to 1.0000) and failsafe was seen in 0/343 (0.0000; Wilson 95% CI 0.0000 to 0.0111). Mission/failsafe fields are unavailable for the 17 infrastructure failures; no zero-imputation or new all-attempt scoring rule is used. Attempt success is not conflated with mission success.

## 15. Limitations

Inference is restricted to 74 complete blocks in six fixed scenarios within the tested UAV-swarm reconfiguration domain. Sixteen blocks are incomplete because of infrastructure failure; missingness is not assumed MCAR. Feedback intervention burden was omitted by frozen instrumentation and is not quantitatively testable. Percentile-bootstrap uncertainty reflects paired seeds stratified by the two fixed scenarios per family; it does not establish universal safety, zero collision probability, or superiority to untested methods.

## 16. Claim-level interpretation

- Family A: registered J_hard hypothesis direction=negative; observed Delta_P=-1.6810 (95% CI -1.9786 to -1.4690; N=23); directionally consistent and resolved away from zero.
- Family B: registered J_hard hypothesis direction=negative; observed Delta_F=-1.2275 (95% CI -1.3890 to -1.0562; N=26); directionally consistent and resolved away from zero.
- Family C: J_hard Delta_P=-1.7116 (95% CI -1.9162 to -1.5084; N=25), Delta_F=-1.2004 (95% CI -1.3834 to -1.0129; N=25), Delta_PF=0.3239 (95% CI -0.0825 to 0.7311; N=25). The observed planning and feedback responsibility pattern, not a post-hoc nonzero-interaction requirement, governs the decomposition interpretation.

Family A supports planning responsibility: planning reduced J_hard, events, and binary risk while increasing minimum separation. Family B resolves the previous feedback-side uncertainty within the redesigned confirmatory assay: feedback reduced J_hard, events, and binary risk while increasing minimum separation. Family C supports a responsibility-decomposition interpretation because both registered responsibility effects reduce J_hard and the P1_F0 cell retains residual risk that F1 reduces; the interaction need not be nonzero and its CI crossing zero is compatible with approximately orthogonal components.

Accordingly, the scientifically defensible Contribution 2 wording is **planning–execution safety decomposition within the tested UAV-swarm reconfiguration scenarios**. This stronger wording must remain domain-bounded and mechanism-specific. The missing feedback-intervention-burden instrumentation prevents a quantitative efficiency/burden claim and should be disclosed, but it does not replace or negate the registered safety-endpoint evidence. The evidence does not authorize universal guarantees, zero-collision claims, generalization beyond the tested domain, or comparisons with unevaluated methods. E3-v3 is not pooled with E3-v4.
