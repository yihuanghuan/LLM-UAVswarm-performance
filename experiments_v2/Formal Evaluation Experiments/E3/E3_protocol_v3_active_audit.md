# E3 protocol v3 active compile-only audit

Status: **PASS**

No PX4/Gazebo process or live demo was launched.

## Reviewed four-UAV geometry

| Mode | Permutation | N_hard | J_margin | J_distance | d_min (m) | D_max (m) | v/a/j peaks |
|---|---|---:|---:|---:|---:|---:|---|
| P0 | `[2, 3, 0, 1]` | 2 | 0.672365532501 | 32.330354919151 | 0.427482299927 | 15.297058540778 | 4.780330793993 / 2.453266907313 / 4.249182927994 |
| P1 | `[0, 1, 2, 3]` | 0 | 0.000000000000 | 32.542218118643 | 2.000000000000 | 9.486832980505 | 2.964635306408 / 1.521451548625 / 2.635231383474 |

## E3-wide validation

- Scenario-condition consistency: 24/24 PASS.
- Production compile: 360/360 PASS.
- Demo compile-only classes: 8/8 PASS.
- Population: 6 scenarios × 4 conditions × 15 seeds = 360 trials; global order remains 610 entries.

Canonical audit SHA-256: `bc3ff7a75ee4dcf55c49e2043e33529b216c108c993880eaf65206951cefb4e6`
