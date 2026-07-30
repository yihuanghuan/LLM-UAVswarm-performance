# Experiment 09: planning/execution safety ablation

This experiment runs a paired 2×2 ablation of distance versus safety-aware
assignment and disabled versus dual-channel IAPF. Four scenarios, four
variants, and fifteen formal seeds produce 240 formal trials. A 16-arm pilot
with seed 9001 precedes parameter freezing.

```bash
cd ~/learning/LLM_swarm_ws
source /opt/ros/humble/setup.bash
source install/setup.bash
cd src/LLM-UAVswarm-performance
export PYTHONPATH="$PWD/location_allocate:$PWD/experiments/09-safety-ablation/scripts${PYTHONPATH:+:$PYTHONPATH}"

python3 -m pytest -q experiments/09-safety-ablation/tests

python3 experiments/09-safety-ablation/scripts/run_batch.py \
  --batch-id exp09-pilot-YYYYMMDD --phase pilot --manage-sim --resume

python3 experiments/09-safety-ablation/scripts/validate_pilot.py \
  experiments/results/experiments_09/pilot/<batch_id>

python3 experiments/09-safety-ablation/scripts/run_batch.py \
  --batch-id exp09-formal-YYYYMMDD --phase formal --manage-sim --resume

python3 experiments/09-safety-ablation/scripts/aggregate_trials.py \
  experiments/results/experiments_09/formal/<batch_id>
python3 experiments/09-safety-ablation/scripts/plot_results.py \
  experiments/results/experiments_09/formal/<batch_id>
python3 experiments/09-safety-ablation/scripts/render_videos.py \
  experiments/results/experiments_09/formal/<batch_id>
python3 experiments/09-safety-ablation/scripts/checksum_results.py \
  experiments/results/experiments_09/formal/<batch_id>
```

Every trial stores metadata and CSV data. Formal seed 4201 records rosbag for
all four variants in every scenario. Existing batch/trial directories are
never overwritten; `--resume` only skips completed trials.
