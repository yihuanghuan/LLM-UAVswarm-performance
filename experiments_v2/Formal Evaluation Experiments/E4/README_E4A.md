# E4A behavioral isolation exact-trial runner

This runner is synthetic/contract-validation only. It accepts one exact sealed
E4A ID and has no global-order or “next” authority. It writes an immutable mock
artifact before appending its local hash-chained journal. All outputs state
`synthetic_validation`, `accepted_formal_result: false`, and
`NOT_FORMAL_RESULT`.

For every scenario/seed, initial state, assigned targets, explicit requested T,
T_exec requirement, safety, seed, and the frozen Minimum-Jerk nominal reference
are identical across styles. Only the registered style and frozen profile
fields derived from it differ. The backend never launches scientific runtime
or generates endpoint values. LOCAL SYNTHETIC ENUMERATION IS NOT FORMAL
DATA-COLLECTION ORDER.
