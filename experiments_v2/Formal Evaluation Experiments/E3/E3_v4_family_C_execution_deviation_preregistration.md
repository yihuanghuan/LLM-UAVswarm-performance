# E3-v4 Family-C deterministic mixed-risk preregistration

Status: `FROZEN_BEFORE_PHYSICAL_SCREENING`

Family C is constructed from two spatially isolated components in one shared
mission. UAVs 1-4 retain the authoritative E3-v3 A-01 offset-trapezoid target
set. Under P0 it has two predicted hard conflicts; under P1 identity ownership
removes them. The second component uses a now-qualified deterministic Family-B
execution deviation after the joint allocation is committed.

C-01 adds the qualified four-UAV parallel timing-deviation component translated
by `[20,0,0]` and screens delays 0.4 and 0.5 s. C-02 adds UAVs 1-4 of the
qualified concentric reference-deviation geometry, also translated by
`[20,0,0]`, and screens offsets 1.2 and 1.5 m. Translation preserves within-
component geometry; the omitted two far-side circle members do not define or
mediate intended pair 6-7. Physical qualification is nevertheless required and
does not inherit a pass automatically from Family B.

The finite population is four cells by two F0 planning conditions by five
qualification-only seeds, exactly 40 registered attempts. F1 and formal
execution are refused. Selection is all-gates-first, then smallest deviation,
then lexical ID. P0 may contain the registered structural-component events;
the intended residual pair must independently have nonzero events/exposure in
at least 3/5 seeds. Under P1, which removes structural risk, only intended pair
6-7 may have hard events. C-02 must have zero intended-pair hard events before
reference activation.

The spatial separation and allocator assignments must pass the offline audit
before physical screening. No cross-component assignment is permitted.
Infrastructure retries are append-only and keep the same seed. Every attempt is
retained.

Frozen artifacts before physical execution:

```text
grid_sha256 = a46469f71206b71cf4d85c8190196757c8ee996ff6bb5708e3483f47bf87cd83
expanded_order_sha256 = 7a0e786a966d691d448ed15f18900207c3222e597a549b26ae7b8bc2aefb2891
offline_audit_sha256 = b986311f510bb8694ef09f6d6c7152e4dfe93565c12d479ce6ecb2c3feb42b3c
offline_audit_status = PASS
```

```text
F1_attempt_count = 0
formal_attempt_count = 0
production_method_changed = false
```
