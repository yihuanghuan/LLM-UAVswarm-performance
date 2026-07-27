# Experiment 05 Results

## Analytic reference metrics (worst case across UAV paths)

| Profile | Max velocity | Max acceleration | Max jerk | Integrated squared jerk |
| --- | ---: | ---: | ---: | ---: |
| step | N/A | N/A | N/A | N/A |
| linear | 1.872747 | N/A | N/A | N/A |
| trapezoidal | 2.498773 | 1.249386 | N/A | N/A |
| minimum_jerk | 3.514611 | 1.352774 | 1.757305 | 4.940995 |

N/A denotes a distributional boundary derivative, not a finite physical value.

## Closed-loop metrics

| Profile | Successful | Sync (s) | Final error (m) | Tracking RMSE (m) |
| --- | ---: | ---: | ---: | ---: |
| step | 3/3 | 4.1935 | 0.2366 | 5.1664 |
| linear | 3/3 | 2.3856 | 0.2557 | 1.5001 |
| trapezoidal | 3/3 | 1.7653 | 0.2342 | 1.6815 |
| minimum_jerk | 3/3 | 1.6864 | 0.2232 | 1.8491 |
