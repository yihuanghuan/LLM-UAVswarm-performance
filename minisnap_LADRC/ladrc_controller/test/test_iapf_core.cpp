#include <gtest/gtest.h>

#include "ladrc_controller/iapf_core.hpp"

using ladrc_controller::AvoidanceMode;
using ladrc_controller::EscapeMode;
using ladrc_controller::IAPFParameters;
using ladrc_controller::NeighborSample;

TEST(IAPFCore, ParsesOnlySupportedModes)
{
  EXPECT_EQ(ladrc_controller::parseAvoidanceMode("off"), AvoidanceMode::OFF);
  EXPECT_THROW(ladrc_controller::parseAvoidanceMode("unknown"), std::invalid_argument);
  EXPECT_THROW(ladrc_controller::parseEscapeMode("unknown"), std::invalid_argument);
}

TEST(IAPFCore, ClassicHasNoEscapeOrAcceleration)
{
  IAPFParameters parameters;
  const auto result = ladrc_controller::computeIAPF(
    Eigen::Vector3d::Zero(), 1,
    {{2, Eigen::Vector3d(1.0, 0.0, 0.0), true}},
    AvoidanceMode::CLASSIC_POSITION, EscapeMode::ID_ORDER, parameters, 1.0);
  EXPECT_TRUE(result.active);
  EXPECT_DOUBLE_EQ(result.raw_repulsion.z(), 0.0);
  EXPECT_DOUBLE_EQ(result.acceleration_offset.norm(), 0.0);
}

TEST(IAPFCore, IdOrderEscapeIsPairwiseOpposite)
{
  IAPFParameters parameters;
  const auto first = ladrc_controller::computeIAPF(
    Eigen::Vector3d(-0.5, 0.0, 0.0), 1,
    {{2, Eigen::Vector3d(0.5, 0.0, 0.0), true}},
    AvoidanceMode::IAPF_DUAL, EscapeMode::ID_ORDER, parameters, 1.0);
  const auto second = ladrc_controller::computeIAPF(
    Eigen::Vector3d(0.5, 0.0, 0.0), 2,
    {{1, Eigen::Vector3d(-0.5, 0.0, 0.0), true}},
    AvoidanceMode::IAPF_DUAL, EscapeMode::ID_ORDER, parameters, 1.0);
  EXPECT_NEAR((first.raw_repulsion + second.raw_repulsion).norm(), 0.0, 1e-9);
}

TEST(IAPFCore, CoincidentNeighborsRemainFiniteAndSaturate)
{
  IAPFParameters parameters;
  const auto result = ladrc_controller::computeIAPF(
    Eigen::Vector3d::Zero(), 1,
    {{2, Eigen::Vector3d::Zero(), true}},
    AvoidanceMode::IAPF_DUAL, EscapeMode::ID_ORDER, parameters, 1.0);
  EXPECT_TRUE(result.raw_repulsion.allFinite());
  EXPECT_TRUE(result.position_saturated);
  EXPECT_TRUE(result.acceleration_saturated);
  EXPECT_NEAR(result.position_offset.norm(), parameters.position_limit, 1e-9);
  EXPECT_NEAR(result.acceleration_offset.norm(), parameters.acceleration_limit, 1e-9);
}

TEST(IAPFCore, StaleNeighborsDoNotRepel)
{
  IAPFParameters parameters;
  const auto result = ladrc_controller::computeIAPF(
    Eigen::Vector3d::Zero(), 1,
    {{2, Eigen::Vector3d(0.5, 0.0, 0.0), false}},
    AvoidanceMode::IAPF_DUAL, EscapeMode::ID_ORDER, parameters, 1.0);
  EXPECT_FALSE(result.active);
  EXPECT_EQ(result.valid_neighbor_count, 0);
  EXPECT_EQ(result.stale_neighbor_count, 1);
  EXPECT_DOUBLE_EQ(result.raw_repulsion.norm(), 0.0);
}

TEST(IAPFCore, RejectsUnsafeParameterRanges)
{
  IAPFParameters parameters;
  parameters.distance_epsilon = parameters.safe_distance;
  EXPECT_THROW(
    ladrc_controller::computeIAPF(
      Eigen::Vector3d::Zero(), 1, {}, AvoidanceMode::IAPF_DUAL,
      EscapeMode::ID_ORDER, parameters, 1.0),
    std::invalid_argument);
}
