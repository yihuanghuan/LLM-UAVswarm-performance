# E3-v4 Family-C deterministic mixed-risk qualification report

Status: `PASS`

This is calibration/pilot evidence only. It contains no F1 attempt and no
formal result. The finite grid was committed at `aefa13dc` before any physical
Family-C attempt. Raw data for every attempt instance remain append-only under
`results/qualification/family_C_execution_deviation_raw/`.

## Registered construction and planning manipulation

Both scenes spatially combine the unchanged E3-v3 A-01 offset-trapezoid
structural component (UAVs 1-4) with a qualified deterministic post-planning
execution-deviation component (UAVs 5-8). The components are separated by a
20 m world-x translation. Offline allocation found, for both scenes:

| condition | assignment | predicted hard count | predicted d_min (m) |
|---|---|---:|---:|
| P0_F0 | `[2,3,0,1,4,5,6,7]` | 2 | 0.427482 |
| P1_F0 | `[0,1,2,3,4,5,6,7]` | 0 | 2.000000 |

No assignment crosses the structural/residual component boundary. The
residual component remains identity-assigned in both planning modes. Thus P1
removes the registered predictable component without planning away the
execution-deviation assay.

## Frozen finite-grid results

The grid contained exactly four cells x two F0 planning modes x five frozen
qualification seeds = 40 registered attempts. One original attempt had a
staging command-acknowledgment timeout before interaction and was retained as
an infrastructure failure; its append-only same-seed `retry-r1` succeeded.
There are 41 retained instances and 40 scientifically eligible registered
attempts.

| candidate | condition | intended-pair prevalence | intended d_min range (m) | intended exposure range (pair-s) | result |
|---|---|---:|---:|---:|---|
| C01-DELAY-D0p4 | P0_F0 | 5/5 | 1.372634-1.477582 | 0.767388-2.605355 | PASS |
| C01-DELAY-D0p4 | P1_F0 | 5/5 | 1.384964-1.448884 | 1.589106-2.595928 | PASS |
| C01-DELAY-D0p5 | P0_F0 | 5/5 | 1.242327-1.316570 | 3.266422-3.602237 | PASS |
| C01-DELAY-D0p5 | P1_F0 | 5/5 | 1.255872-1.294347 | 3.238043-3.572813 | PASS |
| C02-REF-O1p2 | P0_F0 | 0/5 | 1.691596-1.742517 | 0 | REJECT_FLOOR |
| C02-REF-O1p2 | P1_F0 | 0/5 | 1.700767-1.728367 | 0 | REJECT_FLOOR |
| C02-REF-O1p5 | P0_F0 | 5/5 | 1.381735-1.438581 | 0.769236-1.140560 | PASS |
| C02-REF-O1p5 | P1_F0 | 5/5 | 1.377404-1.408422 | 0.929191-1.131803 | PASS |

For P0 the global minimum is, as intended, structural pair 1-3. Qualification
does not use that event as residual evidence; the table reports pair 6-7
separately. Under P1, pair 6-7 is the global minimum and is the only pair with
hard-risk events. Every C02 attempt had zero intended-pair hard events before
reference-deviation activation; pre-activation pair 6-7 minimum distances were
4.390-4.478 m (P0) and 4.396-4.412 m (P1) for the selected cell.

All scientifically eligible attempts verified the registered post-planning
delivery. Every condition had mission success 5/5, no failsafe, no distance at
or below 0.25 m, and no saturation-dominated attempt. The largest observed
near-acceleration-limit sample fraction was 0.039375.

## Treatment-blind selection

The frozen selection rule first requires all gates and then chooses the
smallest deviation magnitude. C-01 therefore selects `C01-DELAY-D0p4`. C-02
selects `C02-REF-O1p5`, because O1p2 failed the residual-prevalence/exposure
gate. No feedback-on condition was run or inspected.

```text
grid_sha256 = a46469f71206b71cf4d85c8190196757c8ee996ff6bb5708e3483f47bf87cd83
offline_audit_sha256 = b986311f510bb8694ef09f6d6c7152e4dfe93565c12d479ce6ecb2c3feb42b3c
qualification_evidence_sha256 = 7481080bd9b43da66773b9d3e18c37dc3047a8dda27a5427854550028d52ad12
compact_raw_inventory_sha256 = f798556b4f4e152f1ee7159b9cb143e439d566c3b36cf608d3e596def22f77e7
F1_attempt_count = 0
formal_attempt_count = 0
```
