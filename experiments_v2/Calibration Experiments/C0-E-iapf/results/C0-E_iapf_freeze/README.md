# C0-E IAPF calibration freeze

Status: **PASS / frozen**. The selected C0-E policy is integrated as
`paper-current-v10-c0-e-frozen` after the locked 20-run confirmation and all
three deferred C0-D integration smokes passed.

## Frozen result

- Threshold/hysteresis: `enter_base=1.60 m`, `exit_base=1.70 m` (T1).
- Repulsion: `base=1.00`, `margin=0.25` (C_M025).
- IAPF filter: `alpha=0.20` (D_A020).
- Inherited IAPF gains, epsilon, modulation limits, and escape policy remain
  unchanged; see `frozen_iapf_policy.yaml`.
- Hard clamps are deterministic mapping-coverage bounds over `s in [1,2]`,
  not a separate tuning grid.

The immutable pre-confirmation policy is `locked_candidate_policy.yaml`; its
SHA-256 is
`fbd2747711ffd05c70541c69af17818030f74f6cbdbd97f3349afa66310d62e7`.
The candidate lock SHA-256 is
`bbd161ef7b96b52ecabe9f40b830c3d9a0967833c59a605f2a3075163a176e09`.

## Runtime protocol

All scored trials use `location_allocate.candidate_dispatch`,
`UAVFormationNode/PaperMissionRuntime`, and
`control_mode=ladrc_acceleration`. The C0-C experimental prewarm helper is not
an operational dependency.

The deterministic scene definitions are in `scene_definitions.yaml`:

- S1: four-UAV head-on closing geometry.
- S2: four-UAV offset perpendicular crossing.
- S3: four-UAV three-dimensional crossing with vertical relative motion.
- S4: dense eight-UAV, four-pair interaction.
- S5: four nearby UAVs moving apart to test nonintrusiveness.

Staging motion is excluded. Scoring begins at the first interaction execution
command. For pair `(i,j)`, the recorded closing metric is
`dot(p_i-p_j, v_i-v_j)`: negative means closing and positive means separating.
The semantic sanity screen passed one valid, initially safe runtime trial for
each of S1--S5 before calibration evidence was scored.

## Artifact index

- `calibration_plan.csv`: preregistered stage plan.
- `scene_sanity_results.csv`: five-scene semantic sanity gate.
- `threshold_screen.csv`: valid Stage B runtime evidence (29 trials).
- `repulsion_screen.csv`: valid Stage C runtime evidence (18 trials).
- `filter_screen.csv`: valid Stage D runtime evidence (18 trials).
- `screening_excluded_attempts.csv`: two retained incomplete attempts excluded
  from ranking.
- `candidate_lock.yaml`: immutable pre-confirmation lock.
- `final_validation.csv`: 20 locked confirmation trials.
- `integrated_runtime_smokes.csv`: the three final deferred C0-D smokes using
  the locked C0-E policy.
- `frozen_iapf_policy.yaml`: authoritative C0-E component freeze.
- `C0-E_freeze_report.md`: selection and acceptance report.
- `manifest.yaml`: hashes, provenance, exact candidate/scene/seed protocol,
  runtime contract, and final results.

Raw trial directories are retained locally and never overwritten. Committed
per-trial manifests and derived metrics preserve reproducibility without
adding large rosbag/log payloads.

## Historical evidence classification

The pre-semantic `runtime_raw/B_T1_S1_s1_cold4_1787389631` run is classified
only as a production-harness smoke and was not used for ranking. Earlier v9
eight-UAV smokes remain infrastructure regression history; they are not the
three final C0-D deferred smokes. Historical freshness failures likewise do
not rank IAPF candidates.

The confirmation manifests truthfully retain the runner's recorded label
`c0e-screen-20260822`. The preregistered confirmation label was
`c0e-confirm-20260822`; the label is not consumed by any RNG or scene/runtime
logic, so the deterministic scene specifications, two distinct cold starts,
and resulting evidence are unaffected. This provenance discrepancy is
recorded rather than retroactively rewriting raw manifests.
