# Paper Parameter Calibration Manifest

This document records the calibration inventory as it evolved. The current
authoritative runnable Paper policy is `paper-current-v11-c0-f-frozen`; its
canonical values and final C0-A through C0-F status are recorded in
`lfs_policy/config/lfs_policy.paper_current.yaml` and the formal-baseline
provenance manifest.

| Parameter | Current value | Current provenance | Status | Required calibration | Affects experiments |
|---|---:|---|---|---|---|
| LADRC baseline `omega_c` | `[1.5,1.5,1.75] rad/s` | C0-A frozen execution policy | frozen | C0-A Stage C validated execution-policy freeze | tracking and execution |
| LADRC baseline `omega_o` | `[5.0,5.0,7.5] rad/s` | C0-A frozen execution policy | frozen | C0-A Stage C validated execution-policy freeze | tracking and execution |
| workspace AABB | `[-15,-10,0.5]`–`[15,35,15]` m | C0-C accepted geometry/scale freeze | frozen | C0-C Stage A/B accepted | feasibility/rejection rate |
| state timeout/skew/wait | `0.022080/0.022043/0.010000 s` | C0-B state-freshness freeze (P99 + 10 ms) | frozen | C0-B combined runtime freshness measurements | late-resolution availability |
| v/a/j limits | `5/5/10` | C0-A frozen execution policy | frozen | C0-A Stage C validated execution-policy freeze | timing and trajectory metrics |
| d_hard | `1.50 m` | C0-D frozen planning-safety component, integrated by C0-E | frozen | collision geometry + C0-A P99 tracking error + C0-B timeout travel | all safety metrics |
| nominal spacing | `2.25 m` | C0-C accepted geometry/scale freeze | frozen | C0-C Stage A/B accepted | formation scale |
| qualitative multipliers | `0.8/1/1.25` | C0-C accepted geometry/scale freeze | frozen | C0-C Stage A/B accepted | language-scale experiments |
| d_plan base | `1.80 m` at s=1 | C0-D frozen planning-safety component, integrated by C0-E | frozen | first descending C0-D planning/geometry-compatible candidate | assignment safety |
| IAPF enter/exit | `1.60/1.70 m` at s=1 | C0-E frozen IAPF policy | frozen | C0-E T1 selected and confirmed | avoidance activation |
| IAPF repulsion scale | `1.0 + 0.25(s-1)` | C0-E frozen IAPF policy | frozen | C0-E C_M025 selected and confirmed | avoidance strength |
| IAPF runtime filter | `alpha=0.20` | C0-E frozen IAPF policy | frozen | C0-E D_A020 selected and confirmed | avoidance modulation |
| safety preference domain | `s_min=1.0`, `s_max=2.0` | C0-D frozen safety envelope, integrated by C0-E | frozen | C0-D selection and C0-E coverage validation | safety-factor experiments |
| allocator comparison tolerance | `1e-6` | Paper policy `comparison_tolerance` | sealed baseline | Supporting Method Verification only; no parameter selection or retuning | floating-point lexicographic comparison only |
| variable-duration numerical sample rate | `20 Hz` | Paper policy `sample_hz` | sealed baseline | Supporting Method Verification only; no parameter selection or retuning | variable-duration ParallelGroup assignment comparison |
| minimum executable duration | `0.5 s` | inherited Paper policy floor; sealed by formal baseline | `RETAINED_BASELINE` | not calibration-selected; immutable during E1-E5 | timing feasibility |
| auto-duration style factors | `1.30/1.15/1.10` (smooth, normal, aggressive) | C0-F frozen motion-style policy | frozen | C0-F locked candidate and confirmation | completion-time results |
| style gain | `0.8/1.0/1.1` (smooth, normal, aggressive) | C0-F frozen motion-style policy | frozen | C0-F locked candidate and confirmation | semantic controller results |
| task adaptation | `identity`, `task_gain=1.0` | architecture-frozen style-isolation boundary, preserved by C0-F | architecture-frozen | not a C0-F calibration selector | none in this style-only study |
| omega hard clamps | `0.75x–1.25x` baseline | inherited abnormal-profile safety envelope; sealed by formal baseline | `RETAINED_BASELINE` | not calibration-selected; immutable during E1-E5 | profile rejection/clamping |
| profile apply smoothing | `1.0` | C0-F frozen motion-style policy | frozen | C0-F style-switch smoke validation | guarded atomic application |

`RETAINED_BASELINE` rows were not calibration-selected and must not be
described as experimentally tuned. They are nevertheless immutable during
E1-E5. C0-D was integrated with the C0-E freeze, and the canonical full-runtime
configuration is `paper-current-v11-c0-f-frozen`.

The C0-A frozen policy also fixes its campaign inputs `b0=[1,1,1]`, control
frequency `50 Hz`, and `control_mode=ladrc_acceleration`; these are immutable
execution inputs rather than further calibration selectors. C0-C geometry and
qualitative-scale values and the C0-D planning-safety component are frozen.
C0-E IAPF and C0-F motion-style parameters were subsequently frozen in the
canonical `paper-current-v11-c0-f-frozen` policy. Allocator numerical
convergence is Supporting Method Verification rather than a calibration stage.

The semantic motion-style architecture is frozen: `m` has one deterministic
timing path for auto T and one deterministic controller-profile path. The
style factors, style gains, and profile-application smoothing above are frozen
by the C0-F artifact at
`experiments_v2/Calibration Experiments/C0-F-motion-style/results/C0-F_motion_style_freeze/frozen_motion_style_policy.yaml`.

The safety-factor propagation architecture is also frozen: `s` is compiled
once into `d_plan`, IAPF enter/exit distances, and repulsion scale, while
`d_hard` remains fixed. C0-D froze the planning-safety envelope and C0-E froze
the IAPF mapping and filter; see
[paper_safety_factor.md](paper_safety_factor.md).

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
