# E3-v4 Raw-Storage Amendment v2 Audit

## Outcome

The storage-governance clarification passes. Slot 105 remains the single
consumed formal attempt at campaign position 105 and remains classified
scientifically as `infrastructure_failure`. Its storage disposition is
`PRE_RAW_ACQUISITION_INFRASTRUCTURE_FAILURE`, not `RAW_EVIDENCE_LOSS` and not
`RAW_ARCHIVE_PENDING`.

The one authorized non-formal post-slot-105 smoke produced 8/8 ready vehicles
but its overall recorded status is `FAIL` because two auxiliary discovery
probes failed. In accordance with the human stop rule, the smoke was not
repeated and slot 106 was not started. Campaign resumption therefore remains
stopped for human review.

## Baseline and governance

- Baseline HEAD: `093a66f27cbb1936b10cff6b61c716ffaa0cd1b9`.
- Storage-v2 governance commit:
  `a5d82745e29e772393437362c19e1c69b7993546`.
- Storage policy v1 SHA-256:
  `71557c662d12d8f6fe840b2f429f6c735ac4bde27c1ecd367ceac2ab8479f3ad`.
- Storage policy v2 SHA-256:
  `5a0ffedcd1088f0516f669b15ec3d613c857b1a9304917b2f4db728fce18f2b9`.

## Slot 105 evidence and disposition

- Trial: `E3-C-02__P1_F0__S730940`.
- Attempt SHA-256:
  `8cc8bdb81cf33a2f0b635078fa3d80485dadbbca0078c10d58142471d540690c`.
- Proximate failure: `RuntimeError: all-UAV readiness failed`.
- Root-cause class:
  `SIMULATION_STARTUP_INFRASTRUCTURE_FAILURE`.
- Failure stage: `PRE_FORMAL_INTERACTION_READINESS`.
- Readiness passed: false.
- Scientific interaction/scoring started: false / false.
- Rosbag acquisition started: false.
- Rosbag source exists / was expected: false / false.
- Raw evidence loss: false.
- Storage disposition:
  `PRE_RAW_ACQUISITION_INFRASTRUCTURE_FAILURE`.
- Disposition file SHA-256:
  `e57b3c3449db9b229c822d8072376c6e2b6cf32a5a29e286d3cd166226c06b31`.
- Slot 105 reruns: 0.

The frozen orchestrator starts PX4/Gazebo and the controllers, runs the
all-UAV readiness gate, and raises immediately on readiness failure. Rosbag
startup appears only after that gate succeeds. The retained slot evidence
therefore establishes that no source bag was created or expected for slot 105.
No archive inventory or fake source/archive hash was generated.

The compact evidence SHA-256 values are preserved in the machine-readable
audit and in `raw_storage_disposition.json`.

## Storage ledger coverage

- Ledger SHA-256:
  `7233afd23c35abb69e3245111189499c729a138b62e86964baa730dd0d1309f5`.
- Storage disposition records: 105.
- `RAW_ARCHIVE_VERIFIED`: 104.
- `PRE_RAW_ACQUISITION_INFRASTRUCTURE_FAILURE`: 1.

The new slot-105 line is a disposition record, not an archive-verification
record. It contains no fabricated source or archive hash.

## One non-formal infrastructure smoke

- ID: `E3-V4-INFRASTRUCTURE-SMOKE-AFTER-SLOT105-v1`.
- Engineering-only seed: `8105105`; it is absent from the checked formal and
  qualification seed registries.
- Dataset class: `engineering_validation`.
- Accepted formal result: false.
- Formal campaign position/trial ID: null / null.
- Output:
  `results/formal_v4/infrastructure_smoke_after_slot105/`.
- Result SHA-256:
  `de9dcaf787dd7b6645d2cd0471b0b38104ff35097a52a6485b31b634a8fbd7e7`.
- Recorded overall status: `FAIL`.

The required live infrastructure observations were largely positive:

- readiness process returned zero and reported `ready=true`;
- `uav_count=8`;
- all 8 diagnostics reported `system_ready=true` and finite odometry-derived
  altitude;
- at least 8 PX4 and 8 controller processes were live;
- Gazebo master and MicroXRCEAgent were live.

Two auxiliary probes failed:

- one `ros2 topic list` snapshot did not enumerate all eight externally named
  VehicleOdometry topics, despite the readiness diagnostics receiving valid
  per-UAV odometry;
- `gz model --list` returned `Invalid arguments`, so it produced no model
  inventory.

These observations do not reproduce slot 105's 8/8 readiness failure, but the
smoke utility's fail-closed result remains `FAIL`. It was not rerun or edited.
All spawned processes were cleaned up, and the journal, storage ledger, formal
attempt directories, and formal context directories remained unchanged by the
smoke.

## Frozen identities (SHA-256)

- Sealed registry:
  `2b3dccc2ad27cf317029c2b7b014bca3a8b28fc8c0a196fd4c2e5abe0be9d4b7`.
- Formal seed registry:
  `665600871ad3fb6cff324ab3ef9144b0d84b42acc19505283679b6ae01586841`.
- Formal order:
  `60ee30a7100b53c4964e3f9f086ff3d137fb41282eebc4439760bf17f033b39b`.
- Analysis contract:
  `987ff29aa814a0dc5e9e64081fcf0fc79ceb3086b21a0e945bfe2f8252185c58`.
- Production policy:
  `6b47d27f4253d7311e79ea51f6dd1cf0d0182e6df24374a94abae0aa6a135858`.
- Immutable E3-v3 registry:
  `b56344c6cd257e99851523d640d9a89d6def994884877e2303d8fab836e0faf2`.
- Activated formal execution tooling bundle:
  `78cb5dbc374983c64752433fa1c62c4990903b03b5b813f0248f13105eb074bf`.

All match their frozen values. Candidate-baseline-to-current changes are
confined to post-attempt E3 storage governance and evidence. Scientific
protocol changes, production changes, formal execution-tooling changes, and
new formal attempts are all zero.

## Campaign cursor

- Campaign journal SHA-256:
  `f6a619ea20a9e1bc8c664db2a7c42aeb723f684ae7de1ad2d652d761ca10f6dd`.
- Registered slots: 360.
- Journal records / consumed slots: 105 / 105.
- Success / infrastructure failure: 98 / 7.
- Next position: 106.
- Next trial: `E3-A-02__P1_F0__S876320`.
- Slot 106 started: false.

Final governance state:

```text
E3-v4 RAW STORAGE AMENDMENT V2: PASS
SLOT 105: INFRASTRUCTURE_FAILURE RETAINED
SLOT 105 STORAGE DISPOSITION: PRE_RAW_ACQUISITION_INFRASTRUCTURE_FAILURE
RAW BAG EXPECTED: false
RAW EVIDENCE LOSS: false
SLOT 105 RERUN: false
POST-SLOT105 INFRASTRUCTURE SMOKE: FAIL
CAMPAIGN PROGRESSION: STOPPED FOR HUMAN REVIEW
SCIENTIFIC PROTOCOL CHANGES: 0
FORMAL EXECUTION TOOLING CHANGES: 0
CAMPAIGN JOURNAL RECORDS: 105
CONSUMED SLOTS: 105
NEXT CAMPAIGN POSITION: 106
NEXT TRIAL: E3-A-02__P1_F0__S876320
SLOT 106 NOT STARTED
```
