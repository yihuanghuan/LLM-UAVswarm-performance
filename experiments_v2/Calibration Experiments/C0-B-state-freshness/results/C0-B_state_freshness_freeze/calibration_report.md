# C0-B state freshness calibration report

This freeze uses a single pre-declared P99-plus-margin rule; no task-performance metric or threshold search was used.

## Frozen policy

```yaml
state_freshness:
  state_timeout_ms: 22.08
  snapshot_skew_threshold_ms: 22.043
  planner_wait_timeout_ms: 10.0
selection_rule:
  percentile: P99
  safety_margin_ms: 10.0
  method: linear percentile plus fixed safety margin
source_dataset:
  file: freshness_measurements.csv
  rows: 16064
  scenarios:
  - hover
  - straight_motion
  - waypoint_transition
  - multi_uav_4
  - multi_uav_8
freeze_status: frozen
```
## Validation

- Normal operation: pass — fresh states accepted.
- Stale-state rejection: pass — a controlled stale timestamp raised `SnapshotError` before a snapshot could reach command resolution.
