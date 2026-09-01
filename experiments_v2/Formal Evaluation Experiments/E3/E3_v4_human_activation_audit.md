# E3-v4 Human Activation Audit

Status: **PASS**

This is a static activation audit. No physical trial, Gazebo/PX4 process,
formal attempt artifact, or campaign-journal record was created.

## Activation identity

- Candidate Git commit: `1c782a14eb1e812f6eaabd95fd01f3ba7dab5f05`
- Activation Git commit: `957e65aef5e379ec668f5a9f9b01fe84df7ea5f9`
- Candidate registry SHA-256: `80ddbb8701f1c7feb84ae64a7985f233742f522c1204131ab4dd6d09960bd79b`
- Sealed registry SHA-256: `2b3dccc2ad27cf317029c2b7b014bca3a8b28fc8c0a196fd4c2e5abe0be9d4b7`
- Registry status: `SEALED_FOR_FORMAL_EXECUTION`

## Scientific equivalence

- Candidate scientific payload SHA-256: `43a4805a5c9bd881fc3cc8ff0785bbf3436a5fbbffc38596d05e985b88a896e0`
- Sealed scientific payload SHA-256: `43a4805a5c9bd881fc3cc8ff0785bbf3436a5fbbffc38596d05e985b88a896e0`
- Equivalent after removing only activation fields: `true`
- Scientific protocol changes: `0`

## Frozen population and analysis

- Formal seeds SHA-256: `665600871ad3fb6cff324ab3ef9144b0d84b42acc19505283679b6ae01586841`
- 360-order SHA-256: `60ee30a7100b53c4964e3f9f086ff3d137fb41282eebc4439760bf17f033b39b`
- Analysis contract SHA-256: `987ff29aa814a0dc5e9e64081fcf0fc79ceb3086b21a0e945bfe2f8252185c58`
- Journal contract SHA-256: `7f00d14504fc914d396909c333700700b4ac68f0f2dddb77d5259ab69b257d84`
- Specs / unique IDs / complete blocks: `360 / 360 / 90`

## Execution gate and cursor

- Static sealed formal-context validation: `PASS`
- Explicit authorization and wrong-context/hash rejection checks: `PASS`
- Formal attempts: `0`
- Journal consumed slots: `0`
- Next campaign position: `1`
- Next trial ID: `E3-C-01__P1_F1__S934882`

## Provenance and invariance

- Policy SHA-256 before/after: `6b47d27f4253d7311e79ea51f6dd1cf0d0182e6df24374a94abae0aa6a135858` / `6b47d27f4253d7311e79ea51f6dd1cf0d0182e6df24374a94abae0aa6a135858`
- E3-v3 registry SHA-256 before/after: `b56344c6cd257e99851523d640d9a89d6def994884877e2303d8fab836e0faf2` / `b56344c6cd257e99851523d640d9a89d6def994884877e2303d8fab836e0faf2`
- Trial-registry source SHA-256: `60c138946fcc6a19a9780184b23f996f0c7f1d8f0bc66cc1bde3663117e625a1`
- Formal-adapter source SHA-256: `91b1efc31df9796c41fb5118f40fcc6d775e98f742da33a960db95a538bba16c`
- Execution tooling bundle SHA-256: `78cb5dbc374983c64752433fa1c62c4990903b03b5b813f0248f13105eb074bf`
- Activation manifest SHA-256: `49726b77d60fff8a83c3c7602a7b1236047265995a719e44a9657f8e0f31f993`
- Candidate-to-activation changes outside E3: `0`
- Production changes: `0`

## Final gate

```text
E3-v4 HUMAN ACTIVATION: PASS
REGISTRY SEALED FOR FORMAL EXECUTION
FORMAL CAMPAIGN READY TO START AT SLOT 1
FORMAL EXECUTION NOT STARTED
```
