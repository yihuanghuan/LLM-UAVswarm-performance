# Experiment 10 v2 completion report: exp10-formal-v2-gated-20260803

## Reproduction record

- branch: `exp/10-system-8uav`
- execution code commit: `797cfecb`
- frozen configuration: `/home/yihuang/learning/LLM_swarm_ws/src/LLM-UAVswarm-performance/experiments/results/experiments_10/exp10-formal-v2-gated-20260803/configuration/full_system.yaml`
- data location: `/home/yihuang/learning/LLM_swarm_ws/src/LLM-UAVswarm-performance/experiments/results/experiments_10/exp10-formal-v2-gated-20260803`
- run command: `source /opt/ros/humble/setup.bash && source /home/yihuang/learning/LLM_swarm_ws/install/setup.bash && /home/yihuang/learning/LLM_swarm_ws/llm_env/bin/python -u experiments/system_8uav/scripts/run_batch.py --batch-id exp10-formal-v2-gated-20260803 --phase formal --manage-sim`
- completed successfully: yes

## Attempt accounting

- attempts: 51
- execution-entry trials: 50

- task_a_simple: 10 execution trials / 10 attempts; 9 successful, 1 stage timeouts
- task_b_sequential: 10 execution trials / 10 attempts; 3 successful, 7 stage timeouts
- task_c_grouped: 10 execution trials / 10 attempts; 10 successful, 0 stage timeouts
- task_d_dense: 10 execution trials / 10 attempts; 9 successful, 1 stage timeouts
- task_e_mixed: 10 execution trials / 11 attempts; 3 successful, 7 stage timeouts

## Validation

- readiness failures: 0
- valid stage rows: 44 / 61
- valid UAV arrival rows: 405 / 488
- negative completion or arrival times: 0
- distinct configuration checksums: 1
- distinct prompts per task: task_a_simple=1, task_b_sequential=1, task_c_grouped=1, task_d_dense=1, task_e_mixed=1
- the configured model does not support a fixed seed; model output may remain stochastic.
- invalid rows remain in the CSV files with explicit reasons; they are not imputed.

Outliers are flagged with the frozen 1.5×IQR rule and are not removed.
The legacy and v2 batches are not pooled because parser and stability semantics differ.
