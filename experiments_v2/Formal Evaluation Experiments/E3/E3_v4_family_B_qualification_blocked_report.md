# E3-v4 Family B qualification report — blocked at B-02

Status: `BLOCKED_AT_E3_B_02_FINITE_GRID_EXHAUSTED`  
Dataset class: calibration/pilot only; not formal effect-estimation data  
Feedback firewall: only `P0_F0` and `P1_F0` were executed  
Formal E3-v4 attempts executed: **0**

## Governance and provenance

Qualification followed the contract committed before the first new physical pilot.
The five qualification seeds were `69707, 69912, 68907, 67442, 64654`. The frozen
candidate-grid SHA-256 is
`39df52f5949e7a5e544a2cc90dca5f2d928e341f6035e1ea1f628f0b824e419d`, and the
qualification-seed-registry SHA-256 is
`0da0c28cb3c9368135ae6031a6e32efa03e9588e65d4e81c67b6d0eaa0159459`.

The production baseline remained
`6cf402debf23851b1eff3edc6f3ab49eae7127c4`; the production policy SHA-256 remained
`6b47d27f4253d7311e79ea51f6dd1cf0d0182e6df24374a94abae0aa6a135858`; and the
sealed E3-v3 registry SHA-256 remained
`b56344c6cd257e99851523d640d9a89d6def994884877e2303d8fab836e0faf2`.

There are 102 retained attempt rows: 100 scientific-complete F0 attempts and two
append-only infrastructure failures. Both failures were repeated with the same seed
and an explicit `retry-r1` identity. No replacement seed was used. The compact
machine-readable evidence freeze contains per-attempt manifest, metric, and raw
inventory hashes.

## B-01: qualified horizontal residual-risk scene

The first passing candidate was `B01-G2-1p5N-1p5`; search stopped immediately after
this full pass. Its exact external conditions are:

- duration: 8.0 s;
- initial positions: UAV1 `[-3,-1,3]`, UAV2 `[-1,-1,3]`, UAV3 `[-1,1,3]`,
  UAV4 `[1,1,3]` m;
- ordered targets: UAV1 `[5,-1,3]`, UAV2 `[7,-1,3]`, UAV3 `[7,1,3]`,
  UAV4 `[9,1,3]` m;
- affected pair: UAV2/UAV3;
- rectangular world-frame force: UAV2 `[0,+1.5,0]` N and UAV3 `[0,-1.5,0]` N;
- onset 2.0 s, force duration 1.5 s, zero torque and zero wrench at end.

Both planning modes had nominal predicted `d_min = 2.0 m`, zero predicted hard
violations, and the same registered predicted-hard outcome. Thus risk was not
inserted into the nominal plan.

| F0 planning mode | Events / 5 | Actual d_min range (m) | Aggregate J_hard (pair·s) | Affected-pair event attempts | Mission success |
|---|---:|---:|---:|---:|---:|
| P0_F0 | 4/5 | 1.463471–1.972081 | 0.810054 | 4 | 5/5 |
| P1_F0 | 4/5 | 1.475001–1.502772 | 1.180295 | 4 | 5/5 |

Every registered event involved pair 2–3 and began after disturbance onset. No
attempt had `d_min <= 0.25 m`, failsafe, or mission failure. This is measurable but
recoverable residual realized risk and passes B-Q1 through B-Q5 without observing F1.

Rejected B-01 candidates are retained:

| Candidate | P0_F0 | P1_F0 | Classification and reason |
|---|---:|---:|---|
| B01-V3-5N-2p0 | not run | not run | `REJECT_ANALYTIC_IMPOSSIBILITY`: pure-y force leaves a 2.0 m longitudinal lower bound |
| B01-G1-4N-1p5 | 5/5 | 5/5 | `REJECT_CEILING` |
| B01-G1-5N-1p5 | 5/5 | 5/5 | `REJECT_CEILING` |
| B01-G1-4N-2p0 | 5/5 | 5/5 | `REJECT_CEILING` |
| B01-G2-2N-1p5 | not run | not run | not evaluated after first pass |
| B01-G2-2p5N-1p5 | not run | not run | not evaluated after first pass |

## B-02: no qualified vertical scene in the frozen finite grid

The v3 geometry was analytically rejected before physical execution: pure-z force on
UAV2/UAV3 leaves a 3.4409 m horizontal separation lower bound, above `d_hard`.
The registered aligned 3 m and 2 m vertical-pair fallbacks were then evaluated in
the exact frozen order.

| Candidate | P0_F0 events / 5; d_min range (m) | P1_F0 events / 5; d_min range (m) | Classification |
|---|---|---|---|
| B02-G1-4N-1p5 | 0/5; 1.892542–1.963973 | 0/5; 1.888413–1.965242 | `REJECT_FLOOR` |
| B02-G1-5N-1p5 | 0/5; 1.866926–1.907401 | 0/5; 1.850818–1.923606 | `REJECT_FLOOR` |
| B02-G1-6N-2p0 | 0/5; 1.809088–1.863165 | 1/5; 0.113200–1.947153 | `REJECT_FLOOR`, `REJECT_STABILITY`, `REJECT_CAUSAL_ALIGNMENT` |
| B02-G2-2N-1p5 | 0/5; 1.817751–1.872754 | 1/5; 0.301613–1.831961 | `REJECT_FLOOR`, `REJECT_CAUSAL_ALIGNMENT` |
| B02-G2-3N-1p5 | 0/5; 1.710476–1.916088 | 1/5; 0.186106–1.734738 | `REJECT_FLOOR`, `REJECT_STABILITY`, `REJECT_CAUSAL_ALIGNMENT` |
| B02-G2-4N-1p5 | 0/5; 1.617804–1.969589 | 0/5; 1.616398–1.641592 | `REJECT_FLOOR` |

The isolated P1_F0 events above involved pair 1–2, not the registered affected pair
2–3, so they cannot satisfy the residual-risk manipulation check. Two also crossed
the preregistered 0.25 m catastrophic exclusion. All P0_F0 candidates remained at
0/5 events; the final and strongest registered G2 candidate also remained 0/5 in
both modes. Therefore no B-02 candidate passes B-Q3/B-Q5.

## Stopping decision

The prospectively frozen finite B-02 grid is exhausted. Adding a 5 N G2 stimulus,
altering seed prevalence, changing geometry again, or expanding the search after
seeing these results would be an unregistered adaptive search. The committed
qualification contract requires stopping here rather than tuning further.

Accordingly, Family C qualification and Family A compatibility validation were not
started. No E3-v4 six-scene registry, formal-seed registry, 360-trial order, or v4
analysis freeze was created, because doing so would falsely label an incomplete
factorial as preflight-ready. No production method change is requested or authorized.

Continuation, if desired, requires a human-approved, prospectively versioned
qualification amendment containing a new finite external-condition grid. It must be
committed before any further B-02 pilot and must continue to prohibit F1-based scene
selection.
