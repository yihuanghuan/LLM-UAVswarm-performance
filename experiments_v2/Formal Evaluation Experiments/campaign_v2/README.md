# Campaign v2 final freeze

This directory freezes the prospective E2–E5 610-attempt Campaign v2. It does
not contain a formal result and does not authorize an unattended launch.

The append-only suite journal is the sole cursor authority. Formal startup
accepts either the strictly pristine position-1 state or a fully validated,
contiguous retained journal/artifact prefix; the next position is always
derived from that prefix. The real formal root is pristine at position 1 and
contains metadata only. A future formal launch
requires a separately created `results/formal/HUMAN_LAUNCH_TRIGGER.json` plus
its SHA-256 in `CAMPAIGN_V2_HUMAN_LAUNCH_TOKEN_SHA256`; neither exists in this
freeze phase.

The retained `campaign-v2-full-610-rehearsal-r4` supersedes r3 for the resume
repair validation and is synthetic validation. It
uses the actual pinned adapter entrypoints in `spec_rehearsal` mode, performs no
PX4/Gazebo execution, makes no provider call, and cannot consume a formal
cursor. Synthetic failure classifications are deliberate journal/resume
fixtures, not scientific outcomes.

The preferred human-trigger field is `authorize_campaign_v2: true`. The legacy
prospective field `authorize_formal_attempt_1: true` remains accepted as an
auditable campaign-start authorization, so the same immutable trigger/token can
authorize ordinary coordinator restarts after retained attempts. This does not
change pause or recovery governance and never bypasses the dual lock.

Campaign v1 remains in its original worktree and result root. The supersession
record in this directory is metadata only and does not mutate Campaign v1.
