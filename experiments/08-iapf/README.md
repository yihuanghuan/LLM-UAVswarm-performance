# Experiment 08: execution-layer IAPF fallback

The v2 protocol tests whether IAPF remains non-intrusive on nominally safe
missions, reduces risk after reproducible execution deviations, and
complements safety-aware assignment. Legacy M0–M5 configurations remain in
`methods.yaml` only to reproduce the v1 batch.

The formal matrix contains 230 trials:

- non-intrusive: 2 scenarios × off/on × 10 seeds = 40;
- execution-deviation fallback: 3 scenarios × off/on × 10 seeds = 60;
- assignment–IAPF complement: 2 scenarios × 4 modes × 10 seeds = 80;
- stress/failure boundary: 4 scenarios × off/on × 5 seeds = 40;
- two-agent position-only ablation: 1 scenario × 10 seeds = 10.

Every formal arm is first exercised once with seed `9001` (27 pilot trials).
Paired off/on trials reuse the same seed, initial perturbation, assignment
inputs, and disturbance.

```bash
cd ~/learning/LLM_swarm_ws
source /opt/ros/humble/setup.bash
source install/setup.bash
cd src/LLM-UAVswarm-performance
export PYTHONPATH="$PWD/location_allocate:$PWD/experiments/08-iapf/scripts"

python3 -m pytest -q experiments/08-iapf/tests

# 27-arm pilot
python3 experiments/08-iapf/scripts/run_batch.py \
  --batch-id exp08-v2-pilot-YYYYMMDD --phase pilot --manage-sim --resume

# 230 formal trials
python3 experiments/08-iapf/scripts/run_batch.py \
  --batch-id exp08-v2-formal-YYYYMMDD --phase formal --manage-sim --resume

python3 experiments/08-iapf/scripts/aggregate_trials.py \
  experiments/results/experiments_08/v2_patch/formal/<batch_id>
python3 experiments/08-iapf/scripts/plot_iapf_results.py \
  experiments/results/experiments_08/v2_patch/formal/<batch_id>
python3 experiments/08-iapf/scripts/checksum_results.py \
  experiments/results/experiments_08/v2_patch/formal/<batch_id>
```

The batch runner automatically selects the `pilot` or `formal` result
partition. `EXPERIMENT_08_RESULTS_ROOT` may override the v2 base directory.
A batch directory is never reused unless `--resume` is used; individual trial
directories are never overwritten.
