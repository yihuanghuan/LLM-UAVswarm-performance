#include <gtest/gtest.h>

#include <cmath>
#include <stdexcept>

#include "ladrc_controller/minimum_jerk_trajectory.hpp"

using ladrc_controller::MinimumJerkTrajectory;
using ladrc_controller::TrajectoryProfile;

TEST(TrajectoryProfiles, MinimumJerkBoundaryConditions)
{
  MinimumJerkTrajectory trajectory;
  trajectory.initialize(2.0, 12.0, 8.0, TrajectoryProfile::MINIMUM_JERK);
  const auto start = trajectory.evaluate(0.0);
  const auto end = trajectory.evaluate(8.0);
  EXPECT_DOUBLE_EQ(start.position, 2.0);
  EXPECT_NEAR(start.velocity, 0.0, 1e-12);
  EXPECT_NEAR(start.acceleration, 0.0, 1e-12);
  EXPECT_NEAR(end.position, 12.0, 1e-10);
  EXPECT_NEAR(end.velocity, 0.0, 1e-10);
  EXPECT_NEAR(end.acceleration, 0.0, 1e-10);
  EXPECT_TRUE(std::isfinite(start.jerk));
  EXPECT_TRUE(std::isfinite(end.jerk));
}

TEST(TrajectoryProfiles, TrapezoidalIsContinuousAtSwitches)
{
  MinimumJerkTrajectory trajectory;
  trajectory.initialize(0.0, 10.0, 8.0, TrajectoryProfile::TRAPEZOIDAL);
  constexpr double epsilon = 1e-8;
  for (const double boundary : {2.0, 6.0}) {
    const auto before = trajectory.evaluate(boundary - epsilon);
    const auto after = trajectory.evaluate(boundary + epsilon);
    EXPECT_NEAR(before.position, after.position, 1e-6);
    EXPECT_NEAR(before.velocity, after.velocity, 1e-6);
  }
}

TEST(TrajectoryProfiles, OperationalSetpointsAreFinite)
{
  for (const auto profile : {
      TrajectoryProfile::STEP,
      TrajectoryProfile::LINEAR,
      TrajectoryProfile::TRAPEZOIDAL,
      TrajectoryProfile::MINIMUM_JERK})
  {
    MinimumJerkTrajectory trajectory;
    trajectory.initialize(0.0, 10.0, 8.0, profile);
    for (const double time : {0.0, 0.02, 2.0, 6.0, 8.0, 10.0}) {
      const auto point = trajectory.evaluate(time);
      EXPECT_TRUE(std::isfinite(point.position));
      EXPECT_TRUE(std::isfinite(point.velocity));
      EXPECT_TRUE(std::isfinite(point.acceleration));
      EXPECT_TRUE(std::isfinite(point.jerk));
    }
  }
}

TEST(TrajectoryProfiles, RejectsUnknownProfile)
{
  EXPECT_THROW(
    ladrc_controller::trajectoryProfileFromString("cubic"),
    std::invalid_argument);
}
