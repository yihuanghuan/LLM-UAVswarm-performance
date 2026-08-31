# E3-v4 B-02 amendment-v1 qualification report — finite grid exhausted

Status: `BLOCKED_AT_E3_B02_AMENDMENT_V1_EXHAUSTED`

Dataset class: calibration/pilot only; not formal effect-estimation data

Formal E3-v4 attempts executed: **0**

## Prospective governance

The geometry diagnosis, amendment contract, exact 9-cell grid, offline allocator
audit, and reserved holdout seeds were committed as
`3b18353080cd2ee0ef77b75c4705c07aff2dd2cb` at
`2026-08-31T10:53:12Z`. The first amendment pilot began at
`2026-08-31T10:53:59Z`, 47 seconds after that commit. Thus the amendment commit
preceded every new physical pilot.

The frozen inputs have these SHA-256 values:

- amendment grid: `b07e27a9201a71719fd0c5120c756b7e74824e7303ac10840d9df9d081fa18fa`;
- screening-seed registry: `0da0c28cb3c9368135ae6031a6e32efa03e9588e65d4e81c67b6d0eaa0159459`;
- reserved holdout-seed registry: `f830fab12339f17198ba495a38ac25199d5ab120551b6e5735cdb30058c6ec48`.

The screening seeds were `69707, 69912, 68907, 67442, 64654`. The unseen
holdout seeds were prospectively reserved as `76174, 77507, 78307, 77571,
76333`, but were not run because no screening candidate passed. No screening
selection file was created.

The amendment screen contains exactly 90 unique successful scientific attempts:
9 candidates x 2 F0 planning modes x 5 screening seeds. There were no
infrastructure failures or retries. Every attempt is retained append-only in the
qualification raw-data tree, and the machine-readable evidence freeze records the
attempt-manifest, qualification-metric, and raw-inventory hashes.

`F1_attempt_count = 0`, `holdout_attempt_count = 0`, and
`formal_attempt_count = 0`.

## Why the old B-02 geometry failed

For a pure world-z compression of pair 2–3,

\[
d_{23}(t)=\sqrt{d_{xy,23}^2+d_{z,23}(t)^2}\ge d_{xy,23}.
\]

In the original E3-v3 B-02 geometry,
`d_xy,23 = sqrt(2.0^2 + 2.8^2) = 3.440930 m`,
`d_z,23 = 3.0 m`, and `d_23 = 4.565085 m`. Because the pure-z lower bound
`3.440930 m` exceeds `d_hard = 1.5 m`, target-pair hard risk was analytically
impossible regardless of vertical-force magnitude. That original geometry was
geometry-limited.

The later aligned G1/G2 fallbacks had zero horizontal lower bound, so their finite
grid failures were response-limited rather than analytically impossible. This
distinction is preserved in `E3_v4_B02_geometry_failure_diagnosis.md`; the historical
blocked report and original contract were not overwritten.

## Amendment geometry and stimulus

The amendment used the prospectively fixed family

\[
z_{sep}(h)=\sqrt{2.0^2-h^2},\qquad h\in\{1.0,1.1,1.2\}\ \mathrm{m}.
\]

For every geometry, UAV1 was `[0,-4,3]`, UAV4 was `[0,+4,3]`, and each
target was its initial position plus `[8,0,0]` m. The affected-pair coordinates
were:

| Geometry | h (m) | z_sep (m) | UAV2 initial | UAV3 initial |
|---|---:|---:|---|---|
| H1p0 | 1.0 | 1.7320508075688772 | `[0,-0.5,2.1339745962155616]` | `[0,+0.5,3.8660254037844384]` |
| H1p1 | 1.1 | 1.6703293088490065 | `[0,-0.55,2.1648353455754967]` | `[0,+0.55,3.8351646544245033]` |
| H1p2 | 1.2 | 1.6 | `[0,-0.6,2.2]` | `[0,+0.6,3.8]` |

Thus each candidate had `d_xy,23=h<1.5 m` and nominal `d_23=2.0 m`: pure
vertical compression was geometrically capable of entering the hard region while
the nominal three-dimensional plan remained safe.

All stimuli were zero-torque, pure world-z inward forces on UAV2/UAV3 (`+z/-z`),
with 2.0 s onset after the disturbance-arm timestamp and 1.5 s duration. The only
per-UAV magnitudes were 2, 3, and 4 N, giving the exact 3 x 3 grid requested. In
the recorded timing, onset relative to the arm timestamp was exactly 2.0 s and
duration exactly 1.5 s in every attempt. Because the arm command arrived
0.000703–0.994715 s after interaction t0, the force-start timestamp expressed
relative to interaction t0 ranged 2.000703–2.994715 s; these observations are
retained rather than hidden or used to alter the frozen gates.

## Offline nominal-safety gate

