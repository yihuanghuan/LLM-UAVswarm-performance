# Experiment 06 tracking comparison

| Scenario | Method | Trials | RMSE (m) | Max error (m) | Settling (s) | Overshoot (m) |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| eight_uav_line_to_circle | linear_ladrc | 5 | 0.294 | 1.225 | nan | 0.062 |
| eight_uav_line_to_circle | minimum_jerk_ladrc | 5 | 0.314 | 1.553 | nan | 0.047 |
| eight_uav_line_to_circle | px4_step | 5 | 4.353 | 16.988 | 8.202 | 0.792 |
| five_uav_circle | linear_ladrc | 5 | 0.501 | 1.471 | nan | 0.049 |
| five_uav_circle | minimum_jerk_ladrc | 5 | 0.638 | 2.109 | nan | 0.059 |
| five_uav_circle | px4_step | 5 | 5.148 | 15.048 | 8.671 | 0.728 |
| single_uav | linear_ladrc | 5 | 0.337 | 0.561 | nan | 0.055 |
| single_uav | minimum_jerk_ladrc | 5 | 0.354 | 0.677 | nan | 0.056 |
| single_uav | px4_step | 5 | 3.418 | 8.092 | 7.067 | 0.479 |
