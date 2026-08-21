# C0-A: Dynamic Feasibility Calibration

C0-A freezes one execution policy for subsequent experiments. It is not a controller comparison, gain optimiser, or paper result.

Stage A validates the fixed LADRC baseline on short/medium/long x, y, z, and diagonal single-UAV moves. Stage B changes exactly one of velocity, acceleration, and jerk at a time. Stage C repeats the full scenario set with the selected limits and only then writes `frozen_execution_policy.yaml`.

Create the Stage A+B plan:

```bash
python3 experiments/calibration/C0_A_motion_limits/run_calibration.py
```

`execution.command_template` is configured for this repository's existing
PX4/Gazebo C0-A path. Plain `--execute` runs only the configured deterministic
smoke case (`baseline`, `short_x`, repetition 1); `--execute-all` is required
before running a campaign. The adapter writes `{trial_dir}/metrics.json` with
`success`, `failure_reason`, `tracking_rmse_m`, `final_position_error_m`,
`max_position_error_m`, `settling_time_s`, `velocity_peak_mps`,
`acceleration_peak_mps2`, `jerk_peak_mps3`, and `saturation_ratio`.

Metric sources are the existing rosbagged `control_tracking_debug`,
`control_adaptation`, and `trajectory_metrics` topics. Acceleration and the
reported measured jerk are finite differences of measured motion and are
diagnostic only. C0-A jerk feasibility is evaluated from the analytic/reference
trajectory jerk in `analytic_reference_peaks.jerk`; the legacy
`COMMAND_JERK_P99_5` finite-difference value is also diagnostic only.
Saturation is the fraction of active samples at the LADRC acceleration limit.

After Stage A+B results exist:

```bash
python3 experiments/calibration/C0_A_motion_limits/analysis/summarize_results.py
python3 experiments/calibration/C0_A_motion_limits/run_calibration.py --validation --execute
python3 experiments/calibration/C0_A_motion_limits/analysis/summarize_results.py --validation
```

Artifacts are written to `experiments/results/C0-A_motion_limits_freeze/`: plan, per-trial metrics, `calibration_results.csv`, report, manifest (git/config hashes), selected policy, and—only after Stage C passes—the frozen policy.

Rosbags and raw runtime logs remain under each local trial's `runtime/raw/`
directory for audit and re-extraction. They are intentionally ignored by Git;
committed trial specifications, normalized metrics, plans, and reports identify
their locations.
