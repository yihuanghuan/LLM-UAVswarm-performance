# Safety Factor `s` Contract

`s` has one frozen semantic meaning:

> task-level safety preference / safety-margin multiplier

The Candidate/Executable LFS retains `s`; late resolution acts as the logical
Safety Compiler and produces one validated Safety Profile:

```text
LFS s
→ Safety Compiler
├── allocator d_plan
├── Execution Profile iapf_enter_distance
├── Execution Profile iapf_exit_distance
└── Execution Profile iapf_repulsion_scale
→ controller validates/clamps/applies
→ IAPF executes compiled physical parameters
```

The allocator, controller, and IAPF core do not define independent mappings
from `s`. In particular, IAPF core has no `s` argument and does not multiply
the final raw repulsion by `s`.

## Responsibilities and current mapping

`d_violation` is the fixed system-level hard-risk threshold and is identical to
allocator `d_hard`. It does not vary with a natural-language preference.
`d_plan` is the planning-layer preferred margin. `d_enter` starts runtime IAPF
consideration, `d_exit` provides the larger hysteresis exit boundary, and
`k_rep` scales the configured IAPF repulsion gain once at the controller
boundary. These quantities intentionally have different baselines.

For `paper-current-v11-c0-f-frozen`, with `1 <= s <= 2`, the frozen C0-D/C0-E
mapping is:

```text
d_violation = d_hard = 1.50
d_plan(s)   = d_hard + s * (1.80 - d_hard)
d_enter(s)  = d_hard + s * (1.60 - d_hard)
d_exit(s)   = d_hard + s * (1.70 - d_hard)
k_rep(s)    = 1.0 + 0.25 * (s - 1)
```

| LFS `s` | `d_violation` / `d_hard` | allocator `d_plan` | IAPF `d_enter` | IAPF `d_exit` | IAPF `k_rep` |
|---:|---:|---:|---:|---:|---:|
| 1.0 | 1.50 | 1.80 | 1.60 | 1.70 | 1.0 |
| 1.5 | 1.50 | 1.95 | 1.65 | 1.80 | 1.125 |
| 2.0 | 1.50 | 2.10 | 1.70 | 1.90 | 1.25 |

The semantic architecture and monotonic direction are architecture-frozen.
C0-D froze `d_hard`, `d_plan_base`, and the `s` domain; C0-E froze the IAPF
enter/exit baselines, repulsion mapping, and runtime filter.

## Validation and compatibility

The typed policy loader rejects missing, non-finite, negative, unordered, or
uncovered mappings. Runtime resolution rejects non-finite/out-of-range `s` and
requires:

```text
d_violation > 0
d_plan >= d_violation
d_violation < d_enter < d_exit
k_rep >= 0
```

Mapped IAPF values must fit the configured controller hard limits. The
controller repeats finite/order checks and clamps only as an abnormal-profile
guard. `UAVExecutionCommand` carries compiled values rather than `s`.
Candidate `s` is audited in `ResolutionTrace`; the similarly named
`TrajectoryMetrics.safety_factor` remains legacy-only telemetry and is not a
controller input.

The old `UAVSwarmCommand.safety_factor` field remains wire-compatible. At that
legacy-only boundary it is converted once to the historical repulsion scale;
it is never forwarded to IAPF core. New Candidate commands always use the
compiled Safety Profile.
