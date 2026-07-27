# Experiment 05 Validation Report

## Formal Data Completeness

- Formal trial directories: 12
- Completed markers: 12
- Trials per profile: 3
- UAV outcomes per profile: 15
- Total formal UAV outcomes: 60
- Trials with all five UAVs stably arrived: 12
- Formal timeouts: 0
- Rosbags with metadata and SQLite data: 12
- Exported per-UAV trajectory metrics CSV files: 60
- Exported trajectory metric rows: 7,624
- Minimum samples in any formal per-UAV CSV: 114
- Total formal rosbag database size: 5,271,552 bytes

## Rejected Attempts

Four startup attempts failed the strict completeness gate because one or more UAVs did not
produce trajectory metrics. They are retained under `rejected/` for diagnosis and are not
read by `analyze_experiment_05.py`. Every corresponding formal trial was subsequently
completed with a fresh PX4/Gazebo cold start.

## Automated Verification

- `experiments/test/test_experiment_05.py`: 8 passed
- `ladrc_controller/test/test_trajectory_profiles.cpp`: 4 passed
- ROS 2 interface generation: passed
- `uav_swarm_interfaces` and `ladrc_controller` build: passed
- Experiment-specific Flake8 check: passed
- Git whitespace validation (`git diff --check`): passed

The repository-wide legacy Flake8/pep257 tests still report pre-existing style errors in
unrelated files and generated build/install artifacts. No new experiment-05 Python file
reports a Flake8 error under the repository's 99-character limit.
