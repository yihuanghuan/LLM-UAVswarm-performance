# E3 authoritative scientific identity chain

## E3 v1

Original sealed factorial design. Historical protocol and registry remain byte-identical.

↓ Superseded because the registered 8-UAV A-02/C-02 duration of 8.0 seconds was dynamically infeasible under the already frozen Minimum-Jerk profile and motion limits.

## E3 v2

Changed only A-02/C-02 duration from 8.0 to 9.5 seconds. The analytic requirement was 9.229157809087656 seconds, rounded upward to the preregistered 0.5-second grid.

↓ Superseded because A-01/C-01 targets were permutation-equivalent to their initial-position set. Correct free P0 and P1 assignment therefore produced a unique zero-motion optimum and eliminated the intended structural-risk mechanism.

## E3 v3 — ACTIVE

Changed only the shared A-01/C-01 target geometry to:

- `[-3, 4, 3]`
- `[ 3, 4, 3]`
- `[-2,12, 3]`
- `[ 0,12, 3]`

Initial positions, 6.0-second duration, C-01 disturbance, free-assignment semantics, P0/P1 algorithms, F0/F1 behavior, controllers, safety policy, metrics, seeds, population, and global order remain unchanged.

The allocator algorithms were not defective or changed. Infrastructure was not responsible for the geometry inconsistency. No valid formal E3 outcome or live-demo scientific outcome was used to select the replacement. Selection used deterministic offline planning-time objectives and exhaustive enumeration of all 24 assignments.

Production E3 tooling now fail-closed hash-gates the authoritative v3 protocol and registry. The authoritative numerical environment remains Python 3.10.12, NumPy 1.24.4, and SciPy 1.8.0. The known A-02/C-02 equal-cost P0 tie behavior remains separately documented for Campaign-v2 freeze review; allocator tie-breaking was not changed here.
