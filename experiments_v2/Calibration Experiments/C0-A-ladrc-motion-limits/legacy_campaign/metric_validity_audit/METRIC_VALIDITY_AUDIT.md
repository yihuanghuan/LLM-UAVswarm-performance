# C0-A prereg-v2 metric validity audit

## Identity and scope

- Dataset class: `calibration_diagnostic`
- Formal source protocol: `C0-A-prereg-v2`
- Formal source result: `NO_ACCEPTABLE_CONFIGURATION`
- Formal A1 records: `300/300`; 26 PASS, 274 FAIL, 0/25 survivors
- Numeric/time-series coverage: 295 trials; the other five retained formal
  records have no extractable active/post trajectory.
- Parameter selection use: prohibited
- Diagnostic reruns: none

This audit does not reclassify a formal trial, alter a v2 metric, or choose a
candidate.  The v2 result, its denominator, its two recorded deviations and
all raw evidence remain unchanged.  A2, A3 and scale validation remain not
activated; no C0-A parameter is frozen.

## Actual v2 ZERO_CROSSINGS implementation

The implementation was inspected in `scripts/extract_metrics.py` and then
independently reproduced from every usable rosbag.  For axis `a`, it first
forms target-relative terminal position error over the five-second post window:

```text
e_a[k] = actual_position_a[k] - target_position_a
mean_a = (1/N) * sum_k e_a[k]
z_a[k] = e_a[k] - mean_a
```

It drops samples for which `z_a[k] == 0` and counts adjacent non-zero sign
changes:

```text
N_zc,a = sum 1[sign(z_a[i]) != sign(z_a[i+1])]
```

The trial fails when `max_a N_zc,a > 6`.  There is:

- no deadband;
- no hysteresis;
- no low-pass filter or smoothing;
- no minimum amplitude or persistence requirement;
- target-relative error before centering, followed by centering on the same
  post-window mean.

The independent implementation exactly reproduced all saved per-axis counts
and all 295 saved command-jerk values.  Therefore the audit concerns construct
validity, not a transcription or aggregation mismatch.

## Full cross-metric result

There are 265 valid trials with `ZERO_CROSSINGS` failure.  Of those, 263 also
pass every comparison requested for this audit:

- post RMS `<=0.25 m`;
- per-axis peak-to-peak `<=0.60 m`;
- last/first RMS ratio `<=1.0`;
- tracking RMSE `<=0.50 m`;
- maximum tracking error `<=1.00 m`;
- final error `<=0.40 m`;
- mission success.

Thus the cross-metric-clean ZERO_CROSSINGS failure count is **263**, equal to
**99.245% of ZERO_CROSSINGS failures** and **87.667% of all 300 formal
trials**.  A stricter formal definition—`ZERO_CROSSINGS` is the only saved
hard-failure code—contains 236 trials.

The complete trial table is in `metrics/trial_cross_metrics.csv` and
`metrics/aggregate_v2.csv`; it includes all 300 formal records and retains
missing numeric fields for the five infrastructure-affected records.

## Relationship to physical oscillation measures

Across the 295 trials with numeric metrics, using the maximum per-axis crossing
count:

| Pair | Pearson | Spearman |
|---|---:|---:|
| crossing count vs post RMS | 0.3761 | 0.3184 |
| crossing count vs post peak-to-peak | 0.4550 | 0.3930 |
| crossing count vs last/first RMS ratio | -0.0693 | -0.2472 |

The count has a moderate association with RMS/P2P, so it is not pure random
noise.  It does not, however, track growth/decay: higher count is weakly
associated with a *lower* last/first ratio.  More importantly, an unbounded
number of arbitrarily small mean crossings can trip the hard veto, while a
larger, smoothly decaying response can remain at or below six crossings.

One plotted Group-1 example fails on 22 z-axis crossings with z-axis RMS
`0.0044 m` and P2P `0.0213 m`.  A Group-2 example passes at `[4,4,6]`
crossings despite overall post RMS `0.1482 m` and maximum-axis P2P `0.4531 m`.
The latter remains within v2 amplitude limits, but it demonstrates that raw
crossing count does not order physical response severity.

Axis dominance reinforces this finding.  Among 265 ZERO_CROSSINGS failures,
z is tied for the maximum count in 249 and is the sole maximum in 247.  For
those 247 z-triggered trials, z-axis post RMS has median `0.00626 m` and P95
`0.01786 m`; z-axis P2P has median `0.02568 m` and P95 `0.07860 m`.

## Consistency with GROWING_OSCILLATION

The valid-trial contingency table is:

| | Growing PASS | Growing FAIL |
|---|---:|---:|
| ZeroCross PASS | 30 | 0 |
| ZeroCross FAIL | 264 | 1 |

Only one trial fails the registered growth ratio, and that trial also fails
ZERO_CROSSINGS.  The raw crossing veto additionally rejects 264 trials whose
post-window RMS does not grow.  This is a severe semantic mismatch between
“number of crossings of a self-estimated mean” and the claimed construct of
persistent/growing closed-loop oscillation.

## Crossing-event amplitude and noise scale

The 263 cross-metric-clean trials contain 7,015 reconstructed crossing events.
At each event, linear interpolation makes the target-relative crossing value
equal to the post-window mean.  Its absolute magnitude is:

| Statistic | `|e_a(t_cross)|` |
|---|---:|
| median | 0.002524 m |
| P90 | 0.009248 m |
| P95 | 0.013030 m |
| maximum | 0.060044 m |

The more direct measure of sign-switching scale—the nearer bracketing sample's
distance from the centered mean—is:

| Statistic | centered bracket amplitude |
|---|---:|
| median | 0.000290 m |
| P90 | 0.000921 m |
| P95 | 0.001262 m |
| maximum | 0.007768 m |

