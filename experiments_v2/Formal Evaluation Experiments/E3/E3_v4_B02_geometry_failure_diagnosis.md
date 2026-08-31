# E3-v4 B-02 geometry failure diagnosis

Status: analytic diagnosis completed before B-02 amendment-v1 pilot execution.

For a pure world-z relative disturbance on UAV2/UAV3,

\[
d_{23}(t)=\sqrt{d_{xy,23}^{2}+d_{z,23}(t)^2}\ge d_{xy,23}.
\]

The frozen hard-risk threshold is `d_hard = 1.5 m`. The geometrically reachable
minimum below assumes arbitrary vertical compression to `d_z = 0`; it is a lower
bound, not a claim that the frozen controller and registered force can attain it.

| Geometry | d_xy,23 (m) | nominal d_z,23 (m) | nominal d_23 (m) | d_hard (m) | pure-z geometric lower bound (m) | Diagnosis |
|---|---:|---:|---:|---:|---:|---|
| E3-v3 B-02 | 3.440930107 | 3.000000000 | 4.565084884 | 1.500000000 | 3.440930107 | geometry-limited/impossible |
| B02 G1 aligned 3 m pair | 0.000000000 | 3.000000000 | 3.000000000 | 1.500000000 | 0.000000000 | geometrically possible |
| B02 G2 aligned 2 m pair | 0.000000000 | 2.000000000 | 2.000000000 | 1.500000000 | 0.000000000 | geometrically possible |

The v3 values follow from UAV2 `[-1,-1.4,2]` and UAV3 `[1,1.4,5]`:

\[
d_{xy,23}=\sqrt{2^2+2.8^2}=3.4409301068170506\ {\rm m}.
\]

Thus no pure-z force could create a target-pair hard-risk event in the original v3
geometry. That historical failure was geometry-limited.

G1 and G2 deliberately aligned the affected pair in x/y, so their horizontal
projection was zero. Their amendment-predecessor failure was **not** a geometric
impossibility. Across the five qualification seeds, the registered pair-2/3 minimum
ranges were:

| Candidate | P0_F0 pair-2/3 range (m) | P1_F0 pair-2/3 range (m) |
|---|---:|---:|
| G1, 4 N × 1.5 s | 2.652320505–2.981113471 | 2.601623456–2.987388693 |
| G1, 5 N × 1.5 s | 2.501513243–2.555267582 | 2.522248772–2.659978055 |
| G1, 6 N × 2.0 s | 2.406204365–2.459617092 | 2.388218568–2.987057773 |
| G2, 2 N × 1.5 s | 1.817751462–1.872754243 | 1.797714793–1.831960946 |
| G2, 3 N × 1.5 s | 1.710476207–1.978309385 | 1.706682725–1.863120830 |
| G2, 4 N × 1.5 s | 1.617803784–1.988546492 | 1.616398384–1.641591583 |

Therefore the exhausted G1/G2 finite-grid failure was response-limited: the realized
vertical compression of the correct pair did not reach the hard-risk region. The
isolated hard-risk events in some P1_F0 attempts involved pair 1–2 and do not alter
this target-pair diagnosis.

The statement “B-02 v1 finite-grid failure was geometry-limited” applies to the
original E3-v3 geometry, but would be false for the already redesigned aligned G1/G2
geometries. Increasing vertical force alone was geometrically meaningful for G1/G2;
it nevertheless failed within the prospectively frozen grid. Amendment v1 therefore
uses the newly authorized analytic family satisfying
`d_xy,23 < d_hard < d_23_nominal` and a separately frozen finite force grid.
