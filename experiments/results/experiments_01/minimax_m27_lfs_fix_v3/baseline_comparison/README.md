# Fixed LFS vs Baseline Comparison

This comparison keeps all three baseline methods from the original 100-command run.
For LFS + Schema, 20 affected commands are replaced by the final selective rerun; the other 80 observations remain from the original run.

| Method | Overall success | Field accuracy | Exact task | Invalid rejection | Latency (s) | Total tokens | Mean retries | Errors |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Plain JSON | 0.6200 | 0.7157 | 0.5366 | 1.0000 | 29.58 | 2248.01 | 0.74 | 38 |
| Few-shot JSON | 0.9500 | 0.9954 | 0.9634 | 0.8889 | 17.06 | 1825.41 | 0.09 | 5 |
| LFS + Schema (fixed) | 0.9800 | 1.0000 | 1.0000 | 0.8889 | 14.43 | 1222.47 | 0.00 | 2 |
| Dense Waypoints | 0.7400 | 0.9360 | 0.7439 | 0.7222 | 45.84 | 3216.30 | 0.24 | 26 |

Key observations:

- Fixed LFS reaches 98% overall semantic success and 100% exact-task accuracy on valid commands.
- Relative to Few-shot JSON, fixed LFS uses 15.4% less mean latency and 33.0% fewer mean tokens.
- Fixed LFS retains 2 residual errors, both in invalid-command handling; its invalid rejection accuracy (0.8889) ties Few-shot JSON but remains below Plain JSON.

Metric scopes:

- Overall success uses exact-task accuracy for 82 valid commands and rejection accuracy for 18 invalid commands.
- Field, exact-task, and semantic-field metrics use only valid commands.
- Invalid rejection uses only invalid/ambiguous commands.
- Latency, tokens, retries, schema validity, and JSON validity use all 100 commands per method.
- The fixed LFS result is a selective replacement comparison, not a new 100-command API rerun.
