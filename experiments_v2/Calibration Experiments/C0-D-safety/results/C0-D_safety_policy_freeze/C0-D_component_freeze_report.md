# C0-D planning-safety component freeze

## Frozen component policy

`d_hard=1.50 m`, `d_plan_base=1.80 m`, `s_min=1.0`, and `s_max=2.00` are frozen under `hard_anchored_linear` mapping.

The collision-only 3-D verification corrects the Iris center-to-collision-extent bound from the previous horizontal `0.3835386468 m` to `0.3843854102 m`. The corrected preregistered requirement is `1.4656074248 m`, which still rounds up to `1.50 m` at the required 0.05-m granularity. Thus it does not change Stage A's selected value and is below the C0-C `1.80 m` compact compatibility ceiling.

The preserved Stage-B result selects `1.80 m`: it is the first descending candidate above `d_hard` satisfying the bounded C0-D planning/geometry checks, including the C0-C compact `s=1` no-extra-raise condition. The preserved Stage-C planning/geometry rows pass all four candidates. With the downstream C0-E provisional-loader condition correctly removed from C0-D ownership, the largest preregistered C0-D-feasible candidate is `s_max=2.00`.

## Integration boundary

The two recorded cold-start attempts are reclassified as `integration_blocked_by_downstream_provisional_iapf_policy`. Policy loading rejected the composite candidate before any physical flight/controller execution, because old C0-E provisional `iapf_enter_min=1.50 m` is not strictly above C0-D `d_hard=1.50 m`. They are neither safety nor flight failures and were not used for selection.

Full-policy loading and the three integrated runtime smokes are deferred to C0-E. C0-E must integrate this frozen envelope without altering C0-D values. The full-runtime canonical policy remains `paper-current-v9-c0-c-frozen`; it has not been overwritten with an intentionally unloadable C0-D/C0-E composite.

## Governance audit

C0-A/B/C values are unchanged. All C0-E-owned numerics remain unchanged and provisional. Production loader inequalities remain unchanged. No allocator/objective/equation, geometry, Minimum Jerk, LADRC, or IAPF implementation was modified.
