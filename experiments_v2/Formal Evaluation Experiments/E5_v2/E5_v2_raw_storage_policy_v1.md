# E5-v2 raw-evidence storage policy v1

Status: frozen before formal slot 1.

Full ROS 2 bag payloads are retained outside ordinary Git at the frozen external
archive root. Git retains compact attempt metadata, metrics, per-file inventories,
cryptographic hashes, storage dispositions, and one immutable ledger record per
consumed slot. Topic selection is fixed by
`E5_v2_formal_execution_config.yaml` and expands only over registered UAV IDs.

## Transaction and dispositions

1. Create a unique compact working directory and external `.pending` raw directory.
2. Run the attempt and finalize/verify the terminal raw disposition.
3. Finalize `attempt.json` and verify all mandatory compact evidence.
4. Exclusively publish the compact attempt directory.
5. Exclusively append the corresponding raw-ledger record.
6. Exclusively append the chained campaign-journal record. Only then is the next
   slot eligible. Orphan artifacts, ledger records, pending directories, or chain
   mismatches stop startup for audited recovery; they never authorize a rerun.

The four allowed raw dispositions are:

- `PRE_RAW_ACQUISITION_INFRASTRUCTURE_FAILURE`: startup/readiness failed before
  raw acquisition began. No bag is expected; the retained attempt consumes the
  slot without retry or replacement.
- `RAW_ARCHIVE_VERIFIED`: acquisition began and the external archive was finalized.
  The ledger records archive reference, every file path/size/SHA-256, total bytes,
  inventory SHA-256, and a second verification pass.
- `RAW_EVIDENCE_LOSS`: acquisition began but required evidence could not be
  verified or preserved. The attempt and slot are retained; continuous metrics
  become `NA` with reasons and the campaign stops after journal consumption.
- `RAW_ARCHIVE_PENDING`: transient only inside the same transaction. It is never
  a terminal journal value and any pending state at startup is a campaign blocker.

Full `.db3`/`.mcap` files are prohibited from ordinary Git. No outcome-dependent
topic selection, deletion, replacement seed, or best-retry selection is allowed.
