# E3 A-01/C-01 read-only scientific scenario audit

## Outcome

This is **Case S1: genuine frozen scenario inconsistency**, not an audit/tooling error.

Both A-01 and C-01 are `INVALID_FOR_INTENDED_FAMILY`. Under the actual production allocator, P0 and P1 assign every UAV to the target already at its current position. Consequently, all four nominal Minimum-Jerk trajectories are constant, no geometric crossing exists, and the intended structural-risk mechanism is absent.

Final diagnosis: `GENUINE_E3_SCENARIO_PROTOCOL_INCONSISTENCY`.

No protocol, registry, geometry, target ownership, allocator, P0/P1 semantics, demo, or campaign artifact was modified. No live runtime was launched.

## Frozen assignment contract

- P0: `distance_hungarian`.
- P1: `safety_aware`, allocator `lexicographic-safety-aware-v2`.
- `target_labels_define_input_order_not_uav_ownership: true`.
- `fixed_target_ownership_for_P0: false`.
- Therefore target keys 1–4 are input-order labels. They do not bind UAV 1 to target 1, and so on.

Production numeric environment:

- Python executable: `/usr/bin/python3`
- Python: `3.10.12`
- NumPy: `1.24.4`
- SciPy: `1.8.0`
- Hungarian call: `scipy.optimize.linear_sum_assignment` over the Euclidean start-to-target cost matrix.

## E3-A-01

Intended family: `A_predictable_structural_risk`  
Intended label: `four-UAV crossing target set`  
Duration: `6.0 s`

### Frozen geometry

| UAV / target label | Initial position (m) | Ordered target input (m) |
|---:|---|---|
| 1 | `[-3,-3,3]` | `[-3,3,3]` |
| 2 | `[3,-3,3]` | `[3,3,3]` |
| 3 | `[-3,3,3]` | `[-3,-3,3]` |
| 4 | `[3,3,3]` | `[3,-3,3]` |

The target set is exactly the initial-position set in a different input order.

### Production P0 assignment

Permutation convention: each entry is the zero-based target input index assigned to UAVs 1–4.

`[2, 3, 0, 1]`, corresponding to target labels `[3, 4, 1, 2]`.

| UAV | Initial (m) | Target index / label | Assigned target (m) | Displacement vector (m) | Magnitude (m) |
|---:|---|---|---|---|---:|
| 1 | `[-3,-3,3]` | `2 / 3` | `[-3,-3,3]` | `[0,0,0]` | 0 |
| 2 | `[3,-3,3]` | `3 / 4` | `[3,-3,3]` | `[0,0,0]` | 0 |
| 3 | `[-3,3,3]` | `0 / 1` | `[-3,3,3]` | `[0,0,0]` | 0 |
| 4 | `[3,3,3]` | `1 / 2` | `[3,3,3]` | `[0,0,0]` | 0 |

- Total assignment distance: `0.0 m`
- Maximum displacement: `0.0 m`
- All UAVs stationary: yes
- Number of globally optimal assignments: 1
- Equal-cost optimum tie: no

### Production P1 assignment

Hungarian initial permutation and final safety-aware permutation are both `[2,3,0,1]`. Refinement performs zero iterations. Per-UAV displacements are identical to P0.

| Metric | Value |
|---|---:|
| `N_hard` | 0 |
| `J_margin` | 0.0 |
| `J_distance` | 0.0 m |
| Predicted minimum 3-D distance | 6.0 m |
| XY segment crossings | 0 |
| `d_hard` | 1.5 m |
| `d_plan` | 1.8 m |
| Planning margin met | yes |
| Residual planning risk | no |

### Nominal trajectory result

Production uses

`p_i(t) = start_i + (target_i-start_i)(10τ³−15τ⁴+6τ⁵)`.

For every UAV, `target_i-start_i = [0,0,0]`; hence `p_i(t)=start_i` for the full interaction.

- Any UAV moves: no
- Nominal path crossings: 0
- Predicted minimum pairwise distance: 6.0 m
- Predicted hard-violation pairs: 0
- Planning margin cost: 0
- Nominal structural conflict: absent

Classification: `INVALID_FOR_INTENDED_FAMILY`.

