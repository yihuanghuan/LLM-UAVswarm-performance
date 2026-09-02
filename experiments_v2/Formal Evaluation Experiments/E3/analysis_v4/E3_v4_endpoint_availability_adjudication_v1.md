# E3-v4 endpoint-availability adjudication v1

Decision timestamp: `2026-09-02T02:04:05Z`

Decision stage: `BEFORE_FACTORIAL_EFFECT_ESTIMATION`

No E3-v4 factorial treatment-effect estimate was viewed or calculated before
this human decision. The immutable analysis source is commit
`f61c8c174eb4ca836a54af999189550a2bf46f34`.

## Decision

The preregistered operational endpoint `feedback_intervention_burden` is
classified as:

```text
PREREGISTERED_ENDPOINT_UNAVAILABLE_DUE_TO_INSTRUMENTATION_OMISSION
```

It is not a primary safety endpoint. The frozen contract explicitly states
that operational/burden endpoints cannot replace a safety endpoint. Therefore
its absence has no effect on the authorized primary `J_hard` analysis or the
registered supporting safety analyses, but the burden mechanism itself is not
quantitatively testable.

## Frozen-instrumentation findings

All 343 scientifically successful formal attempts were checked. The activated
formal metric extractor and emitted `E3_v4_formal_attempt_metrics_v1` payloads
contain no quantitative field or preregistered formula for feedback
intervention burden, IAPF activation time, intervention duration/fraction,
feedback correction magnitude, or an equivalent burden metric. The sealed
registry freezes the IAPF treatment and configuration but contains no numerical
burden definition or JSON mapping.

The following existing fields are explicitly non-equivalent and will not be
substituted:

- `feedback` is the assigned F0/F1 treatment, not realized feedback activity.
- `manipulation_delivery` verifies the exogenous execution deviation, not
  controller feedback burden.
- `stability.near_acceleration_limit_sample_fraction` is the separately
  registered controller-limit endpoint, not IAPF intervention burden.

## Analysis constraints

```text
formal_success_attempts_checked = 343
endpoint_available_attempts = 0
endpoint_unavailable_attempts = 343
proxy_authorized = false
raw_rederivation_authorized = false
imputation_authorized = false
analysis_contract_modified = false
formal_metric_semantics_modified = false
formal_data_modified = false
impact_on_primary_J_hard_analysis = NONE
impact_on_supporting_safety_analysis = NONE
impact_on_burden_mechanism_analysis = ENDPOINT_NOT_TESTABLE
```

Every analysis table and report must retain an explicit endpoint-availability
row with `N = 0 / 343`, `proxy used = no`, and the result value:

```text
NA — preregistered endpoint unavailable
```

No point estimate, confidence interval, p-value, or factorial contrast may be
reported for this endpoint. The original frozen analysis contract remains
unchanged.
