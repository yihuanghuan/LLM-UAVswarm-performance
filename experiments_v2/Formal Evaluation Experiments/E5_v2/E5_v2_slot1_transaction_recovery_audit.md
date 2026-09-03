# E5-v2 slot-1 transaction recovery audit

Result: **PASS**

Human `J_hard` availability adjudication and the remaining-endpoint mapping
audit passed. Seventeen remaining endpoints have exact prospective mappings;
five deterministic substage latency endpoints are unavailable under the frozen
conditional-observability rule; no further endpoint requires human semantic
review.

The preserved raw inventory
`ff97ad4ef665754e23fc90e06803844580bcfaacd2ae89034d3ecaf8bc56fbda`
and transaction inventory
`2c0c1d9d961ccc63ffee0776f4b36c9ec0b111c9cb6f877b2e28dcc06bbc9152`
both passed. The raw archive remains at its original external path. The original
30-file transaction is retained byte-for-byte under
`results/formal_v2/recovered_transaction_evidence/`.

Slot 1 was physically executed exactly once and was not rerun. Metric extraction
used only the preserved evidence. Compact packaging, raw-ledger publication,
and journal publication all passed. No scientific value was printed during the
dry validation or recovery command.

`J_hard` is NA and not analyzed, with reason
“preregistered continuous endpoint unavailable due to pre-analysis semantic
ambiguity.” Mission success still uses the independently frozen actual
`d_min >= 1.50 m` criterion.

The durable campaign state is:

- registered / consumed: `60 / 1`;
- journal / raw ledger / attempt directories: `1 / 1 / 1`;
- unresolved transactions: `0`;
- completed prefix: `E5V2-B-S2-N12-R1`;
- slot-1 physical execution / rerun counts: `1 / 0`.

Slot-1 physical execution retains bundle v1 identity
`422d82b593ba927dffaee3c14bcf8b6996304a8ae302cdc525ab3c525b786ecb`.
Post-run recovery used recovery bundle
`29eb7421d2095ba88e60df0ed224ad035348b534cb57877a32d967bd933027bb`.
Future physical slots 2–60 are pinned to execution bundle v2
`2800b1a4540ffde75573f5ea7bf580b415302d5c4d86f0ab86898c69f7b02572`.
No external resume authorization was created.

The next frozen slot is position 2,
`E5V2-B-S2-N8-R1`, seed `5202031`, N=8, scenario
`E5V2-B-S2-N8`, substudy E5-v2B, family `UNDER_SPECIFIED`. Slot 2 was not
executed.

All 46 non-formal tests passed. Registry, scientific payload, seed/order,
analysis contract, production policy/method, and old E5-v1 remain unchanged.
