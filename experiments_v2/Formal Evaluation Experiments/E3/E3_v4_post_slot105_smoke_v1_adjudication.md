# E3-v4 Post-Slot-105 Smoke v1 Adjudication

The historical v1 smoke remains `FAIL`. This adjudication does not edit its
result or retroactively convert it to `PASS`; it separates the valid core
startup/readiness observations from two unsuitable auxiliary introspection
checks.

## Core startup/readiness

Assessment: `PASS`.

The retained `smoke_result.json`, readiness log, controller log, SITL log, and
process snapshot establish that:

- the readiness process returned zero and reported `ready=true` for exactly
  eight UAVs;
- UAVs 1--8 were all present, `system_ready=true`, armed, in offboard mode,
  not in failsafe, and had finite odometry-derived altitude;
- all eight controllers logged receipt of VehicleOdometry and transition to
  `READY`;
- the observation-time snapshot contained one gzserver, at least eight PX4
  process matches, eight LADRC controller processes, and one MicroXRCEAgent.

These are direct observations of the state the frozen formal readiness gate
requires before a formal interaction may proceed.

## Auxiliary topic enumeration

Assessment: `NON_AUTHORITATIVE_SINGLE_SHOT_DDS_DISCOVERY`.

The single `ros2 topic list` snapshot listed only one of the eight expected
external PX4 VehicleOdometry names. That snapshot is incomplete relative to
the same run's successful eight-UAV readiness evidence and the eight
controller log acknowledgements of VehicleOdometry. A newly created CLI DDS
participant's single discovery snapshot is therefore not valid evidence that
the other odometry streams were absent.

## Auxiliary Gazebo model query

Assessment: `INVALID_CLI_ASSAY`.

The command `gz model --list` returned `Invalid arguments`. Inspection of the
installed Gazebo Classic 11.10.2 CLI help confirms that its `model` subcommand
has no `--list` option. The command supplied no valid negative observation
about model count. The installed read-only model query is instead
`gz model --model-name <name> --info` (or `--pose`).

## Governance result

```text
historical_recorded_status = FAIL
core_readiness_assessment = PASS
auxiliary_topic_enumeration_assessment =
  NON_AUTHORITATIVE_SINGLE_SHOT_DDS_DISCOVERY
auxiliary_gazebo_model_query_assessment = INVALID_CLI_ASSAY
formal_campaign_effect = NONE
formal_attempt_created = false
slot105_rerun = false
slot106_started = false
```

The historical v1 evidence remains byte-identical and auditable.
