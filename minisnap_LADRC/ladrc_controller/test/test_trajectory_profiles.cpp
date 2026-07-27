#include <gtest/gtest.h>

#include <cmath>
#include <stdexcept>

#include "ladrc_controller/minimum_jerk_trajectory.hpp"

using ladrc_controller::MinimumJerkTrajectory;
using ladrc_controller::TrajectoryProfile;
using ladrc_controller::trajectoryProfileFromString;

TEST(TrajectoryProfiles, ParsesSupportedNames)
{
  EXPECT_EQ(trajectoryProfileFromString("step"), TrajectoryProfile::STEP);
  EXPECT_EQ(trajectoryProfileFromString("linear"), TrajectoryProfile::LINEAR);
  EXPECT_EQ(
    trajectoryProfileFromString("minimum_jerk"),
    TrajectoryProfile::MINIMUM_JERK);
  EXPECT_THROW(trajectoryProfileFromString("trapezoidal"), std::invalid_argument);
}

TEST(TrajectoryProfiles, RejectsNonPositiveDuration)
{
  MinimumJerkTrajectory trajectory;
  EXPECT_THROW(
    trajectory.initialize(0.0, 1.0, 0.0, TrajectoryProfile::LINEAR),
    std::invalid_argument);
}

TEST(TrajectoryProfiles, StepIsFiniteAndImmediate)
{
  MinimumJerkTrajectory trajectory;
  trajectory.initialize(2.0, 5.0, 4.0, TrajectoryProfile::STEP);
  const auto start = trajectory.evaluate(0.0);
  const auto after = trajectory.evaluate(0.01);
  EXPECT_DOUBLE_EQ(start.position, 2.0);
  EXPECT_DOUBLE_EQ(after.position, 5.0);
  EXPECT_DOUBLE_EQ(after.velocity, 0.0);
  EXPECT_TRUE(std::isfinite(after.acceleration));
}

TEST(TrajectoryProfiles, LinearClampsAtTarget)
{
  MinimumJerkTrajectory trajectory;
  trajectory.initialize(0.0, 8.0, 4.0, TrajectoryProfile::LINEAR);
  EXPECT_DOUBLE_EQ(trajectory.evaluate(2.0).position, 4.0);
  EXPECT_DOUBLE_EQ(trajectory.evaluate(2.0).velocity, 2.0);
  EXPECT_DOUBLE_EQ(trajectory.evaluate(5.0).position, 8.0);
  EXPECT_DOUBLE_EQ(trajectory.evaluate(5.0).velocity, 0.0);
}

TEST(TrajectoryProfiles, MinimumJerkHasZeroEndpointDerivatives)
{
  MinimumJerkTrajectory trajectory;
  trajectory.initialize(-1.0, 3.0, 5.0, TrajectoryProfile::MINIMUM_JERK);
  const auto start = trajectory.evaluate(0.0);
  const auto end = trajectory.evaluate(5.0);
  EXPECT_NEAR(start.position, -1.0, 1e-12);
  EXPECT_NEAR(start.velocity, 0.0, 1e-12);
  EXPECT_NEAR(start.acceleration, 0.0, 1e-12);
  EXPECT_NEAR(end.position, 3.0, 1e-12);
  EXPECT_NEAR(end.velocity, 0.0, 1e-12);
  EXPECT_NEAR(end.acceleration, 0.0, 1e-12);
  EXPECT_TRUE(trajectory.isFinished(5.0));
}
