#!/usr/bin/env bash
# 统一采集论文实验所需的多机 ROS 2 话题。

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"

EXPERIMENT_ID="${1:-$(date +%Y%m%d_%H%M%S)}"
OUTPUT_DIR="${REPO_ROOT}/experiments/logs/rosbags/${EXPERIMENT_ID}"
TOPIC_REGEX='^(/uav[0-9]+/(odom|status|trajectory_metrics|control_adaptation|iapf_debug|swarm_command)|/px4_[0-9]+/fmu/out/(vehicle_odometry|vehicle_status)|/fmu/out/vehicle_odometry|/gazebo/performance_metrics|/clock)$'

if ! command -v ros2 >/dev/null 2>&1; then
  echo "错误: 未找到 ros2，请先 source ROS 2 环境。" >&2
  exit 1
fi

mkdir -p "${OUTPUT_DIR}"

echo "实验编号: ${EXPERIMENT_ID}"
echo "输出目录: ${OUTPUT_DIR}"
echo "记录话题正则: ${TOPIC_REGEX}"

exec ros2 bag record \
  --output "${OUTPUT_DIR}" \
  --regex "${TOPIC_REGEX}"
