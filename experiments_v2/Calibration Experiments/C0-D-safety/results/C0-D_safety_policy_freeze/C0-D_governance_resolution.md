# C0-D governance resolution: planning-safety component boundary

The original C0-D blocked audit is preserved as historical evidence. It correctly found that the composite of the C0-D candidate and the *old, provisional* C0-E IAPF policy cannot be loaded: the loader's strict inequality requires `d_hard < iapf_enter_min`, while both values were 1.50 m.

That condition was accidentally made a C0-D Stage-C selection criterion. It creates a circular calibration dependency: C0-D must determine the hard planning envelope before C0-E can select its downstream IAPF activation numerics, but C0-D was being required to remain compatible with those unselected numerics.

C0-D is therefore frozen as a planning-safety **component** only. Its owned fields are `d_hard`, `d_plan_base`, `s_min`, and `s_max`; the hard-anchored linear mapping type and `s_min=1.0` remain architecture-frozen. The C0-D component selection uses physical collision/tracking/freshness evidence plus the bounded planning/geometry checks. It does not require policy loading with C0-E-owned provisional IAPF bases or clamps.

This is a governance correction, not an algorithm change, loader change, or parameter-selection change. The production loader inequalities, allocator objective, geometry logic, Minimum Jerk, LADRC, and IAPF equations are unchanged. C0-E remains responsible for selecting IAPF enter/exit/repulsion/filter/gain/epsilon/modulation-clamp numerics that can integrate the frozen C0-D envelope.

The canonical full-runtime `paper-current-v9-c0-c-frozen` policy remains unchanged and loadable. A new integrated canonical policy is deferred until C0-E incorporates this component's frozen envelope.
