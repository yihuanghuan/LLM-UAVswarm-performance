# IAPF velocity, hysteresis, and smoothing update

The execution-layer IAPF now uses relative velocity in the global ENU frame.
Positive closing speed means that a pair is approaching. A pair enters avoidance
inside `iapf_enter_distance` while approaching (or whenever it is already
inside `iapf_violation_distance`) and remains latched until
`iapf_exit_distance`.

For a receding pair above the violation threshold, repulsion fades linearly
toward the exit distance. The `id_order` escape mode constructs a deterministic
direction perpendicular to the canonical pair relative position and velocity,
then applies opposite signs to the lower and higher UAV IDs.

Position and acceleration offsets are norm-limited before a first-order filter:

```text
filtered = alpha * desired + (1 - alpha) * previous
```

The default parameters are:

```yaml
iapf_violation_distance: 1.00
iapf_enter_distance: 1.50
iapf_exit_distance: 1.65
iapf_filter_alpha: 0.20
```

`iapf_safe_distance` remains a deprecated alias for the enter distance. The
explicit enter-distance parameter takes precedence when both are supplied.
Debug messages include the nearest-neighbor closing speed, hysteresis state,
and number of active neighbors.
