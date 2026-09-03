# E5-v2 formal campaign blocker audit

Status: **BLOCKED — WAITING FOR HUMAN REVIEW**.

The exact-order campaign stopped during the durable transaction for slot 1,
`E5V2-B-S2-N12-R1` (seed 5202036, N=12, UNDER_SPECIFIED). Slot 2 was not
started. No scientific result direction was inspected or used in the stop
decision.

## Exact blocker

The physical attempt passed all-UAV readiness, began raw acquisition, and the
real semantic worker terminated. During frozen metric extraction, the launch
process could not import `rosbag2_py`. The launch command had set `PYTHONPATH`
to the E5-v2 tooling directory only, masking the ambient ROS 2 Python module
paths. The subsequent frozen evidence-loss handling also received
`PermissionError` while trying to rename the already read-only verified archive.

This is a formal execution environment and unresolved-transaction blocker. It
is not production-method drift and is not a scientific outcome-based stop.

## Authoritative campaign state

- Registered slots: 60
- Last journal-consumed slot: 0
- Journal records: 0
- Raw-ledger records: 0
- Published compact attempt directories: 0
- Unresolved formal transactions: 1
- Formal scientific attempts physically executed: 1 (slot 1 only)
- Accepted formal results published: 0
- Replacement/rerun attempts: 0

The journal therefore still derives slot 1 as its next entry, but slot 1 was
physically executed and must not be rerun. Automatic resumption is not
permissible. Human-approved audited recovery must resolve the retained slot-1
transaction without executing it again before any later slot can become
eligible.

## Evidence and cleanup

The external slot-1 rosbag remains preserved and read-only at
`/home/yihuang/learning/LLM_swarm_ws/e5_v2_formal_raw_archive_v1/attempts/000001__E5V2-B-S2-N12-R1`.
`ros2 bag info` independently read 110,197 messages over 25.149640563 seconds.
Its two-file inventory totals 45,883,177 bytes and has canonical inventory
SHA-256 `ff97ad4ef665754e23fc90e06803844580bcfaacd2ae89034d3ecaf8bc56fbda`.

The retained transaction contains 30 files totaling 633,319 bytes, with
canonical inventory SHA-256
`2c0c1d9d961ccc63ffee0776f4b36c9ec0b111c9cb6f877b2e28dcc06bbc9152`.
Raw and transaction evidence are preserved, but formal compact packaging and
journal/ledger publication remain unresolved. No `RAW_EVIDENCE_LOSS` ledger
record was published and no `.pending` raw entry remains.

All scoped PX4, controller, Gazebo, and MicroXRCEAgent process counts are zero.
Scientific protocol changes, production method changes, and old E5-v1 changes
are all zero.
