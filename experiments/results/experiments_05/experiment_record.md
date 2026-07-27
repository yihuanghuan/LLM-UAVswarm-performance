# Experiment 05 Execution Record

## Status

- Experiment: Minimum Jerk trajectory generation comparison
- Branch: `exp/05-minimum-jerk`
- Base: `gazebo-experiment-v1` (`df5c5bc9b7a1af695c41dea5744bcb546b7f0a47`)
- Status: completed successfully
- Result directory: `experiments/results/experiments_05`
- Experiment artifact commit SHA: `774a24ee193f505c442066f67e90982faf95de7d`
- Branch-tip commit SHA: recorded in the final Git handoff because a commit cannot contain its own SHA

## Configuration

- Profiles: Step, Linear, Trapezoidal velocity, Minimum Jerk
- Repeats: 3 cold-started Gazebo/PX4 trials per profile
- UAVs: 5 per trial, 60 formal UAV outcomes in total
- Shared LFS duration: 8 s
- Control frequency: 50 Hz
- Motion style: `normal`
- IAPF: disabled (`safety_factor=0`, acceleration feedforward disabled)
- Trial timeout: 28 s after the common scheduled trajectory start
- Start synchronization: the same ROS timestamp, scheduled 2 s after command publication
- Scenario: spawn line to a horizontal circle centered at `(10, 9, 5)` with radius 4 m
- Arrival condition: position error below 0.3 m and speed below 0.3 m/s
- Synchronization error: latest arrival time minus earliest arrival time
- Tracking RMSE interval: common scheduled trajectory interval `[0, 8]` s
- Formal schedule seed: `20260727`

The exact targets and randomized formal schedule are stored in `run_config.json`.

## Mathematical Metric Policy

- Minimum Jerk uses analytic velocity, acceleration, jerk, and integrated squared jerk.
- Linear reports its analytic segment velocity. Endpoint acceleration, jerk, and integrated
  squared jerk are `N/A` because velocity is discontinuous.
- Trapezoidal reports analytic maximum velocity and acceleration. Jerk and integrated
  squared jerk are `N/A` because acceleration jumps at the segment boundaries.
- Step is a qualitative discontinuous-position baseline; finite derivative metrics are
  intentionally not reported.
- Flight-controller setpoints remain finite for every method. Mathematical singularities
  are represented by validity fields in `TrajectoryMetrics`.

## Commands

```bash
cd /home/yihuang/learning/LLM_swarm_ws
source /opt/ros/humble/setup.bash
source install/setup.bash

colcon build --symlink-install \
  --packages-select uav_swarm_interfaces ladrc_controller \
  --allow-overriding uav_swarm_interfaces ladrc_controller

python3 src/LLM-UAVswarm-performance/experiments/scripts/run_experiment_05.py \
  --output-dir \
  /home/yihuang/learning/LLM_swarm_ws/src/LLM-UAVswarm-performance/experiments/results/experiments_05

cd src/LLM-UAVswarm-performance
python3 experiments/scripts/analyze_experiment_05.py \
  --input-dir experiments/results/experiments_05
```

Interrupted batches can retain completed trials with `run_experiment_05.py --resume`.

## Validation

- 12 formal trial directories contain `completed.json`, status data, logs, and rosbag data.
- Each profile has exactly 3 formal trials and 15 formal UAV outcomes.
- All 12 formal trials reached stable hover with all 5 UAVs before timeout.
- The analysis exported 60 per-UAV trajectory-metric CSV files.
- Experiment-specific Python tests: 8 passed.
- C++ trajectory tests: 4 passed.
- ROS interface generation and the controller build completed successfully.
- Four incomplete startup attempts were rejected by the completeness gate and are stored
  under `rejected/`; they are excluded from every formal CSV, table, and figure.

## Results and Interpretation

The complete values are in `method_summary.csv`, `uav_trial_summary.csv`, and
`table_trajectory_comparison.md`.

- Mean synchronization error decreased from 4.194 s for Step and 2.386 s for Linear to
  1.765 s for Trapezoidal and 1.686 s for Minimum Jerk.
- Minimum Jerk had the lowest mean synchronization error and lowest mean final position
  error (0.223 m) among the four methods.
- Step had the largest mean tracking RMSE (5.166 m), reflecting its immediate target jump.
- Linear had the lowest tracking RMSE, but this does not imply smoothness: its endpoint
  acceleration and jerk remain undefined.
- Trapezoidal has continuous velocity but discontinuous acceleration at segment switches.
- Minimum Jerk is the only evaluated profile with finite analytic jerk and integrated
  squared jerk while satisfying zero endpoint velocity and acceleration.
- Minimum Jerk therefore provides the strongest combination of LFS-boundary synchronization,
  closed-loop endpoint accuracy, and mathematically well-defined smoothness in this scenario.

No controller gains, trajectory parameters, targets, or acceptance thresholds were retuned
after observing the formal results.
