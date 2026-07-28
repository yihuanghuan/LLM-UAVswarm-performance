#include "ladrc_controller/iapf_core.hpp"

#include <algorithm>
#include <cmath>
#include <limits>
#include <stdexcept>

namespace ladrc_controller
{

AvoidanceMode parseAvoidanceMode(const std::string & value)
{
  if (value == "off") {
    return AvoidanceMode::OFF;
  }
  if (value == "classic_position") {
    return AvoidanceMode::CLASSIC_POSITION;
  }
  if (value == "iapf_position") {
    return AvoidanceMode::IAPF_POSITION;
  }
  if (value == "iapf_dual") {
    return AvoidanceMode::IAPF_DUAL;
  }
  throw std::invalid_argument("invalid avoidance_mode: " + value);
}

EscapeMode parseEscapeMode(const std::string & value)
{
  if (value == "none") {
    return EscapeMode::NONE;
  }
  if (value == "fixed_positive_z") {
    return EscapeMode::FIXED_POSITIVE_Z;
  }
  if (value == "id_order") {
    return EscapeMode::ID_ORDER;
  }
  throw std::invalid_argument("invalid iapf_escape_mode: " + value);
}

std::string toString(AvoidanceMode mode)
{
  switch (mode) {
    case AvoidanceMode::OFF:
      return "off";
    case AvoidanceMode::CLASSIC_POSITION:
      return "classic_position";
    case AvoidanceMode::IAPF_POSITION:
      return "iapf_position";
    case AvoidanceMode::IAPF_DUAL:
      return "iapf_dual";
  }
  throw std::invalid_argument("unknown avoidance mode");
}

Eigen::Vector3d clampNorm(
  const Eigen::Vector3d & value, double limit, bool * saturated)
{
  const double norm = value.norm();
  const bool should_saturate = limit > 0.0 && norm > limit;
  if (saturated != nullptr) {
    *saturated = should_saturate;
  }
  if (!should_saturate) {
    return value;
  }
  return value * (limit / norm);
}

IAPFResult computeIAPF(
  const Eigen::Vector3d & own_position,
  uint8_t self_uav_id,
  const std::vector<NeighborSample> & neighbors,
  AvoidanceMode avoidance_mode,
  EscapeMode escape_mode,
  const IAPFParameters & parameters,
  double safety_factor)
{
  if (
    parameters.safe_distance <= 0.0 ||
    parameters.distance_epsilon <= 0.0 ||
    parameters.distance_epsilon >= parameters.safe_distance ||
    parameters.repulsion_gain < 0.0 ||
    parameters.position_gain < 0.0 ||
    parameters.position_limit < 0.0 ||
    parameters.acceleration_gain < 0.0 ||
    parameters.acceleration_limit < 0.0 ||
    parameters.escape_gain < 0.0)
  {
    throw std::invalid_argument("invalid IAPF parameter range");
  }
  IAPFResult result;
  for (const auto & neighbor : neighbors) {
    if (!neighbor.fresh) {
      ++result.stale_neighbor_count;
      continue;
    }
    ++result.valid_neighbor_count;
    const Eigen::Vector3d separation = own_position - neighbor.position;
    const double distance = separation.norm();
    if (!result.has_nearest_neighbor || distance < result.nearest_neighbor_distance) {
      result.has_nearest_neighbor = true;
      result.nearest_neighbor_id = neighbor.id;
      result.nearest_neighbor_distance = distance;
    }

    if (
      avoidance_mode == AvoidanceMode::OFF || safety_factor <= 0.0 ||
      distance >= parameters.safe_distance)
    {
      continue;
    }

    result.active = true;
    const double effective_distance =
      std::max(distance, parameters.distance_epsilon);
    Eigen::Vector3d direction;
    if (distance > std::numeric_limits<double>::epsilon()) {
      direction = separation / distance;
    } else {
      const double sign = self_uav_id < neighbor.id ? 1.0 : -1.0;
      direction = Eigen::Vector3d(sign, 0.0, 0.0);
    }

    const double magnitude =
      parameters.repulsion_gain *
      (1.0 / effective_distance - 1.0 / parameters.safe_distance) /
      (effective_distance * effective_distance);
    Eigen::Vector3d force = direction * magnitude;

    if (avoidance_mode != AvoidanceMode::CLASSIC_POSITION) {
      if (escape_mode == EscapeMode::FIXED_POSITIVE_Z) {
        force.z() += magnitude * parameters.escape_gain;
      } else if (escape_mode == EscapeMode::ID_ORDER) {
        const double sign = self_uav_id < neighbor.id ? 1.0 : -1.0;
        force.z() += sign * magnitude * parameters.escape_gain;
      }
    }
    result.raw_repulsion += force;
  }

  result.raw_repulsion *= safety_factor;
  if (avoidance_mode == AvoidanceMode::OFF) {
    result.active = false;
    result.raw_repulsion.setZero();
  }
  result.position_offset = clampNorm(
    parameters.position_gain * result.raw_repulsion,
    parameters.position_limit, &result.position_saturated);
  if (avoidance_mode == AvoidanceMode::IAPF_DUAL) {
    result.acceleration_offset = clampNorm(
      parameters.acceleration_gain * result.raw_repulsion,
      parameters.acceleration_limit, &result.acceleration_saturated);
  }
  return result;
}

}  // namespace ladrc_controller
