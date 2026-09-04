# Large-swarm root-cause audit (diagnostics v2)

## Governance and conclusion

This audit uses only the retained v1 sweep at commit `adf56c7256ccb7f3e63d78ec2ffb254d1f88b647`. The v1 outcomes remain `N20 PASS`, `N24 FAIL`, `N28 FAIL`, and `N32 FAIL`; none is relabeled or overwritten.

The evidence supports a **method-external PX4/MicroXRCE startup entity-creation backlog**, with simultaneous controller discovery/arm activation as a possible amplifier. It does not support classifying the v1 readiness failure as a scientific-method limitation. All tested simulators connected and all PX4/controller processes survived, but later-started XRCE clients stopped before creating their output writers. The failure was therefore persistent resource/timing degradation, not a timeout that can legitimately be cured by waiting longer.

## N=24 first-failure pattern

At the frozen 300 s timeout, 24 PX4 and 24 controller processes remained alive, all 24 status publications were observed, but only 17 vehicles were armed/offboard and only 18 had fresh finite `swarm_state`. UAV 17 had a fresh finite state but did not arm/offboard. UAVs 19–24 had missing/non-finite state at the controller layer. In the lower layer, UAV 19's PX4 odometry/status output writers appeared only at the timeout boundary, while UAVs 20–24 never created those writers. The agent log shows that the corresponding clients did create one participant and 29 readers each, so their XRCE sessions were not absent; entity construction was incomplete.

The 17 armed vehicles were not all stably parked: multiple PX4 logs contain transient failsafe events, and final altitudes ranged from below ground to about 13 m, with two speeds near 2 m/s. This is consistent with timing/estimator degradation after partial startup, not with a successful hover hidden by a strict predicate.

Full per-UAV evidence is in `per_uav_N24_diagnostics.csv`. Compact N28/N32 tables use the same fields.

## Cross-size evidence

| N | complete PX4 output-writer sets | armed/offboard | fresh finite states | max timesync RTT | final residual processes |
|---:|---:|---:|---:|---:|---:|
| 20 | 20 | 20 | 20 | 220 ms | 0 |
| 24 | 18 | 17 | 18 | 568 ms | 0 |
| 28 | 17 | 16 | 17 | 832 ms | 0 |
| 32 | 9 | 8 | 21 | 2420 ms | 0 |

Memory was not exhausted (about 17.6 GiB available at N24). One-minute host load at N24 was 12.3 on 24 logical CPUs. These diagnostics do not prove absence of scheduling pressure, but they rule out OOM and do not show full CPU exhaustion. Reliable low-intrusion Gazebo real-time factor data were unavailable in v1.

## Hypothesis classification

| Hypothesis | Classification | Evidence |
|---|---|---|
| H1 Gazebo/PX4 real-time or estimator degradation | SUPPORTED | Simulator connections formed, while timesync RTT, height-estimate instability, transient PX4 failsafe messages, and displaced final states appeared at failed sizes. |
| H2 MicroXRCE/DDS delivery degradation | SUPPORTED | Later clients had participants/readers but no output writers; the cutoff worsened with N and writer creation could be delayed to 300 s. |
| H3 controller/offboard startup contention | POSSIBLE | N24 launches 24 nodes, 552 neighbor subscriptions, and arm/offboard startup together. The XRCE backlog begins before that launch, so H3 is an amplifier rather than sole cause. |
| H4 parking/ENU mapping error | UNSUPPORTED | Identical audited rule passed N20; ports and offsets match IDs; failure follows startup order rather than grid location. |
| H5 host scheduling/resource saturation | POSSIBLE | Load and timing delays rise, but N24 load is below CPU count, memory remains ample, and RTF was unavailable. |
| H6 other: startup-concurrency backlog | SUPPORTED | v1 started the next PX4 immediately after model spawn instead of waiting for the prior client's writers; entity-completion delay accumulated monotonically by launch order. |

## Prospectively frozen correction

The single profile v2 applies two coordinated orchestration changes under one configuration:

1. after each PX4/model spawn, passively require simulator connection, XRCE synchronization, and its existing odometry/status writers before starting the next PX4;
2. launch unchanged controllers in deterministic batches of four, five seconds apart, while every controller retains the complete N-UAV neighbor list.

The per-instance writer gate is 30 s and is not the swarm readiness timeout. The authoritative readiness timeout remains 300 s; its freshness, finite-state, armed/offboard, altitude, speed, failsafe, and stable-hold criteria are unchanged. Middleware, XRCE topology, physics, estimator parameters, control frequency, LADRC, IAPF, safety, and scientific method are unchanged. A 1 Hz log/process sampler adds no DDS subscriptions.

The profile values and stop-at-first-failure order were frozen before any v2 run.
