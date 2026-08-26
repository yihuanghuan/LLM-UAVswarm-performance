# Paper parameter freeze ledger

This ledger is the authoritative write-ownership inventory for the
`paper/calibration` line. It was initialized from
`docs/paper_parameter_calibration.md`,
`lfs_policy/config/lfs_policy.paper_current.yaml`, and
`minisnap_LADRC/ladrc_controller/config/ladrc_params.yaml` at algorithm commit
`56e8d2c8e59fc3513769e21910b7a20b2b43088d`.

`PROVISIONAL` means runnable development value, not paper-final evidence. Its
freeze commit and tag remain blank until its owning C0 completes. An
`ARCHITECTURE_FROZEN` item is part of the algorithm contract and has no C0
write owner. A later C0 must not modify a row already marked `FROZEN`.

## Parameter ownership and freeze status

| Parameter / group | Current value | Status | Owner calibration | Freeze commit | Freeze tag | Provenance | Notes |
|---|---|---|---|---|---|---|---|
| LADRC baseline `omega_c` (x/y/z) | `[1.5, 1.5, 1.75] rad/s` | `FROZEN` | C0-A | `a53a3c0bc0dbfbbeffe2a72eaab1bfc0f61dccde` | — | `results/C0-A_motion_limits_freeze/frozen_execution_policy.yaml` (SHA-256 `1ac009c4…5a5d325`) | C0-A Stage C execution-policy freeze; normal style gain remains the architecture-frozen identity. |
| LADRC baseline `omega_o` (x/y/z) | `[5.0, 5.0, 7.5] rad/s` | `FROZEN` | C0-A | `a53a3c0bc0dbfbbeffe2a72eaab1bfc0f61dccde` | — | `results/C0-A_motion_limits_freeze/frozen_execution_policy.yaml` (SHA-256 `1ac009c4…5a5d325`) | C0-A Stage C execution-policy freeze; LESO/LSEF mathematics remain frozen. |
| Motion limits `v/a/j` | `5 m/s`, `5 m/s²`, `10 m/s³` | `FROZEN` | C0-A | `a53a3c0bc0dbfbbeffe2a72eaab1bfc0f61dccde` | — | `results/C0-A_motion_limits_freeze/frozen_execution_policy.yaml` (SHA-256 `1ac009c4…5a5d325`) | C0-A Stage C execution-policy freeze; shared timing/compiler limits. |
| Minimum executable duration | `0.5 s` | `PROVISIONAL` | C0-A | — | — | Paper policy `timing.minimum_duration` | Explicit requests are raised to the frozen feasibility floor. |
| Omega hard-clamp envelope | `omega_c=[1.125,1.125,1.3125]..[1.875,1.875,2.1875]`; `omega_o=[3.75,3.75,5.625]..[6.25,6.25,9.375]` | `PROVISIONAL` | C0-A | — | — | Paper policy `controller_hard_clamps.omega_*` | Current 0.75x–1.25x development envelope; abnormal-profile guard only. |
| Motion hard clamps | `velocity/acceleration/jerk_max=5/5/10` | `PROVISIONAL` | C0-A | — | — | Paper policy `controller_hard_clamps.*_max` | Must cover, and normally equal, selected shared motion limits. |
| Physical controller caps | `max_velocity=5`; `max_acceleration_x/y/z=5/5/8` | `PROVISIONAL` | C0-A | — | — | Controller YAML | Accepted Candidate profiles currently reset LADRC output limits to the scalar profile acceleration limit. |
| Candidate state freshness | timeout/skew/wait `0.022080/0.022043/0.010000 s` | `FROZEN` | C0-B | `ec48c256077698dabc52a6c897c8b6a01fee34d2` | — | C0-B frozen policy and final audit (original result `e7e67bea4a4a07ac5d131376863dc80c1418d1df`) | Candidate state age, inter-UAV skew and planner wait budget only. |
| Controller neighbor freshness | `0.20 s` | `PROVISIONAL` | C0-E | — | — | Controller YAML `neighbor_timeout` | Explicitly excluded from C0-B and not listed as frozen by the authoritative C0-E artifact; no frozen status is inferred. |
| Workspace AABB | lower `[-15,-10,0.5] m`; upper `[15,35,15] m` | `FROZEN` | C0-C | `7b5741267a56a75583f9683268cff2728426b0be` | — | `results/C0-C_geometry_scale_freeze/frozen_geometry_policy.yaml` (SHA-256 `25ab21d7…7819a61fa`) | C0-C Stage A/B accepted; frozen simulation experiment envelope. |
| Nominal formation spacing | `2.25 m` | `FROZEN` | C0-C | `7b5741267a56a75583f9683268cff2728426b0be` | — | `results/C0-C_geometry_scale_freeze/frozen_geometry_policy.yaml` (SHA-256 `25ab21d7…7819a61fa`) | C0-C Stage A/B accepted; geometry equations remain frozen. |
| Qualitative scale multipliers | compact/normal/spacious `0.8/1.0/1.25` | `FROZEN` | C0-C | `7b5741267a56a75583f9683268cff2728426b0be` | — | `results/C0-C_geometry_scale_freeze/frozen_geometry_policy.yaml` (SHA-256 `25ab21d7…7819a61fa`) | C0-C Stage A/B accepted; label semantics/order remain frozen. |
| Allocator comparison tolerance | `1e-6` | `FROZEN` | — | — | `paper-final-sim-v1` | Paper policy `allocator.comparison_tolerance` | Formal-baseline value; numerical convergence is Supporting Method Verification only and may not retune it. |
| Variable-duration closest-approach sample rate | `20 Hz` | `FROZEN` | — | — | `paper-final-sim-v1` | Paper policy `allocator.sample_hz` | Formal-baseline value; equal-progress analytic closest approach is independent of it. Supporting Method Verification may not retune it. |
| `d_hard` / violation distance | `1.50 m` | `FROZEN` | C0-D | `16953f23…` | — | `C0-D_safety_policy_freeze/frozen_safety_policy.yaml` (SHA-256 `901bc588…`) and component manifest | Planning-safety component value; system hard-risk threshold does not scale with `s`. Full-runtime integration completed with C0-E. |
| `d_plan` baseline at `s=1` | `1.80 m` | `FROZEN` | C0-D | `16953f23…` | — | `C0-D_safety_policy_freeze/frozen_safety_policy.yaml` (SHA-256 `901bc588…`) and component manifest | First compatible descending C0-D planning/geometry candidate; formula structure is frozen. |
| Maximum safety preference | `s_max=2.00` | `FROZEN` | C0-D | `16953f23…` | — | `C0-D_safety_policy_freeze/frozen_safety_policy.yaml` (SHA-256 `901bc588…`) and component manifest | Largest C0-D planning/geometry-feasible preregistered candidate. |
| IAPF enter/exit baselines at `s=1` | `1.60/1.70 m` | `FROZEN` | C0-E | `d46dce69f4f3d429243e666c7098c86110d87201` | `paper-final-sim-v1` | `C0-E_iapf_freeze/frozen_iapf_policy.yaml` (SHA-256 `47a491a3…c900e48`) | T1 selected and confirmed; closing-speed gate and hysteresis logic remain architecture-frozen. |
| IAPF repulsion mapping coefficients | base `1.0`; margin `0.25` in `1+0.25(s-1)` | `FROZEN` | C0-E | `d46dce69f4f3d429243e666c7098c86110d87201` | `paper-final-sim-v1` | `C0-E_iapf_freeze/frozen_iapf_policy.yaml` (SHA-256 `47a491a3…c900e48`) | C_M025 selected and confirmed; the mapping structure remains architecture-frozen. |
| IAPF Safety Profile hard clamps | enter min/max `1.60/1.7000000000000002 m`; exit max `1.90 m`; repulsion max `1.25` | `FROZEN` | C0-E | `d46dce69f4f3d429243e666c7098c86110d87201` | `paper-final-sim-v1` | `C0-E_iapf_freeze/frozen_iapf_policy.yaml` (SHA-256 `47a491a3…c900e48`) | Derived monotone coverage bounds over the frozen `s in [1,2]` mapping; not independently swept. |
| IAPF smoothing | filter alpha `0.20` | `FROZEN` | C0-E | `d46dce69f4f3d429243e666c7098c86110d87201` | `paper-final-sim-v1` | `C0-E_iapf_freeze/frozen_iapf_policy.yaml` (SHA-256 `47a491a3…c900e48`) | D_A020 selected and confirmed; first-order filter mathematics remain architecture-frozen. |
| IAPF force and escape numerics | repulsion gain `25.0`; escape mode `id_order`; escape gain `0.05`; distance epsilon `0.10 m` | `FROZEN` | C0-E | `d46dce69f4f3d429243e666c7098c86110d87201` | `paper-final-sim-v1` | C0-E frozen artifact `retained_controller_numerics` | Inherited retained numerics with `changed_by_c0_e: false`; not sweep-selected by C0-E. |
| IAPF position offset gain/clamp | `0.05 / 0.50 m` | `FROZEN` | C0-E | `d46dce69f4f3d429243e666c7098c86110d87201` | `paper-final-sim-v1` | C0-E frozen artifact `retained_controller_numerics` | Inherited retained numerics with `changed_by_c0_e: false`; bounded reference modulation only. |
| IAPF acceleration offset gain/clamp | `0.30 / 2.00 m/s²` | `FROZEN` | C0-E | `d46dce69f4f3d429243e666c7098c86110d87201` | `paper-final-sim-v1` | C0-E frozen artifact `retained_controller_numerics` | Inherited retained numerics with `changed_by_c0_e: false`; bounded reference modulation only. |
| Auto-duration style factors | smooth/normal/aggressive `1.30/1.15/1.10` | `FROZEN` | C0-F | `513b4dd77eb527721ced851ef4d1991a5a6cfd37` | `paper-final-sim-v1` | `C0-F_motion_style_freeze/frozen_motion_style_policy.yaml` (SHA-256 `43f1a9f4…ba4c9a2`) | C0-F locked candidate and confirmation; explicit feasible `T` bypasses these factors. |
| Style-conditioned LADRC gains | smooth/normal/aggressive `0.8/1.0/1.1` | `FROZEN` | C0-F | `513b4dd77eb527721ced851ef4d1991a5a6cfd37` | `paper-final-sim-v1` | `C0-F_motion_style_freeze/frozen_motion_style_policy.yaml` (SHA-256 `43f1a9f4…ba4c9a2`) | C0-F locked candidate and confirmation; normal `1.0` also preserves the architecture-frozen identity. |
| Profile-application smoothing | `smoothing_alpha=1.0` | `FROZEN` | C0-F | `513b4dd77eb527721ced851ef4d1991a5a6cfd37` | `paper-final-sim-v1` | `C0-F_motion_style_freeze/frozen_motion_style_policy.yaml` (SHA-256 `43f1a9f4…ba4c9a2`) | C0-F validated and froze the loader-compatible singleton value with style-switch smokes. |

