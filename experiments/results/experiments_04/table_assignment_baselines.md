# Experiment 04 Assignment Baseline Summary

| Method | Total path (m) | Avg path (m) | XY crossings | Min distance (m) | Safety violations | Arrival variance (s²) | Failed ratio | Compute (ms) |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Random | 40.438 | 6.001 | 6.272 | 0.610 | 955.134 | 3.807 | 0.950 | 0.006 |
| Nearest Neighbor | 31.168 | 4.545 | 3.826 | 1.026 | 867.428 | 2.897 | 0.844 | 0.050 |
| Hungarian-Distance | 28.587 | 4.125 | 5.600 | 1.385 | 842.992 | 1.631 | 0.722 | 0.013 |
| Hungarian + crossing penalty | 29.216 | 4.203 | 0.000 | 1.327 | 895.594 | 1.691 | 0.722 | 23.314 |
| Hungarian + safety-aware local swap | 29.308 | 4.215 | 0.296 | 1.365 | 885.326 | 1.588 | 0.702 | 30.589 |
