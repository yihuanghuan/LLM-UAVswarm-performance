# E3-v4 preflight and provenance audit

Status: `PASS — SCENARIO/PREFLIGHT READY; FORMAL EXECUTION NOT STARTED`

The standalone candidate registry contains six qualified/compatible scenes,
15 new confirmatory paired seeds, four P/F cells, and exactly 360 unique trial
IDs. Static compilation produces 90 complete four-cell scenario×seed blocks.
Every scenario×condition has 15 attempts. The old 610-attempt Campaign-v2
order and cursor are not modified.

The standalone journal contract is append-only and position-checked. It
requires one immutable artifact hash for the exact next trial, retains failed
attempts as consumed slots, and forbids replacement attempts/seeds and manual
cursor edits. No E3-v4 formal journal exists yet.

The exact-spec audit confirms the registered planning manipulation in every
cell: A and C have P0 structural conflicts and P1 removes them; B is nominally
safe under both P0 and P1. Feedback mode does not change allocation/prediction.
A has no execution deviation, B-01/C-01 use command delay, and B-02/C-02 use
temporary reference deviation.

The formal adapter is present and statically validated, but the candidate
registry deliberately has status `CANDIDATE_FOR_HUMAN_REVIEW`. A formal launch
request is therefore rejected with `formal launch blocked pending human
registry activation`. This audit performed no Gazebo run and created no trial
attempt.

All paths changed since redesign start `cda52d13...` are within the E3
experiment subtree. The frozen production policy and immutable E3-v3 registry
hashes match before/after.

```text
production_baseline = 6cf402debf23851b1eff3edc6f3ab49eae7127c4
policy_sha256 = 6b47d27f4253d7311e79ea51f6dd1cf0d0182e6df24374a94abae0aa6a135858
E3_v3_registry_sha256 = b56344c6cd257e99851523d640d9a89d6def994884877e2303d8fab836e0faf2
E3_v4_registry_sha256 = 80ddbb8701f1c7feb84ae64a7985f233742f522c1204131ab4dd6d09960bd79b
formal_seed_registry_sha256 = 665600871ad3fb6cff324ab3ef9144b0d84b42acc19505283679b6ae01586841
360_order_sha256 = 60ee30a7100b53c4964e3f9f086ff3d137fb41282eebc4439760bf17f033b39b
analysis_contract_sha256 = 987ff29aa814a0dc5e9e64081fcf0fc79ceb3086b21a0e945bfe2f8252185c58
F1_qualification_attempt_count = 0
formal_attempt_count = 0
```
