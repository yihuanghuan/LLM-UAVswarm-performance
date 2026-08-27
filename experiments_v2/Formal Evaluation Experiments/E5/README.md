# E5 eight-UAV end-to-end exact-trial runner

This preparation runner is synthetic/contract-validation only. It accepts one
exact sealed E5 ID, owns no global cursor, refuses duplicate retained attempts,
and publishes an immutable artifact before its local hash-chained journal
record. Outputs are `synthetic_validation`, `accepted_formal_result: false`, and
`NOT_FORMAL_RESULT`.

The future execution spec preserves each sealed command byte-for-byte, the
frozen model/prompt/schema/decoding contract, Full Method modes, cold-start
spawn geometry, all-eight PX4 readiness gate, mission timeout, and exact graph
completion semantics. Candidate ground truth is attached only for later audit
and scoring and is never substituted as runtime input.

The synthetic backend makes zero LLM calls, starts no Gazebo/PX4 process, and
creates no scientific endpoint values. LOCAL SYNTHETIC ENUMERATION IS NOT
FORMAL DATA-COLLECTION ORDER.
