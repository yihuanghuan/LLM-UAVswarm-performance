# C0-B — State freshness calibration

C0-B freezes only the candidate runtime's state-snapshot freshness thresholds:
`state_timeout`, `snapshot_skew`, and `fresh_state_wait_timeout`.  It is a
measurement calibration, not a task-performance experiment or a parameter
search.

The frozen C0-A execution policy is an input integrity anchor.  This campaign
does not edit it, the LADRC configuration, trajectory generation, LFS policy,
allocator, IAPF, or planner architecture.

## Run

First run the baseline system for every scenario in `state_freshness_pipeline/
scenarios/` and start the independent observer alongside it.  The waypoint
transition is four-UAV because the frozen Candidate Mission contract does not
permit a one-UAV formation task. The observer is
read-only: it subscribes to `/uavN/swarm_state` and writes the required raw
CSV fields.

```bash
source /opt/ros/humble/setup.bash
python3 state_freshness_pipeline/freshness_probe.py \
  --scenario multi_uav_8 --uav-count 8 --duration-s 60 \
  --output /tmp/multi_uav_8.csv
```

Combine the five resulting files and freeze once; the command refuses missing
scenarios, incorrect UAV counts, or incomplete fields.  The observer must be
run only alongside the baseline system as specified by the scenario files.

```bash
python3 state_freshness_pipeline/run_calibration.py freeze \
  --measurements /path/to/freshness_measurements.csv
```

The default output is `results/C0-B_state_freshness_freeze/`.  It contains the
plan, raw measurements, trial metrics, report, manifest, validation record,
and `frozen_state_freshness_policy.yaml`.

`freshness_probe.py` measures state age and snapshot skew directly from the
received odometry headers.  It measures planner-equivalent wait as the time
from a snapshot request to the first complete, fresh snapshot using the same
freshness predicates as the production snapshot manager.  The value is an
observer metric only; the probe neither publishes commands nor changes the
runtime.
