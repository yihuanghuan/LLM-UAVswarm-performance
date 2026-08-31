# E3-v4 B-02 amendment-v1 response diagnosis

Status: `BLOCKED_AT_E3_B02_RESPONSE_DIAGNOSIS`

Dataset class: retained F0-only qualification/calibration pilots; not formal data

## Scope and method

This diagnosis is a read-only reanalysis of all 90 immutable amendment-v1 attempts:
three horizontal projections, three registered forces, two planning modes, and five
screening seeds. No pilot was rerun or replaced. No F1 or formal condition was
opened. The amendment-v1 qualification evidence, B-01 evidence, and E3-v3 evidence
remain unchanged.

The machine-readable companion records every attempt/rosbag hash and the complete
per-attempt signal extraction. Positions and velocities come from synchronized
UAV2/UAV3 `/swarm_state`; controller acceleration response comes from
`/control_tracking_debug.ladrc_output`; actual wrench publication comes from the
two Gazebo force topics. Wrench-driver timing is evaluated against `/clock`, because
the driver is explicitly simulation-clocked.

Definitions used here are:

- minimum vertical separation: `min |z3-z2|` over the scored interval;
- vertical compression: pre-onset median `|z3-z2|` minus post-onset minimum
  `|z3-z2|`;
- inward relative vertical velocity: `v2_z-v3_z`, positive when the pair compresses;
- opposing relative LADRC acceleration: `a3_z-a2_z`, positive when the two
  controllers jointly oppose the inward wrench;
- acceleration-limit diagnostic: maximum individual affected-UAV LADRC output norm
  compared with the frozen 5.0 m/s^2 limit.

## Actual force publication audit

The registry requested UAV2 `+[0,0,F]` and UAV3 `-[0,0,F]` for `F=2,3,4 N`,
onset 2.0 simulation seconds after arming, and duration 1.5 simulation seconds.

Only 80/90 attempts contain nonzero wrench messages plus a terminating zero message
on both affected-UAV topics. In all 80 observable cases, the active vectors exactly
match the registered magnitudes, signs, zero-x/y components, and zero torque. These
messages were delivered on the topics wired to the frozen Gazebo force plugins;
their dose-dependent vehicle response provides physical application evidence.

Ten attempts contain zero messages on both wrench topics:

- `B02-V1-H1p0-F3p0 P1_F0 S69707`;
- `B02-V1-H1p0-F4p0 P0_F0 S67442`;
- `B02-V1-H1p1-F2p0 P0_F0 S69912`;
- `B02-V1-H1p1-F4p0 P0_F0 S67442`;
- `B02-V1-H1p2-F2p0 P0_F0 S69707`;
- `B02-V1-H1p2-F3p0 P0_F0 S69912`;
- `B02-V1-H1p2-F3p0 P1_F0 S68907`;
- `B02-V1-H1p2-F4p0 P0_F0 S64654`;
- `B02-V1-H1p2-F4p0 P1_F0 S64654`;
- `B02-V1-H1p2-F4p0 P1_F0 S69707`.

Those ten attempts also exhibit the no-force response pattern: actual d_min
1.947864–1.989908 m, vertical compression only 0.002238–0.048906 m, and much
smaller inward relative velocity/controller response. The evidence therefore does
not support treating zero topic counts as harmless recorder loss.

Across the 160 affected-UAV streams from the remaining 80 attempts, reconstructed
first-active simulation-clock offsets were: 1.0 s for 8 streams, 1.1 s for 2,
2.0 s for 146, and 2.1 s for 4. The published-hold duration was 1.5 s for 158
streams and 1.6 s for 2. Thus most observable streams follow the registered timing,
but the full population does not establish exact, uniform onset/duration semantics.

Direct force-plugin internal state was not separately logged. Accordingly, this
diagnosis distinguishes observed publication plus physical response from an
unsupported claim that every registered attempt received the force.

## Cell-level response

`Pub` is the count of attempts with verified messages on both affected topics.
Compression is reported as mean followed by its five-seed range. All d_min pairs
were 2–3: `90/90` attempts. Ranges include every retained attempt, including the
zero-publication cases; this is why some ranges contain a conspicuous near-2.0 m
endpoint.