## E3-C-01

Intended family: `C_mixed_risk`  
Intended label: `four-UAV crossing plus lateral wrench`  
Duration: `6.0 s`

C-01 has the same initial geometry, ordered target input, P0 assignment, P1 assignment, per-UAV zero displacements, and nominal trajectory diagnostics as A-01.

Its registered disturbance remains:

- UAV 1: `[0,2,0] N`
- UAV 3: `[0,-2,0] N`
- Onset: `2.0 s`
- Duration: `1.5 s`

The disturbance component exists, but the nominal structural component does not. Therefore the scenario is not mixed structural-plus-disturbance risk under actual production assignment.

Classification: `INVALID_FOR_INTENDED_FAMILY`.

## Why this is not a tooling error

The audit assignment was independently reconstructed through both:

1. the frozen allocator's `allocate_mode_with_metrics`; and
2. the production `build_runtime_spec` path used before physical execution.

The assigned target arrays match exactly. The zero-distance P0 solution is also the unique global minimum among all `4!` assignments. P1 begins from that solution and has no lexicographic reason to replace a plan with `N_hard=0`, `J_margin=0`, and `J_distance=0`.

## Other scenario family-consistency check

| Scenario | P0 nominal result | P1 nominal result | Disturbance | Classification |
|---|---|---|---|---|
| A-02 | `N_hard=2`, `d_min=0`, `J_margin=2.002244726`; structural conflict present | `N_hard=0`, `d_min=2.248386605`, `J_margin=0`; assignment changes | none | `VALID` predictable structural risk |
| B-01 | Parallel safe motion, `d_min=2.0`, no hard/margin event | Same safe nominal plan | lateral wrench on UAVs 2/3 | `VALID` residual execution risk |
| B-02 | Separated safe motion, `d_min=2.0`, no hard/margin event | Same safe nominal plan | vertical wrench on UAVs 2/3 | `VALID` residual execution risk |
| C-02 | Same structural P0 conflict as A-02 | Safety-aware assignment removes predicted hard conflict | lateral wrench on UAVs 4/8 | `VALID` mixed risk |

The A-01/C-01 family mismatch is isolated geometrically. A separate numeric reproducibility issue remains for A-02/C-02.

## Numeric-environment and tie audit

For A-01/C-01:

- Production SciPy 1.8.0 permutation: `[2,3,0,1]`
- SciPy 1.15.3 permutation: `[2,3,0,1]`
- Optimal assignment count: 1
- Tie exists: no
- Structural interpretation changes: no

Thus the A-01/C-01 failure is independent of SciPy tie behavior.

For A-02/C-02, brute-force enumeration finds eight equal-total-distance Hungarian optima. This is a separate protocol reproducibility issue:

| Environment | P0 permutation | Total distance | D_max | `N_hard` | `J_margin` |
|---|---|---:|---:|---:|---:|
| Production SciPy 1.8.0 | `[7,0,5,2,3,4,1,6]` | 112.0 | 22.485281374 | 2 | 2.002244726 |
| SciPy 1.15.3 | `[7,0,1,2,3,4,5,6]` | 112.0 | 26.0 | 3 | 3.002244726 |

Both retain A-02/C-02's structural-risk family interpretation, but scientific numeric outputs change. No tie-breaking modification was made.

## Campaign and evidence protection

Before and after the audit:

- Campaign journal remains exactly `000001` and `000002`.
- Accepted formal attempt count remains 2.
- No `000003` exists.
- Formal cursor is unchanged.
- Formal file-map hash remains `29a6539e4b6b4372e0adc98bc5b45b4a8a40c20c3f23f244460e45695d14ba37`.
- Launcher manifest hash remains `dd5ed80049b138d4e97c82ce556ed306efbc6e4b2a369f7616be0ff101f332d1`.
- Launcher commit remains `8c532288c8b5c47a20da954caad4f717cdc92ddb`.
- Protocol v1/v2, registry v1/v2, duration audit, demos, and global order retain their prior hashes.

## Stop decision

`GENUINE_E3_SCENARIO_PROTOCOL_INCONSISTENCY`

No replacement geometry or protocol v3 is proposed or implemented. Human scientific review is required before any further demo execution.
