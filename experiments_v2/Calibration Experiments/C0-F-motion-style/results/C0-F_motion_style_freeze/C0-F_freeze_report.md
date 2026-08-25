# C0-F motion-style freeze report

## Decision

**FROZEN.** The first provisional candidate passed unchanged; Stage-2 fallback
was not entered and parameter search stopped at the candidate lock.

| Item | Frozen value |
| --- | --- |
| `alpha_T(smooth/normal/aggressive)` | `1.30 / 1.15 / 1.10` |
| `kappa_style(smooth/normal/aggressive)` | `0.80 / 1.00 / 1.10` |
| `execution_profile_smoothing_alpha` | `1.0` |
| `task_adaptation`, `task_gain` | `identity`, `1.0` |
| canonical configuration | `paper-current-v11-c0-f-frozen` |
| canonical SHA-256 | `6b47d27f4253d7311e79ea51f6dd1cf0d0182e6df24374a94abae0aa6a135858` |
| locked-candidate SHA-256 | `fcfaabdecbef9bb0bd622cabe003d5c38cf91fde8ddb4c1f4db60dac6f37333c` |

## Evidence

- Screening: **12/12 PASS**; candidate unchanged.
- Locked confirmation: **24/24 PASS**.
- Sequential style-switch smoke: **2/2 PASS** at alpha `1.0`.
- Hard/dynamic violations, controller saturation, profile/IAPF clamps,
  instability, and IAPF activation: **0**.
- Maximum tracking RMSE: `0.190090696 m`.
- Maximum final error: `0.145045623 m`.
- Minimum measured pairwise distance: `2.166674220 m`.
- Maximum measured tilt: `25.295521502 deg`.
- Explicit-T invariance: **PASS**.
- Auto-T ordering: **PASS**.
- Compiled/applied profile consistency: **PASS**.

## Governance

Starting C0-E commit: `1e58f78ae3678eafdf9d0213e59514879601d461`. The C0-A through C0-E frozen artifact
hashes match their inherited manifests, and the field-level ownership audit has
no violations. Canonical integration changes only C0-F status/provenance
metadata because the first candidate itself was selected without numeric
deviation. No C0-G or E1-E6 work was started.