For comparison, the terminal position increment has median `0.000749 m` and
P95 `0.004424 m`.  The median crossing bracket is smaller than a typical
single-sample position increment, and its P95 is the same millimetre-scale
order.  Exact repeated positions are essentially absent (median repeat
fraction zero), and the minimum observed non-zero float increment is
`1.86e-9 m`; there is no evidence of coarse numeric quantization.  The relevant
floor is continuous estimator/hover/control variation, not integer rounding.

Control debug sampling is stable at median `19.9995 ms` (about 50.001 Hz),
with P99 `20.0922 ms` and P95 absolute jitter `0.0649 ms`.  Odometry bag
spacing has median `9.9483 ms` and P95 `12.0430 ms`.  Timestamp jitter is far
too small to explain the high crossing counts.  Instead, raw sign logic turns
millimetre-scale hover/estimator/control chatter about a sample-estimated mean
into full crossing events without amplitude qualification.

## Representative traces

`representative_trials/` contains terminal plots with target-relative error,
mean-centered error, raw sign and every reconstructed event:

- Group 1: 10 ZERO_CROSSINGS failures whose other registered stability,
  tracking and mission comparisons pass;
- Group 2: 5 ZERO_CROSSINGS passes;
- Group 3: the complete set of GROWING_OSCILLATION failures (one);
- Group 4: 5 COMMAND_JERK_P99_5 failures, with separate command/jerk/dt plots.

Selection is deterministic and spans metric quantiles; it is not based on
candidate desirability.  The index is `representative_trials/selection.csv`.

## COMMAND_JERK_P99_5 audit

The command jerk metric is a finite difference of the actual LADRC acceleration
command using intervals in `[0.005,0.1] s`.  It has 143–163 samples per trial
(median 163).  With the registered nearest-rank implementation, empirical
P99.5 equals the sample maximum in all 295 trials.  This is an important
finite-window limitation, but it is transparent and exactly reproduced.

The 31 failures are not produced by anomalously short sample intervals:

- peak-jerk dt median: `19.994 ms`;
- peak-jerk dt P95: `20.041 ms`;
- correlation of all 46,605 jerk samples with dt: Pearson `-0.00055`,
  Spearman `-0.00136`;
- failing trials have a median of 2 samples above `15 m/s^3` (maximum 16).

They show stable candidate discrimination.  Twenty-one of 31 failures occur
at `omega_o multiplier=1.33`, five at `1.17`, five at `1.00`, and none at
`0.67/0.83`.  The `(omega_c,omega_o)=(1.33,1.33)` package fails 9/12.  The
representative traces show real discrete command changes at normal 50 Hz dt,
not division by a small timestamp.  No trial has acceleration saturation, so
jerk measures command roughness rather than duplicate saturation.  Higher
jerk is associated with lower tracking error, consistent with a bandwidth
tradeoff rather than a broken measurement.

**COMMAND_JERK conclusion: VALID calibration evidence**, with the explicit
caveat that P99.5 is effectively a maximum for this window length.  This audit
does not change its threshold or formal v2 status.

## Infrastructure records

Seven non-success termination records are listed in
`metrics/infrastructure_failures.csv`:

- 2 `INFRASTRUCTURE_ERROR` records from DEV-001, both
  `METRIC_EXTRACTION_FAILED`;
- 2 `MANDATORY_TOPIC_MISSING` records from DEV-002; their two
  `MISSION_FAILED` codes follow the unsuccessful driver manifest and are not
  clean evidence of a physical mission failure;
- 2 `CAMPAIGN_INTERRUPTED` records retained while the campaign stopped for the
  documented repairs; `PROCESS_CRASH` is the conservative formal placeholder,
  not evidence that PX4 or Gazebo crashed;
- 1 isolated `COMMAND_REJECTED` record with `METRIC_EXTRACTION_FAILED`.

All seven remain in the 300-trial denominator, no original was overwritten,
and no replacement rerun was performed.  This matches v2 failure semantics.

## Candidate-level diagnostic map

`metrics/candidate_failure_map.csv` and
`figures/v2_candidate_failure_heatmap.png` report, for every 5x5 package, the
formal pass count, ZERO_CROSSINGS count, COMMAND_JERK count, other failures and
the counterfactual pass count after removing only the ZERO_CROSSINGS code.
Eleven packages are 12/12 on the other saved hard criteria.  This fact is
reported only to show that ZERO_CROSSINGS dominates the formal map.  It is not
a v2 reclassification, ranking, shortlist or winner selection.

## Metric validity conclusion

### Outcome B

```text
ZERO_CROSSINGS metric has a construct-validity failure.
Raw mean-centered sign changes are dominated by small-amplitude hover/noise
and low-amplitude closed-loop chatter rather than physically meaningful
unstable oscillation.
```

The conclusion is based on the scale of crossing events, the 263/265
cross-metric agreement result, axis dominance, the growth contingency and
representative traces—not on whether any candidate would become a survivor.
Moderate correlation with RMS/P2P is retained as contrary/qualifying evidence;
the failure is specifically the use of amplitude-free raw crossing count as a
hard veto for physical oscillation.

The existing motion-terminal data are candidate-contaminated and therefore
must not be used to choose a numeric deadband.  A new v3 protocol cannot be
run until an independent stationary-hover noise characterization establishes
the measurement floor and the proposed metric definition receives review.

## Invariants after this audit

- `C0-A-prereg-v2 STATUS = NO_ACCEPTABLE_CONFIGURATION`
- Frozen C0-A parameters: none
- `paper/calibration`: unchanged
- `paper-cal-C0A-v1`: absent
- v3 formal trials started: false
- C0-B started: false
- `READY_FOR_C0_B = NO`
