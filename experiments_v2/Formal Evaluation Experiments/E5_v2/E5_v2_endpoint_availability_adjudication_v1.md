# E5-v2 endpoint-availability adjudication v1

## Human decision

E5-v2 continues. The preregistered endpoint `J_hard` is classified as:

`PREREGISTERED_ENDPOINT_UNAVAILABLE_DUE_TO_SEMANTIC_AMBIGUITY`

The decision occurred after one physical attempt, but before any scientific
metric extraction or accepted-result publication. At decision time there was
one physical attempt, zero accepted formal results, zero journal records, and no
scientific metric value had been viewed.

## Required handling

`J_hard` was preregistered as a continuous safety outcome, but its exact
functional was not prospectively identifiable. It is unavailable for all 60
E5-v2 attempts. Every compact attempt must emit exactly:

```json
{
  "available": false,
  "value": null,
  "reason": "preregistered continuous endpoint unavailable due to pre-analysis semantic ambiguity"
}
```

There is no replacement definition, proxy, imputation, or permitted raw
rederivation. In particular, none of the following is an accepted substitute:

- `int(not d_min_ok)`;
- planner `hard_violations`;
- C0-E hard-duration;
- E3-v4 pair-second exposure;
- any-pair union duration;
- hard-risk event count;
- distance-deficit integral.

The old binary implementation must not be reported as `J_hard` or renamed into
a new scientific endpoint.

## Consequences

The unavailability of `J_hard` does not change mission success. The independently
frozen criterion remains `actual d_min >= d_hard = 1.50 m`, together with every
other frozen mission-success requirement.

E5-v2 may continue to report all-attempt mission success, scientific
completeness, Candidate correctness, resolver success, mission completion,
actual `d_min`, tracking RMSE, final error, failsafe, hard failure, resolved
`c_exec`/`r_exec`/`T_exec`, completion time, and registered latency components
when available.

E5-v2 may not report a continuous `J_hard`, exposure duration, pair-seconds,
event count, or deficit integral. The analysis contract remains byte-unchanged,
and E5-v2 remains integration evidence only.
