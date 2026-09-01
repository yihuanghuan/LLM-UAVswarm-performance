# E3-v4 Family-B deterministic execution-deviation qualification

Status: `FAMILY_B_QUALIFIED`

This is F0-only calibration evidence, not a formal result. The six-cell grid
was committed in `ad66252e7af7378b256b1370fc19d8c63246921f` before physical
screening. Grid SHA-256 is
`fd2ef8d93644d3efe16522b2a953fe529e05ec0227a9364aa20f14fa74793e7f`.
The compact evidence SHA-256 is
`6b5bf5e63f6ae89218c44593ed5e9e1e1ca6c65569898ba60fa98f84eaa141a0`.

## Planning and delivery gates

The offline frozen-policy audit passed for both mechanisms and both planning
modes. B-01 used identity assignment, zero predicted hard violations, and
predicted minimum separation 2.0 m. B-02 used identity assignment, zero
predicted hard violations, and predicted minimum separation 2.4 m. P0 and P1
therefore differed neither in ownership nor registered nominal safety.

Every selected scientific attempt has exactly verified post-planning delivery.
The planning-commitment ledger precedes the first nominal command and contains
the resolved assignment and runtime-spec hash. B-01 command timestamps and
controller acknowledgments verify the delayed publication. B-02 nominal,
bias, and reset commands have distinct mission IDs; exact payload, activation,
runtime reference endpoint, reset, and controller acknowledgments are present.

All 60 registered trials have one eligible F0 record. Sixty-nine attempt
instances are retained: 60 eligible records, seven recorded infrastructure
failures, and two original records rejected by the post-hoc global staging
audit. The latter had approximately 7 m maximum staging error and remain
immutable. Their same-seed retries passed the fail-closed online staging gate.
No seed was replaced. Raw bags remain append-only under
`results/qualification/execution_deviation_raw/`; the compact raw-inventory SHA
is `4a3a9e4a8335f02f7ca291d4bdbe7767f4e5dac5042e180e59555fedf7054bcf`.

## Complete finite-grid result

| Candidate | P0 event seeds | P1 event seeds | P0 d_min range (m) | P1 d_min range (m) | Decision |
|---|---:|---:|---:|---:|---|
| B01-DELAY-D0p4 | 5/5 | 5/5 | 1.407–1.453 | 1.407–1.434 | PASS, selected |
| B01-DELAY-D0p5 | 5/5 | 5/5 | 1.257–1.305 | 1.276–1.345 | PASS, larger deviation |
| B01-DELAY-D0p6 | 5/5 | 5/5 | 1.169–1.220 | 1.169–1.275 | PASS, larger deviation |
| B02-REF-O1p2 | 0/5 | 0/5 | 1.711–1.724 | 1.705–1.729 | REJECT, floor |
| B02-REF-O1p5 | 5/5 | 5/5 | 1.402–1.437 | 1.387–1.402 | PASS, selected |
| B02-REF-O1p8 | 5/5 | 5/5 | 1.063–1.093 | 1.073–1.119 | PASS, larger deviation |

The preregistered treatment-blind selection rule therefore selects the
smallest passing deviation for each mechanism: `B01-DELAY-D0p4` and
`B02-REF-O1p5`.

## Selected B-01

B-01 is a four-UAV parallel translation lasting 8.0 s. Initial positions are:

```text
1 [ 0.0000000000000000, -4.0, 3.0]
2 [-1.7320508075688772, -0.5, 3.0]
3 [ 0.0000000000000000,  0.5, 3.0]
4 [ 0.0000000000000000,  4.0, 3.0]
```

Each target adds `[8,0,0]`. UAV3 receives its already committed nominal
command 0.4 s after UAVs 1, 2, and 4. Across both planning modes all ten actual
delays equal 0.4 s to floating-point precision, within the frozen 0.05 s
tolerance. Pair 2-3 is the minimum and only event pair in all ten records.
P0 exposure ranges 1.755–2.455 pair-s; P1 exposure ranges 2.110–2.444 pair-s.

## Selected B-02

B-02 is a six-UAV concentric contraction from radius 5.0 m to radius 2.4 m,
lasting 10.0 s, with the exact coordinates frozen in the Family-B registry.
At 3.5 s after nominal command acceptance, UAV3 receives a temporary reference
command whose endpoint is its counterfactual nominal reference at 6.5 s plus
`[1.5,0,0]` m in world ENU. At 6.5 s it receives a reset command to the original
committed target.

All ten activation times are exactly 3.5 s and all ten durations exactly 3.0 s.
The independently observed runtime endpoint error is at most 0.0092 m, below
the frozen 0.15 m tolerance. Pre-activation minimum separation is
4.387–4.410 m with zero hard events. Pair 2-3 is the minimum and only event pair
in all ten eligible records. P0 exposure ranges 0.699–1.042 pair-s; P1 exposure
ranges 0.929–1.071 pair-s.

## Recoverability and sealed conditions

Every selected-cell record completed the mission, no PX4 failsafe was observed,
no distance was at or below 0.25 m, and the near-acceleration-limit sample
fraction was zero. Both assays are measurable and non-catastrophic under F0.

```text
F1_attempt_count = 0
formal_attempt_count = 0
production_method_changed = false
```

No F1 outcome was generated or used. Family B is ready for use as an input to
the separately preregistered Family-C qualification; E3-v4 as a whole is not
yet preflight-ready.
