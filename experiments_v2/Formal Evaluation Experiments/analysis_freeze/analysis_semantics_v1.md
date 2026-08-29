# Analysis Semantics v1

Status: **FROZEN BEFORE CAMPAIGN v2**  
Approval class: `HUMAN_APPROVED_PROSPECTIVE_ANALYSIS_DECISION`

This artifact freezes the prospective mapping from retained raw evidence to scientific metrics. It is separate from the sealed E2/E3/E4/E5 scientific protocols and does not revise them. No Campaign-v2 formal outcome existed when these definitions were approved, and no demo effect ordering or magnitude was used to select them.

The machine-readable authority is `analysis_semantics_v1.yaml`. This document is its human-readable companion.

## Authoritative identities

| Family | Protocol SHA-256 | Registry SHA-256 |
|---|---|---|
| E2 | `9ea7234db111b69cccb72315eed26e4abf117955eb20a2d593f2d854ea0b40e3` | `8215a5d8248c946c480ca4c8cb41e2afac28e6021c9f308a068580da69369bae` |
| E3 v3 | `2eea03e2bb33aa1c10c1ae104b965f909690f00c8caee4446291faf2c9893013` | `b56344c6cd257e99851523d640d9a89d6def994884877e2303d8fab836e0faf2` |
| E4 | `5a7eeb923aebcfb068827c6513a37e856dc8d6f05166a4b84775b33572bd83d0` | `48779a6667759955dd7dab2d8509f61a5439cca51a4bf98fcb48b6d17c499f95` |
| E5 | `116002154cd2395b6a9f55d7c1aae6e0a2c42440f0ceaa827a1a8cb02828319c` | `9bb6bc9b46b5211c50c8f2e29bd434235424beb2bb0fc36ec857a3298d89511e` |

E3 is gated to protocol v3 and activation commit `16de9c7ffd83b67925fc5817f33665727ccbb75f`. The frozen policy SHA-256 is `6b47d27f4253d7311e79ea51f6dd1cf0d0182e6df24374a94abae0aa6a135858`.

## Human-approved prospective decisions

Every item in this section is a `HUMAN_APPROVED_PROSPECTIVE_ANALYSIS_DECISION`.

### E3 hard risk

A hard-risk event is one maximal connected interval, for one unordered UAV pair, in which measured 3-D distance is strictly below the policy `d_hard` (currently 1.50 m). Equality is outside risk. Exiting and re-entering creates a new event. There is no debounce, hysteresis, minimum duration, merging, or cross-pair coalescing.

The primary count is the sum of pair-specific events. The primary exposure is the sum of pair-specific durations in pair-seconds. `any_pair_hard_risk_duration` is a temporal-union diagnostic only.

### E4A metrics

Commanded acceleration is the 3-D norm of the LADRC command. Its peak is the global peak over `[t0, t0 + T_explicit]`. Rise time is the first interpolated 10% crossing to the first later interpolated 90%-of-global-peak crossing. If already above 10% at interval start, `t10` is the interval start. A complete signal without a valid 90% crossing yields an invalid per-UAV value; no smoothing is permitted.

Control effort, acceleration peak/RMS/rise time, and tracking RMSE use `[t0, t0 + T_explicit]`, derived from the exact spec. Settling time is stable-hover entry minus `t0` and is not truncated at explicit T.

Per-UAV results are always retained. Swarm primaries are: maximum settling time; mean per-UAV control effort; mean per-UAV acceleration peak; equal-UAV pooled acceleration RMS; all-UAV-valid mean rise time; and equal-UAV pooled tracking RMSE. The maximum per-UAV acceleration peak is diagnostic.

### E5 mission metrics

Physical scoring begins at the first actual execution-command publication for the first registered task/group and ends at the exact registered terminal mission-completion event reconstructed from the mission graph. This interval governs actual minimum distance, tracking RMSE, and IAPF burden; mission timeout remains separate.

Tracking RMSE uses equal-UAV pooled RMS. Final error is evaluated only at terminal mission completion against each UAV's final registered assigned target; the primary is the mean per-UAV final error and maximum is diagnostic. Without terminal completion final error is `NA`.

IAPF activation time, integral delta-p, and integral delta-a are summed across participating UAVs for the swarm primary, while per-UAV values and means remain diagnostics.

Latency components are stage service times and need not sum: provider inference (including frozen retry/backoff), parse/validation, summed snapshot waits, summed resolution calls excluding allocation, summed allocation calls, summed dispatch spans, and physical execution. Language-command-to-terminal wall clock is diagnostic. Physical latency is `NA` without terminal completion.

### Failure and partial metrics

A continuous primary is numeric only when its entire required evidence interval is present and passes coverage. A later independent failure does not erase an earlier complete metric. Truncated values may be retained only as explicitly labelled partial diagnostics and never enter primary contrasts. Missing values are never encoded as zero. Boolean outcomes and all-attempt denominators retain every attempt, including infrastructure and method failures.

## Frozen A1 numerical conventions

Message-header ROS experiment time is authoritative; bag receive time is retained diagnostically. Duplicate timestamps with serialization-equivalent values collapse to one sample; materially conflicting duplicates fail closed. Exact registered boundaries are clipped with piecewise-linear interpolation and never extrapolated. Multi-UAV continuous signals synchronize on the union timestamp grid using piecewise-linear interpolation. Pairwise threshold crossings are linearly interpolated between adjacent distance samples. Continuous integrals use trapezoids and RMS is time-weighted. Discrete state duration uses zero-order hold. Analysis smoothing is forbidden.

The controller logging contract is 50 Hz (20 ms period). The prospective completeness gate permits no gap above 0.20 s, matching the frozen controller neighbor-staleness contract; both interval boundaries must be sampled or bracketed within that bound. This is a logging-health criterion fixed independently of condition effects. Failure produces `NA` plus coverage diagnostics, never extrapolation.

## Population rules

E3 requires complete P0/P1 × F0/F1 cells for each scenario/seed pair. E4A preserves scenario/geometry/seed style pairing. E4B Priority-Preservation Rate and E5 mission success retain all attempts in their denominators. Continuous summaries report valid N and NA N. Post-hoc filtering and significance-driven test selection are forbidden.

Descriptive summaries use sample SD (`ddof=1`), linear empirical quartiles, and a two-sided 95% Student-t confidence interval for the arithmetic mean. Paired effect size is Cohen's dz (mean paired difference divided by its sample SD), reported `NA` for zero paired-difference SD. These are fixed descriptive/effect-estimation conventions, not a data-selected inferential test.
