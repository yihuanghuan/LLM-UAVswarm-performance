# E3 protocol v3 candidate consistency audit

Status: **PASS**

This is compile-only engineering validation. The candidate is not frozen or active.

## Scenario-family consistency

| Scenario | Family | P0 N_hard | P1 N_hard | P0 d_min | P1 d_min | Disturbance | Result |
|---|---|---:|---:|---:|---:|---|---|
| E3-A-01 | A_predictable_structural_risk | 2 | 0 | 0.427482 | 2.000000 | False | PASS |
| E3-A-02 | A_predictable_structural_risk | 2 | 0 | 0.000000 | 2.248387 | False | PASS |
| E3-B-01 | B_residual_execution_risk | 0 | 0 | 2.000000 | 2.000000 | True | PASS |
| E3-B-02 | B_residual_execution_risk | 0 | 0 | 2.000000 | 2.000000 | True | PASS |
| E3-C-01 | C_mixed_risk | 2 | 0 | 0.427482 | 2.000000 | True | PASS |
| E3-C-02 | C_mixed_risk | 2 | 0 | 0.000000 | 2.248387 | True | PASS |

## Compile and population invariants

- Production compile-only specs: 360/360 PASS.
- Population: 6 scenarios × 4 conditions × 15 seeds = 360 trials.
- Trial IDs unchanged: True.
- Global order line count: 610; SHA-256 `db28bf8d734e1f206987519e91ff27c67b2d9ab2971aeb68c4e13735762f1dce`.
- No physical runtime was launched.

Canonical audit SHA-256: `954690cc07c5322216961a9827d16396452a0c062ef304dff87ac1d774bfaee5`