## Architecture-frozen values and structures

| Parameter / group | Current value | Status | Owner calibration | Freeze commit | Freeze tag | Provenance | Notes |
|---|---|---|---|---|---|---|---|
| Candidate/schema version and LFS semantics | schema v2, `lfs_version=2.1` | `ARCHITECTURE_FROZEN` | — | `56e8d2c8…` | `paper-algorithm-freeze-v1` | Schema, prompt and parser hashes in algorithm manifest | No C0 may change fields or meanings. |
| Validator/resolver/geometry algorithms | current freeze implementation | `ARCHITECTURE_FROZEN` | — | `56e8d2c8…` | `paper-algorithm-freeze-v1` | Algorithm manifest | Numeric C0-C policy inputs do not authorize equation changes. |
| Timing and Minimum-Jerk structure | quintic zero-end-derivative trajectory; max-pairwise planning bound; final recheck tolerance `0` | `ARCHITECTURE_FROZEN` | — | `56e8d2c8…` | `paper-algorithm-freeze-v1` | Timing policy, motion-limit peak equations and C++ trajectory | C0-A changes limits/duration only. |
| Allocator objective/search and aggregation | lexicographic `(N_hard,J_margin,J_distance)`; parallel `d_plan=max` | `ARCHITECTURE_FROZEN` | — | `56e8d2c8…` | `paper-algorithm-freeze-v1` | `safety_aware_allocator.py`, paper policy | Numerical precision controls are sealed by the formal baseline; convergence checks are Supporting Method Verification only. |
| Safety mapping type and lower semantic anchor | `hard_anchored_linear`; `s_min=1.0` | `ARCHITECTURE_FROZEN` | — | `56e8d2c8…` | `paper-algorithm-freeze-v1` | Paper policy and `policy_adapter.py` | `s` meaning and mapping structure cannot be recalibrated. |
| Task adaptation | `identity`; `task_gain=1.0` | `ARCHITECTURE_FROZEN` | — | `56e8d2c8…` | `paper-algorithm-freeze-v1` | Execution Profile Compiler, paper policy, and C0-F frozen artifact | Explicitly excluded from C0-F selection; C0-F preserved and validated the identity contract. |
| Normal style identity | `style_gain(normal)=1.0` | `ARCHITECTURE_FROZEN` | — | `56e8d2c8…` | `paper-algorithm-freeze-v1` | Paper loader invariant | C0-A therefore observes the unscaled baseline. |
| LADRC/LESO/LSEF mathematics | current freeze implementation | `ARCHITECTURE_FROZEN` | — | `56e8d2c8…` | `paper-algorithm-freeze-v1` | LADRC hashes in algorithm manifest | C0-A owns numeric baseline/envelope only. |
| LADRC discretization/input normalization | `control_frequency=50 Hz`; `b0_x/y/z=1.0/1.0/1.0` | `ARCHITECTURE_FROZEN` | — | `56e8d2c8…` | `paper-algorithm-freeze-v1` | Controller YAML and LADRC implementation | Not declared provisional by the calibration manifest; fixed input to C0-A. |
| Completion and takeoff semantics/numerics | hover position enter/exit `0.40/0.50 m`; speed enter/exit `0.30/0.40 m/s`; hold `1.0 s`; filter tau `0.5 s`; startup speed `0.15 m/s`; takeoff `1.5 m`, position `0.25 m`, hold `0.5 s` | `ARCHITECTURE_FROZEN` | — | `56e8d2c8…` | `paper-algorithm-freeze-v1` | Controller YAML, hover and startup state machines | Used as C0-A acceptance inputs, never sweep variables. |
| Startup orchestration numerics | settle `10 s`; odom/status timeout `0.5/2.0 s`; prestream `1.5 s`; retry `1.0 s`; runtime debounce `0.5 s`; total timeout `60 s`; max attempts `20` | `ARCHITECTURE_FROZEN` | — | `56e8d2c8…` | `paper-algorithm-freeze-v1` | Controller YAML and startup state machine | Operational orchestration is outside C0-B; C0-B calibrates Candidate snapshot freshness only. |
| IAPF equations and logic | closing-speed gate, hysteresis, escape direction, bounded dual-channel modulation | `ARCHITECTURE_FROZEN` | — | `56e8d2c8…` | `paper-algorithm-freeze-v1` | IAPF hashes in algorithm manifest | C0-E owns numeric coefficients only. |
| Safety/IAPF operational modes | `avoidance_mode=iapf_dual`; `escape_mode=id_order` for Full Method | `ARCHITECTURE_FROZEN` | — | `56e8d2c8…` | `paper-algorithm-freeze-v1` | Controller config and IAPF mode parser | Formal Full Method may not switch these as tuning. |
| State validity semantics | receive-time fallback `false`; velocity required `true` | `ARCHITECTURE_FROZEN` | — | `56e8d2c8…` | `paper-algorithm-freeze-v1` | Paper policy `state_snapshot` | C0-B owns time thresholds, not validity semantics. |
| PX4 control interface for C0-A / Full Method | explicit `control_mode:=ladrc_acceleration` | `ARCHITECTURE_FROZEN` | — | `56e8d2c8…` | `paper-algorithm-freeze-v1` | Architecture documentation and acceleration setpoint path | Launch default `px4_position` remains a comparison baseline; C0-A must override it explicitly. |

## Ownership audit

The ledger contains no unowned `PROVISIONAL` row and no row with multiple C0
owners. C0-E and C0-F are closed. In particular, profile-application smoothing
is frozen at the loader-compatible singleton `1.0`. Controller neighbor
freshness remains provisional because the authoritative C0-E artifact does not
list it as frozen; this reconciliation does not infer missing provenance.

C0-A through C0-F frozen rows are read-only. Formal evaluation results may not
select, reject, or revise any frozen value. Architecture-frozen values remain
architecture contracts even when a later calibration artifact confirms that
they were preserved.