| h (m) | F (N) | Condition | Pub | actual d_min (m) | min |dz| (m) | compression mean (range), m | max inward rel. v_z (m/s) |
|---:|---:|---|---:|---:|---:|---:|---:|
| 1.0 | 2 | P0_F0 | 5/5 | 1.807–1.848 | 1.513–1.563 | 0.197 (0.174–0.215) | 0.486–0.691 |
| 1.0 | 2 | P1_F0 | 5/5 | 1.818–1.886 | 1.519–1.595 | 0.182 (0.156–0.209) | 0.450–0.639 |
| 1.0 | 3 | P0_F0 | 5/5 | 1.745–1.783 | 1.430–1.486 | 0.259 (0.240–0.280) | 0.223–0.975 |
| 1.0 | 3 | P1_F0 | 4/5 | 1.743–1.990 | 1.442–1.723 | 0.209 (0.002–0.284) | 0.018–0.885 |
| 1.0 | 4 | P0_F0 | 4/5 | 1.681–1.978 | 1.369–1.717 | 0.286 (0.015–0.368) | 0.046–1.158 |
| 1.0 | 4 | P1_F0 | 5/5 | 1.684–1.724 | 1.364–1.411 | 0.354 (0.337–0.370) | 1.042–1.277 |
| 1.1 | 2 | P0_F0 | 4/5 | 1.777–1.959 | 1.409–1.632 | 0.168 (0.047–0.229) | 0.223–0.689 |
| 1.1 | 2 | P1_F0 | 5/5 | 1.820–1.877 | 1.464–1.527 | 0.177 (0.163–0.193) | 0.497–0.659 |
| 1.1 | 3 | P0_F0 | 5/5 | 1.770–1.800 | 1.390–1.431 | 0.264 (0.250–0.275) | 0.774–0.936 |
| 1.1 | 3 | P1_F0 | 5/5 | 1.732–1.787 | 1.350–1.415 | 0.277 (0.254–0.298) | 0.781–1.022 |
| 1.1 | 4 | P0_F0 | 4/5 | 1.667–1.986 | 1.269–1.657 | 0.298 (0.019–0.408) | 0.067–1.120 |
| 1.1 | 4 | P1_F0 | 5/5 | 1.693–1.732 | 1.284–1.334 | 0.360 (0.335–0.379) | 1.061–1.120 |
| 1.2 | 2 | P0_F0 | 4/5 | 1.833–1.986 | 1.395–1.587 | 0.143 (0.011–0.194) | 0.035–0.555 |
| 1.2 | 2 | P1_F0 | 5/5 | 1.815–1.868 | 1.377–1.435 | 0.183 (0.166–0.206) | 0.531–0.702 |
| 1.2 | 3 | P0_F0 | 4/5 | 1.777–1.977 | 1.314–1.576 | 0.216 (0.011–0.286) | 0.035–0.848 |
| 1.2 | 3 | P1_F0 | 4/5 | 1.769–1.964 | 1.313–1.560 | 0.211 (0.049–0.281) | 0.217–0.840 |
| 1.2 | 4 | P0_F0 | 4/5 | 1.693–1.982 | 1.210–1.585 | 0.286 (0.016–0.381) | 0.031–1.147 |
| 1.2 | 4 | P1_F0 | 3/5 | 1.720–1.977 | 1.236–1.579 | 0.226 (0.021–0.371) | 0.063–1.115 |

## Timing and controller response

The next table gives the maximum opposing relative LADRC acceleration range, the
maximum individual affected-UAV LADRC norm, and d_min timing relative to the
registered onset/end reconstructed from `/clock`. Negative onset-relative times or
large post-end minima occur in the force-unverified/no-response attempts or later
nominal fluctuations; they are retained rather than censored.

