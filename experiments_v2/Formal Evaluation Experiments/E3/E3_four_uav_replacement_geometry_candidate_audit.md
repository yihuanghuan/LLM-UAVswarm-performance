# E3 four-UAV replacement geometry candidate audit

This is an offline planning/compile audit. No PX4/Gazebo result was used.

Recommended target set: `[-3,4,3]`, `[3,4,3]`, `[-2,12,3]`, `[0,12,3]`.

| Candidate | Disposition | P0 perm | P1 perm | N_hard | J_margin | d_min (m) | J_distance (m) | D_max (m) | P0 ties | P1 global |
|---|---|---|---|---|---|---|---|---|---:|---|
| G1_OFFSET_TRAPEZOID_SELECTED | ACCEPTED_RECOMMENDED | `[2, 3, 0, 1]` | `[0, 1, 2, 3]` | 2→0 | 0.672365532501→0.000000000000 | 0.427482299927→2.000000000000 | 32.330354919151→32.542218118643 | 15.297058540778→9.486832980505 | 1 | True |
| G2_LOWER_OFFSET_TRAPEZOID | ACCEPTED_NOT_SELECTED_LOWER_MARGIN_IMPROVEMENT | `[2, 3, 0, 1]` | `[0, 1, 2, 3]` | 2→0 | 0.559682424465→0.000000000000 | 0.498272879122→2.000000000000 | 28.380068874532→28.686840917729 | 13.341664064126→7.615773105864 | 1 | True |
| G3_TRANSLATED_COMPACT_DIAMOND | ACCEPTED_NOT_SELECTED_THRESHOLD_FRAGILE_P0_CONFLICT | `[3, 1, 2, 0]` | `[2, 0, 3, 1]` | 2→0 | 0.073381208666→0.000000000000 | 1.455213750218→2.828427124746 | 29.770403248129→30.211663907014 | 13.038404810405→10.295630140987 | 1 | True |
| R1_SUPERSEDED_ZERO_MOTION | REJECTED_ZERO_MOTION | `[2, 3, 0, 1]` | `[2, 3, 0, 1]` | 0→0 | 0.000000000000→0.000000000000 | 6.000000000000→6.000000000000 | 0.000000000000→0.000000000000 | 0.000000000000→0.000000000000 | 1 | True |
| R2_TRANSLATED_SQUARE | REJECTED_NO_P0_STRUCTURAL_RISK | `[0, 1, 2, 3]` | `[0, 1, 2, 3]` | 0→0 | 0.000000000000→0.000000000000 | 6.000000000000→6.000000000000 | 32.000000000000→32.000000000000 | 8.000000000000→8.000000000000 | 4 | True |
| R3_SYMMETRIC_TRAPEZOID | REJECTED_P1_NOT_EXHAUSTIVE_GLOBAL_LEXICOGRAPHIC_OPTIMUM | `[2, 3, 0, 1]` | `[0, 2, 3, 1]` | 2→0 | 1.162842491983→0.000000000000 | 0.427482299927→2.018018381989 | 32.066592756746→34.107018441829 | 15.033296378373→15.811388300842 | 1 | False |
| R4_HIGH_TRAPEZOID | REJECTED_MINIMUM_JERK_VELOCITY_INFEASIBLE | `[2, 3, 0, 1]` | `[3, 0, 2, 1]` | 2→0 | 1.254757308679→0.000000000000 | 0.374269716931→3.328201177351 | 44.052595180881→46.501941341186 | 19.026297590440→19.646882704388 | 1 | False |

## Recommended per-UAV assignments

### P0

| UAV | Start | Target label | Target | Displacement | Distance (m) |
|---:|---|---:|---|---|---:|
| 1 | `[-3.0, -3.0, 3.0]` | 3 | `[-2.0, 12.0, 3.0]` | `[1.0, 15.0, 0.0]` | 15.033296378373 |
| 2 | `[3.0, -3.0, 3.0]` | 4 | `[0.0, 12.0, 3.0]` | `[-3.0, 15.0, 0.0]` | 15.297058540778 |
| 3 | `[-3.0, 3.0, 3.0]` | 1 | `[-3.0, 4.0, 3.0]` | `[0.0, 1.0, 0.0]` | 1.000000000000 |
| 4 | `[3.0, 3.0, 3.0]` | 2 | `[3.0, 4.0, 3.0]` | `[0.0, 1.0, 0.0]` | 1.000000000000 |

`N_hard=2`, `J_margin=0.672365532501112`, `J_distance=32.33035491915126`, `d_min=0.42748229992745784`, `v_peak=4.780330793993236`, `a_peak=2.453266907313291`, `j_peak=4.249182927993988`.

### P1

| UAV | Start | Target label | Target | Displacement | Distance (m) |
|---:|---|---:|---|---|---:|
| 1 | `[-3.0, -3.0, 3.0]` | 1 | `[-3.0, 4.0, 3.0]` | `[0.0, 7.0, 0.0]` | 7.000000000000 |
| 2 | `[3.0, -3.0, 3.0]` | 2 | `[3.0, 4.0, 3.0]` | `[0.0, 7.0, 0.0]` | 7.000000000000 |
| 3 | `[-3.0, 3.0, 3.0]` | 3 | `[-2.0, 12.0, 3.0]` | `[1.0, 9.0, 0.0]` | 9.055385138137 |
| 4 | `[3.0, 3.0, 3.0]` | 4 | `[0.0, 12.0, 3.0]` | `[-3.0, 9.0, 0.0]` | 9.486832980505 |

`N_hard=0`, `J_margin=0.0`, `J_distance=32.54221811864255`, `d_min=2.0`, `v_peak=2.9646353064078554`, `a_peak=1.5214515486254616`, `j_peak=2.6352313834736494`.

## Exhaustive assignment evidence

The JSON companion retains all 24 permutations for every shortlisted candidate, including objective values and motion peaks.

Final candidate status: `READY_FOR_HUMAN_REVIEW`; it is not sealed or activated.
