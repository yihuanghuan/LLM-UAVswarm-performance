# E5-v2 raw archive ledger

This directory is the append-only ledger implementation frozen before formal
slot 1. Each consumed position publishes exactly one immutable JSON record named
`000001__ATTEMPT_ID.json`, chained to its predecessor and cross-referenced by the
campaign journal. Files are created with exclusive-create semantics and are
never overwritten.

The initial ledger has zero JSON records. Its deterministic state digest is
`sha256(canonical-json([])) =
4f53cda18c2baa0c0354bb5f9a3ecbe5ed12ab4d8e11ba873c2f11161202b945`.

Full raw bags live in the external archive named by the frozen storage policy;
this Git directory stores only immutable inventory/hash/disposition records.