| h | F | Condition | opposing rel. LADRC (m/s^2) | max individual norm (m/s^2) | t_min - onset (s) | t_min - end (s) |
|---:|---:|---|---:|---:|---:|---:|
| 1.0 | 2 | P0_F0 | 2.966–4.492 | 2.008–2.751 | 0.500–0.672 | -1.000–-0.828 |
| 1.0 | 2 | P1_F0 | 2.719–3.323 | 2.080–2.344 | 0.560–0.664 | -0.940–-0.836 |
| 1.0 | 3 | P0_F0 | 4.212–6.226 | 2.823–3.508 | -0.476–0.584 | -1.976–-0.916 |
| 1.0 | 3 | P1_F0 | 0.108–4.830 | 1.473–3.471 | -0.839–0.620 | -2.339–-0.880 |
| 1.0 | 4 | P0_F0 | 0.344–6.676 | 1.537–4.336 | -0.216–0.588 | -1.716–-0.912 |
| 1.0 | 4 | P1_F0 | 5.746–7.256 | 3.568–3.994 | 0.616–0.764 | -0.884–-0.736 |
| 1.1 | 2 | P0_F0 | 1.614–4.629 | 1.531–2.740 | -1.758–1.172 | -3.258–-0.328 |
| 1.1 | 2 | P1_F0 | 2.837–4.423 | 2.229–2.674 | 0.544–1.272 | -0.956–-0.228 |
| 1.1 | 3 | P0_F0 | 4.395–5.936 | 2.844–3.613 | 0.540–1.172 | -0.960–-0.328 |
| 1.1 | 3 | P1_F0 | 4.303–5.811 | 2.881–3.800 | 0.512–0.696 | -0.988–-0.804 |
| 1.1 | 4 | P0_F0 | 0.204–7.482 | 1.551–4.328 | 0.536–7.233 | -0.964–5.733 |
| 1.1 | 4 | P1_F0 | 5.674–7.548 | 3.456–4.341 | 0.560–1.220 | -0.940–-0.280 |
| 1.2 | 2 | P0_F0 | 0.218–3.327 | 1.486–2.828 | -0.388–2.372 | -1.888–0.872 |
| 1.2 | 2 | P1_F0 | 2.809–3.709 | 2.096–2.832 | 0.492–0.684 | -1.008–-0.816 |
| 1.2 | 3 | P0_F0 | 0.156–4.718 | 1.509–3.307 | -1.396–0.620 | -2.896–-0.880 |
| 1.2 | 3 | P1_F0 | 1.583–5.922 | 1.807–3.379 | -0.404–6.672 | -1.904–5.172 |
| 1.2 | 4 | P0_F0 | 0.189–7.625 | 1.445–4.196 | 0.516–7.376 | -0.984–5.876 |
| 1.2 | 4 | P1_F0 | 0.315–6.586 | 1.440–4.219 | -1.491–0.612 | -2.991–-0.888 |

All 90 missions succeeded and no failsafe or catastrophic d_min <= 0.25 m was
observed. For the 25 4 N attempts with verified wrench publication, actual d_min
was 1.667356–1.970956 m and maximum individual LADRC norm was
3.328112–4.340770 m/s^2, below the frozen 5.0 m/s^2 limit. The relative opposing
acceleration can exceed 5 because it is the difference of two vehicles' opposing
outputs; it is not an individual-controller saturation measure.

## Dose-response answer

Yes, stronger observed vertical force produces measurably greater pair-2–3
compression. Restricting the descriptive dose check to attempts with matching
wrench messages on both affected topics gives:

| Registered force | Verified n | mean actual d_min (m) | mean vertical compression (m) | mean max inward relative v_z (m/s) |
|---:|---:|---:|---:|---:|
| 2 N | 28 | 1.841771 | 0.185380 | 0.550499 |
| 3 N | 27 | 1.773010 | 0.263558 | 0.761160 |
| 4 N | 25 | 1.728725 | 0.357332 | 1.095227 |

This is a monotone descriptive dose response in all three measures. It supports R2
and shows that amendment-v1 was not simply a dynamically insensitive geometry.
It does not repair the missing/incorrect stimulus evidence required by R1.

## Response-diagnosis gates

- **R1: FAIL.** Only 80/90 attempts have observable registry-matching wrench
  publication; ten show neither wrench messages nor the expected physical response.
  A smaller set also has first-active simulation-clock timing inconsistent with the
  registered 2.0 s onset. The full registered stimulus population is therefore not
  verified.
- **R2: PASS.** The force-verified population shows increasing compression and
  inward relative velocity, with decreasing d_min, from 2 to 4 N.
- **R3: PASS.** The force-verified 4 N regime is mission-stable, failsafe-free,
  non-catastrophic, and below the individual acceleration limit.

The user-provided gate requires all of R1–R3 before amendment-v2. Because R1 fails,
the correct stopping state is:

```text
BLOCKED_AT_E3_B02_RESPONSE_DIAGNOSIS
E3-v4 SCENARIO/PREFLIGHT NOT READY
FORMAL EXECUTION NOT STARTED
```

No amendment-v2 protocol/grid, planning validation, v2 pilot, holdout, Family C
qualification, Family A audit, v4 registry/order, or analysis contract may be
created in this turn. Continuing would require new human direction on the
experiment-only stimulus-delivery/verification issue; production controller or
planner semantics must not be changed.
