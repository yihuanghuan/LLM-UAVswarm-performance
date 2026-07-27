# Experiment 02: LFS Representation Ablation

Primary metrics use only the 82 valid commands. Invalid commands are reported separately.

| Method | Executable rate | Mean retries | Invalid UAV ratio | Invalid formation ratio | Missing field ratio | Compilation success |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Direct waypoint | 1.0000 | 0.0488 | 0.0000 | 0.0169 | 0.0000 | 1.0000 |
| Task JSON (no schema) | 0.9878 | 0.0000 | 0.0000 | 0.0169 | 0.0000 | 0.9878 |
| LFS + schema | 1.0000 | 0.0000 | 0.0000 | 0.0085 | 0.0000 | 1.0000 |
| LFS + schema + semantic | 1.0000 | 0.0000 | 0.0000 | 0.0000 | 0.0000 | 1.0000 |

## Invalid / ambiguous commands

| Method | Correct rejection rate | False executable rate | Mean retries |
| --- | ---: | ---: | ---: |
| Direct waypoint | 0.8333 | 0.0556 | 0.0000 |
| Task JSON (no schema) | 1.0000 | 0.0000 | 0.0000 |
| LFS + schema | 0.9444 | 0.0000 | 0.0000 |
| LFS + schema + semantic | 1.0000 | 0.0000 | 0.0556 |
