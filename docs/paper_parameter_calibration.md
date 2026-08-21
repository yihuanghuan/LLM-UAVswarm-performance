# Paper Parameter Calibration Manifest

`paper-current-v7` is runnable but is not a paper-final calibrated policy.

| Parameter | Current value | Current provenance | Status | Required calibration | Affects experiments |
|---|---:|---|---|---|---|
| workspace AABB | `[-15,-10,0.5]`–`[15,35,15]` m | current simulation workspace | provisional | Measure usable Gazebo and motion-capture regions | feasibility/rejection rate |
| state timeout/skew/wait | `0.022080/0.022043/0.010000 s` | C0-B state-freshness freeze (P99 + 10 ms) | frozen | C0-B combined runtime freshness measurements | late-resolution availability |
| v/a/j limits | `5/5/10` | current controller velocity/acceleration values; jerk newly architectural | provisional | PX4 limits plus single-UAV trajectory sweep | timing and trajectory metrics |
| d_hard | `1.0 m` | `iapf_violation_distance` | provisional | vehicle geometry + localization/tracking error + reserve | all safety metrics |
| nominal spacing | `2.0 m` | current formation policy baseline | provisional | formation tracking and downwash study | formation scale |
| qualitative multipliers | `0.8/1/1.25` | current Candidate policy | provisional | perception study and safety-floor interaction | language-scale experiments |
| d_plan base | `2.0 m` at s=1 | current planning-margin baseline | provisional | development scenarios independent of final tests | assignment safety |
| IAPF enter/exit | `1.5/1.65 m` at s=1 | controller baseline | provisional | collision-avoidance sweeps | avoidance activation |
| IAPF repulsion scale | `1.0 + 0.25(s-1)` | conservative semantic-safety development mapping | provisional | targeted avoidance sweep without changing IAPF formula | avoidance strength |
| s_max | `2.0` | current policy coverage | provisional | validate feasible workspace and controller clamp coverage | safety-factor experiments |
| allocator comparison tolerance | `1e-6` | Paper policy `comparison_tolerance` | provisional | verify numerical stability on separate calibration scenarios, then lock before test set | floating-point lexicographic comparison only |
| variable-duration numerical sample rate | `20 Hz` | Paper policy `sample_hz` | provisional | validate numerical closest-approach resolution on separate calibration scenarios, then lock before test set | variable-duration ParallelGroup assignment comparison |
| minimum duration / auto style | `0.5 s / 1.30,1.15,1.10` (smooth, normal, aggressive) | 2026-08-14 motion-style development sweep; aggressive raised from 1.00 after saturation at the jerk boundary | provisional | broader displacement/payload sweep | completion-time results |
| style gain | `0.8,1.0,1.1` | 2026-08-14 explicit/auto-T Gazebo development sweep; initial aggressive 1.2 reduced after targeted saturation checks | provisional | broader trajectory and disturbance sweep | semantic controller results |
| task adaptation | `identity`, `task_gain=1.0` | deliberate style-isolation boundary | architecture-frozen, value fixed for current study | only revisit in a separate task-adaptation study | none in this style-only study |
| omega hard clamps | `0.75x–1.25x` baseline | bounded safety envelope around enabled styles | provisional safety boundary | stress invalid/out-of-family profiles | profile rejection/clamping |
| profile apply smoothing | `1.0` | guarded atomic application baseline | provisional | dedicated repeated mid-flight switching study | switching transient |

No parameter in this table may be described as experimentally tuned or paper-final without a new calibrated policy and a changed configuration ID/hash.

The semantic motion-style architecture is frozen: `m` has one deterministic
timing path for auto T and one deterministic controller-profile path. The
development multipliers above remain provisional parameter calibration. The
current evidence and the reason for the conservative aggressive adjustment are
recorded in `experiments/results/semantic_motion_style_v6_20260814/`.

The safety-factor propagation architecture is also frozen: `s` is compiled
once into `d_plan`, IAPF enter/exit distances, and repulsion scale, while
`d_hard` remains fixed. The numeric safety baselines and repulsion margin are
provisional calibration values; see [paper_safety_factor.md](paper_safety_factor.md).

The Paper allocator has no `alpha`/`beta`/`gamma` weighted-sum weights.
`comparison_tolerance` is only the floating-point tolerance used while comparing
the lexicographic score; it does not change that score's mathematical
definition. `sample_hz` only controls the numerical closest-approach evaluation
for variable-duration ParallelGroup motions. Equal-progress motions use the
analytic synchronized 3-D closest approach and are therefore independent of
`sample_hz`.

## Provenance boundary

The current runnable values inherit existing controller/allocator baselines
where an equivalent physical quantity existed. Workspace, freshness,
qualitative scale, jerk, auto timing and semantic adaptation were introduced as
explicitly documented integration baselines. The deleted
`lfs_policy.migration.yaml` was never a runtime dependency of the Paper path;
Git history retains it for historical audit. `lfs_policy.legacy.yaml` now serves
only explicit legacy compatibility, while `lfs_policy.paper_current.yaml` is the
sole default Paper policy.
