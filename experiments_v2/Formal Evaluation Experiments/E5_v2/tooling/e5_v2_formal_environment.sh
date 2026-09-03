#!/usr/bin/env bash
set -eo pipefail

# Infrastructure-only environment construction for E5-v2 formal tooling v2.
# It preserves the pinned semantic interpreter while exposing both ROS Humble
# and the frozen E5-v2 install/tooling trees to that interpreter.
source /opt/ros/humble/setup.bash
source /home/yihuang/learning/LLM_swarm_ws/e5_v2_build/install/setup.bash
set -u

e5_v2_repo=/home/yihuang/learning/LLM_swarm_ws/e5_v2_design_worktree
e5_v2_tooling="${e5_v2_repo}/experiments_v2/Formal Evaluation Experiments/E5_v2/tooling"
e5_v2_existing_pythonpath="${PYTHONPATH:-}"
export PYTHONPATH="${e5_v2_tooling}:${e5_v2_repo}/location_allocate:${e5_v2_repo}/lfs_policy:${e5_v2_existing_pythonpath}"

exec /home/yihuang/learning/LLM_swarm_ws/llm_env/bin/python "$@"
