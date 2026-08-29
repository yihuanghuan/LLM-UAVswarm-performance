# Campaign v2 Formal Resume Repair / Final Launch Audit

Verdict: `CAMPAIGN_V2_FORMAL_RESUME_FIXED_READY_FOR_HUMAN_LAUNCH`

No Campaign-v2 formal attempt was launched. The formal root remains pristine at `0 retained / 0 journal / next #1`, and the future human trigger is absent.

The audit at `085b4b4edda160a005f6217767935ce0f7d01809` is superseded. Its coordinator required a pristine formal root on every process start, preventing #1 -> restart -> #2. This was repaired before any Campaign-v2 formal result existed. Classification: `campaign_infrastructure_only`; scientific semantics changed: `false`.

## Campaign identity

- Campaign: `E2-E5-final-paper-campaign-v2`
- Branch: `formal/campaign-v2-freeze`
- Freeze tooling source commit: `83757ec5a87993960d3e5ad6823cede02460e9f2`
- Manifest SHA-256: `475e5e4cd1234a4dc9f552678aec0387fc8bcce3f2deef468362d6f3c2314488`
- Launch tooling bundle SHA-256: `1e33c386a56565ee832e2525e493ad01794844b7aa7eb1e3539aee59ae228325`
- Baseline: `paper-final-sim-v3` at `6cf402debf23851b1eff3edc6f3ab49eae7127c4`
- Policy SHA-256: `6b47d27f4253d7311e79ea51f6dd1cf0d0182e6df24374a94abae0aa6a135858`

## Scientific and analysis pins

- E2: `c361d21360252b4b6d24a615c421825b40ae1c59`; bundle `72ad8fbdec4e4962d1d5b353077e1f5114f8e83faa150f375f8f4e1e250e71f1`
- E3 v3: `fe1f06ea8cd30f2846afa47294169c556ade1926`; bundle `6c8fc316e140e7d4c31dd26d07850af217a53e65060c1fa10b16ea35bdfe78af`; protocol `2eea03e2bb33aa1c10c1ae104b965f909690f00c8caee4446291faf2c9893013`
- E4A: `7ca02a1bc079f1f36d4bb9a4f29344fcae54a059`; bundle `fcbc0188b7f637c9bf9d49d4297b945013257deb53b2c1512e33a078a72eb1ac`
- E4B: `71451469a2cd8cdd375977636beb0b906b6e94e1`; bundle `7b47c744a943a680d05468a4c76e0957f9979fb0d5ef1d5b8df3a94240fabc93`
- E5: `6abaf2b53136d2d5e4d64cde8b9c9acb72ab2485`; bundle `b876317fb431c1d63adea2ae150ebc3bdcb786d3a7f93700bc142d39b6197921`
- Analysis semantics: `f19440262a96d784177e5367e8de2a2ec50b7b6ca5b229d4a6d09816408c0db3`
- Formal-analysis-v1 bundle: `9210245b12a108447cf03715ca6fd90e6ad3bf85fcab7a61e4dcfc6e5ac545b4` (independent recomputation PASS)

All source commits are reachable from the named remote authoritative branches. Evidence-only later commits are not execution dependencies.

## Population and rehearsal

- E2 120; E3 360; E4A 45; E4B 60; E5 25; total 610.
- Original global-order SHA-256: `db28bf8d734e1f206987519e91ff27c67b2d9ab2971aeb68c4e13735762f1dce`.
- Exact membership and analysis-schema compatibility: PASS.
- Full pinned-adapter non-formal rehearsal: 610/610, exact order, correct routing, journal tail `4917df8af35c99073140a08b0ee8839c4223d33797abad0464b7e503fe74679f`.
- Rehearsal-mode restart checkpoints: 13; 610/610 PASS.
- Formal-mode restart/resume independently validated at retained 0, 1, 2, method failure, infrastructure failure, mixed-family boundary, 609, and complete 610.
- Ten formal crash/orphan/hash/temporary/foreign-state fixtures fail closed; wrong-family protection and formal/non-formal isolation: PASS.
- A campaign-scoped human trigger plus matching token authorizes a valid resumed coordinator; the dual lock remains mandatory.

## Environment and provider

- Python 3.10.12; NumPy 1.24.4; SciPy 1.8.0.
- ROS 2 Humble; `rmw_fastrtps_cpp` 6.2.9; ROS domain 42; Gazebo Classic 11.10.2.
- PX4 `30e763b6780061d70a14894e3e8b06e6a656f9b8`; Gazebo submodule `da7206e057703cc645770f02437013358b71e1c0`.
- Installed controller, interface, launch, policy, simulator overlays, prompt, schema, and model hashes: PASS.
- MiniMax `MiniMax-M2.7-highspeed`: 2/2 independent non-formal health probes PASS. The provider exposes no campaign-total quota endpoint; no quota value is invented.

## Regression and protection

- 245/245 tests PASS across Campaign v2, E2, E3, E4A, E4B, E5, and analysis fixtures.
- Campaign v1: exactly #1/#2, no #3, launcher manifest and full file-map hashes unchanged.
- Campaign v2 formal root: 0 retained, 0 journal records, 0 accepted results, next position #1.
- Unresolved blockers: none.

The authorization artifact says `authorized_for_future_human-triggered_formal_launch`; it does not claim launch has started. A separate untracked human trigger and matching runtime SHA-256 are still required. The preferred trigger field is `authorize_campaign_v2`; the legacy prospective `authorize_formal_attempt_1` spelling remains backwards-auditable as campaign-start authorization across ordinary restarts.
