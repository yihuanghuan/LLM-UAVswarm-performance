# Paper Parameter Calibration Manifest

`paper-current-v2` is runnable but is not a paper-final calibrated policy.

| Parameter | Current value | Current provenance | Status | Required calibration | Affects experiments |
|---|---:|---|---|---|---|
| workspace AABB | `[-15,-10,0.5]`–`[15,35,15]` m | current simulation workspace | provisional | Measure usable Gazebo and motion-capture regions | feasibility/rejection rate |
| state timeout/skew/wait | `0.5/0.15/2.0 s` | Candidate integration baseline | provisional | Measure message age and inter-UAV skew distributions | late-resolution availability |
| v/a/j limits | `5/5/10` | current controller velocity/acceleration values; jerk newly architectural | provisional | PX4 limits plus single-UAV trajectory sweep | timing and trajectory metrics |
| d_hard | `1.0 m` | `iapf_violation_distance` | provisional | vehicle geometry + localization/tracking error + reserve | all safety metrics |
| nominal spacing | `2.0 m` | current formation policy baseline | provisional | formation tracking and downwash study | formation scale |
| qualitative multipliers | `0.8/1/1.25` | current Candidate policy | provisional | perception study and safety-floor interaction | language-scale experiments |
| d_plan base | `2.0 m` at s=1 | current planning-margin baseline | provisional | development scenarios independent of final tests | assignment safety |
| IAPF enter/exit | `1.5/1.65 m` at s=1 | controller baseline | provisional | collision-avoidance sweeps | avoidance activation |
| s_max | `2.0` | current policy coverage | provisional | validate feasible workspace and controller clamp coverage | safety-factor experiments |
| allocator weights/rate | `1,10,10,1; 20 Hz` | allocator constructor defaults | provisional | tune on separate calibration scenarios, then lock before test set | assignment comparison |
| minimum duration / auto style | `0.5 s / all 1` | Candidate timing baseline | provisional | PX4 trajectory sweep | completion-time results |
| style/task/omega adaptation | identity | neutral baseline | baseline-frozen, revisitable | dedicated semantic LADRC redesign | future third contribution |
| smoothing under semantic switching | `1.0` | user-confirmed neutral baseline | baseline-frozen, revisitable | switching-transient experiments | future semantic controller |

No parameter in this table may be described as experimentally tuned or paper-final without a new calibrated policy and a changed configuration ID/hash.

## Provenance boundary

The current runnable values inherit existing controller/allocator baselines
where an equivalent physical quantity existed. Workspace, freshness,
qualitative scale, jerk, auto timing and semantic adaptation were introduced as
explicitly documented integration baselines. The deleted
`lfs_policy.migration.yaml` was never a runtime dependency of the Paper path;
Git history retains it for historical audit. `lfs_policy.legacy.yaml` now serves
only explicit legacy compatibility, while `lfs_policy.paper_current.yaml` is the
sole default Paper policy.
