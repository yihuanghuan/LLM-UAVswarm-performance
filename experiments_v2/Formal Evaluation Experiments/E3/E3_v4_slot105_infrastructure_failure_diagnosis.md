# E3-v4 Slot-105 Infrastructure-Failure Diagnosis

Status: `FROZEN_FROM_RETAINED_EVIDENCE_BEFORE_SLOT_106`

Baseline evidence commit:
`093a66f27cbb1936b10cff6b61c716ffaa0cd1b9`.

Slot 105 remains the consumed formal attempt
`E3-C-02__P1_F0__S730940`. Its immutable `attempt.json` has SHA-256
`8cc8bdb81cf33a2f0b635078fa3d80485dadbbca0078c10d58142471d540690c`
and records `attempt_status: infrastructure_failure`,
`accepted_formal_result: true`, `replacement_attempt: false`, null metrics,
and no retry. This diagnosis does not change that artifact or its campaign
journal record.

## Retained-evidence finding

The proximate failure is exactly `RuntimeError: all-UAV readiness failed`.
The retained evidence supports the following bounded infrastructure sequence:

1. The PX4/Gazebo multi-instance launcher started, but `sitl.log` subsequently
   reports `An instance of Gazebo is not running.` for the later instances.
2. All eight controller processes started. They remained in
   `WAIT_ESTIMATOR_READY`, reporting that they were waiting for fresh
   `VehicleOdometry` while unarmed and not in Offboard mode.
3. The controllers eventually latched `STARTUP_FAILED`; the retained readiness
   snapshot reports eight present status publishers but no system-ready UAV,
   NaN altitude, no arming, and no Offboard activation.
4. The all-UAV readiness command returned failure and the formal harness
   terminated at that gate.

This supports the bounded root-cause class
`SIMULATION_STARTUP_INFRASTRUCTURE_FAILURE`: Gazebo/PX4 multi-instance
simulation startup did not provide valid estimator/odometry readiness, which
caused the all-UAV readiness gate to fail. The retained evidence does not
identify a more specific internal Gazebo cause, so no claim about a crash
mechanism, memory pressure, or a race condition is made.

```text
failure_stage: PRE_FORMAL_INTERACTION_READINESS
readiness_passed: false
scientific_method_execution_started: false
interaction_scoring_started: false
```

## Frozen acquisition order

The activated runner is unchanged. In
`tooling/e3_v4_execution_deviation_trial.py`, the frozen `orchestrate` path:

1. starts Micro XRCE Agent and PX4/Gazebo;
2. starts the eight controller nodes;
3. runs `wait_swarm_ready.py`;
4. writes `readiness.log`;
5. raises `RuntimeError("all-UAV readiness failed")` when readiness returns
   nonzero; and only otherwise
6. constructs and starts `ros2 bag record`.

The readiness return-code check is at lines 583--584 of the frozen source and
the bag command follows at lines 585--586. Therefore the slot-105 failure
occurred before the rosbag-start statement was reachable. No rosbag directory,
rosbag log, runtime-provenance file, staging result, interaction result,
metrics, raw-archive inventory, independent archive directory, or slot-105
archive-ledger record exists.

## Storage conclusion

The source bag was never created and was not expected after this pre-readiness
termination. Accordingly:

```text
slot105_root_cause_class: SIMULATION_STARTUP_INFRASTRUCTURE_FAILURE
storage_disposition: PRE_RAW_ACQUISITION_INFRASTRUCTURE_FAILURE
raw_bag_expected: false
raw_bag_lost: false
raw_evidence_loss: false
archive_required: false
scientific_retry_authorized: false
replacement_seed_authorized: false
slot_remains_consumed: true
```

Slot 105 remains in the all-attempt denominator as an infrastructure failure,
contributes no continuous metrics, and is not rerun or replaced. Its incomplete
scenario-by-seed block remains subject to the prospectively frozen E3-v4
analysis contract.
