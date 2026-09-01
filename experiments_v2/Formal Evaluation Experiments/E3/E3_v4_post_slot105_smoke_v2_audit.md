# E3-v4 Post-Slot-105 Infrastructure Smoke v2 Audit

## Result

`E3-v4 POST-SLOT105 INFRASTRUCTURE REVIEW: PASS`.

The historical v1 smoke remains `FAIL`, while its retained core readiness
evidence is adjudicated `PASS`. The new prospectively frozen v2 smoke ran
exactly once and passed all 20 authoritative core checks. No formal state
changed, slot 105 was not rerun, and slot 106 was not started.

## V1 adjudication

- Historical result SHA-256:
  `de9dcaf787dd7b6645d2cd0471b0b38104ff35097a52a6485b31b634a8fbd7e7`.
- Historical recorded status: `FAIL` (unchanged).
- Core readiness assessment: `PASS`.
- Topic-list assessment:
  `NON_AUTHORITATIVE_SINGLE_SHOT_DDS_DISCOVERY`.
- Gazebo model-query assessment: `INVALID_CLI_ASSAY`.
- Adjudication JSON SHA-256:
  `6db191a77dd2674f741557c38662ae472991ae7fd4ce561db485bcd7081fa611`.

The single-shot DDS list was incomplete relative to the same run's eight
successful readiness observations. The installed Gazebo Classic CLI has no
`gz model --list` option, so its `Invalid arguments` output was not a valid
negative model-count observation. This adjudication does not rewrite or
reinterpret the historical overall status in place.

## Prospectively frozen v2

- Preregistration commit:
  `c7d3305b90149f55cf11115b2ff0672d9f08ccfa`.
- Protocol SHA-256:
  `2291635f1a6dabd09266f432b0749d5855f683c428d03dca43d7be180496a511`.
- Engineering-only tool SHA-256:
  `da1c78882f43fa196ebb74e6258d03fa84b5e35a9ad9941835e0c1a715e0e921`.
- Seed namespace: `E3-v4-post-slot105-smoke-v2-seed`.
- Namespace SHA-256:
  `80de3bd4797d9dd98c9a41db4329f3037f4f9d0b8c34fefcd3481cfe85b7339b`.
- Seed derivation: first eight SHA-256 hex digits interpreted as an integer,
  modulo 9,000,000, plus 1,000,000.
- Engineering seed: `3047956`; no collision with the checked formal,
  qualification, or holdout registries.
- Runs: exactly one; no retry.

The v2 PASS rule was frozen before execution: `PASS` if and only if all named
core checks pass. DDS discovery and valid named Gazebo model-info queries were
diagnostic-only and could not affect status.

## V2 evidence

- Overall status: `PASS`.
- Result SHA-256:
  `4fd2e51e35b2a216fcc9efaefbd5229586545fc00aa826479913be1b9f6f679f`.
- Dataset class: `engineering_validation`.
- Accepted formal result / formal authorization: false / false.
- Formal campaign position / registered trial ID: null / null.
- Scientific scene / interaction executed: false / false.
- Rosbag acquisition started: false.
- Core checks: 20/20 true.
- Frozen readiness utility: success, `ready=true`, exactly 8 UAVs.
- UAVs 1--8: present, age no greater than the existing 0.5-second freshness
  gate, ready, armed, offboard, not in failsafe, finite altitude.
- Maximum reported readiness age: `0.019945359003031626 s`.
- Live process snapshot: 1 gzserver, at least 8 PX4 matches, 8 controllers,
  and 1 MicroXRCEAgent.
- Cleanup: pass; no residual simulator/controller/agent processes.

Diagnostic-only observations also succeeded:

- five bounded DDS snapshots contained 436, 444, 444, 444, and 444 topics;
  their union contained all eight expected VehicleOdometry topic names;
- eight supported read-only commands of the form
  `gz model --model-name iris_<id> --info` succeeded.

These diagnostics are retained but were not used to determine v2 status.

## Formal-state invariance

- Journal SHA-256 before/after:
  `f6a619ea20a9e1bc8c664db2a7c42aeb723f684ae7de1ad2d652d761ca10f6dd`
  / same.
- Raw-storage ledger SHA-256 before/after:
  `7233afd23c35abb69e3245111189499c729a138b62e86964baa730dd0d1309f5`
  / same.
- Formal attempt directories before/after: 105 / 105.
- Formal context entries before/after: 105 / 105.
- Journal records / consumed slots: 105 / 105.
- Success / infrastructure failure: 98 / 7.
- Slot 105 rerun count: 0.
- New formal attempts: 0.
- Next campaign position: 106.
- Next trial: `E3-A-02__P1_F0__S876320`.
- Slot 106 started: false.

Frozen SHA-256 identities remain:

- sealed registry:
  `2b3dccc2ad27cf317029c2b7b014bca3a8b28fc8c0a196fd4c2e5abe0be9d4b7`;
- formal seeds:
  `665600871ad3fb6cff324ab3ef9144b0d84b42acc19505283679b6ae01586841`;
- formal order:
  `60ee30a7100b53c4964e3f9f086ff3d137fb41282eebc4439760bf17f033b39b`;
- analysis contract:
  `987ff29aa814a0dc5e9e64081fcf0fc79ceb3086b21a0e945bfe2f8252185c58`;
- production policy:
  `6b47d27f4253d7311e79ea51f6dd1cf0d0182e6df24374a94abae0aa6a135858`;
- immutable E3-v3 registry:
  `b56344c6cd257e99851523d640d9a89d6def994884877e2303d8fab836e0faf2`;
- activated formal execution tooling bundle:
  `78cb5dbc374983c64752433fa1c62c4990903b03b5b813f0248f13105eb074bf`.

Formal scientific protocol changes, production changes, formal execution
tooling changes, and new formal attempts are all zero.

```text
E3-v4 POST-SLOT105 INFRASTRUCTURE REVIEW: PASS
SLOT 105: INFRASTRUCTURE_FAILURE RETAINED
V1 SMOKE HISTORICAL STATUS: FAIL
V1 CORE READINESS: PASS
V1 AUXILIARY INTROSPECTION: INVALID / NON-AUTHORITATIVE
V2 SMOKE: PASS
FORMAL SCIENTIFIC PROTOCOL CHANGES: 0
PRODUCTION CHANGES: 0
FORMAL EXECUTION TOOLING CHANGES: 0
SLOT 105 RERUN: false
CAMPAIGN JOURNAL RECORDS: 105
CONSUMED SLOTS: 105
NEXT CAMPAIGN POSITION: 106
NEXT TRIAL: E3-A-02__P1_F0__S876320
SLOT 106 NOT STARTED
```
