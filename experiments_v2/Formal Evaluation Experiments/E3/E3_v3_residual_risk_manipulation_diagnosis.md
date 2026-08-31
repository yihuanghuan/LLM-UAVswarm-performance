# E3-v3 residual-risk manipulation diagnosis

Status: historical diagnosis of sealed formal evidence; no E3-v3 artifact is changed.

## Evidence and provenance

This diagnosis was completed before any E3-v4 qualification execution. It uses only the
immutable Campaign-v2 formal population and its frozen analysis outputs:

- production baseline: `paper-final-sim-v3` at
  `6cf402debf23851b1eff3edc6f3ab49eae7127c4`;
- actual E3 execution source: `fe1f06ea8cd30f2846afa47294169c556ade1926`;
- frozen policy SHA-256:
  `6b47d27f4253d7311e79ea51f6dd1cf0d0182e6df24374a94abae0aa6a135858`;
- authoritative registry:
  `experiments_v2/Formal Evaluation Experiments/E3/e3_factorial_registry_v3.yaml`,
  SHA-256 `b56344c6cd257e99851523d640d9a89d6def994884877e2303d8fab836e0faf2`;
- Campaign-v2 result archive: `formal/campaign-v2-results-v1` at
  `33538b91ab9e0c53b918cdc0e47e3b7fa6f08592`;
- frozen analysis: `formal/analysis-results-v1` at
  `511192273a61f97e2742a1cc6608e18ed960cc1f`.

The registered hard threshold is `d_hard = 1.5 m`. Rosbag re-extraction used the
frozen analysis signal definitions and the interaction-command timestamp as `t0`.
Only `P0_F0` and `P1_F0` are evaluated below. No feedback-on contrast is used.

## Family B: registered disturbance did not create residual hard risk

All 60 Family-B feedback-off attempts were scientifically complete. Every attempt had
`predicted_d_min = 2.0 m`, zero predicted hard violations, zero realized hard-risk
events, and zero hard-risk exposure.

| Scenario | Condition | N | actual d_min mean (range), m | hard-event attempts | total J_hard, pair-s | minimum-time mean (range), s after t0 |
|---|---:|---:|---:|---:|---:|---:|
| B-01 | P0_F0 | 15 | 1.9602 (1.9390--1.9790) | 0/15 | 0 | 5.253 (2.589--6.429) |
| B-01 | P1_F0 | 15 | 1.9660 (1.9577--1.9793) | 0/15 | 0 | 5.731 (3.689--8.737) |
| B-02 | P0_F0 | 15 | 1.9556 (1.9347--1.9774) | 0/15 | 0 | 3.672 (2.804--5.442) |
| B-02 | P1_F0 | 15 | 1.9429 (1.9249--1.9714) | 0/15 | 0 | 3.428 (2.955--5.486) |

Pooled over B-01 and B-02, the feedback-off actual minima were 1.9579 m for P0
and 1.9544 m for P1. Thus the 30 P0_F0 attempts and the 30 P1_F0 attempts both
show a strict floor of 0/30 hard-risk attempts.

### B-01: lateral inward wrench

The arm message was retained at a mean of 0.00085 s after the interaction command.
The realized rectangular-force interval was therefore approximately
`[t0 + 2.00085, t0 + 3.50085]` (registered interval `[2.0, 3.5]` s). Across the
30 feedback-off attempts, the two affected UAVs showed a mean maximum inward
tracking displacement of 0.2767 m and a mean maximum inward velocity of 0.4069 m/s.
The force therefore produced a measurable vehicle response.

It did not act on the pair that set `d_min`. In all 30 attempts, the minimum pair was
the same-lane pair 1--2 or 3--4; the disturbed pair 2--3 never set the minimum. Under
the registered parallel paths, UAVs 2 and 3 retain a 2 m longitudinal offset. A pure
world-y inward displacement cannot reduce their ideal pair distance below that 2 m
offset, even if their lateral separation is reduced to zero. This geometric floor is
above `d_hard = 1.5 m`.

### B-02: vertical inward wrench

The arm message was retained at a mean of 0.00370 s after `t0` across both planning
modes; 59/60 offsets were near 1 ms and one P0_F0 offset was 0.0858 s. The resulting
mean force interval was approximately `[t0 + 2.00370, t0 + 3.50370]`. Across the
30 feedback-off attempts, the affected UAVs showed a mean maximum inward tracking
displacement of 0.0935 m and a mean maximum inward velocity of 0.2770 m/s.

Again the minimum pair was always 1--2 or 3--4, never disturbed pair 2--3. The
affected pair retains 2 m world-x and 2.8 m world-y separation, a horizontal norm of
`sqrt(2^2 + 2.8^2) = 3.441 m`. A pure world-z inward wrench cannot bring that pair
below 3.441 m even if its vertical separation becomes zero. The registered physical
mode therefore could not create the intended hard-risk event through its stated axis.

### Family-B diagnosis

The 2 N x 1.5 s stimuli were not merely associated with small safety changes. They
were applied to pair/axis combinations whose invariant orthogonal separation kept the
affected pair outside the hard-risk regime. The measured displacement and velocity
response confirms that this is not evidence of a missing stimulus. It is a failure of
the external-condition manipulation to map that response into the registered endpoint.

## Family C: planning removes the only measured hard-risk component

| Scenario | Condition | scientific-complete N | predicted d_min, m | predicted-hard attempts | actual d_min mean (range), m | hard-event attempts | total J_hard, pair-s |
|---|---:|---:|---:|---:|---:|---:|---:|
| C-01 | P0_F0 | 15 | 0.4275 | 15/15 | 0.3050 (0.0474--0.7695) | 15/15 | 14.6454 |
| C-01 | P1_F0 | 15 | 2.0000 | 0/15 | 1.9418 (1.9151--1.9586) | 0/15 | 0 |
| C-02 | P0_F0 | 11 | 0.0000 | 11/11 | 0.3462 (0.1791--0.4304) | 11/11 | 40.3447 |
| C-02 | P1_F0 | 13 | 2.2484 | 0/13 | 2.2497 (2.2326--2.2902) | 0/13 | 0 |

The four and six non-complete rows, respectively, remain retained Campaign-v2
infrastructure outcomes and are not silently removed from operational accounting.

For both mixed-risk scenarios, P0_F0 confirms a strong predictable structural-risk
manipulation. P1 removes the nominal structural component, but P1_F0 then has zero
hard-risk events and zero exposure in every scientific-complete attempt. Consequently,
the registered C disturbances do not leave a measurable residual realized-risk
component after planning. E3-v3 Family C principally tests planning, not the intended
planning-plus-execution responsibility decomposition.

## Conclusion

The sealed E3-v3 evidence implements

`nominally safe plan + registered disturbance -> still safe`

in Family B, and implements `structural risk -> planning removal -> safe execution`
in Family C. This is an experimental manipulation failure/floor effect. It is not
evidence that feedback execution is ineffective because the feedback responsibility
was never tested against a qualified residual hard-risk population. E3-v3 remains
valid and immutable historical evidence; E3-v4 must be a separately versioned
confirmatory experiment.
