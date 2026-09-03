# E5-v2 formal campaign completion audit

Result: **PASS**

This is an accounting and evidence-integrity freeze. It does not perform or
interpret the preregistered scientific analysis.

## Durable campaign state

- Registered / consumed / journal / raw ledger / attempt directories:
  `60 / 60 / 60 / 60 / 60`.
- Unresolved transactions: `0`.
- The journal reconstructs the complete frozen 60-attempt order exactly.
- Unique attempt IDs: `60`; replacement attempts: `0`; additional samples: `0`.
- Slot 1 was physically executed once and was not rerun.

## Terminal accounting

- Mission success: `60`.
- Scientific failure: `0`.
- Semantic/frontend failure: `0`.
- Infrastructure failure: `0`.
- Scientific-complete: `60`; unavailable scientific-complete classification:
  `0`.

By substudy, E5-v2A is `15/15` scientific-complete with `0`
infrastructure failures, and E5-v2B is `45/45` scientific-complete with `0`
infrastructure failures. By registered swarm size, N=8 is `30/30`, N=12 is
`15/15`, and N=16 is `15/15` scientific-complete, each with `0`
infrastructure failures. These are completion/accounting statements only.

## Evidence and endpoint availability

- `RAW_ARCHIVE_VERIFIED`: `60`.
- `PRE_RAW_ACQUISITION_INFRASTRUCTURE_FAILURE`: `0`.
- `RAW_EVIDENCE_LOSS`: `0`; `RAW_ARCHIVE_PENDING`: `0`.
- All 60 external archive inventories were independently reverified.
- Continuous `J_hard` available: `0/60`; it remains
  `PREREGISTERED_ENDPOINT_UNAVAILABLE_DUE_TO_SEMANTIC_AMBIGUITY` with no
  replacement, proxy, or imputation.
- `T_validation`, `T_state_resolution`, `T_geometry`, `T_allocator`, and
  `T_profile` are each available for `0/60`, as frozen.

## Chain and inventory identities

- Journal chain tip SHA-256:
  `c39fcdbf0418b979209c70387932794eb0cd514a5a0b9bdaf32057dd286acb38`.
- Journal record-inventory SHA-256:
  `fa4e3db2530bcc496279e3d7df0f454b4f8fdd278343131809f0bb78723bb06e`.
- Raw-ledger chain tip SHA-256:
  `a09a5612ba93a32f3be9ab43c3bf6fe43358c09a02e3484ec93ee5b9342565d8`.
- Raw-ledger record-inventory SHA-256:
  `d7d8adfcc5964d33e9070cad4eb9b07dbc0bbdcd1cae80d3f5e1927ad6eed68c`.
- Compact-results inventory SHA-256:
  `cb1a0ef155cf7b9856c5cec93221c493a3c1715220ad57a0ff08389856fd1860`
  over 1,261 files.

## Frozen identity and provenance checks

The sealed registry, scientific payload, formal seeds, order, analysis
contract, production policy, and old E5-v1 registry match their frozen
identities. Scientific protocol changes and production-method changes are
both zero.

Slot 1 records physical bundle
`422d82b593ba927dffaee3c14bcf8b6996304a8ae302cdc525ab3c525b786ecb`
and transaction-recovery bundle
`29eb7421d2095ba88e60df0ed224ad035348b534cb57877a32d967bd933027bb`.
Slots 2–60 record physical execution bundle v2
`2800b1a4540ffde75573f5ea7bf580b415302d5c4d86f0ab86898c69f7b02572`.
The scientific method/protocol remained unchanged across the tooling
amendment; byte-identical instrumentation across all attempts is not claimed.

Final state:

`E5_V2_FORMAL_CAMPAIGN_COMPLETE_WAITING_FOR_ANALYSIS_AUTHORIZATION`
