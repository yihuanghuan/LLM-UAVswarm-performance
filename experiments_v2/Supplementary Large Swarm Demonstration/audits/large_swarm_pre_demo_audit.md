# Large-swarm pre-demonstration audit

Result: **PASS**.

| N | result | readiness s | PX4 | controllers | armed/offboard | fresh state | cleanup |
|---:|---|---:|---:|---:|---:|---:|---|
| 20 | PASS | 30.932 | 20 | 20 | 20 | 20 | PASS |
| 24 | FAIL | 300.000 | 24 | 24 | 17 | 18 | PASS |
| 28 | FAIL | 300.000 | 28 | 28 | 16 | 17 | PASS |
| 32 | FAIL | 300.001 | 32 | 32 | 8 | 21 | PASS |

Largest successfully tested supplementary configuration: **N=20**.

D1/D2/D3 deterministic feasibility is PASS for N=24, 28, and 32. Nevertheless, none of those three sizes passed infrastructure readiness, so `primary_showcase_N` and `secondary_showcase_N` are null. The protocol is a human-review candidate but is not launch-eligible.

Production method changes = 0; E5-v2 formal changes = 0; E5-v2 analysis changes = 0; scientific showcase missions executed = 0.
