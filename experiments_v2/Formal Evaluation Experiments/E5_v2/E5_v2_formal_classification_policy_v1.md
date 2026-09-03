# E5-v2 formal terminal-classification implementation

Status: frozen before formal slot 1. This document implements, without adding
an endpoint, the stage-separated and all-attempt rules in the activated registry
and prospective analysis contract.

- Startup, spawn, controller launch, readiness, or raw-recorder failure before
  command submission is an infrastructure failure and is not scientific-complete.
- A provider/frontend terminal failure before a valid Candidate exists is a
  semantic-frontend failure and is not scientific-complete. It is retained in
  the all-attempt denominator and is not an infrastructure failure.
- A valid Candidate that is rejected by the frozen resolver or planner is a
  scientific-complete fail-closed scientific failure. This preserves the old
  E5-v1 REL-QUAL treatment.
- Once dispatch begins, timeout, controller/PX4 failure, failsafe, hard-distance
  violation, incomplete mission, or completed-but-unsuccessful tracking is a
  scientific-complete scientific failure when the required evidence is verified.
- `RAW_EVIDENCE_LOSS` consumes its slot and stops the campaign. Metrics without
  valid evidence are `NA` with a reason and never zero-imputed.
- Continuous metrics are available only when their registered interval and raw
  source coverage satisfy the frozen evidence rules. Binary all-attempt mission
  success remains false for every non-success terminal class.

Infrastructure, frontend, resolver/planning, execution/control, metrics, and
storage outcomes remain separate fields in every attempt artifact. E5-v1 and
E5-v2 are never pooled. E5-v2 remains integration evidence only and does not add
C1/C2/C3 causal evidence or a formal/asymptotic scaling claim.
