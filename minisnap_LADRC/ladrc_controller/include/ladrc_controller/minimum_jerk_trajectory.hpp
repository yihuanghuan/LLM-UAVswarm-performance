#ifndef LADRC_CONTROLLER__MINIMUM_JERK_TRAJECTORY_HPP_
#define LADRC_CONTROLLER__MINIMUM_JERK_TRAJECTORY_HPP_

#include <algorithm>
#include <cmath>
#include <stdexcept>
#include <string>

namespace ladrc_controller
{

enum class TrajectoryProfile
{
  STEP,
  LINEAR,
  TRAPEZOIDAL,
  MINIMUM_JERK
};

inline TrajectoryProfile trajectoryProfileFromString(const std::string & name)
{
  if (name == "step") {
    return TrajectoryProfile::STEP;
  }
  if (name == "linear") {
    return TrajectoryProfile::LINEAR;
  }
  if (name == "trapezoidal") {
    return TrajectoryProfile::TRAPEZOIDAL;
  }
  if (name == "minimum_jerk") {
    return TrajectoryProfile::MINIMUM_JERK;
  }
  throw std::invalid_argument(
          "trajectory_profile must be one of: step, linear, trapezoidal, minimum_jerk");
}

inline const char * trajectoryProfileName(TrajectoryProfile profile)
{
  switch (profile) {
    case TrajectoryProfile::STEP:
      return "step";
    case TrajectoryProfile::LINEAR:
      return "linear";
    case TrajectoryProfile::TRAPEZOIDAL:
      return "trapezoidal";
    case TrajectoryProfile::MINIMUM_JERK:
      return "minimum_jerk";
  }
  return "unknown";
}

/**
 * One-dimensional point-to-point reference trajectory.
 *
 * The operational setpoint is always finite. Mathematical discontinuities at
 * the boundaries of step, linear, and trapezoidal profiles are represented in
 * the experiment metadata rather than injected into the flight controller.
 */
class MinimumJerkTrajectory
{
public:
  struct TrajectoryPoint
  {
    double position;
    double velocity;
    double acceleration;
    double jerk;
  };

  MinimumJerkTrajectory()
  : p0_(0.0), pT_(0.0), T_(1e-3), dp_(0.0),
    a0_(0.0), a1_(0.0), a2_(0.0), a3_(0.0), a4_(0.0), a5_(0.0),
    profile_(TrajectoryProfile::MINIMUM_JERK), initialized_(false)
  {}

  void initialize(
    double start_pos, double end_pos, double duration,
    TrajectoryProfile profile = TrajectoryProfile::MINIMUM_JERK)
  {
    p0_ = start_pos;
    pT_ = end_pos;
    T_ = std::max(duration, 1e-3);
    dp_ = pT_ - p0_;
    profile_ = profile;

    const double T2 = T_ * T_;
    const double T3 = T2 * T_;
    const double T4 = T3 * T_;
    const double T5 = T4 * T_;
    a0_ = p0_;
    a1_ = 0.0;
    a2_ = 0.0;
    a3_ = 10.0 * dp_ / T3;
    a4_ = -15.0 * dp_ / T4;
    a5_ = 6.0 * dp_ / T5;
    initialized_ = true;
  }

  TrajectoryPoint evaluate(double t) const
  {
    if (!initialized_) {
      return {p0_, 0.0, 0.0, 0.0};
    }

    const double tc = std::clamp(t, 0.0, T_);
    switch (profile_) {
      case TrajectoryProfile::STEP:
        return {t <= 0.0 ? p0_ : pT_, 0.0, 0.0, 0.0};
      case TrajectoryProfile::LINEAR:
        if (tc >= T_) {
          return {pT_, 0.0, 0.0, 0.0};
        }
        return {p0_ + dp_ * tc / T_, dp_ / T_, 0.0, 0.0};
      case TrajectoryProfile::TRAPEZOIDAL:
        return evaluateTrapezoidal(tc);
      case TrajectoryProfile::MINIMUM_JERK:
        return evaluateMinimumJerk(tc);
    }
    return {p0_, 0.0, 0.0, 0.0};
  }

  bool isFinished(double t) const {return t >= T_;}
  double getDuration() const {return T_;}
  double getStartPosition() const {return p0_;}
  double getEndPosition() const {return pT_;}
  TrajectoryProfile getProfile() const {return profile_;}
  bool isInitialized() const {return initialized_;}

private:
  TrajectoryPoint evaluateTrapezoidal(double t) const
  {
    const double accel_time = T_ / 4.0;
    const double cruise_end = 3.0 * T_ / 4.0;
    const double accel = dp_ / (accel_time * (T_ - accel_time));
    const double peak_velocity = accel * accel_time;

    if (t <= accel_time) {
      return {
        p0_ + 0.5 * accel * t * t,
        accel * t,
        accel,
        0.0};
    }
    if (t <= cruise_end) {
      return {
        p0_ + 0.5 * accel * accel_time * accel_time +
        peak_velocity * (t - accel_time),
        peak_velocity,
        0.0,
        0.0};
    }
    if (t >= T_) {
      return {pT_, 0.0, 0.0, 0.0};
    }
    const double decel_t = t - cruise_end;
    return {
      p0_ + 0.5 * accel * accel_time * accel_time +
      peak_velocity * (T_ / 2.0) +
      peak_velocity * decel_t - 0.5 * accel * decel_t * decel_t,
      peak_velocity - accel * decel_t,
      -accel,
      0.0};
  }

  TrajectoryPoint evaluateMinimumJerk(double t) const
  {
    const double t2 = t * t;
    const double t3 = t2 * t;
    const double t4 = t3 * t;
    return {
      a0_ + a1_ * t + a2_ * t2 + a3_ * t3 + a4_ * t4 + a5_ * t4 * t,
      a1_ + 2.0 * a2_ * t + 3.0 * a3_ * t2 + 4.0 * a4_ * t3 + 5.0 * a5_ * t4,
      2.0 * a2_ + 6.0 * a3_ * t + 12.0 * a4_ * t2 + 20.0 * a5_ * t3,
      6.0 * a3_ + 24.0 * a4_ * t + 60.0 * a5_ * t2};
  }

  double p0_;
  double pT_;
  double T_;
  double dp_;
  double a0_;
  double a1_;
  double a2_;
  double a3_;
  double a4_;
  double a5_;
  TrajectoryProfile profile_;
  bool initialized_;
};

}  // namespace ladrc_controller

#endif  // LADRC_CONTROLLER__MINIMUM_JERK_TRAJECTORY_HPP_
