# E5-v2 engineering scale smoke audit

Result: `E5_V2_ENGINEERING_SCALE_SMOKE = PASS`.

These are infrastructure-only spawn/arm/offboard/stable-hover checks. They contain no registered Candidate mission, no scientific command, no formal trial ID/journal, and `accepted_formal_result=false`.
The JSON companion records the exact successful runner and readiness-gate source hashes; both retained failed revisions remain separately hashed below.

| N | ready | readiness s | PX4 | controllers | gzserver | finite | cleanup | RTF |
|---:|---|---:|---:|---:|---:|---|---|---|
| 8 | True | 24.105 | 8 | 8 | 1 | True | True | NA |
| 12 | True | 31.816 | 12 | 12 | 1 | True | True | NA |
| 16 | True | 32.537 | 16 | 16 | 1 | True | True | NA |

Observed stable infrastructure bound: N=16.

No physics fidelity, scientific policy, safety value, controller value, or timeout was changed between N conditions. Failures, if any, remain retained in the raw engineering evidence and are not formal outcomes.

## Retained engineering harness failure

- N=8: `RuntimeError: continuous readiness gate failed`. Classification: `engineering_readiness_harness_metric_bug`. The initial experiment-only gate incorrectly required finite pre-mission position_error. Production intentionally publishes +Inf before a command; all UAVs were armed, offboard, system_ready, finite in altitude/speed, and the exact process counts were present. The corrected gate uses finite standardized swarm_state position/velocity.
- N=8: `RuntimeError: continuous readiness gate failed`. Classification: `engineering_readiness_harness_qos_bug`. The experiment-only finite-state subscription initially used reliable QoS while the frozen production swarm_state publisher uses SensorData/Best-Effort QoS. ROS reported the reliability incompatibility; all UAV status streams and exact process counts were otherwise ready. The subscription was corrected to SensorData QoS.
