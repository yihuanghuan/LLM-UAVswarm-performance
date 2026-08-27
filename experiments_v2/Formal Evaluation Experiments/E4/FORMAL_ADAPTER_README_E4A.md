# E4A formal exact-trial adapter

The adapter accepts one globally supplied E4A ID and directly constructs the
frozen execution profiles and `UAVExecutionCommand` batch.  It never invokes
an LLM, selects a trial, modifies the suite journal, retries a command, or
changes explicit T/Minimum-Jerk nominal reference across styles.  Formal mode
is protected by the global launch gate; live plumbing validation uses only the
non-registered `ENG-E4A-FIXED-MJ-4UAV-v1` fixture.
