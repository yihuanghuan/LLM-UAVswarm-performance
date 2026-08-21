# C0-A calibration result v2

## Experiment identity

- Calibration: `C0-A`
- Protocol: `C0-A-prereg-v2`
- Reason for v2: pre-outcome protocol clarification
- Previous protocol: `C0-A-prereg-v1`, status `INFRASTRUCTURE_BLOCKED`, formal trials `0`
- Experiment branch: `cal/C0-A-ladrc-motion-limits`
- Experiment source commits: `["6dbbb92446c67a1623be31fbb576752d14f0cb18", "7a8371360c410d9bfbd4dfe71413b832b6c3b7ff", "da47b3a08a6c271b2053c41dfff8c744370a0637"]`
- Algorithm freeze: `paper-algorithm-freeze-v1`
- Dataset class: `calibration`
- Formal trials executed: `300`
- Trial hard passes/failures: `26` / `274`

## Stage A1

- Screening trials: `300`
- Survivors: `0`
- Winner ID: `NONE`
- Winner omega_c: `N/A`
- Winner omega_o: `N/A`

## Stage A2

- Status: `NOT ACTIVATED (A1 survivor count was zero)`
- Winner ID: `NONE`
- v_limit: `N/A`
- a_limit: `N/A`
- j_limit: `N/A`
- minimum_duration: `N/A`

## Stage A3

- Status: `NOT ACTIVATED (A1 survivor count was zero)`
- Winner ID: `NONE`
- Omega clamps: `N/A`
- Motion clamps: `N/A`
- Physical caps: `N/A`

## Scale validation

- Status: `NOT ACTIVATED (A1 survivor count was zero)`
- 1 UAV: `0/0`
- 4 UAV: `0/0`
- 8 UAV: `0/0`

## Worst-case evidence

The values below are maxima across the `295` trials with extractable numeric
metrics. Failed trials without extractable metrics remain in the formal
denominator and failure counts.

- Tracking RMSE: `0.23033117461558195`
- Maximum tracking error: `0.34131649573653217`
- Final error: `0.054473113268613815`
- Saturation ratio: `0.0`
- Roll/pitch: `18.777299152805863` / `12.061578937306534` deg
- Post-trajectory RMS: `0.17473385725833007`
- Post-trajectory peak-to-peak: `0.45428466796875`
- Last/first RMS ratio: `1.0327317381745835`
- Zero crossings on worst axis: `26`
- Command jerk p99.5: `30.87586325757432`
- Minimum separation: `N/A`

## Failures

`{"CAMPAIGN_INTERRUPTED": 2, "COMMAND_JERK_P99_5": 31, "GROWING_OSCILLATION": 1, "METRIC_EXTRACTION_FAILED": 3, "MISSION_FAILED": 2, "PROCESS_CRASH": 2, "ZERO_CROSSINGS": 265}`

Trial termination reasons: `{"CAMPAIGN_INTERRUPTED": 2, "COMMAND_REJECTED": 1, "INFRASTRUCTURE_ERROR": 2, "MANDATORY_TOPIC_MISSING": 2, "SUCCESS": 293}`

## Deviations from C0-A-prereg-v2

`["C0-A-prereg-v2_DEV-001.md", "C0-A-prereg-v2_DEV-002.md"]`

## Conclusion

`C0-A = NO_ACCEPTABLE_CONFIGURATION`

- Frozen parameter commit: `NONE`
- Checkpoint tag: `NONE`
- Policy SHA-256: `N/A (no winner and no frozen policy)`
- READY_FOR_C0_B: `NO`
