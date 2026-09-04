# Large-swarm parking layout specification

Status: **FROZEN BEFORE THE FIRST N=20 INFRASTRUCTURE SWEEP**.

The same deterministic row-major rule is used for every requested N:

1. UAV IDs are `1..N`.
2. Maximum row capacity is eight UAVs.
3. The number of rows is `ceil(N/8)`.
4. Rows are centered at world-frame `y=12.5 m` with spacing `3.0 m`.
5. Within each row, the occupied UAVs are centered at `x=0 m` with spacing
   `3.0 m`; a partial final row is independently centered.
6. Every model spawns at `z=0.83 m`; the frozen controller takes off to its
   unchanged startup hover altitude. The controller global ENU offset is the
   exact `(x,y,0)` spawn position.
7. IDs are assigned row-major, left to right and then low to high y.

For row index `r` and column index `c`, with `R=ceil(N/8)` and `K_r` occupied
columns in row r:

`y_r = 12.5 + 3.0 * (r - (R-1)/2)`

`x_rc = 3.0 * (c - (K_r-1)/2)`

This is experiment infrastructure and initial layout only. It does not change
Candidate semantics, frozen geometry, safety, allocation, control, or mission
scheduling. The 3.0 m spacing is strictly above frozen `d_plan=1.80 m`.

