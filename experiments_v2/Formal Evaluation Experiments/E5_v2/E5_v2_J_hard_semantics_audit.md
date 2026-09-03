# E5-v2 prospective `J_hard` semantics audit

## Conclusion

`PREREGISTERED_ENDPOINT_SEMANTICS_AMBIGUOUS`

`BLOCKED_AT_E5_V2_J_HARD_SEMANTIC_AMBIGUITY`

No slot-1 scientific metric was computed or inspected in reaching this
conclusion. The audit cutoff is the pre-slot-1 tooling-freeze commit
`9276cbe1dcff8299d3edcd73e10cc3a686b2441c`.

## Prospective evidence

| Frozen artifact at `9276cbe1...` | SHA-256 | Prospective statement or implementation |
|---|---|---|
| `E5_v2_analysis_contract.md` | `05802cb32e8dc2f990d9e0144f2cfd118b87228ab0c441578e084aeefc0d008a` | Calls `J_hard` a continuous outcome, but gives no formula, unit, `J_hard`-specific interval, interpolation, or aggregation convention. |
| `E5_v2_registry.yaml` | `e915575f23b1bd83810f3a8e5aa8092806b9076960c5a2f1fc2bb5faa73ad985` | Freezes the binary mission-success condition `actual d_min >= 1.50 m`; it does not define `J_hard`. |
| `E5_v2_formal_classification_policy_v1.md` | `aca54b60ff51835b936dc20a3871eac4fa5e03c95d68b5b39716f27bf7e53451` | Classifies a hard-distance violation and requires interval coverage, but does not define `J_hard`. |
| `tooling/e5_v2_formal_metrics.py` | `2129862ea6e3bcabdd4b744a41ff05312e82c5a9bc2ca389ffc57a6acf9bce8e` | Maps `J_hard` to `int(not d_min_ok)`: a dimensionless whole-attempt binary indicator, not the preregistered continuous outcome. |
| `tooling/e5_v2_feasibility.py` | `1dcc881b475cc89d0d2fce2892c03c9f45f9d4766070ddaed19d464e7dfa9e61` | Labels `final_metrics.hard_violations` as `J_hard`: an integer nominal-planning violation count, not an observed continuous closed-loop exposure definition. |
| C0-E `extract_trial_metrics.py` | `f769d8a29c50bcf2a12395747b6985fee8dae67dea30234042806922bd216195` | Separately computes event count and any-pair violation duration on a 0.02 s grid. E5-v2 never explicitly or unambiguously inherits either one as `J_hard`. |

An exact-name repository search at the prospective cutoff found `J_hard` only
in the E5-v2 contract, design audit/tooling, and frozen formal implementation.
No E5-v2 artifact identifies an external analysis-semantics authority for this
endpoint.

## Why no exact mapping can be recovered

At least three non-equivalent prospective representations exist:

1. `int(not (d_min >= 1.50 m))`, unitless and binary;
2. the allocator's integer count of nominal hard-constraint violations;
3. C0-E's seconds of any-pair threshold exposure on a fixed 50 Hz grid.

The third representation is not an E5-v2 inheritance, and even it does not
resolve whether E5-v2 intended union time, summed pair-time, event count,
distance-deficit integral, or another continuous functional. The frozen E5-v2
artifacts also do not specify:

- a unit;
- the exact `J_hard` interval for all mission structures;
- `< d_hard` versus `<= d_hard` at equality;
- threshold-crossing interpolation;
- aggregation across pairs, simultaneous violations, and compositional tasks;
- treatment of coverage gaps.

Consequently, treating the frozen binary implementation as a continuous
outcome is not defensible, while choosing a replacement now would define the
endpoint after slot 1 was physically executed. This requires human
adjudication before scientific metric extraction or transaction recovery.

## Preserved blocker state

- Raw archive: 2 files, 45,883,177 bytes, inventory SHA-256
  `ff97ad4ef665754e23fc90e06803844580bcfaacd2ae89034d3ecaf8bc56fbda`.
  Both file hashes and `ros2 bag info` passed; 110,197 messages and
  25.149640563 s duration were confirmed.
- Unresolved transaction: 30 files, 633,319 bytes, inventory SHA-256
  `2c0c1d9d961ccc63ffee0776f4b36c9ec0b111c9cb6f877b2e28dcc06bbc9152`.
- The preserved originals were not modified.
- Journal / raw ledger / published attempt directories remain `0 / 0 / 0`.
- Slot 1 remains physically executed exactly once, unresolved, and not rerun.
- Slot 2 was not started.

No infrastructure amendment, metric change, recovery tool, compact publication,
ledger record, or journal record was created. Scientific payload, registry,
seeds, formal order, analysis contract, production method, and old E5-v1 remain
unchanged.
