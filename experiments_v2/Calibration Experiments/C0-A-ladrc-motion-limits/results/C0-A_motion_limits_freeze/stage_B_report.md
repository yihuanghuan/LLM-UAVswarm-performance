# C0-A Stage B — Bounded Motion-Limit Sweep

Fixed LADRC baseline: `omega_c=[1.5,1.5,1.75]`, `omega_o=[5,5,7.5]`. Each candidate ran the long-diagonal all-axis stress case three times. This is feasibility calibration, not controller optimisation.

## Results

| Phase | Candidate | Success | RMSE mean/max (m) | Final error max (m) | Settling max (s) | Peak velocity mean (m/s) | Peak acceleration mean (m/s²) | Analytic jerk (m/s³) | Saturation max | Result |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|
| B1 | velocity=3 | 3/3 | 0.0894/0.0932 | 0.0108 | 5.8394 | 2.5128 | 2.7125 | 3.4953 | 0.0000 | ACCEPT |
| B1 | velocity=5 | 3/3 | 0.1195/0.1218 | 0.0214 | 5.3593 | 3.0161 | 3.4335 | 5.1200 | 0.0000 | ACCEPT |
| B1 | velocity=7 | 3/3 | 0.1203/0.1220 | 0.0197 | 5.3594 | 2.9551 | 3.1788 | 5.1200 | 0.0000 | ACCEPT |
| B2 | acceleration=3 | 3/3 | 0.1145/0.1179 | 0.0111 | 5.4595 | 2.9109 | 3.2270 | 4.6975 | 0.0000 | ACCEPT |
| B2 | acceleration=5 | 3/3 | 0.1145/0.1181 | 0.0251 | 5.3594 | 2.9535 | 3.2425 | 5.1200 | 0.0000 | ACCEPT |
| B2 | acceleration=7 | 3/3 | 0.1167/0.1250 | 0.0230 | 5.3393 | 2.9778 | 3.2964 | 5.1200 | 0.0000 | ACCEPT |
| B3 | jerk=5 | 3/3 | 0.0760/0.0789 | 0.0081 | 6.2794 | 2.1903 | 2.1167 | 2.5600 | 0.0000 | ACCEPT |
| B3 | jerk=10 | 3/3 | 0.1209/0.1230 | 0.0105 | 5.3595 | 2.9956 | 3.3316 | 5.1200 | 0.0000 | ACCEPT |
| B3 | jerk=15 | 3/3 | 0.1721/0.1750 | 0.0267 | 4.8595 | 3.5732 | 4.7252 | 7.6800 | 0.0000 | ACCEPT |

## Selection

- B1 selected velocity: **5 m/s**. Values 3 and 7 m/s were stable, but 3 is lower capacity and 7 is the aggressive sweep boundary.
- B2 selected acceleration: **5 m/s²**. Values 3 and 7 m/s² were stable, but 7 is the aggressive boundary.
- B3 selected jerk: **10 m/s³**. Values 5 and 15 m/s³ were stable, but 15 is the aggressive boundary.

Recommended provisional Stage C candidate: **velocity=5 m/s, acceleration=5 m/s², jerk=10 m/s³**.

## Rejected alternatives

- None failed acceptance; lower values were not selected because they provide less operating margin, and 7/7/15 were not selected because they are the aggressive boundaries.

## Remaining validation

Run Stage C confirmation of the selected 5/5/10 policy across the complete Stage A scenario set and three repetitions before any freeze artifact is created.
