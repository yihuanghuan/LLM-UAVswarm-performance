# Large-swarm diagnostics v2 final audit

Status: **PASS** (governance and diagnostic completion; not an N24 infrastructure PASS).

- Immutable v1 outcomes remain N20 PASS, N24 FAIL, N28 FAIL, N32 FAIL.
- Production baseline remains `paper-final-sim-v3` / `6cf402debf23851b1eff3edc6f3ab49eae7127c4`.
- Production policy remains SHA-256 `6b47d27f4253d7311e79ea51f6dd1cf0d0182e6df24374a94abae0aa6a135858`.
- Production controller source is unchanged and byte-identical to the baseline (SHA-256 `cc7a3b1c36126555749504d03b504c1c6c01e210ffb829b473d8980a87973dfa`).
- Production method changes: 0.
- E5-v2 changes: 0.
- Profile v2 changes were limited to staged PX4/XRCE startup, batched controller startup, and observation-only 1 Hz file/process summaries.
- N24 profile v2: FAIL at unchanged readiness gate after 300.000 s; lower-layer writer gate PASS 24/24; cleanup PASS with zero residuals.
- N28 profile v2: NOT RUN, as required after N24 failure.
- N32 profile v2: NOT RUN, as required after N24 failure.
- No weakened readiness criterion, timeout inflation, middleware/topology change, physics-fidelity reduction, control change, or safety disablement occurred.
- Largest stable N under profile v2: null (N20 was not rerun under v2).
- Historical largest tested stable N under v1: 20.
- `primary_showcase_N_v2`: null.
- Scientific showcase missions: 0; D1/D2/D3 missions: 0.

The audit concludes that the v1 missing-state tail was infrastructure related and was removed by staged XRCE startup, while stable grid hover remains blocked by a frozen production-method line-layout assumption. No N>=24 showcase configuration has been validated under authorized method-preserving changes.
