# C0-A calibration result

## Experiment identity

- Calibration: `C0-A`
- Protocol: `C0-A-prereg-v1`
- Protocol SHA-256: `9b71550f76e2bb536cf0451ca0ea65f4665d7419b84377867868d72c972670bd`
- Base branch: `paper/calibration`
- Base commit: `c57e1c771817e70c5aca1ad1a9abd610d1205149`
- Algorithm freeze tag: `paper-algorithm-freeze-v1`
- Algorithm freeze commit: `56e8d2c8e59fc3513769e21910b7a20b2b43088d`
- Experiment branch: `cal/C0-A-ladrc-motion-limits`
- Starting policy: `paper-current-v7`
- Dataset class: `calibration`
- Formal trials started: **NO**

## Pre-trial gates

- Algorithm freeze: **PASS**
- C0-A parameter ownership against `origin/paper/calibration`: **PASS**
- Gate output: `logs/preflight_checks.txt`

## Preregistration execution audit

The frozen protocol does not define one unambiguous complete trial schedule.
Resolving the following items in the runner would add or remove registered
trials, scenarios, repetitions, or duration choices, which this calibration is
explicitly forbidden to do after protocol freeze.

1. **A1 screening trial count is contradictory.** Lines 107--110 require the
   three named scenarios over three seeds and state that each candidate has
   "all nine trials". Lines 172--183 define `C0A-S-HX-3` with two signed
   displacements and require each signed displacement to be a separate trial.
   The latter rule yields four displacement trials per seed across the named
   scenarios, or 12 trials per candidate, not nine.
2. **A3 has no registered execution set.** Lines 138--156 define clamp
   candidates and selection semantics, but do not assign A3 scenarios, seeds,
   repetitions, or explicit durations. The generic seed section distinguishes
   screening from confirmation/scale validation and does not classify A3.
3. **The single-UAV scale-validation case is not registered.** Lines 183--187
   require a 1-to-4-to-8 UAV validation with the same per-UAV displacement and
   explicit duration. The scenario table defines only `C0A-M-4` and `C0A-M-8`
   with the `[-4,3i,3]` to `[+4,3i,3]` displacement; it defines no corresponding
   single-UAV scenario, start/target pair, or scale-validation duration.

No formal trial order can truthfully be called complete while these choices
remain undefined. Per the task rule for an unexecutable protocol, execution
stopped before generating or inspecting any C0-A outcome. No registered range,
candidate, threshold, metric, selection rule, timeout, or failure rule was
changed.

## Stage A1

- Registered candidates: 25
- Trials executed: 0
- Pass/fail: not evaluated
- Survivors: not evaluated
- Confirmation: not run
- Winner: none

## Stage A2

- Registered packages: acknowledged but not scheduled because A1 has no winner
- Trials executed: 0
- Pass/fail: not evaluated
- Confirmation: not run
- Winner: none

## Stage A3

- Clamp validation: not run; registered trial set is incomplete
- Selected hard envelope: none

## Scale validation

- 1 UAV: 0/0; scenario/duration not registered
- 4 UAV: 0/0; not run
- 8 UAV: 0/0; not run

## Frozen values

No values were frozen. All C0-A-owned ledger rows remain `PROVISIONAL`:

- `omega_c`: unchanged development value `[1.5, 1.5, 1.75]`
- `omega_o`: unchanged development value `[5.0, 5.0, 7.5]`
- `v_limit/a_limit/j_limit`: unchanged development values `5/5/10`
- `minimum_duration`: unchanged development value `0.5 s`
- omega hard clamps: unchanged development values
- motion hard clamps: unchanged development values
- physical controller caps: unchanged development values

These values are recorded only to prove that no parameter freeze occurred;
they are not C0-A winners.

## Evidence

- Formal trial manifests: 0
- Raw bags: 0
- Metrics/figures: none; no outcomes were generated
- Failures: preregistration execution audit failed before trial scheduling
- Policy before/after: `paper-current-v7` / `paper-current-v7`
- Policy SHA-256 before/after:
  `5b2d9e73b076e950a975ffb33596817ac4824926ed1598c7f2009c06ba014c11`
- Controller configuration SHA-256 before/after:
  `d3546709533b9470d88502406be136e1c7afbf7dfd9c23a1dfad81cd5c49d556`

## Deviations from preregistration

**NONE.** The campaign stopped before the first formal trial rather than
silently choosing an interpretation for the contradictory or missing fields.

## Conclusion

`C0-A = INVALIDATED / INFRASTRUCTURE_BLOCKED`

C0-A parameters must not be merged to `paper/calibration`; checkpoint tag
`paper-cal-C0A-v1` must not be created; C0-B must not begin.
