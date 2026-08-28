# Runtime Demo Completion Audit

Generated for the E3/E4A/E4B/E5 Formal-equivalent Runtime Demo Execution Phase on 2026-08-28.

## Decision

All 25 required registered runtime paths have at least one infrastructure-PASS cold execution with complete retained raw evidence. Four failed primary attempts remain retained and are paired with successful diagnostic reruns where required. No unresolved infrastructure or provenance defect remains. No scientific parameter, method, metric, timeout, seed, or success criterion was changed.

**Readiness decision: `READY_FOR_ANALYSIS_FREEZE`.**

## Non-formal boundary

Every current-phase demo is labeled `dataset_class=engineering_validation`, `accepted_formal_result=false`, `result_notice=NOT_FORMAL_RESULT`, and `formal_cursor_consumed=false`. The executions used the registered adapter/backend paths and are not formal scientific results. No scientific live scoring or Analysis Freeze decision was performed in this phase.

The current phase contains 25 primary demos and 4 diagnostic reruns, for 29 physical cold starts. The previously completed E2 matrix remains 9/9 PASS and was not rerun. Three superseded E3 development-history instances are retained on disk but explicitly excluded from E3-v3 completion counts.

## Campaign v1 protection

Campaign v1 passed the baseline, post-E3, post-E4, post-E5, and final byte-integrity checks:

- Journal: exactly `000001-attempt.json` and `000002-attempt.json`.
- Accepted formal attempt count: 2.
- Attempt #3: absent.
- Formal cursor: not consumed or moved by any demo.
- Launcher checkout: `8c532288c8b5c47a20da954caad4f717cdc92ddb`.
- Launcher manifest SHA-256: `dd5ed80049b138d4e97c82ce556ed306efbc6e4b2a369f7616be0ff101f332d1`.
- Full retained Campaign v1 file-map SHA-256: `29a6539e4b6b4372e0adc98bc5b45b4a8a40c20c3f23f244460e45695d14ba37`.
- Final status: PASS; Campaign v1 remained byte-identical to the pre-execution snapshot.

## E3 v3

Authoritative identity was validated before execution: activation commit `16de9c7ffd83b67925fc5817f33665727ccbb75f`, protocol SHA-256 `2eea03e2bb33aa1c10c1ae104b965f909690f00c8caee4446291faf2c9893013`, registry SHA-256 `b56344c6cd257e99851523d640d9a89d6def994884877e2303d8fab836e0faf2`. The production numeric environment was Python 3.10.12, NumPy 1.24.4, and SciPy 1.8.0.

- Planned primary demos: 12; completed: 12.
- Primary attempt status: 10 PASS, 2 retained FAIL.
- Diagnostic reruns: 2/2 PASS.
- Registered runtime paths resolved with complete evidence: 12/12; unresolved: none.
- Cold starts: 14, including diagnostics.
- Coverage: four P0/P1 × F0/F1 conditions; four successful 4-UAV A-01 paths; four successful 8-UAV A-02 paths; four successful 8-UAV C-02 paths.
- Disturbance coverage: all four C-02 condition paths; registered wrench topics and driver evidence retained. No-disturbance coverage: all A-01/A-02 paths.
- Discovery: 80 successful per-controller convergence records; 73 converged on observation 1 and 7 on observation 2. No successful controller required observations 3 or 4. The frozen maximum 4 observations at 1-second intervals was unchanged, and every observation was retained.
- Raw evidence: all 12 successful registered paths have all 12 sealed requirements, including clock, t0 commands, 3-D positions, nominal/safe references, IAPF state/deltas, allocator prediction, completion/failure evidence, and wrench evidence.
- Teardown: PASS for all 14 E3 attempts; no persistent orphan process.

Retained failures:

- `E3-V3-P1-F0-A02-S53101-r1`: pre-interaction staging convergence timeout for UAV4/UAV6. A cold diagnostic rerun with unchanged geometry and runtime, `...-r2`, passed. No code or scientific change was made for this transient startup event.
- `E3-V3-P1-F0-C02-S53101-r1`: ROS parameter CLI observation timed out before runtime provenance completed. The failed evidence remains retained; `...-r2` passed after the bounded observation fix described below.

