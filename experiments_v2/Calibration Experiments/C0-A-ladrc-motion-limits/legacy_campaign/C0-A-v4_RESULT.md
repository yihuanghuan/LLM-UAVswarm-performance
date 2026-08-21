# C0-A simplified continuation result

`C0-A-prereg-v4` was a post-start calibration-workload amendment. The prior
v3 campaign was terminated for calibration efficiency after preserving 561
completed records (300 A1 screening, 261 partial A1 confirmation, and one
interrupted launch directory). The partial confirmation was diagnostic only.

The v4 continuation added 114 completed trials before the protocol stop:

| stage | completed | result |
|---|---:|---|
| A1 confirmation | 54/54 | PASS; A1 winner selected |
| A2 screening | 30/30 | screening survivors available |
| A2 confirmation | 30/30 | no acceptable envelope |
| A3 validation | 0 | not activated |
| scale validation | 0 | not activated |

The A1 winner was `A1-OC067-OO117`, with
`omega_c=[1.005,1.005,1.1725]` and `omega_o=[5.85,5.85,8.775]`.
The A2 confirmation candidates were packages `[5,5,10]` and `[5,4,10]`.
Each had a confirmation hard failure, so v4 ended with
`NO_ACCEPTABLE_CONFIGURATION` under the unchanged valid hard criteria.

Failure counts in new v4 trials were four `COMMAND_JERK_P99_5` failures
(two in A2 screening and two in A2 confirmation). No A3/scale trials were
started, no parameter was frozen, and no paper/calibration writeback or
checkpoint tag was created. C0-B is not activated.
