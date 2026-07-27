# Experiment 04 Assignment Baseline Summary

| Method | Total path (m) | Avg path (m) | XY crossings | Min distance (m) | Safety violations | Critical violations | Safety-margin failure | Critical failure | Arrival variance (s²) | Compute (ms) |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Random | 37.673 | 6.467 | 4.006 | 0.973 | 164.226 | 67.046 | 0.904 | 0.654 | 4.533 | 0.005 |
| Nearest Neighbor | 25.259 | 4.582 | 1.292 | 1.711 | 70.400 | 16.424 | 0.698 | 0.368 | 2.931 | 0.043 |
| Hungarian-Distance | 23.010 | 4.214 | 1.096 | 2.332 | 50.164 | 1.436 | 0.438 | 0.048 | 1.516 | 0.012 |
| Hungarian + crossing penalty | 23.019 | 4.215 | 0.000 | 2.324 | 75.162 | 1.558 | 0.438 | 0.056 | 1.525 | 13.493 |
| Hungarian + safety-aware local swap | 23.144 | 4.234 | 0.524 | 2.414 | 26.770 | 1.218 | 0.316 | 0.036 | 1.347 | 16.196 |