## E4A

- Planned/completed/PASS: 3/3/3.
- Coverage: horizontal smooth, vertical normal, and diagonal-3D aggressive; every frozen motion-style execution profile was physically deployed.
- Physical execution: three 4-UAV cold starts through the formal adapter → backend → physical-trial path.
- Profile/provenance: PASS for all three. Controller node, execution-command endpoint, installed runtime identity, frozen policy, and enabled execution profiles were observed.
- Discovery: 12 controller records; 8 converged on observation 1 and 4 on observation 2.
- Raw evidence: 3/3 complete, with all six sealed tracking/control requirements, rosbag, and logs retained.
- Teardown: 3/3 PASS; unresolved issues: none.

No style gain, timing factor, controller gain, trajectory parameter, or metric definition was changed or tuned.

## E4B

- Planned primary demos: 5; completed: 5.
- Primary attempt status: 4 PASS, 1 retained FAIL; diagnostic rerun: 1/1 PASS.
- Registered runtime paths resolved with complete evidence: 5/5; unresolved: none.
- Cold starts: 6.
- Feasible explicit T: requested 4.0 s, `T_min=2.8844991406148166 s`, `T_exec=4.0 s`; style did not change it.
- Mandatory infeasible explicit T: requested 1.5 s, `T_min=2.8844991406148166 s`, `T_exec=2.8844991406148166 s`; the frozen correction occurred and no rejection was invented.
- Auto-T smooth: `T_exec=3.7498488827992618 s >= T_min`.
- Auto-T aggressive: `T_exec=3.1729490546762986 s >= T_min`; aggressive style did not bypass feasibility.
- Safety-active: successful post-fix execution retained the frozen `d_hard=1.5 m`, `d_plan=1.8 m`, soft-IAPF mapping, and the diagnostic proof that style cannot change hard safety.
- Authority diagnostics: all five successful paths retained all six deterministic authority checks and all 14 sealed raw requirements.
- Discovery: 20 successful controller records; 16 converged on observation 1 and 4 on observation 2.
- Teardown: 6/6 PASS.

The retained `E4B-SAFETY-normal-S54201-r1` failure reached provenance and rosbag capture but published no interaction command because registered integral coordinate objects were rejected by the ROS geometry message setter. `...-r2` passed after equal-valued float normalization. The registered values and all timing/safety semantics are identical.

## E5

- Planned primary demos: 5; completed: 5.
- Primary attempt status: 4 PASS, 1 retained FAIL; diagnostic rerun: 1/1 PASS.
- Mission-graph family paths resolved: simple 1/1, relative/qualitative 1/1, sequential 1/1, parallel 1/1, mixed sequential-parallel 1/1.
- Cold starts: 6, each with 8 PX4 instances and 8 controllers.
- Provider: the real MiniMax provider was invoked for every resolved path. Each retained current path logged one provider request; the frozen formal-command retry setting remained zero. No model, prompt, decoding, or provider setting changed.
- Provenance: all six attempts passed controller/install/policy provenance. The 40 successful-path controller observations converged on observation 1 (36) or observation 2 (4).
- Raw evidence: all five resolved mission-family paths have all 15 sealed requirements. Provider records, parser validation, resolver/allocator trace, dispatch or explicit zero-dispatch method termination, mission completion/termination, per-UAV tracking/IAPF/status, PX4 readiness, logs, and rosbag are retained.
- Scientific outcomes are separate: simple, sequential, and parallel entered and completed dispatch; relative/qualitative and mixed terminated as frozen-method `GeometryError` outcomes during resolution. Those two method failures are valid infrastructure-PASS outcomes and were not tuned away.
- Cleanup: 6/6 PASS; no persistent orphan process.

The retained `E5-REL-QUAL-S55101-r1` failure was an orchestration-classification defect: a frozen resolver rejection was reported as infrastructure failure. `...-r2` passed infrastructure after classification-only repair and retained the method-failure reason, resolution stage, provider record, zero-dispatch fact, and termination evidence.

## Cross-cutting audit

