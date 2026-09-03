# E5-v2 formal infrastructure amendment v1

## Timing and boundary

This amendment is frozen after slot 1 was physically executed once, before any
slot-1 accepted-result publication, and before slot 2. At amendment time there
was one physical attempt, zero accepted results, and zero journal records.

Scientific payload, registry, seeds, formal order, analysis contract, production
policy/method, and old E5-v1 are unchanged. The `J_hard` action is
`endpoint_availability_adjudication_only`, not a new endpoint definition.

## Infrastructure corrections

The orchestrator process lacked ROS 2 Humble Python-module visibility even
though its physical subprocess environment had been sourced. The new formal
wrapper sources `/opt/ros/humble/setup.bash` and the frozen install
`setup.bash`, preserves those Python paths, adds the E5-v2 tooling paths, and
then invokes the same pinned semantic Python interpreter. No package is
installed and neither ROS distribution nor scientific dependency versions are
changed. This is `formal_environment_only`.

The v1 storage path also treated a metric-reader exception after successful raw
publication as evidence loss and attempted to move the read-only archive. The
amended path independently reverifies the published inventory. If it remains
intact, the archive stays in place and a recoverable transaction blocker is
raised. `RAW_EVIDENCE_LOSS` is reserved for missing, corrupt, or unverifiable
required evidence. This is `raw_storage_error_handling_only`.

## Other allowed tooling changes

- The metric extractor always emits adjudicated `J_hard` NA, classified as
  `unavailable_endpoint_enforcement`. Mission success continues to use the
  independently frozen `actual d_min >= 1.50 m` rule.
- A dedicated recovery-only program verifies the exact slot-1 transaction/raw
  identities, reads preserved evidence, and performs exactly-once compact,
  ledger, and journal publication. It contains no physical backend path. This
  is `transaction_recovery_only`.
- Future authorization requires the exact one-slot journal prefix, slot-1 ID and
  seed, next position 2, no slot-1 rerun, and continuous exact order. This is
  `resume_gate_only`; no actual resume authorization is created here.

No change falls outside `formal_environment_only`,
`transaction_recovery_only`, `raw_storage_error_handling_only`,
`unavailable_endpoint_enforcement`, or `resume_gate_only`.
