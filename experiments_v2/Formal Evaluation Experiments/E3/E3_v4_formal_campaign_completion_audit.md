# E3-v4 formal campaign completion audit

Generated: `2026-09-01T20:41:48Z`

## Completion gate

The sealed standalone E3-v4 formal campaign has consumed all 360 registered
slots in the exact frozen order. Formal execution is complete. Statistical
analysis has not been started and requires a separate human instruction.

- Registered slots: `360`
- Consumed slots: `360`
- Campaign-journal records: `360`
- Unique registered trial IDs: `360`
- Attempt directories: `360`
- Campaign contexts: `360`
- Next campaign position: none
- Next trial ID: none
- Evidence HEAD before this audit: `005848613c7887dfb8ad68312f86617a630c478b`

The journal positions and trial IDs are an exact complete prefix of the frozen
360-order. No seed was replaced, no attempt was rerun to improve an outcome,
and no additional sample was added.

## Registered attempt outcomes

- `success`: `343`
- `infrastructure_failure`: `17`
- Other registered statuses: `0`

All failures remain durably retained, journaled, and consumed under the frozen
contract. No continuous metric is invented for an infrastructure failure.

The 360 registered attempts define 90 complete registered scenario-by-seed
four-cell blocks. For the frozen primary scientific population:

- Complete four-success-cell blocks: `74`
- Incomplete blocks due to at least one infrastructure failure: `16`

One incomplete block contains two failed cells, hence 17 infrastructure
failures occur across 16 incomplete blocks. Missingness is left for the
prospectively frozen analysis contract; this audit performs no treatment-effect
or statistical analysis.

## Raw-evidence integrity

- Raw-storage ledger records: `360`
- `RAW_ARCHIVE_VERIFIED`: `359`
- `PRE_RAW_ACQUISITION_INFRASTRUCTURE_FAILURE`: `1` (slot 105)
- `RAW_ARCHIVE_PENDING`: `0`
- `RAW_EVIDENCE_LOSS`: `0`
- Missing storage dispositions: `0`
- Source/archive hashes verified wherever an archive was required: `true`

The only Git-tracked raw payload remains the documented historical slot-1
exception. No later `.db3` or `.mcap` payload is tracked by ordinary Git.

- Campaign journal SHA-256:
  `d00e59091ad598bdd5c1ffbbfded888aa04f0e3a7089cf9c225b21c196f49066`
- Raw archive ledger SHA-256:
  `87ff7e952cb3829921e0c0a47b3a4b82d077a9f68355dcb351e407df5be3ba57`

## Frozen identities

- Sealed registry SHA-256:
  `2b3dccc2ad27cf317029c2b7b014bca3a8b28fc8c0a196fd4c2e5abe0be9d4b7`
- Formal seed registry SHA-256:
  `665600871ad3fb6cff324ab3ef9144b0d84b42acc19505283679b6ae01586841`
- Formal order SHA-256:
  `60ee30a7100b53c4964e3f9f086ff3d137fb41282eebc4439760bf17f033b39b`
- Analysis contract SHA-256:
  `987ff29aa814a0dc5e9e64081fcf0fc79ceb3086b21a0e945bfe2f8252185c58`
- Production policy SHA-256:
  `6b47d27f4253d7311e79ea51f6dd1cf0d0182e6df24374a94abae0aa6a135858`
- Immutable E3-v3 registry SHA-256:
  `b56344c6cd257e99851523d640d9a89d6def994884877e2303d8fab836e0faf2`
- Activated execution tooling bundle SHA-256:
  `78cb5dbc374983c64752433fa1c62c4990903b03b5b813f0248f13105eb074bf`
- Raw-storage policy v2 SHA-256:
  `5a0ffedcd1088f0516f669b15ec3d613c857b1a9304917b2f4db728fce18f2b9`

## Invariance and stopping state

```text
scientific_protocol_changes = 0
formal_seed_changes = 0
formal_order_changes = 0
analysis_contract_changes = 0
production_source_changes = 0
formal_execution_tooling_changes = 0
replacement_attempts = 0
additional_samples = 0
interim_statistical_analysis_performed = false
```

PX4, Gazebo, MicroXRCEAgent, and LADRC controller processes were absent after
the final slot cleanup.

Final state:

```text
E3-v4 FORMAL CAMPAIGN COMPLETE
REGISTERED SLOTS: 360
CONSUMED SLOTS: 360
FORMAL EXECUTION STOPPED
STATISTICAL ANALYSIS NOT STARTED
WAITING FOR SEPARATE HUMAN ANALYSIS AUTHORIZATION
```
