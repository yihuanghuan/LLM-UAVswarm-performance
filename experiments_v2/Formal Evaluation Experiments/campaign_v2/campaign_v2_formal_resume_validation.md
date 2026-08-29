# Campaign v2 Formal Resume Validation

Status: `PASS`

## Scope and defect

The previous launch audit at `085b4b4edda160a005f6217767935ce0f7d01809` was superseded because formal `_initialize()` rejected any root containing a retained journal/artifact prefix. The repair is classified `campaign_infrastructure_only`; scientific semantics changed: `false`; Campaign-v2 formal results existing at repair time: `false`.

## Rehearsal restart validation

The corrected r4 synthetic rehearsal retained 610/610 positions in the exact frozen order. Its 13 restart checkpoints cover retained counts 0, 1, 2, failure fixtures, mixed-family boundaries, 609, and 610. Summary SHA-256: `27da3b71bcafe9d68bdc0ef6a6dd25f9e01f77bb55317f1d957741f321557638`.

## Formal-mode restart validation

The tests instantiate the production `Coordinator("formal", root)` path against disposable roots constrained beneath `results/synthetic-validation/formal-mode-tests`. Only root, runtime-environment validation, and authorization-path dependencies are injected; production constants remain the CLI defaults.

- F0: 0 retained -> next #1: PASS.
- F1: 1 retained -> next #2: PASS.
- F2: 2 retained -> next #3: PASS.
- Retained method and infrastructure failures consume their positions: PASS.
- Mixed-family routing comes only from the global journal cursor: PASS.
- 609 -> 610 and complete 610 -> no #611: PASS.
- Missing, orphaned, foreign, noncontiguous, hash-mismatched, wrong-trial, and temporary states: all fail closed.
- Campaign trigger plus matching token remains valid after retained #1; missing trigger, wrong token SHA, and wrong campaign-manifest SHA all fail closed.

## Identity

- Scientific Campaign-v2 manifest unchanged: `475e5e4cd1234a4dc9f552678aec0387fc8bcce3f2deef468362d6f3c2314488`.
- Old launch tooling bundle: `86901a67a6e676b69e86624c9ccf86c23ea876df27e7442b5d569766451053a4`.
- Corrected launch tooling bundle: `1e33c386a56565ee832e2525e493ad01794844b7aa7eb1e3539aee59ae228325`.
- Change reason: `formal_resume_infrastructure_fix_before_first_campaign_v2_attempt`.

The real formal root remains 0 retained / 0 journal / 0 accepted / next #1, and no real `HUMAN_LAUNCH_TRIGGER.json` exists.
