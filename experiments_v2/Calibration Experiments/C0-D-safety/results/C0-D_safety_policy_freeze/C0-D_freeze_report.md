# C0-D safety calibration — blocked, no freeze issued

## Result

C0-D cannot freeze a safety policy without violating the stated ownership boundary. Stage A derives a required `d_hard=1.50 m`; Stage B's first compatible candidate is `d_plan_base=1.80 m`. Stage C has no feasible candidate in the preregistered `[2.00, 1.75, 1.50, 1.25]` grid because the unchanged C0-E provisional IAPF entry value and hard clamp are `1.50 m`, while the frozen loader requires `d_hard < iapf_enter_min` strictly.

The first two cold-start smokes (8-UAV compact and crossing-prone reconfiguration, both at `s=1`) reached controller launch and were rejected with `safety ordering or IAPF hysteresis is invalid`. Their raw logs are retained in `runtime_raw/compact_s1` and `runtime_raw/crossing_prone_s1`; the `s=s_max` smoke was not run because no loadable C0-D candidate policy exists. Runtime observations were not used to tune any value.

## Stage A

- Gazebo Classic Iris collision radius: `0.3835386468 m`, computed conservatively from collision primitives only (maximum link/collision horizontal offset plus primitive radius), not visual meshes.
- C0-A frozen-policy validation samples: 14,985 active `control_tracking_debug` samples from 36 `C_selected_validation_*` bags; instantaneous position-error P99: `0.2380183022 m`.
- C0-B state timeout: `0.02208 s`; C0-A velocity limit: `5.0 m/s`.
- Requirement: `2*0.3835386468 + 2*0.2380183022 + 2*5.0*0.02208 = 1.4639138979 m`; 0.05-m upward rounding gives **`d_hard=1.50 m`**.

## Stage B

At `d_hard=1.50 m`, `d_plan_base=1.80 m` is the first descending candidate that preserves C0-C compact `s=1` (no geometry safety raise) and passes the bounded deterministic 3/5/8-UAV ordinary, compact, crossing-prone, and dense-feasible allocator scenes. All rows have `N_hard=0`; no allocator/objective/geometry/MJ/LADRC/IAPF code was changed.

## Stage C conflict

For every candidate `s_max`, C0-D planning and canonical geometry conditions pass. The downstream compilation prerequisite fails before the `s` value matters: `d_hard=1.50` is equal to C0-E's unchanged `controller_hard_clamps.iapf_enter_min=1.50`, contrary to the loader invariant `iapf_violation_distance < iapf_enter_min`. Changing the IAPF base, enter clamp, exit clamp, filters, gains, epsilon, or modulation clamps is expressly owned by C0-E and was not performed.

Therefore there is no `frozen_safety_policy.yaml`, no canonical policy update, and no C0-D freeze status. C0-A/B/C numerical values remain unchanged.
