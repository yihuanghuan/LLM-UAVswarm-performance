# E3-v4 Raw-Storage Governance Amendment v1

Status: `FROZEN_BEFORE_FORMAL_SLOT_2`

Baseline evidence commit:
`baa570c79b8202c008f47800cfc277f1dcb74fa0`.

## Classification and reason

This is a storage/provenance amendment only. Slot 1 produced a rosbag of
approximately 51 MB. Directly committing one comparable binary rosbag for each
of 360 registered formal attempts would unnecessarily inflate ordinary Git
history and risks future remote-storage and push failures. Complete raw
evidence remains scientifically required, so raw acquisition, local retention,
independent backup, and SHA-256 provenance all remain mandatory. For future
slots, ordinary Git stores compact evidence and verified hashes instead of the
binary rosbag payload.

```text
scientific_protocol_changed: false
formal_registry_changed: false
formal_seed_population_changed: false
formal_order_changed: false
analysis_contract_changed: false
journal_semantics_changed: false
execution_semantics_changed: false
production_semantics_changed: false
```

The activated execution tooling bundle is byte-identical and remains
`78cb5dbc374983c64752433fa1c62c4990903b03b5b813f0248f13105eb074bf`.
The new archive utility is post-attempt evidence-preservation tooling and is not
in `e3_v4_formal_adapter.py::TOOLING_PATHS`.

## Slot-1 historical exception

The slot-1 commit and all its formal evidence are immutable. Its tracked
`rosbag_0.db3` remains in ordinary Git history. It must not be removed,
rewritten, rebased, filtered, or retroactively migrated to Git LFS. The
existing attempt, metrics, and campaign-journal record must not be modified or
recomputed. Slot 1 is used only to verify the new independent backup workflow;
that operation is not a new formal attempt.

## Storage rule effective for slots 2--360

The archive root must be explicitly supplied through
`E3_V4_RAW_ARCHIVE_ROOT` or the utility's explicit `--archive-root` option. It
must be outside the Git repository and must not silently default to `/tmp`.
For each completed and already journaled attempt, the utility copies the full
`raw/rosbag` tree to:

```text
<archive-root>/slot_<six-digit-position>__<trial-id>/rosbag/
```

Every source and archive file is independently measured by byte size and
SHA-256. Archive verification passes only when every pair is equal. The source
raw bag remains in its formal attempt directory and the verified archive copy
also remains. Neither copy is deleted by the utility.

The attempt directory receives a compact `raw_archive_inventory.json` without
modifying `attempt.json`. A separate append-only
`results/formal_v4/raw_archive_ledger.jsonl` records the inventory SHA-256 and
canonical raw-payload SHA-256. The ledger uses an exclusive lock and fsync; it
does not control scientific campaign order and does not replace or change
`campaign_journal.jsonl`.

The narrow E3 results ignore rules cover only future
`formal_v4/attempts/*/raw/rosbag/*.db3` and `*.mcap` binary payloads. They do not
ignore attempt or metric artifacts, contexts, journals, inventories, rosbag
metadata, command validation, runtime provenance, stage/interaction evidence,
or logs. Slot 1 remains tracked despite the new matching rule.

## Required post-attempt sequence

For each future registered slot:

1. Execute the exact registered trial and create immutable `attempt.json`.
2. Compute formal metrics and append that attempt to the campaign journal.
3. Retain the complete source rosbag locally.
4. Run the post-attempt archive utility and require a verified independent copy.
5. Write `raw_archive_inventory.json` and append the raw archive ledger.
6. Commit/push compact evidence, including attempt, metrics, context, campaign
   journal, inventory, archive ledger, metadata, logs, and compact provenance.
7. Do not commit future `.db3` or `.mcap` payloads to ordinary Git.

## Storage failure and retention semantics

Archive failure is not a scientific retry condition. If an attempt has already
executed and been journaled but backup verification fails, the attempt is
classified `RAW_ARCHIVE_PENDING` / `STORAGE_INFRASTRUCTURE_FAILURE`. The
scientific trial is not rerun, its seed is not replaced, and no additional
formal slot is consumed. Campaign progression stops until storage is repaired
from the retained source raw data.

Raw evidence may not be deleted merely because metrics were generated, the
attempt was journaled, evidence was pushed to GitHub, or paper analysis was
completed. Source-raw retention and independent-backup retention are required
throughout this campaign. Any later deletion requires a separate human archival
decision outside this campaign.
