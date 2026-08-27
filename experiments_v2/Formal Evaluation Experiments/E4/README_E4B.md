# E4B authority-preservation exact-trial runner

Synthetic/contract validation only. The exact-trial API owns no global cursor,
rejects nonregistered IDs and duplicate retained attempts, and publishes its
artifact before the local hash-chained journal record. All outputs are labeled
`synthetic_validation`, `accepted_formal_result: false`, and
`NOT_FORMAL_RESULT`.

All six sealed unauthorized-override predicates have stable machine-readable
IDs and raw evidence requirements. Deterministic timing policy checks use the
frozen production implementation and `1e-9` comparison tolerance. The
SAFETY-ACTIVE physical registered trial is never executed here; only its exact
launch modes, authority predicates, and event-extraction schema are validated.
LOCAL SYNTHETIC ENUMERATION IS NOT FORMAL DATA-COLLECTION ORDER.
