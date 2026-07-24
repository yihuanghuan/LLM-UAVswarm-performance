# LFS Fix Selective Rerun

Retested commands: 20

| Scope | Count | Before field accuracy | After field accuracy | Before exact | After exact | Before trigger | After trigger |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| all | 20 | 0.8333 | 1.0000 | 0.0000 | 1.0000 | 0.3667 | 1.0000 |
| sequential | 18 | 0.8287 | 1.0000 | 0.0000 | 1.0000 | 0.2963 | 1.0000 |
| simple | 1 | 0.8750 | 1.0000 | 0.0000 | 1.0000 | 1.0000 | 1.0000 |
| style-conditioned | 1 | 0.8750 | 1.0000 | 0.0000 | 1.0000 | 1.0000 | 1.0000 |

The rerun contains only commands affected by deterministic LFS canonicalization, transition derivation, enum normalization, safety grounding, and LFS few-shot changes.
The original 400-row experiment remains unchanged.
