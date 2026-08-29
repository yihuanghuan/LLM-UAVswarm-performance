# Campaign v2 final freeze

This directory freezes the prospective E2–E5 610-attempt Campaign v2. It does
not contain a formal result and does not authorize an unattended launch.

The append-only suite journal is the sole cursor authority. The formal root is
pristine at position 1 and contains metadata only. A future formal launch
requires a separately created `results/formal/HUMAN_LAUNCH_TRIGGER.json` plus
its SHA-256 in `CAMPAIGN_V2_HUMAN_LAUNCH_TOKEN_SHA256`; neither exists in this
freeze phase.

The retained `campaign-v2-full-610-rehearsal-r3` is synthetic validation. It
uses the actual pinned adapter entrypoints in `spec_rehearsal` mode, performs no
PX4/Gazebo execution, makes no provider call, and cannot consume a formal
cursor. Synthetic failure classifications are deliberate journal/resume
fixtures, not scientific outcomes.

Campaign v1 remains in its original worktree and result root. The supersession
record in this directory is metadata only and does not mutate Campaign v1.
