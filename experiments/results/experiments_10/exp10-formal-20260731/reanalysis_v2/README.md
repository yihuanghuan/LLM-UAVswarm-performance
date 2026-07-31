# Legacy batch v2 reanalysis

Existing command and trajectory streams recover dispatch, reference finish, trajectory spread, and stage-level stabilization delay. Per-UAV stable-confirmed timestamps were not logged and the recorder could associate a pre-dispatch status with the next mission, so `stable_arrival_spread` is `not_recoverable_from_existing_logs`.
