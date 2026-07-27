# Experiment 04 Assignment Baseline Summary

| Method | Total path (m) | Avg path (m) | XY crossings | Min distance (m) | Safety violations | Critical violations | Safety-margin failure | Critical failure | Arrival variance (s²) | Compute (ms) |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Random | 38.046 | 6.514 | 4.052 | 0.976 | 145.682 | 60.494 | 0.904 | 0.654 | 4.621 | 0.005 |
| Nearest Neighbor | 25.264 | 4.583 | 1.292 | 1.725 | 60.916 | 14.744 | 0.688 | 0.356 | 2.971 | 0.043 |
| Hungarian-Distance | 22.930 | 4.203 | 1.096 | 2.362 | 42.152 | 1.092 | 0.372 | 0.038 | 1.533 | 0.012 |
| Hungarian + crossing penalty | 22.939 | 4.205 | 0.000 | 2.354 | 67.150 | 1.214 | 0.372 | 0.046 | 1.541 | 13.528 |
| Hungarian + safety-aware local swap | 23.031 | 4.219 | 0.524 | 2.460 | 18.920 | 0.146 | 0.240 | 0.006 | 1.365 | 15.471 |
