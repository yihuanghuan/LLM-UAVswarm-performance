# C0-A-prereg-v2 deviation 001: trial-driver infrastructure stop

Date: 2026-08-19 (Asia/Shanghai)

Classification: pre-candidate-outcome infrastructure defect; formal failures
retained in the denominator.

## Trigger

The first two scheduled A1 trials terminated before command publication because
`TrialDriver` assigned to the reserved read-only `rclpy.node.Node.publishers`
property. Both trials are retained as `INFRASTRUCTURE_ERROR` with
`METRIC_EXTRACTION_FAILED`. The campaign was stopped immediately after the
second result. A third entry had already been rendered while the stop signal
was delivered; it is retained as `CAMPAIGN_INTERRUPTED`/`PROCESS_CRASH` and is
not rerun under the same trial ID.

Affected formal trial IDs:

1. `C0A-v2-A1-SCREENING-A1-OC133-OO083-C0A-S-HX-3-POS-X-3-D125-S41001`
2. `C0A-v2-A1-SCREENING-A1-OC133-OO083-C0A-S-HX-3-POS-X-3-D125-S41002`
3. `C0A-v2-A1-SCREENING-A1-OC083-OO133-C0A-S-HX-3-POS-X-3-D125-S41001`

## Correction

The calibration-only driver storage attributes were renamed to
`command_publishers` and `command_subscriptions`. No ROS publisher, topic, QoS, timer, controller callback,
algorithm file, candidate, scenario, seed, metric, threshold, selection rule,
or schedule entry changed. An offline construction test was added to prevent
reuse of a reserved Node attribute. Resume logic now writes a terminal failure
record for an interrupted rendered entry instead of rerunning its trial ID.

## Outcome isolation

No command reached the controller in the affected trials, so no LADRC candidate
tracking outcome was observed. The three failed formal entries remain in their
original schedule positions and denominator. They are not replaced by
diagnostic or successful reruns. The full preflight is rerun against the new
instrumentation commit before the next scheduled formal trial.
