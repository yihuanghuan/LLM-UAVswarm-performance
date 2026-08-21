# C0-A-prereg-v2 deviation 002: driver debug-observer QoS

Date: 2026-08-19 (Asia/Shanghai)

Classification: read-only instrumentation observation defect; formal failures
retained in the denominator.

## Trigger

After DEV-001, the next two formal commands reached the controller and their
rosbags contained complete `control_tracking_debug` samples. The separate
real-time trial driver did not receive that topic because it requested the
default reliable QoS while the frozen controller offers SensorData best-effort
QoS. It therefore terminated the trials as `MANDATORY_TOPIC_MISSING` even
though the bag-based metric extractor could read the topic.

Affected completed formal trial IDs:

1. `C0A-v2-A1-SCREENING-A1-OC133-OO133-C0A-S-DIAG-1-POS-X2-Y2-Z1-D125-S41003`
2. `C0A-v2-A1-SCREENING-A1-OC100-OO100-C0A-S-VU-2-POS-Z-2-D125-S41001`

The following rendered entry was interrupted when the campaign was stopped and
is retained as `CAMPAIGN_INTERRUPTED`/`PROCESS_CRASH` without a rerun:

`C0A-v2-A1-SCREENING-A1-OC067-OO117-C0A-S-VU-2-POS-Z-2-D125-S41001`

## Correction

Only the read-only driver's subscription was changed to
`qos_profile_sensor_data`, matching the already-frozen publisher. No controller
publisher, callback, timer, control frequency, algorithm, command, candidate,
scenario, seed, metric, threshold, selection rule, or schedule entry changed.

## Outcome handling

The affected completed trials keep their original driver failure and bag-based
hard failures. They are not relabeled or rerun. The rendered interrupted entry
is also a formal failure. A full preflight is required against the corrected
instrumentation commit before the next schedule entry.
