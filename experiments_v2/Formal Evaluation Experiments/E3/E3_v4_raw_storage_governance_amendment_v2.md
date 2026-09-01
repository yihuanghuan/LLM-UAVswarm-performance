# E3-v4 Raw-Storage Governance Amendment v2

Status: `FROZEN_AFTER_SLOT_105_BEFORE_SLOT_106`

Baseline evidence commit:
`093a66f27cbb1936b10cff6b61c716ffaa0cd1b9`.

## Scope and reason

This is a storage/governance clarification only. It preserves the v1 policy as
immutable historical governance and adds a lifecycle distinction required by
the activated runner: raw acquisition starts only after all-UAV readiness has
passed. A formal infrastructure failure before that gate can therefore
legitimately produce compact failure evidence without ever creating a rosbag.

```text
scientific_protocol_changed: false
formal_registry_changed: false
formal_seed_population_changed: false
formal_order_changed: false
analysis_contract_changed: false
journal_semantics_changed: false
execution_semantics_changed: false
production_semantics_changed: false
activated_execution_tooling_changed: false
```

The activated execution tooling bundle remains
`78cb5dbc374983c64752433fa1c62c4990903b03b5b813f0248f13105eb074bf`.
Rosbag acquisition is not moved earlier and no file in that bundle is changed.

## Acquisition distinction

Each consumed formal slot receives a storage disposition based on retained
evidence:

- `RAW_ACQUISITION_STARTED`: the frozen runner reached its rosbag-start step.
  A source raw bag is required and is governed by verified, pending, or loss
  semantics.
- `PRE_RAW_ACQUISITION_FAILURE`: the immutable attempt ended before the
  rosbag-start step. No source bag was created or expected, and sufficient
  compact evidence must establish the pre-acquisition failure stage.

Absence of a bag is not, by itself, sufficient for the second classification.
The attempt status, retained logs, lifecycle order, and nonexistence of any bag
or archive artifact must agree. Ambiguity remains fail-closed.

## Storage states

### `RAW_ARCHIVE_VERIFIED`

Raw acquisition started, the source bag and independent archive both exist,
and their sizes and SHA-256 values match. V1 retention and Git-exclusion
requirements remain unchanged.

### `RAW_ARCHIVE_PENDING`

Raw acquisition started and the retained source exists, but the independent
archive is not verified. Scientific rerun and replacement are forbidden.
Campaign progression is blocked until storage is repaired from that source.

### `RAW_EVIDENCE_LOSS`

Raw acquisition started, or retained lifecycle evidence proves a raw source was
expected, but required source evidence is unavailable. This remains a genuine
campaign blocker. This state must not be used merely because acquisition never
began.

### `PRE_RAW_ACQUISITION_INFRASTRUCTURE_FAILURE`

This state is valid only when an immutable formal attempt records
`infrastructure_failure`, the failure is proven to precede rosbag acquisition,
interaction and scoring never began, no source bag was created, and retained
compact evidence is sufficient to establish the stage.

```text
raw_bag_expected: false
raw_bag_lost: false
archive_required: false
archive_missing_is_not_error: true
scientific_retry_authorized: false
replacement_seed_authorized: false
additional_campaign_slot_consumed: false
slot_remains_consumed: true
```

This state is neither `RAW_EVIDENCE_LOSS` nor `RAW_ARCHIVE_PENDING`. The
scientific attempt remains an infrastructure failure in the journal and
all-attempt denominator and contributes no fabricated continuous metrics.

## Ledger coverage

The append-only raw storage ledger may contain its historical v1
`E3_v4_raw_archive_ledger_record_v1` archive records and v2
`E3_v4_raw_storage_disposition_record_v2` records. Each consumed slot must have
exactly one applicable storage disposition. A pre-acquisition record carries no
fake source/archive sizes or hashes and never claims archive verification.

Slot 105 is prospectively clarified by retained evidence as
`PRE_RAW_ACQUISITION_INFRASTRUCTURE_FAILURE`; it remains consumed and is not
rerun. Slot 106 remains unstarted while this amendment is frozen and audited.
