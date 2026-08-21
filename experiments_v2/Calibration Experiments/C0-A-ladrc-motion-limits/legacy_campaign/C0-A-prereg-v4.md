# C0-A-prereg-v4 — Simplified continuation

**Status:** post-start calibration-workload amendment; continuation only.

This document preserves C0-A-prereg-v1/v2/v3 and all completed raw data. It
does not claim pre-outcome purity and does not alter the LADRC algorithm,
candidate grid, motion packages, scenarios, or hard thresholds. Its sole
purpose is efficient Phase-0 parameter freezing.

## Reuse and exclusion

The complete v3 A1 screening block (300/300) is reused under the v3 V3-B
rule. `raw_zero_crossings` remains diagnostic only and has no PASS/FAIL,
ranking, or tie-break role. The interrupted/partial v3 A1 confirmation block
is preserved as `calibration_diagnostic_partial` and is prohibited from v4
selection.

## Continuation schedule

The top three candidates from the complete A1 screening are confirmed using
six representative motions (`+3 m x`, `-3 m x`, `+3 m y`, `+2 m z`, `-1 m z`,
and mixed 3-D diagonal), seeds `44001,44002,44003`, for 54 cold-start trials.
The first candidate passing all valid hard criteria is the A1 winner under the
existing lexicographic rule.

A2 uses the six registered motion packages only. Analytical
`T_min(D)` feasibility is evaluated first; the registered `minimum_duration`
floor is 0.5 s because it is non-binding over the registered displacements.
Thirty screening trials use five representative motions at `1.15*T_min`,
seed `45001`. The top two envelopes receive at most 30 confirmation trials
with seeds `45002,45003,45004`. Selection prioritizes the highest reliably
executable envelope, then the existing safety/jerk/tracking tie-breaks.

A3 is a nine-trial guard-envelope verification (three representative motions
and three seeds), not a clamp sweep. The selected guard must cover the
admissible style interval `[0.75,1.20]` with no unexpected omega or motion
clamp, saturation, or instability.

Scale validation is nine cold starts: 1, 4, and 8 UAV, three seeds
`46001,46002,46003`. It validates only the fixed A1/A2/A3 result.

Maximum new trials are 132. Any stage with no acceptable configuration stops
immediately. No C0-B activation is permitted by this amendment.

## Preservation

The interrupted v3 campaign is classified `TERMINATED_FOR_CALIBRATION_EFFICIENCY`,
not algorithm failure. No parameter is frozen until A1, A2, A3, and all three
scale levels pass. No algorithm or paper policy parameter is changed.
