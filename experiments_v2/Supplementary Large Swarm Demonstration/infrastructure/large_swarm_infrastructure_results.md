# Large-swarm infrastructure sweep results

These are non-formal supplementary infrastructure validations. No Candidate, LLM call, formation command, or scientific mission occurred.

| N | Result | readiness (s) | PX4 | controllers | armed/offboard | fresh states | failsafe | RSS MiB | available memory MiB | load (1m) | cleanup |
|---:|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|
| 20 | PASS | 30.932 | 20 | 20 | 20 | 20 | 0 | 1716.0 | 17418.6 | 3.32 | PASS |
| 24 | FAIL | 300.000 | 24 | 24 | 17 | 18 | 0 | 2086.0 | 17169.0 | 12.30 | PASS |
| 28 | FAIL | 300.000 | 28 | 28 | 16 | 17 | 0 | 2505.3 | 16885.9 | 8.68 | PASS |
| 32 | FAIL | 300.001 | 32 | 32 | 8 | 21 | 0 | 2980.9 | 16479.1 | 12.87 | PASS |

Observed result: **largest successfully tested supplementary configuration = N=20**. This does not mean the method supports at most that N; only N=20,24,28,32 were tested.

Gazebo real-time factor is NA for all four conditions because the low-intrusion `gz stats -p` probe returned no parseable sample. Physics was not changed.

The initial N=20 run is retained as a diagnostic-gate tooling failure. It satisfied all frozen readiness/process gates; recovery1 corrected only the extra CLI diagnostic classification and passed.
