# E3-v4 Family-B assay transition governance

Status: `HUMAN_APPROVED_ASSAY_TRANSITION_FROZEN`

Decision date: 2026-09-01

Parent redesign HEAD: `cda52d13c14cb05b3d92ee57dcae8fdfba0b157f`

## Decision

The external-wrench pathway is abandoned as the primary E3-v4 Family-B assay.
Neither the previously qualified wrench B-01 nor any failed vertical-wrench B-02
candidate will be tuned further or promoted into the future E3-v4 confirmatory
registry.

This decision is not based on absence of physical dose response alone. The frozen
B-02 response diagnosis found a measurable vertical dose response in attempts with
verified wrench publication. The decisive issue is that the wrench pathway is an
unnecessarily indirect execution-risk manipulation and did not provide deterministic
stimulus-delivery verification across its registered qualification population.

The human-approved replacement is two deterministic deviations introduced only
after normal planning and assignment commitment:

1. execution timing deviation / delayed command delivery;
2. execution reference deviation / temporary local reference bias.

Both replacements must leave the planning input, assignment, and nominal planner
prediction unchanged. Qualification remains F0-only, uses current paper thresholds
and metrics, and requires authoritative delivery evidence. F1 remains sealed for
future effect evaluation.

## Historical evidence preservation

All wrench qualification attempts, manifests, raw bags, hashes, reports, amendments,
and response-diagnosis artifacts remain calibration history and are immutable. This
transition supersedes the wrench assay only for future E3-v4 confirmation; it does
not delete, overwrite, relabel, or invalidate historical results.

Frozen hashes at transition:

- B-02 amendment-v1 response diagnosis JSON:
  `57ee2cdf4f54080cc003d4120e89cf913a32d7464f8db64c6849a54a3f018ea4`;
- original Family-B qualification evidence:
  `572aca4c85c93387b548f17735f40845d7d0836ed72301eebbc572eb0b4b90ff`;
- B-02 amendment-v1 qualification evidence:
  `d797eb283002776bab8af5fa03b8d889ee7bf310991b0447b55c173cafd87635`.

## Production invariance

This is an experimental-assay redesign, not a production-method change. Production
planner, allocator, controller, IAPF, thresholds, motion limits, policy, and runtime
semantics remain frozen. Any implementation must reside in the E3 experiment subtree
or experiment-only tooling and must stop if it requires production semantic changes.

Frozen production policy SHA-256:
`6b47d27f4253d7311e79ea51f6dd1cf0d0182e6df24374a94abae0aa6a135858`.

Sealed E3-v3 registry SHA-256:
`b56344c6cd257e99851523d640d9a89d6def994884877e2303d8fab836e0faf2`.

E3-v3 formal evidence and all preceding E3-v4 failed-assay evidence remain
untouched. No E3-v4 formal attempt is authorized by this transition.
