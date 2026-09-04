# Large-swarm infrastructure profile v2 results

Profile SHA-256: `155817c38e9cfc456cc1988cff3a0a98f07559ee222cf90725787b471a383907`

This is supplementary infrastructure diagnostic evidence only (`accepted_formal_result=false`). No LLM, Candidate, formation command, or D1/D2/D3 mission was executed.

## Conditional sweep accounting

| N | result | lower-layer PX4/XRCE gate | frozen readiness | disposition |
|---:|---|---|---|---|
| 24 | FAIL | PASS: 24/24 | FAIL: 18/24 arm/offboard; 24/24 fresh finite states | retained; stop upward sweep |
| 28 | NOT RUN | — | — | prohibited after N24 failure |
| 32 | NOT RUN | — | — | prohibited after N24 failure |

For N24, every per-instance writer gate completed in 6.0–6.4 s, all 24 PX4 and all 24 controllers remained alive, and final state delivery was fresh and finite for 24/24. The unchanged readiness gate nevertheless reached 300.000 s without a stable all-UAV hold. It found 18/24 armed/offboard, zero final-snapshot failsafe flags, and highly displaced altitudes on multiple vehicles. Cleanup succeeded with zero scoped residual processes.

Host diagnostics at the terminal snapshot: 24 logical CPUs, load average 12.18/8.47/4.16, 17,517,104 KiB available memory, and 2,144,496 KiB aggregate scoped-process RSS. Gazebo RTF remains NA because no reliable low-intrusion parseable source was available.

## Interpretation boundary

The v2 profile demonstrates that deterministic PX4 startup gating removes the v1 XRCE output-writer truncation. It does not validate N24 stable hover. The remaining failure is consistent with the exact frozen neighbor coordinate expression `y = msg.position[0] + 3.0 * neighbor_id`, which is incompatible with the supplementary 2-D grid. Fixing that expression would change production method semantics and was therefore not attempted.

No stable N was established under profile v2 because N20 was not retested and N24 failed. The historical v1 largest successfully tested configuration remains N20. `primary_showcase_N_v2` is null.
