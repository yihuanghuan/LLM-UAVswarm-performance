# Experiment 10 v3 replay pilot gate report

## Decision

The execution-only replay pilot failed the pre-registered continuation gate.
No diagnostic 10-run batch, end-to-end pilot, or 50-run formal batch was started.

The gate was: stop when either Task B or Task E has more than 2
`stabilization_timeout` outcomes among 5 execution-entry trials.

| Task | Execution-entry trials | Successful | Stabilization timeout | Rate | Gate |
|---|---:|---:|---:|---:|---|
| Task B | 5 | 1 | 4 | 80% | Fail |
| Task E | 5 | 0 | 5 | 100% | Fail |

All 10 attempts passed readiness and entered execution. There were no
`dispatch_timeout`, `reference_finish_timeout`, or `stage_data_stale` outcomes.

## Frozen execution inputs

- Execution code commit: `2c8ab5f2`
- Task B LFS SHA256:
  `716f94982160e2a5b10b7861a62919c5f8fd931b8d7f2277de4a3fb5bdff85c9`
- Task E LFS SHA256:
  `3bf0e8a78cefb42d2e665c9a533286ad4a26fe09d0a27498f62bd76e834cc8f2`
- Input mode: execution-only replay; no live LLM request
- Startup mode: gated concurrent

## Observed failure modes

### Task B

Three stage-1 failures contained UAVs that remained near their initial XY
positions and descended instead of following the commanded trajectory, despite
fresh odometry and PX4 reporting armed, offboard, and no failsafe:

- `attempt_0002`: UAV 2, 3, 6, and 7 never entered a stability candidate;
  final position errors were approximately 9.21--12.53 m.
- `attempt_0007`: UAV 2 and 7 never entered a stability candidate; final
  position errors were approximately 12.52 m.
- `attempt_0009`: UAV 2, 3, 6, and 7 never entered a stability candidate;
  final position errors were approximately 9.21--12.54 m.

This is an execution/actuation failure after readiness, not an LLM or stage
timeout accounting failure. `attempt_0004` was different: all UAVs executed
both references, but the final confirmed stability intervals became invalid.

### Task E

All five trials completed stage 1. In stage 2 all command acknowledgements and
reference finishes were observed. Multiple UAVs entered candidate and confirmed
states approximately 1--3 s after reference finish, then exited confirmed when
speed exceeded the 0.40 m/s hysteresis threshold. At timeout:

- position error range: approximately 0.332--0.399 m;
- speed range: approximately 0.339--0.401 m/s;
- IAPF inactive for every UAV;
- nearest-neighbor distance approximately 3.50--3.54 m;
- odometry and status samples were fresh.

The endpoint motion therefore does not satisfy the configured
`speed <= 0.30 m/s` entry criterion for a final valid confirmed interval. It
must not be hidden by latching an earlier confirmation or zero-filling the
missing timing.

## Reproduction command

```bash
source /opt/ros/humble/setup.bash
source /home/yihuang/learning/LLM_swarm_ws/install/setup.bash
/home/yihuang/learning/LLM_swarm_ws/llm_env/bin/python -u \
  experiments/system_8uav/scripts/run_batch.py \
  --batch-id exp10-pilot-v3-replay-20260803 \
  --phase pilot \
  --task task_b_sequential \
  --task task_e_mixed \
  --trials-per-task 5 \
  --input-mode replay \
  --manage-sim
```

## Data locations

- Aggregate outcome: `pilot_batch_outcomes.json`
- Attempt and stage summaries: `summaries/`
- Per-UAV timeout table: `summaries/timeout_diagnostics.csv`
- Timeout classification figure: `figures/stage_timeout_classification.*`
- Per-attempt raw diagnostics: ignored local `pilot/raw/**/stage_failure_diagnostics.json`
- Runtime logs and rosbag2 recordings: ignored local `runtime_logs/` and
  `pilot/raw/**/rosbag2/`
