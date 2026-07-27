# Feasible-Scenario Pilot Record

This directory preserves the first endpoint-feasible pilot run. It used the
same 2.1 m endpoint constraint and dual 2.0/1.5 m thresholds as the final
revision, but its dense target radius was 2.8 m.

The pilot showed that a radius only 0.143 m above the 2 m neighbour-spacing
boundary remained overly sensitive: both Hungarian-Distance and the complete
safety-aware method had a 0.88 safety-margin failure ratio in `dense`.

The data are retained to satisfy the no-overwrite requirement. They are
superseded for reporting by `../feasible_scenarios_v3`, which uses a
pre-declared 3.2 m dense radius while remaining substantially tighter than the
5 m `large` target formation.
