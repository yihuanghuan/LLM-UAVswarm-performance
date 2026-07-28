#ifndef LADRC_CONTROLLER__IAPF_CORE_HPP_
#define LADRC_CONTROLLER__IAPF_CORE_HPP_

#include <cstdint>
#include <string>
#include <vector>

#include <Eigen/Dense>

namespace ladrc_controller
{

enum class AvoidanceMode
{
  OFF,
  CLASSIC_POSITION,
  IAPF_POSITION,
  IAPF_DUAL,
};

enum class EscapeMode
{
  NONE,
  FIXED_POSITIVE_Z,
  ID_ORDER,
};

struct IAPFParameters
{
  double safe_distance{1.5};
  double repulsion_gain{25.0};
  double distance_epsilon{0.1};
  double position_gain{0.05};
  double position_limit{0.5};
  double acceleration_gain{0.3};
  double acceleration_limit{2.0};
  double escape_gain{0.05};
};

struct NeighborSample
{
  uint8_t id{0};
  Eigen::Vector3d position{Eigen::Vector3d::Zero()};
  bool fresh{false};
};

struct IAPFResult
{
  Eigen::Vector3d raw_repulsion{Eigen::Vector3d::Zero()};
  Eigen::Vector3d position_offset{Eigen::Vector3d::Zero()};
  Eigen::Vector3d acceleration_offset{Eigen::Vector3d::Zero()};
  bool active{false};
  bool position_saturated{false};
  bool acceleration_saturated{false};
  bool has_nearest_neighbor{false};
  uint8_t nearest_neighbor_id{0};
  double nearest_neighbor_distance{-1.0};
  uint16_t valid_neighbor_count{0};
  uint16_t stale_neighbor_count{0};
};

AvoidanceMode parseAvoidanceMode(const std::string & value);
EscapeMode parseEscapeMode(const std::string & value);
std::string toString(AvoidanceMode mode);
Eigen::Vector3d clampNorm(
  const Eigen::Vector3d & value, double limit, bool * saturated = nullptr);
IAPFResult computeIAPF(
  const Eigen::Vector3d & own_position,
  uint8_t self_uav_id,
  const std::vector<NeighborSample> & neighbors,
  AvoidanceMode avoidance_mode,
  EscapeMode escape_mode,
  const IAPFParameters & parameters,
  double safety_factor);

}  // namespace ladrc_controller

#endif  // LADRC_CONTROLLER__IAPF_CORE_HPP_
