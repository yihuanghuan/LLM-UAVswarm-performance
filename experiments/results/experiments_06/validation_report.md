# Experiment 06 validation report

## Result

Validation passed. The analysis includes exactly 45 formal cold-start trials and
210 per-UAV outcomes.

| Check | Expected | Observed | Result |
| --- | ---: | ---: | --- |
| Completed trial directories | 45 | 45 | PASS |
| Scenario × method cells | 9 | 9 | PASS |
| Trials per cell | 5 | 5 | PASS |
| Per-UAV trajectory CSV files | 210 | 210 | PASS |
| Per-UAV VehicleStatus CSV files | 210 | 210 | PASS |
| Rosbag metadata files | 45 | 45 | PASS |
| Rosbag database files | 45 | 45 | PASS |
| UAV summary data rows | 210 | 210 | PASS |
| Trial summary data rows | 45 | 45 | PASS |
| Method summary data rows | 9 | 9 | PASS |

For every formal trial:

- `trial_config.json`, `trial_status.json`, `completed.json`, rosbag metadata and
  a non-empty rosbag database are present;
- the number of trajectory and VehicleStatus CSV files equals the scenario's UAV
  count;
- each VehicleStatus export contains at least one armed (`arming_state=2`),
  OFFBOARD (`nav_state=14`), non-failsafe sample;
- telemetry was complete for every commanded UAV.

## Rejected-attempt audit

`rejected/` contains 30 preserved directories and is excluded from analysis:

- 23 otherwise completed trials generated before the readiness gate was added;
  all were rerun under the final protocol;
- 7 startup-failed or interrupted attempts retained for audit.

These attempts were not deleted, overwritten, or included in any summary or
figure. A failed readiness check is not counted as a formal trial. A formally
started trial with complete telemetry remains in the dataset even when the tested
method does not meet the arrival/settling criterion.

## Analysis checksums

SHA-256:

```text
f24869348678230b601d33c610f5ec58c063972dcfb36a79afce44d8ff8ef0a6  run_config.json
35e4a4473d15fa0f5a1b3897a02d2c2ee5a0d868bfef1f1b274674ab2e215b56  uav_trial_summary.csv
a442b3b7e3a3817f1bf5c0aaab497327fb048c79d073e223a4684ab17c573a16  trial_summary.csv
87a2d8d927cb4492c9cc7f974e89b5f8bef93a35d4e6fb10fba11eb00a856775  method_summary.csv
a4250cece8667fa2dd998b5319c5cc0d36549d00b40c7c5ec7b7aa5ed0acd830  tracking_timeseries.csv
945c4479ab81ca12566fe732ae7aa14fbd256a9d7d0242f9c1129c53d2595497  table_tracking_comparison.md
b57026cb26afabcc213ab2aa5399e9c4969ae485671c05033ca60792645744bc  fig_3d_tracking.pdf
70a496b763754710537c07402b7e878d67543ccce79c579fdced66bdb9185947  fig_tracking_error.pdf
dfe382b8a43fa0762162f59c6f57f4c941ee34defd07e0029e754fc9e45b7a64  fig_velocity_acceleration.pdf
9273270a6ba2c453b0a226dd3386a0fc94a7a3c5e81965fd401d8f5483db6dad  fig_rmse_boxplot.pdf
```