Before the first physical pilot, both actual production assignment modes were
audited for all three geometries. Every P0 and P1 result selected identity mapping
`[0,1,2,3]`, had zero predicted hard violations, and had predicted minimum distance
2.0 m (up to floating-point representation). The 8 m / 8 s minimum-jerk move was
within the frozen velocity, acceleration, and jerk limits. Therefore the analytic
template was compatible and did not create a Family-A structural distinction.

The physical evidence reconfirmed this for all 90 attempts: every predicted hard
count was zero and every predicted assignment was identity.

## Complete 9-cell F0 screening evidence

All `J_hard` values below are aggregate pair-seconds over five seeds. The closest
realized pair was 2–3 in all 90 attempts. All 90 missions succeeded, no failsafe
was observed, and no attempt had `d_min <= 0.25 m`.

| Candidate | P0_F0 events/5; actual d_min range (m); J_hard | P1_F0 events/5; actual d_min range (m); J_hard | Classification |
|---|---|---|---|
| B02-V1-H1p0-F2p0 | 0/5; 1.807336–1.847717; 0 | 0/5; 1.818072–1.886022; 0 | `REJECT_FLOOR`, `REJECT_ZERO_EXPOSURE` |
| B02-V1-H1p0-F3p0 | 0/5; 1.744617–1.783225; 0 | 0/5; 1.743209–1.989908; 0 | `REJECT_FLOOR`, `REJECT_ZERO_EXPOSURE` |
| B02-V1-H1p0-F4p0 | 0/5; 1.681024–1.977945; 0 | 0/5; 1.683624–1.724385; 0 | `REJECT_FLOOR`, `REJECT_ZERO_EXPOSURE` |
| B02-V1-H1p1-F2p0 | 0/5; 1.776511–1.958598; 0 | 0/5; 1.820417–1.876964; 0 | `REJECT_FLOOR`, `REJECT_ZERO_EXPOSURE` |
| B02-V1-H1p1-F3p0 | 0/5; 1.770034–1.799620; 0 | 0/5; 1.731681–1.787390; 0 | `REJECT_FLOOR`, `REJECT_ZERO_EXPOSURE` |
| B02-V1-H1p1-F4p0 | 0/5; 1.667356–1.986188; 0 | 0/5; 1.692698–1.731796; 0 | `REJECT_FLOOR`, `REJECT_ZERO_EXPOSURE` |
| B02-V1-H1p2-F2p0 | 0/5; 1.833227–1.985794; 0 | 0/5; 1.815152–1.867635; 0 | `REJECT_FLOOR`, `REJECT_ZERO_EXPOSURE` |
| B02-V1-H1p2-F3p0 | 0/5; 1.776675–1.976687; 0 | 0/5; 1.769234–1.964097; 0 | `REJECT_FLOOR`, `REJECT_ZERO_EXPOSURE` |
| B02-V1-H1p2-F4p0 | 0/5; 1.692719–1.981784; 0 | 0/5; 1.719717–1.976688; 0 | `REJECT_FLOOR`, `REJECT_ZERO_EXPOSURE` |

Gate 1 passed for all candidates. Gate 2 had no qualifying hard-risk event to admit;
nevertheless, all realized minima were correctly localized to the registered pair
2–3, and no non-disturbed-pair collapse occurred. Gates 3 and 4 failed for every
candidate in both planning modes: prevalence was universally 0/5 and exposure was
universally zero. Gate 5 passed as a stability observation but cannot rescue the
failed manipulation.

No candidate passed all gates, so the frozen lexicographic selection rule had no
eligible input and **no B-02 scene was selected**. In particular, the strongest or
smallest-distance candidate was not promoted post hoc. The reserved holdout was not
opened, and the protocol forbids cycling to another candidate or creating a second
amendment without new human authorization.

## Invariance and stopping decision

B-01 was not rerun or retuned. Its frozen evidence and report are byte-identical to
commit `5c078f9a`, with SHA-256 values
`572aca4c85c93387b548f17735f40845d7d0836ed72301eebbc572eb0b4b90ff`
and `789bef47aaa46264d77c9103e76b5c99bbcdea19725fb4b4ae0bfbf8d2db862b`.

All redesign-branch changes relative to parent
`d55ba9e3faddcc258a2b0985f6db821f8efcabfb` are confined to
`experiments_v2/Formal Evaluation Experiments/E3/`. The production policy file is
unchanged and retains SHA-256
`6b47d27f4253d7311e79ea51f6dd1cf0d0182e6df24374a94abae0aa6a135858`.
The sealed E3-v3 registry remains byte-identical with SHA-256
`b56344c6cd257e99851523d640d9a89d6def994884877e2303d8fab836e0faf2`.
No production runtime or method semantics changed.

The amendment's finite grid is exhausted without a qualified vertical residual-risk
assay. Per the prospectively committed stopping rule, Family C qualification and
Family A compatibility validation were not started. No E3-v4 registry, formal seed
population, 360-trial order, or v4 analysis contract was created, and no formal
attempt was executed.

Further external-condition search requires fresh human authorization for a separately
versioned amendment. Nothing in this result is evidence about F1 effectiveness:
feedback was never enabled.
