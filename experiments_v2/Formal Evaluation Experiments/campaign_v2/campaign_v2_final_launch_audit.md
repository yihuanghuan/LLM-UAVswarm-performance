# Campaign v2 Final Freeze / Preflight Audit

Verdict: `CAMPAIGN_V2_FREEZE_COMPLETE_READY_FOR_FORMAL_LAUNCH`

No Campaign-v2 formal attempt was launched. The formal root remains pristine at `0 retained / 0 journal / next #1`, and the future human trigger is absent.

## Campaign identity

- Campaign: `E2-E5-final-paper-campaign-v2`
- Branch: `formal/campaign-v2-freeze`
- Freeze tooling source commit: `a2e6ccd8cbc7aba8f2244caa704cc605e383503e`
- Manifest SHA-256: `475e5e4cd1234a4dc9f552678aec0387fc8bcce3f2deef468362d6f3c2314488`
- Launch tooling bundle SHA-256: `86901a67a6e676b69e86624c9ccf86c23ea876df27e7442b5d569766451053a4`
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
- Full pinned-adapter non-formal rehearsal: 610/610, exact order, correct routing, journal tail `25ae6e1e20989ee1efb15884df2772286d532a9ccac2e27e6b11f45a93e853d7`.
- Restart checkpoints: 13; crash-consistency, wrong-family protection, and formal/non-formal isolation: PASS.

## Environment and provider

- Python 3.10.12; NumPy 1.24.4; SciPy 1.8.0.
- ROS 2 Humble; `rmw_fastrtps_cpp` 6.2.9; ROS domain 42; Gazebo Classic 11.10.2.
- PX4 `30e763b6780061d70a14894e3e8b06e6a656f9b8`; Gazebo submodule `da7206e057703cc645770f02437013358b71e1c0`.
- Installed controller, interface, launch, policy, simulator overlays, prompt, schema, and model hashes: PASS.
- MiniMax `MiniMax-M2.7-highspeed`: 2/2 independent non-formal health probes PASS. The provider exposes no campaign-total quota endpoint; no quota value is invented.

## Regression and protection

- 222/222 tests PASS across Campaign v2, E2, E3, E4A, E4B, E5, and analysis fixtures.
- Campaign v1: exactly #1/#2, no #3, launcher manifest and full file-map hashes unchanged.
- Campaign v2 formal root: 0 retained, 0 journal records, 0 accepted results, next position #1.
- Unresolved blockers: none.

The authorization artifact says `authorized_for_future_human-triggered_formal_launch`; it does not claim launch has started. A separate untracked human trigger and matching runtime SHA-256 are still required.
