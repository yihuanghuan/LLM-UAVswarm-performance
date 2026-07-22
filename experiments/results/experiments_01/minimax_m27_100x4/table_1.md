# Experiment 01 Summary

| method | valid_json_rate | schema_valid_rate | field_accuracy | exact_task_accuracy | rejection_accuracy | mean_latency_ms |
| --- | --- | --- | --- | --- | --- | --- |
| plain_json | 1.0000 | 0.8000 | 0.7157 | 0.5366 | 1.0000 | 29578.5600 |
| few_shot_json | 1.0000 | 1.0000 | 0.9954 | 0.9634 | 0.8889 | 17062.4100 |
| lfs_schema | 1.0000 | 1.0000 | 0.9593 | 0.7561 | 0.8889 | 16598.3700 |
| dense_waypoints | 0.9800 | 0.9500 | 0.9360 | 0.7439 | 0.7222 | 45838.1600 |

- Field and exact-task accuracy exclude invalid/ambiguous samples.
- Rejection accuracy is computed only on invalid/ambiguous samples.
- Latency and token counts include retries.
