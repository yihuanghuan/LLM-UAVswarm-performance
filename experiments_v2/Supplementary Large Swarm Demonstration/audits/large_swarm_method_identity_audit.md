# Large-swarm method identity audit

Result: **PASS**.

- Frozen production tag: `paper-final-sim-v3`.
- Frozen production commit: `6cf402debf23851b1eff3edc6f3ab49eae7127c4`.
- Production policy SHA-256: `6b47d27f4253d7311e79ea51f6dd1cf0d0182e6df24374a94abae0aa6a135858`.
- E5-v2 completed formal source remains `558def6238826460cb3f9323af445e8c299fb610`.
- E5-v2 final analysis remote remains `bc760d5795ff87c62df6e86875d9a906cc449e2d`.
- Production method changes across `lfs_policy`, `location_allocate`,
  `minisnap_LADRC`, `schemas`, and `uav_swarm_interfaces`: **0**.
- E5-v2 formal source/result changes: **0**.
- E5-v2 analysis changes: **0**.

The supplementary launcher calls the unchanged installed PX4 binary, Gazebo
world/plugins, LADRC controller executable, control mode, IAPF modes, policy,
readiness predicate, and topic mappings. Its only method-external differences
are dynamic N enumeration and explicit global offsets from the prospectively
frozen parking layout.

Two old N=8 infrastructure assumptions were not propagated: PX4's stock
multi-instance shell defaults to a `y=3*ID` line, and the production controller
launch computes the corresponding line offset. The supplementary launcher
supplies the same deterministic grid position to Gazebo and to the unchanged
controller's ENU-offset parameter. This is classified as supplementary initial
spawn/layout infrastructure, not a Candidate, resolver, geometry, allocator,
safety, Minimum-Jerk, LADRC, IAPF, or scheduling change.

No N>16 method-semantic change was required. The observed N>=24 failures arose
at infrastructure readiness while all requested PX4/controller processes were
present; no method parameter was changed in response.