- ROS discovery stability: all resolved controller paths converged within observations 1–2; no discovery-policy widening was needed.
- Controller startup stability: one retained E3 staging-convergence timeout occurred among 29 cold starts; the unchanged diagnostic rerun passed.
- PX4/Gazebo startup: 4-UAV and 8-UAV paths launched successfully across all registered path classes. No persistent Gazebo, PX4, MicroXRCEAgent, controller, or rosbag orphan remained.
- 4-UAV versus 8-UAV: E3 and E4 exercised 4-UAV operation; E3 structural/mixed and all E5 missions exercised 8-UAV operation. Both sizes achieved complete successful path coverage.
- Disturbance infrastructure: every E3 C-02 condition reached the registered disturbance driver and retained wrench evidence; no disturbance semantics changed.
- Rosbag completeness: every resolved live path retained metadata and SQLite bag data with required topics. Failed attempts were also retained without overwrite.
- Artifact persistence: every planned attempt has a matrix record with manifest, log, rosbag, and full-artifact paths, sizes, and SHA-256 hashes.
- MiniMax stability: five resolved family paths reached the real provider with one logged request apiece and no retry-policy change.
- Process cleanup: PASS for all 29 current-phase attempts, including all retained failures; persistent orphan-process incidents: 0.
- Provenance integrity: all resolved paths passed deployed controller, endpoint, execution-profile, installed policy, launch/package, and frozen scientific identity checks.
- Raw-data sufficiency: complete for 12/12 E3, 3/3 E4A, 5/5 E4B, and 5/5 E5 registered paths. Metric extraction and synchronization decisions remain deferred.

## Infrastructure and provenance repairs

1. `fe1f06ea8cd30f2846afa47294169c556ade1926` — `e3_runtime_diagnostics.py`, `test_e3_formal_adapter.py`. Root cause: an individual ROS CLI timeout raised outside the frozen four-observation discovery loop. The repair records timeout return code 124 and continues the same maximum-4, 1-second bounded observations; persistent absence still fails closed. Regression: E3 suite 88/88 PASS. Scientific semantics are unchanged because it only retains and retries provenance observations.
2. `71451469a2cd8cdd375977636beb0b906b6e94e1` — `e4b_formal_backend.py`, `test_e4b_formal_adapter.py`. Root cause: equal-valued registered integer coordinates were incompatible with ROS float message setters. The repair serializes the same numeric coordinates as Python floats. Regression: E4B suite 24/24 PASS. No coordinate, assignment, timing, safety, or controller value changed.
3. `6abaf2b53136d2d5e4d64cde8b9c9acb72ab2485` — `e5_language_driver.py`, `e5_physical_trial.py`, `test_e5_formal_adapter.py`. Root cause: frozen `GeometryError` resolver rejection was conflated with infrastructure failure. The repair separates method outcome from provider/runtime failure and retains stage/reason/termination. Regression: E5 suite 27/27 PASS. Provider invocation, parser, resolver, allocator, mission graph, and dispatch behavior are unchanged.
4. `73f7c0b5f487f9c90bdf479748f8591f7523bc1d` — `runtime_demo.py`, `test_runtime_demo.py`. Root cause: the demo raw-evidence audit required dispatch topics even when an explicitly classified frozen-method rejection correctly terminated before dispatch. The audit now accepts zero dispatch only with retained `method_failure + frozen_method_rejection + failure_stage` evidence. Regression: audit test 1/1 PASS. This changes only audit classification, not production execution.

No repair changed scientific behavior. The first E3 staging timeout required no code change and passed an unchanged cold diagnostic rerun.

## Artifact index

The machine-readable completion record is `formal_equivalent_demo_matrix.json` (SHA-256 `b8a10608017b250148be1806c3aba294a3b9bfbb8a83b5956eca177be0126e8d`). It contains all 38 planned records (9 previously completed E2, 25 current primary, and 4 current diagnostics), per-demo identity and non-formal labels, source/tooling and frozen-policy identity, numeric environment, provenance, discovery convergence, separate infrastructure/scientific outcomes, teardown, and SHA-256 artifact inventories. No planned record is missing.

## Final boundary

This audit establishes runtime and raw-evidence readiness only. It does not score scientific endpoints, freeze analysis decisions, start formal collection, or consume formal campaign authority.

`READY_FOR_ANALYSIS_FREEZE`
