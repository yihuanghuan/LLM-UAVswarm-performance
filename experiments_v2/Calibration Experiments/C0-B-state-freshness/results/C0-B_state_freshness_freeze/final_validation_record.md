# C0-B final validation record

## Frozen policy under test

- State timeout: 22.080 ms
- Snapshot skew threshold: 22.043 ms
- Planner freshness wait timeout: 10.000 ms
- Selection rule: P99 plus fixed 10 ms margin

## Snapshot and deadline regression

Executed from the repository root with ROS Humble sourced:

```text
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 PYTHONPATH=lfs_policy:location_allocate \
  /home/yihuang/learning/LLM_swarm_ws/llm_env/bin/python -m pytest -q \
  lfs_policy/test/test_policy_loader.py \
  location_allocate/test/test_policy_adapter.py \
  location_allocate/test/test_paper_runtime_fresh_snapshot.py \
  location_allocate/test/test_production_state_snapshot.py
```

Result: `32 passed`.

- Normal fresh-state acceptance is covered by the immediately available fresh
  snapshot regression and the production snapshot tests.
- Stale-state rejection is covered by the production snapshot tests and by the
  deadline regression whose unavailable/stale snapshot raises `RuntimeError`
  without scheduling command resolution.
- The transient regression confirms a snapshot received before the configured
  deadline is accepted, while each `spin_once` is bounded by remaining time.

## Real Candidate smoke test

A cold-start real PX4/Gazebo 4-UAV Candidate trial was run through the existing
`experiments-legacy/system_motion_style/run_cold_start_trial.py` wrapper with
the frozen C0-B canonical policy passed explicitly to both controllers and the
scheduler.  The wrapper output is retained locally under the gitignored
`results/runtime_campaign_final_smoke/normal_trial_2/` directory.

Evidence from `manifest.json`:

- `uav_ids`: `[1, 2, 3, 4]`
- `readiness`: `true`
- `scheduler_returncode`: `0`
- `candidate_completed`: `true`
- `lfs_policy_file`: `lfs_policy/config/lfs_policy.paper_current.yaml`

Evidence from `scheduler.log`:

```text
Paper Candidate runtime enabled with policy paper-current-v8-c0-b-frozen
Candidate mission 1 completed
```

This smoke test did not enlarge or tune the C0-B wait timeout.
