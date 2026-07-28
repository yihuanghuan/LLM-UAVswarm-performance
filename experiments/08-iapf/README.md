# Experiment 08 runner

This directory contains the fixed M0–M5 configurations, deterministic scenario
runner, analysis, aggregation, and plotting code. Generated artifacts are stored
under `experiments/results/experiments_08/<batch_id>` and are never overwritten.

```bash
cd ~/learning/LLM_swarm_ws
source /opt/ros/humble/setup.bash
source install/setup.bash
cd src/LLM-UAVswarm-performance

# Validate without Gazebo
python3 -m pytest -q experiments/08-iapf/tests
python3 experiments/08-iapf/scripts/validate_synthetic_data.py

# One trial against an already running 2/8-UAV simulator
python3 experiments/08-iapf/scripts/run_experiment.py \
  --scenario head_on --method M3 --trial 1 --seed 42 \
  --batch-id exp08-YYYYMMDD --phase smoke

# Complete 522-trial protocol, including simulator supervision and retries
python3 experiments/08-iapf/scripts/run_batch.py \
  --batch-id exp08-YYYYMMDD --phase all --manage-sim --resume

python3 experiments/08-iapf/scripts/aggregate_trials.py \
  experiments/results/experiments_08/exp08-YYYYMMDD
python3 experiments/08-iapf/scripts/plot_iapf_results.py \
  experiments/results/experiments_08/exp08-YYYYMMDD
python3 experiments/08-iapf/scripts/checksum_results.py \
  experiments/results/experiments_08/exp08-YYYYMMDD
```

The complete protocol comprises 42 calibration, 90 pilot, 240 main, 60
infeasible stress, 10 additional vertical escape-ablation, and 80 additional
sensitivity trials. Main M3 nominal trials are reused as the `id_order` and
nominal sensitivity arms.
