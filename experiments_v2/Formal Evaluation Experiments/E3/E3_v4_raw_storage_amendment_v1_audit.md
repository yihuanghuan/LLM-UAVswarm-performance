# E3-v4 Raw-Storage Amendment v1 Audit

Status: **PASS**

Baseline evidence commit:
`baa570c79b8202c008f47800cfc277f1dcb74fa0`.

## Slot-1 archive verification

- Trial: `E3-C-01__P1_F1__S934882`, campaign position `1`.
- Attempt SHA-256:
  `6e1713c35282e42352550dba5377a693c8ce5f5451a3160ec580898a52684555`.
- Source bag:
  `results/formal_v4/attempts/000001__E3-C-01__P1_F1__S934882/raw/rosbag/rosbag_0.db3`.
- Source size: `53,854,208` bytes.
- Source SHA-256:
  `3cd9a1049332fc9f5258ad54e804adf8f8dcf3b35b2e98daf84e285e01e55573`.
- Independent archive:
  `/home/yihuang/learning/LLM_swarm_ws/E3_v4_raw_archive/slot_000001__E3-C-01__P1_F1__S934882/rosbag/rosbag_0.db3`.
- Archive size: `53,854,208` bytes.
- Archive SHA-256:
  `3cd9a1049332fc9f5258ad54e804adf8f8dcf3b35b2e98daf84e285e01e55573`.
- Source/archive equality: `true`.
- Source retained: `true`; archive retained: `true`.
- Inventory SHA-256:
  `d18cbc2609acd3faf61c3aae8c515b4b2ac56abf6951672cfe95c90e4fd68f05`.
- Raw archive ledger SHA-256:
  `2402f8467a65f82654fc2afa9fb224925b8c8bbdce1572aa474171a07cf5baf9`.

The tracked slot-1 `.db3`, attempt, metrics, and existing campaign-journal line
were not modified. Slot 1 remains the documented historical Git-storage
exception. No new formal attempt was executed.

## Frozen scientific identities

- Sealed registry SHA-256:
  `2b3dccc2ad27cf317029c2b7b014bca3a8b28fc8c0a196fd4c2e5abe0be9d4b7`.
- Formal seed registry SHA-256:
  `665600871ad3fb6cff324ab3ef9144b0d84b42acc19505283679b6ae01586841`.
- Formal order SHA-256:
  `60ee30a7100b53c4964e3f9f086ff3d137fb41282eebc4439760bf17f033b39b`.
- Analysis contract SHA-256:
  `987ff29aa814a0dc5e9e64081fcf0fc79ceb3086b21a0e945bfe2f8252185c58`.
- Policy SHA-256:
  `6b47d27f4253d7311e79ea51f6dd1cf0d0182e6df24374a94abae0aa6a135858`.
- E3-v3 registry SHA-256:
  `b56344c6cd257e99851523d640d9a89d6def994884877e2303d8fab836e0faf2`.
- Activated execution tooling bundle SHA-256:
  `78cb5dbc374983c64752433fa1c62c4990903b03b5b813f0248f13105eb074bf`.

```text
scientific_protocol_changes = 0
production_changes = 0
formal_execution_tooling_changes = 0
new_formal_attempts = 0
```

## Campaign cursor

The campaign journal SHA-256 remains
`6aa96ef8938a8a6a07766bf8e0da50e585c62488f30cd8bf33b7f793b06e20a3`
and contains exactly one record.

```text
consumed_slot_count = 1
next_campaign_position = 2
next_trial_id = E3-C-02__P0_F1__S934882
slot_2_context_exists = false
slot_2_attempt_directory_exists = false
slot_2_rosbag_exists = false
```

No simulator was launched for slot 2.

## Final gate

```text
E3-v4 RAW STORAGE AMENDMENT: PASS
SLOT 1 RAW ARCHIVE: VERIFIED
SCIENTIFIC PROTOCOL CHANGES: 0
FORMAL EXECUTION TOOLING CHANGES: 0
CAMPAIGN JOURNAL CONSUMED SLOTS: 1
NEXT CAMPAIGN POSITION: 2
NEXT TRIAL: E3-C-02__P0_F1__S934882
SLOT 2 NOT STARTED
```
