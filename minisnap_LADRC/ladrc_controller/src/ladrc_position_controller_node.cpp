#include <rclcpp/rclcpp.hpp>
#include <px4_msgs/msg/vehicle_odometry.hpp>
#include <px4_msgs/msg/offboard_control_mode.hpp>
#include <px4_msgs/msg/trajectory_setpoint.hpp>
#include <px4_msgs/msg/vehicle_command.hpp>
#include <px4_msgs/msg/vehicle_control_mode.hpp>
#include <uav_swarm_interfaces/msg/uav_swarm_command.hpp>
#include <uav_swarm_interfaces/msg/uav_execution_command.hpp>
#include <uav_swarm_interfaces/msg/uav_status.hpp>
#include <uav_swarm_interfaces/msg/trajectory_metrics.hpp>
#include <uav_swarm_interfaces/msg/control_adaptation_log.hpp>
#include <uav_swarm_interfaces/msg/iapf_debug.hpp>
#include <uav_swarm_interfaces/msg/control_tracking_debug.hpp>
#include <geometry_msgs/msg/point.hpp>
#include <nav_msgs/msg/odometry.hpp>
#include "ladrc_controller/ladrc_core.hpp"
#include "ladrc_controller/control_setpoint.hpp"
#include "ladrc_controller/iapf_core.hpp"
#include "ladrc_controller/minimum_jerk_trajectory.hpp"
#include "ladrc_controller/execution_profile_guard.hpp"
#include "ladrc_controller/swarm_state_builder.hpp"
#include <cmath>
#include <chrono>
#include <atomic>
#include <algorithm>
#include <filesystem>
#include <fstream>
#include <iomanip>
#include <limits>
#include <string>
#include <unordered_map>
#include <Eigen/Dense>

using namespace std::chrono_literals;

// 自动起飞状态机
enum class FlightState
{
  INIT,
  ARMING,
  SETTING_OFFBOARD,
  RUNNING_TRAJECTORY
};

class LADRCPositionControllerNode : public rclcpp::Node
{
  struct NeighborState
  {
    Eigen::Vector3d position;
    Eigen::Vector3d velocity;
    rclcpp::Time receive_time;
    bool iapf_active{false};
  };

public:
  LADRCPositionControllerNode()
      : Node("ladrc_position_controller")
  {
    // 声明参数
    this->declare_parameter("control_frequency", 50.0);
    this->declare_parameter("control_mode", "ladrc_acceleration");
    this->declare_parameter("idle_hover_safety_factor", 1.0);
    this->declare_parameter("omega_o_x", 15.0);
    this->declare_parameter("omega_o_y", 15.0);
    this->declare_parameter("omega_o_z", 15.0);
    this->declare_parameter("omega_c_x", 8.0);
    this->declare_parameter("omega_c_y", 8.0);
    this->declare_parameter("omega_c_z", 8.0);
    this->declare_parameter("b0_x", 1.0);
    this->declare_parameter("b0_y", 1.0);
    this->declare_parameter("b0_z", 1.0);
    this->declare_parameter("max_velocity", 5.0);
    this->declare_parameter("max_acceleration_x", 3.0);
    this->declare_parameter("max_acceleration_y", 3.0);
    this->declare_parameter("max_acceleration_z", 3.0);
    this->declare_parameter("enable_execution_profiles", false);
    this->declare_parameter("execution_profile_smoothing_alpha", -1.0);
    this->declare_parameter("execution_profile_omega_c_min", std::vector<double>{});
    this->declare_parameter("execution_profile_omega_c_max", std::vector<double>{});
    this->declare_parameter("execution_profile_omega_o_min", std::vector<double>{});
    this->declare_parameter("execution_profile_omega_o_max", std::vector<double>{});
    this->declare_parameter("execution_profile_velocity_max", -1.0);
    this->declare_parameter("execution_profile_acceleration_max", -1.0);
    this->declare_parameter("execution_profile_jerk_max", -1.0);
    this->declare_parameter("execution_profile_iapf_enter_min", -1.0);
    this->declare_parameter("execution_profile_iapf_enter_max", -1.0);
    this->declare_parameter("execution_profile_iapf_exit_max", -1.0);
    this->declare_parameter("execution_profile_iapf_repulsion_max", -1.0);

    // Gazebo 多机 spawn 偏移量（sitl_multiple_run.sh 默认 Y=3*instance）
    this->declare_parameter("enu_offset_x", 0.0);
    this->declare_parameter("enu_offset_y", 0.0);
    this->declare_parameter("enu_offset_z", 0.0);
    this->declare_parameter("px4_target_system", 0);

    // [Phase 4] IAPF 避障参数
    this->declare_parameter("avoidance_mode", "iapf_dual");
    this->declare_parameter("iapf_safe_distance", 1.0);
    this->declare_parameter("iapf_violation_distance", 1.0);
    this->declare_parameter("iapf_enter_distance", 1.5);
    this->declare_parameter("iapf_exit_distance", 1.65);
    this->declare_parameter("iapf_filter_alpha", 0.20);
    this->declare_parameter("iapf_repulsion_gain", 1.0);
    this->declare_parameter("enable_iapf_accel_feedforward", true);
    this->declare_parameter("iapf_escape_mode", "id_order");
    this->declare_parameter("iapf_escape_gain", 0.05);
    this->declare_parameter("iapf_distance_epsilon", 0.10);
    this->declare_parameter("iapf_position_gain", 0.05);
    this->declare_parameter("iapf_position_limit", 0.50);
    this->declare_parameter("iapf_accel_gain", 0.3);
    this->declare_parameter("iapf_accel_limit", 2.0);
    this->declare_parameter("neighbor_timeout", 0.20);
    this->declare_parameter("neighbor_uav_ids", std::vector<int64_t>{});
    this->declare_parameter(
        "control_adaptation_log_path",
        defaultControlAdaptationLogPath());

    const auto & parameter_overrides =
      this->get_node_parameters_interface()->get_parameter_overrides();
    const bool avoidance_overridden =
      parameter_overrides.count("avoidance_mode") > 0;
    const bool legacy_overridden =
      parameter_overrides.count("enable_iapf_accel_feedforward") > 0;
    const bool safe_distance_overridden =
      parameter_overrides.count("iapf_safe_distance") > 0;
    const bool enter_distance_overridden =
      parameter_overrides.count("iapf_enter_distance") > 0;
    enter_distance_from_legacy_ =
      safe_distance_overridden && !enter_distance_overridden;
    avoidance_mode_from_legacy_ = legacy_overridden && !avoidance_overridden;
    if (legacy_overridden && avoidance_overridden)
    {
      RCLCPP_WARN(
        this->get_logger(),
        "avoidance_mode 与 enable_iapf_accel_feedforward 同时设置；"
        "优先使用 avoidance_mode，旧参数已弃用");
    }
    else if (avoidance_mode_from_legacy_)
    {
      RCLCPP_WARN(
        this->get_logger(),
        "enable_iapf_accel_feedforward 已弃用；请改用 avoidance_mode");
    }
    if (safe_distance_overridden && enter_distance_overridden)
    {
      RCLCPP_WARN(
        this->get_logger(),
        "iapf_safe_distance 与 iapf_enter_distance 同时设置；"
        "优先使用 iapf_enter_distance");
    }
    else if (enter_distance_from_legacy_)
    {
      RCLCPP_WARN(
        this->get_logger(),
        "iapf_safe_distance 已弃用；请改用 iapf_enter_distance");
    }
    (void)currentAvoidanceMode();
    (void)ladrc_controller::parseEscapeMode(
      this->get_parameter("iapf_escape_mode").as_string());

    // 获取参数
    double control_freq = this->get_parameter("control_frequency").as_double();
    dt_ = 1.0 / control_freq;
    control_mode_ = ladrc_controller::parseControlMode(
      this->get_parameter("control_mode").as_string());
    const double idle_hover_safety_factor =
      this->get_parameter("idle_hover_safety_factor").as_double();
    if (!std::isfinite(idle_hover_safety_factor) || idle_hover_safety_factor < 0.0)
    {
      throw std::invalid_argument(
        "idle_hover_safety_factor must be finite and non-negative");
    }

    // 初始化 LADRC 控制器
    initializeControllers();

    // --- [Phase 1] 订阅 swarm_command（相对话题，自动拼接到命名空间） ---
    swarm_command_sub_ = this->create_subscription<uav_swarm_interfaces::msg::UAVSwarmCommand>(
        "swarm_command", rclcpp::QoS(10),
        std::bind(&LADRCPositionControllerNode::swarmCommandCallback, this, std::placeholders::_1));
    execution_command_sub_ =
      this->create_subscription<uav_swarm_interfaces::msg::UAVExecutionCommand>(
        "execution_command", rclcpp::QoS(10),
        std::bind(
          &LADRCPositionControllerNode::executionCommandCallback,
          this, std::placeholders::_1));

    odom_sub_ = this->create_subscription<px4_msgs::msg::VehicleOdometry>(
        "fmu/out/vehicle_odometry",
        rclcpp::SensorDataQoS(),
        std::bind(&LADRCPositionControllerNode::odomCallback, this, std::placeholders::_1));

    // 从命名空间提取自身 UAV ID（例如 /uav3 → 3）
    std::string ns = this->get_namespace();
    size_t uav_pos = ns.find("/uav");
    if (uav_pos != std::string::npos)
    {
      std::string id_str = ns.substr(uav_pos + 4);  // "/uav" 后 4 个字符
      // 去掉可能的尾部斜杠
      while (!id_str.empty() && id_str.back() == '/') id_str.pop_back();
      try { self_uav_id_ = static_cast<uint8_t>(std::stoi(id_str)); }
      catch (...) { self_uav_id_ = 0; }
    }

    // --- [Phase 4] 邻居无人机 Odometry 订阅 ---
    auto neighbor_ids = this->get_parameter("neighbor_uav_ids").as_integer_array();
    for (auto id : neighbor_ids)
    {
      uint8_t neighbor_id = static_cast<uint8_t>(id);
      if (neighbor_id == 0 || neighbor_id == self_uav_id_) continue;  // 跳过无效 ID 和自身
      configured_neighbor_ids_.push_back(neighbor_id);

      auto callback = [this, neighbor_id](const px4_msgs::msg::VehicleOdometry::SharedPtr msg) {
        // 存入邻居位置 map：全局 ENU（本地 + spawn 偏移 Y=3*id）
        const auto previous = neighbor_states_.find(neighbor_id);
        const bool was_active =
          previous != neighbor_states_.end() && previous->second.iapf_active;
        neighbor_states_[neighbor_id] = NeighborState{
          Eigen::Vector3d(
            msg->position[1],
            msg->position[0] + 3.0 * neighbor_id,
            -msg->position[2]),
          Eigen::Vector3d(
            msg->velocity[1],
            msg->velocity[0],
            -msg->velocity[2]),
          this->now(),
          was_active};
      };

      auto sub = this->create_subscription<px4_msgs::msg::VehicleOdometry>(
          "/uav" + std::to_string(neighbor_id) + "/fmu/out/vehicle_odometry",
          rclcpp::SensorDataQoS(),
          callback);
      neighbor_subs_.push_back(sub);
    }
    RCLCPP_INFO(this->get_logger(), "已创建 %zu 个邻居 Odom 订阅", neighbor_subs_.size());

    // --- [Phase 1] 新增状态发布器 ---
    status_pub_ = this->create_publisher<uav_swarm_interfaces::msg::UAVStatus>(
        "status", 10);

    // 低频 ENU 位置发布器（供调度层获取真实坐标）
    odom_pub_ = this->create_publisher<geometry_msgs::msg::Point>("odom", 10);
    swarm_state_pub_ = this->create_publisher<nav_msgs::msg::Odometry>(
        "swarm_state", rclcpp::SensorDataQoS());

    // 低频轨迹指标发布器（供外部订阅查看 Minimum Jerk 编译结果）
    trajectory_metrics_pub_ =
        this->create_publisher<uav_swarm_interfaces::msg::TrajectoryMetrics>(
            "trajectory_metrics", 10);

    control_adaptation_pub_ =
        this->create_publisher<uav_swarm_interfaces::msg::ControlAdaptationLog>(
            "control_adaptation", 10);
    iapf_debug_pub_ =
        this->create_publisher<uav_swarm_interfaces::msg::IAPFDebug>(
            "iapf_debug", 10);
    control_tracking_debug_pub_ =
        this->create_publisher<uav_swarm_interfaces::msg::ControlTrackingDebug>(
            "control_tracking_debug", rclcpp::SensorDataQoS());

    // Publishers — [Phase 1] 使用相对话题以支持命名空间
    // 必须使用 SensorDataQoS (Best Effort)，PX4 XRCE-DDS 桥接器默认使用 Best Effort 订阅
    // 使用默认 Reliable QoS 会导致静默无法匹配，收不到数据
    offboard_mode_pub_ = this->create_publisher<px4_msgs::msg::OffboardControlMode>(
        "fmu/in/offboard_control_mode", rclcpp::SensorDataQoS());

    trajectory_pub_ = this->create_publisher<px4_msgs::msg::TrajectorySetpoint>(
        "fmu/in/trajectory_setpoint", rclcpp::SensorDataQoS());

    vehicle_command_pub_ = this->create_publisher<px4_msgs::msg::VehicleCommand>(
        "fmu/in/vehicle_command", rclcpp::SensorDataQoS());

    // 控制循环定时器
    auto control_timer_period = std::chrono::duration<double>(dt_);
    control_timer_ = this->create_wall_timer(
        control_timer_period,
        std::bind(&LADRCPositionControllerNode::controlLoop, this));

    // 状态机定时器 (10 Hz)
    auto command_timer_period = std::chrono::milliseconds(100);
    command_timer_ = this->create_wall_timer(
        command_timer_period,
        std::bind(&LADRCPositionControllerNode::stateMachine, this));

    // 初始化状态
    flight_state_ = FlightState::INIT;
    offboard_setpoint_counter_ = 0;

    RCLCPP_INFO(this->get_logger(), "LADRC 集群执行节点已初始化 (命名空间: %s), ENU偏移=[%.1f, %.1f, %.1f]",
        this->get_namespace(),
        this->get_parameter("enu_offset_x").as_double(),
        this->get_parameter("enu_offset_y").as_double(),
        this->get_parameter("enu_offset_z").as_double());
    RCLCPP_INFO(this->get_logger(), "等待 swarm_command 和 vehicle_odometry 消息...");
    RCLCPP_INFO(this->get_logger(), "控制模式: %s",
        ladrc_controller::toString(control_mode_));
  }

private:
  void initializeControllers()
  {
    ladrc_controller::LADRCParams params_x, params_y, params_z;

    double max_acc_x = this->get_parameter("max_acceleration_x").as_double();
    double max_acc_y = this->get_parameter("max_acceleration_y").as_double();
    double max_acc_z = this->get_parameter("max_acceleration_z").as_double();

    // X-axis controller
    params_x.omega_o = this->get_parameter("omega_o_x").as_double();
    params_x.omega_c = this->get_parameter("omega_c_x").as_double();
    params_x.kp = params_x.omega_c * params_x.omega_c;
    params_x.kd = 2.0 * params_x.omega_c;
    params_x.b0 = this->get_parameter("b0_x").as_double();
    params_x.dt = dt_;
    params_x.max_output = max_acc_x;
    params_x.min_output = -max_acc_x;

    // Y-axis controller
    params_y.omega_o = this->get_parameter("omega_o_y").as_double();
    params_y.omega_c = this->get_parameter("omega_c_y").as_double();
    params_y.kp = params_y.omega_c * params_y.omega_c;
    params_y.kd = 2.0 * params_y.omega_c;
    params_y.b0 = this->get_parameter("b0_y").as_double();
    params_y.dt = dt_;
    params_y.max_output = max_acc_y;
    params_y.min_output = -max_acc_y;

    // Z-axis controller
    params_z.omega_o = this->get_parameter("omega_o_z").as_double();
    params_z.omega_c = this->get_parameter("omega_c_z").as_double();
    params_z.kp = params_z.omega_c * params_z.omega_c;
    params_z.kd = 2.0 * params_z.omega_c;
    params_z.b0 = this->get_parameter("b0_z").as_double();
    params_z.dt = dt_;
    params_z.max_output = max_acc_z;
    params_z.min_output = -max_acc_z;

    ladrc_x_ = std::make_unique<ladrc_controller::LADRCController>(params_x);
    ladrc_y_ = std::make_unique<ladrc_controller::LADRCController>(params_y);
    ladrc_z_ = std::make_unique<ladrc_controller::LADRCController>(params_z);
  }

  bool readyForCommand(uint8_t message_uav_id)
  {
    if (flight_state_.load() == FlightState::RUNNING_TRAJECTORY && has_odom_)
    {
      return true;
    }
    RCLCPP_WARN_THROTTLE(this->get_logger(), *this->get_clock(), 5000,
        "UAV%d 尚未就绪（状态=%d, odom=%d），忽略命令", message_uav_id,
        (int)flight_state_.load(), has_odom_);
    return false;
  }

  bool loadExecutionProfileLimits(
      ladrc_controller::ExecutionProfileLimits & limits)
  {
    const auto to_array = [this](
      const std::string & name, std::array<double, 3> & result) {
        const auto values = this->get_parameter(name).as_double_array();
        if (values.size() != 3) return false;
        std::copy(values.begin(), values.end(), result.begin());
        return true;
      };
    if (!to_array("execution_profile_omega_c_min", limits.omega_c_min) ||
      !to_array("execution_profile_omega_c_max", limits.omega_c_max) ||
      !to_array("execution_profile_omega_o_min", limits.omega_o_min) ||
      !to_array("execution_profile_omega_o_max", limits.omega_o_max))
    {
      return false;
    }
    limits.velocity_max =
      this->get_parameter("execution_profile_velocity_max").as_double();
    limits.acceleration_max =
      this->get_parameter("execution_profile_acceleration_max").as_double();
    limits.jerk_max =
      this->get_parameter("execution_profile_jerk_max").as_double();
    limits.iapf_enter_min =
      this->get_parameter("execution_profile_iapf_enter_min").as_double();
    limits.iapf_enter_max =
      this->get_parameter("execution_profile_iapf_enter_max").as_double();
    limits.iapf_exit_max =
      this->get_parameter("execution_profile_iapf_exit_max").as_double();
    limits.iapf_repulsion_max =
      this->get_parameter("execution_profile_iapf_repulsion_max").as_double();
    return ladrc_controller::validLimits(limits);
  }

  void initializeAcceptedCommand(
      uint32_t mission_id, uint8_t uav_id,
      double global_x, double global_y, double global_z,
      double duration, const std::string & style, double safety_factor)
  {
    if (has_command_) writeControlAdaptationCsvRow();
    resetIAPFState();
    mission_id_ = mission_id;
    uav_id_ = uav_id;
    target_duration_ = duration;
    motion_style_ = style;
    safety_factor_ = safety_factor;
    has_command_ = true;

    const double off_x = this->get_parameter("enu_offset_x").as_double();
    const double off_y = this->get_parameter("enu_offset_y").as_double();
    const double off_z = this->get_parameter("enu_offset_z").as_double();
    target_pos_x_ = global_x - off_x;
    target_pos_y_ = global_y - off_y;
    target_pos_z_ = global_z - off_z;

    const double p0_x = current_odom_.position[1];
    const double p0_y = current_odom_.position[0];
    const double p0_z = -current_odom_.position[2];
    const double dx = target_pos_x_ - p0_x;
    const double dy = target_pos_y_ - p0_y;
    const double dz = target_pos_z_ - p0_z;
    target_distance_ = std::sqrt(dx * dx + dy * dy + dz * dz);
    average_speed_ = target_distance_ / target_duration_;

    traj_x_.initialize(p0_x, target_pos_x_, target_duration_);
    traj_y_.initialize(p0_y, target_pos_y_, target_duration_);
    traj_z_.initialize(p0_z, target_pos_z_, target_duration_);
    initializeTrajectoryMetrics(
      p0_x, p0_y, p0_z, global_x, global_y, global_z);
    ladrc_x_->setObserverInitialState(p0_x, 0.0, 0.0);
    ladrc_y_->setObserverInitialState(p0_y, 0.0, 0.0);
    ladrc_z_->setObserverInitialState(p0_z, 0.0, 0.0);
    command_start_time_ = this->now();
    is_hover_stable_ = false;
    arrival_time_recorded_ = false;
    arrival_time_error_ = std::numeric_limits<double>::quiet_NaN();
    resetControlAdaptationRuntimeMetrics();
    trajectory_metrics_pub_counter_ = 0;
  }

  void applyBaselineGains()
  {
    gain_multiplier_ = 1.0;
    omega_o_x_ = this->get_parameter("omega_o_x").as_double();
    omega_o_y_ = this->get_parameter("omega_o_y").as_double();
    omega_o_z_ = this->get_parameter("omega_o_z").as_double();
    omega_c_x_ = this->get_parameter("omega_c_x").as_double();
    omega_c_y_ = this->get_parameter("omega_c_y").as_double();
    omega_c_z_ = this->get_parameter("omega_c_z").as_double();
    ladrc_x_->setObserverBandwidth(omega_o_x_);
    ladrc_y_->setObserverBandwidth(omega_o_y_);
    ladrc_z_->setObserverBandwidth(omega_o_z_);
    ladrc_x_->setControllerBandwidth(omega_c_x_);
    ladrc_y_->setControllerBandwidth(omega_c_y_);
    ladrc_z_->setControllerBandwidth(omega_c_z_);
  }

  // --- [Phase 2] legacy swarm_command 回调（安全基值降级） ---
  void swarmCommandCallback(const uav_swarm_interfaces::msg::UAVSwarmCommand::SharedPtr msg)
  {
    RCLCPP_INFO(this->get_logger(),
        "UAV%d swarm_cmd 回调触发 (目标=[%.1f,%.1f,%.1f])",
        self_uav_id_, msg->target_pos.x, msg->target_pos.y, msg->target_pos.z);

    if (!readyForCommand(msg->uav_id))
    {
      return;
    }
    if (active_new_profile_)
    {
      RCLCPP_WARN(this->get_logger(),
        "忽略 legacy UAVSwarmCommand：新 Execution Profile 任务仍在执行");
      return;
    }

    // 判断是否与当前正在执行的任务完全相同（防重复发送）
    // 注意：比较时必须使用 msg 原始值（全局坐标），不能和减去 offset 后的本地坐标比
    if (has_command_)
    {
      double off_x = this->get_parameter("enu_offset_x").as_double();
      double off_y = this->get_parameter("enu_offset_y").as_double();
      double off_z = this->get_parameter("enu_offset_z").as_double();
      bool same_target = (std::abs(msg->target_pos.x - (target_pos_x_ + off_x)) < 1e-6 &&
                          std::abs(msg->target_pos.y - (target_pos_y_ + off_y)) < 1e-6 &&
                          std::abs(msg->target_pos.z - (target_pos_z_ + off_z)) < 1e-6);
      bool same_params = (std::abs(msg->duration - target_duration_) < 1e-6 &&
                          msg->motion_style == motion_style_ &&
                          msg->mission_id == mission_id_);
      if (same_target && same_params)
      {
        return;  // 静默忽略重复消息
      }
      RCLCPP_INFO(this->get_logger(),
          "收到新任务指令 (UAV%d)，目标/参数已变更，覆盖旧任务", msg->uav_id);
    }

    const double duration = static_cast<double>(msg->duration);
    if (!std::isfinite(duration) || duration <= 0.0)
    {
      RCLCPP_ERROR(this->get_logger(), "拒绝非法 legacy duration");
      return;
    }
    active_new_profile_ = false;
    profile_soft_safety_active_ = false;
    initializeAcceptedCommand(
      msg->mission_id, msg->uav_id,
      msg->target_pos.x, msg->target_pos.y, msg->target_pos.z,
      duration, msg->motion_style,
      std::max(1.0, static_cast<double>(msg->safety_factor)));
    applyBaselineGains();
    RCLCPP_WARN(this->get_logger(),
      "legacy UAVSwarmCommand 使用 YAML baseline；motion_style='%s' 仅记录",
      msg->motion_style.c_str());

    RCLCPP_INFO(this->get_logger(),
        ">>> Mission%u UAV%d 全局[%.1f,%.1f,%.1f]→本地[%.1f,%.1f,%.1f] T=%.1fs %s",
        mission_id_, uav_id_,
        msg->target_pos.x, msg->target_pos.y, msg->target_pos.z,
        target_pos_x_, target_pos_y_, target_pos_z_,
        target_duration_, motion_style_.c_str());
  }

  void executionCommandCallback(
      const uav_swarm_interfaces::msg::UAVExecutionCommand::SharedPtr msg)
  {
    if (!this->get_parameter("enable_execution_profiles").as_bool())
    {
      RCLCPP_ERROR(this->get_logger(),
        "收到 UAVExecutionCommand，但 enable_execution_profiles=false");
      return;
    }
    if (!readyForCommand(msg->uav_id)) return;

    ladrc_controller::ExecutionProfileLimits limits;
    if (!loadExecutionProfileLimits(limits))
    {
      RCLCPP_ERROR(this->get_logger(),
        "Execution Profile hard limits 未完整配置，拒绝新命令");
      return;
    }
    ladrc_controller::ExecutionProfileValues values{
      msg->profile.duration,
      {msg->profile.omega_c[0], msg->profile.omega_c[1], msg->profile.omega_c[2]},
      {msg->profile.omega_o[0], msg->profile.omega_o[1], msg->profile.omega_o[2]},
      msg->profile.velocity_limit,
      msg->profile.acceleration_limit,
      msg->profile.jerk_limit,
      msg->profile.iapf_enter_distance,
      msg->profile.iapf_exit_distance,
      msg->profile.iapf_repulsion_scale,
      msg->profile.style_gain,
      msg->profile.task_gain};
    if (msg->uav_id != static_cast<uint8_t>(self_uav_id_) ||
      !std::isfinite(msg->target_pos.x) ||
      !std::isfinite(msg->target_pos.y) ||
      !std::isfinite(msg->target_pos.z) ||
      msg->profile.style.empty() || msg->profile.configuration_id.empty())
    {
      RCLCPP_ERROR(this->get_logger(),
        "拒绝 Execution Profile: command metadata is incomplete or non-finite");
      return;
    }
    std::string error;
    if (!ladrc_controller::validateAndClampExecutionProfile(values, limits, &error))
    {
      RCLCPP_ERROR(this->get_logger(),
        "拒绝 Execution Profile: %s", error.c_str());
      return;
    }

    const double alpha =
      this->get_parameter("execution_profile_smoothing_alpha").as_double();
    for (std::size_t axis = 0; axis < 3; ++axis)
    {
      const std::array<double, 3> previous_c{omega_c_x_, omega_c_y_, omega_c_z_};
      const std::array<double, 3> previous_o{omega_o_x_, omega_o_y_, omega_o_z_};
      values.omega_c[axis] = ladrc_controller::smoothProfileValue(
        previous_c[axis], values.omega_c[axis], alpha);
      values.omega_o[axis] = ladrc_controller::smoothProfileValue(
        previous_o[axis], values.omega_o[axis], alpha);
    }

    initializeAcceptedCommand(
      msg->mission_id, msg->uav_id,
      msg->target_pos.x, msg->target_pos.y, msg->target_pos.z,
      values.duration, msg->profile.style, 1.0);
    omega_c_x_ = values.omega_c[0];
    omega_c_y_ = values.omega_c[1];
    omega_c_z_ = values.omega_c[2];
    omega_o_x_ = values.omega_o[0];
    omega_o_y_ = values.omega_o[1];
    omega_o_z_ = values.omega_o[2];
    ladrc_x_->setControllerBandwidth(omega_c_x_);
    ladrc_y_->setControllerBandwidth(omega_c_y_);
    ladrc_z_->setControllerBandwidth(omega_c_z_);
    ladrc_x_->setObserverBandwidth(omega_o_x_);
    ladrc_y_->setObserverBandwidth(omega_o_y_);
    ladrc_z_->setObserverBandwidth(omega_o_z_);
    ladrc_x_->setOutputLimits(-values.acceleration_limit, values.acceleration_limit);
    ladrc_y_->setOutputLimits(-values.acceleration_limit, values.acceleration_limit);
    ladrc_z_->setOutputLimits(-values.acceleration_limit, values.acceleration_limit);
    gain_multiplier_ = values.style_gain * values.task_gain;
    profile_iapf_enter_distance_ = values.iapf_enter_distance;
    profile_iapf_exit_distance_ = values.iapf_exit_distance;
    profile_iapf_repulsion_scale_ = values.iapf_repulsion_scale;
    profile_soft_safety_active_ = true;
    active_new_profile_ = true;
    active_profile_configuration_id_ = msg->profile.configuration_id;
    // A fresh false sample acknowledges the new command generation. The
    // Candidate FSM will not accept a stale true from the preceding task.
    publishUAVStatus();
    RCLCPP_INFO(this->get_logger(),
      "应用 Execution Profile mission=%u task=%u config=%s T_exec=%.3f",
      msg->mission_id, msg->task_id,
      active_profile_configuration_id_.c_str(), target_duration_);
  }

  void odomCallback(const px4_msgs::msg::VehicleOdometry::SharedPtr msg)
  {
    RCLCPP_INFO_ONCE(this->get_logger(), "已接收到 vehicle_odometry 消息");
    current_odom_ = *msg;
    has_odom_ = true;

    // Standardized Candidate planning state. PX4 timestamps are boot-clock
    // microseconds, so the normalization boundary stamps the received sample
    // with this node's ROS clock instead of pretending it is ROS epoch time.
    auto state = ladrc_controller::buildSwarmState(
      *msg, this->now(), self_uav_id_,
      this->get_parameter("enu_offset_x").as_double(),
      this->get_parameter("enu_offset_y").as_double(),
      this->get_parameter("enu_offset_z").as_double());
    swarm_state_pub_->publish(state);
  }

  // --- 状态机逻辑 ---
  void publishVehicleCommand(uint16_t command, float param1 = 0.0, float param2 = 0.0, float param7 = 0.0)
  {
    px4_msgs::msg::VehicleCommand msg{};
    msg.command = command;
    msg.param1 = param1;
    msg.param2 = param2;
    msg.param7 = param7;
    msg.target_system =
        static_cast<uint8_t>(this->get_parameter("px4_target_system").as_int());
    msg.target_component = 1;
    msg.source_system = 1;
    msg.source_component = 1;
    msg.from_external = true;
    msg.timestamp = this->get_clock()->now().nanoseconds() / 1000;
    vehicle_command_pub_->publish(msg);
  }

  void stateMachine()
  {
    switch (flight_state_.load())
    {
    case FlightState::INIT:
      if (++offboard_setpoint_counter_ * 100 > 10000)
      {
        RCLCPP_INFO(this->get_logger(), "系统稳定，开始解锁 (Arming)...");
        publishVehicleCommand(px4_msgs::msg::VehicleCommand::VEHICLE_CMD_COMPONENT_ARM_DISARM, 1.0);
        flight_state_ = FlightState::ARMING;
        offboard_setpoint_counter_ = 0;
      }
      break;

    case FlightState::ARMING:
      if (++offboard_setpoint_counter_ * 100 > 2000)
      {
        RCLCPP_INFO(this->get_logger(), "解锁成功。切换到 Offboard 模式...");
        publishVehicleCommand(px4_msgs::msg::VehicleCommand::VEHICLE_CMD_DO_SET_MODE, 1.0, 6.0);
        flight_state_ = FlightState::SETTING_OFFBOARD;
        offboard_setpoint_counter_ = 0;
      }
      break;

    case FlightState::SETTING_OFFBOARD:
      if (++offboard_setpoint_counter_ * 100 > 1000)
      {
        RCLCPP_INFO(this->get_logger(), "Offboard 模式已激活。LADRC 控制器接管。");
        flight_state_ = FlightState::RUNNING_TRAJECTORY;
        command_timer_->cancel();
      }
      break;

    case FlightState::RUNNING_TRAJECTORY:
      command_timer_->cancel();
      break;
    }
  }

  void controlLoop()
  {
    // 持续发布 offboard 模式
    publishOffboardControlMode();

    // 状态机未完成或未收到里程计：不发 setpoint，等待
    if (flight_state_.load() != FlightState::RUNNING_TRAJECTORY || !has_odom_)
    {
      if (flight_state_.load() != FlightState::RUNNING_TRAJECTORY) {
           RCLCPP_WARN_THROTTLE(this->get_logger(), *this->get_clock(), 5000,
             "等待状态机进入 RUNNING_TRAJECTORY... (当前: %d)", (int)flight_state_.load());
      } else {
           RCLCPP_WARN_THROTTLE(this->get_logger(), *this->get_clock(), 5000,
             "等待 vehicle_odometry 消息...");
      }
      return;
    }

    // 1. 获取测量值 (Odom) 并转换为 ENU
    double x_meas = current_odom_.position[1];
    double y_meas = current_odom_.position[0];
    double z_meas = -current_odom_.position[2];

    // 低频发布 ENU 位置 (~10Hz at 50Hz control loop)
    if (++odom_pub_counter_ >= 5)
    {
      odom_pub_counter_ = 0;
      geometry_msgs::msg::Point odom_msg;
      odom_msg.x = x_meas + this->get_parameter("enu_offset_x").as_double();
      odom_msg.y = y_meas + this->get_parameter("enu_offset_y").as_double();
      odom_msg.z = z_meas + this->get_parameter("enu_offset_z").as_double();
      odom_pub_->publish(odom_msg);
    }

    // 2. 生成标称参考。无任务时锁定首次测量位置，仍然执行完整闭环。
    double elapsed = 0.0;
    bool all_finished = false;
    Eigen::Vector3d nominal_reference;
    Eigen::Vector3d nominal_velocity = Eigen::Vector3d::Zero();
    Eigen::Vector3d nominal_acceleration = Eigen::Vector3d::Zero();
    if (!has_command_)
    {
      if (!hover_hold_set_)
      {
        hover_hold_x_ = x_meas;
        hover_hold_y_ = y_meas;
        hover_hold_z_ = z_meas;
        hover_hold_set_ = true;
        ladrc_x_->setObserverInitialState(
          x_meas, current_odom_.velocity[1], 0.0);
        ladrc_y_->setObserverInitialState(
          y_meas, current_odom_.velocity[0], 0.0);
        ladrc_z_->setObserverInitialState(
          z_meas, -current_odom_.velocity[2], 0.0);
        RCLCPP_INFO(this->get_logger(),
            "UAV%d 悬停保持锁定: [%.2f, %.2f, %.2f]", self_uav_id_, x_meas, y_meas, z_meas);
      }
      nominal_reference = Eigen::Vector3d(
        hover_hold_x_, hover_hold_y_, hover_hold_z_);
    }
    else
    {
      hover_hold_set_ = false;
      elapsed = (this->now() - command_start_time_).seconds();
      all_finished =
        traj_x_.isFinished(elapsed) &&
        traj_y_.isFinished(elapsed) &&
        traj_z_.isFinished(elapsed);
      const auto ref_x = traj_x_.evaluate(elapsed);
      const auto ref_y = traj_y_.evaluate(elapsed);
      const auto ref_z = traj_z_.evaluate(elapsed);
      nominal_reference = Eigen::Vector3d(
        ref_x.position, ref_y.position, ref_z.position);
      nominal_velocity = Eigen::Vector3d(
        ref_x.velocity, ref_y.velocity, ref_z.velocity);
      nominal_acceleration = Eigen::Vector3d(
        ref_x.acceleration, ref_y.acceleration, ref_z.acceleration);

      updateControlAdaptationRuntimeMetrics(
        elapsed, nominal_reference.x(), nominal_reference.y(), nominal_reference.z(),
        x_meas, y_meas, z_meas);

      // 轨迹结束后 Minimum Jerk 返回终点、零速度和零加速度，继续位置调节。
      if (all_finished)
      {
        const double pos_err = (nominal_reference -
          Eigen::Vector3d(x_meas, y_meas, z_meas)).norm();
        const double vel_mag = std::sqrt(
          current_odom_.velocity[0] * current_odom_.velocity[0] +
          current_odom_.velocity[1] * current_odom_.velocity[1] +
          current_odom_.velocity[2] * current_odom_.velocity[2]);
        if (pos_err < 0.3 && vel_mag < 0.3 && !is_hover_stable_)
        {
          is_hover_stable_ = true;
          if (!arrival_time_recorded_)
          {
            arrival_time_error_ = elapsed - target_duration_;
            arrival_time_recorded_ = true;
          }
          settling_time_ = elapsed;
          writeControlAdaptationCsvRow();
          RCLCPP_INFO(this->get_logger(),
              "悬停稳定! pos_err=%.2fm, vel=%.2fm/s → is_hover_stable=true",
              pos_err, vel_mag);
        }
      }

      if (++trajectory_metrics_pub_counter_ >= 5)
      {
        trajectory_metrics_pub_counter_ = 0;
        publishTrajectoryMetrics(elapsed, x_meas, y_meas, z_meas, all_finished);
        publishControlAdaptationLog();
      }
    }

    // 3. IAPF 先修正参考，再由 LADRC 计算唯一的最终加速度指令。
    const double active_safety_factor = has_command_ ? safety_factor_ :
      this->get_parameter("idle_hover_safety_factor").as_double();
    const auto iapf = computeAvoidance(
      x_meas, y_meas, z_meas, active_safety_factor);
    const Eigen::Vector3d safe_reference =
      nominal_reference + iapf.position_offset;
    const Eigen::Vector3d safe_acceleration =
      nominal_acceleration + iapf.acceleration_offset;
    const Eigen::Vector3d ladrc_output(
      ladrc_x_->update(
        safe_reference.x(), nominal_velocity.x(), safe_acceleration.x(), x_meas),
      ladrc_y_->update(
        safe_reference.y(), nominal_velocity.y(), safe_acceleration.y(), y_meas),
      ladrc_z_->update(
        safe_reference.z(), nominal_velocity.z(), safe_acceleration.z(), z_meas));

    const Eigen::Vector3d actual_position(x_meas, y_meas, z_meas);
    const Eigen::Vector3d actual_velocity(
      current_odom_.velocity[1], current_odom_.velocity[0],
      -current_odom_.velocity[2]);
    if (!nominal_reference.allFinite() || !nominal_velocity.allFinite() ||
      !safe_reference.allFinite() || !safe_acceleration.allFinite() ||
      !ladrc_output.allFinite() || !actual_position.allFinite() ||
      !actual_velocity.allFinite())
    {
      RCLCPP_ERROR_THROTTLE(this->get_logger(), *this->get_clock(), 1000,
        "检测到非有限控制量，已阻止 TrajectorySetpoint 发布");
      return;
    }

    // 4. position 基线发布安全位置；LADRC 模式只发布 LADRC 加速度。
    publishUAVStatus();
    const bool position_mode_acceleration_feedforward =
      currentAvoidanceMode() == ladrc_controller::AvoidanceMode::IAPF_DUAL;
    const Eigen::Vector3d published_acceleration =
      control_mode_ == ladrc_controller::ControlMode::LADRC_ACCELERATION ?
      ladrc_output : safe_acceleration;
    const auto px4_setpoint = publishTrajectorySetpoint(
      safe_reference.x(), safe_reference.y(), safe_reference.z(),
      published_acceleration.x(), published_acceleration.y(),
      published_acceleration.z(), 0.0,
      position_mode_acceleration_feedforward);
    const Eigen::Vector3d global_offset(
      this->get_parameter("enu_offset_x").as_double(),
      this->get_parameter("enu_offset_y").as_double(),
      this->get_parameter("enu_offset_z").as_double());
    publishIAPFDebug(
      iapf, nominal_reference + global_offset,
      safe_reference + global_offset,
      nominal_acceleration, safe_acceleration);
    publishControlTrackingDebug(
      nominal_reference, safe_reference, nominal_velocity,
      nominal_acceleration, safe_acceleration, ladrc_output,
      actual_position, actual_velocity, px4_setpoint);

    // 日志中的 Cmd 即 LADRC 输出；加速度模式下与发布值完全一致。
    RCLCPP_INFO_THROTTLE(this->get_logger(), *this->get_clock(), 1000,
        "UAV%d mode=%s Ref[%.1f,%.1f,%.1f] Safe[%.1f,%.1f,%.1f] "
        "Pos[%.2f,%.2f,%.2f] Cmd[%.1f,%.1f,%.1f]%s",
        self_uav_id_, ladrc_controller::toString(control_mode_),
        nominal_reference.x(), nominal_reference.y(), nominal_reference.z(),
        safe_reference.x(), safe_reference.y(), safe_reference.z(),
        x_meas, y_meas, z_meas,
        ladrc_output.x(), ladrc_output.y(), ladrc_output.z(),
        (iapf.active ? " !IAPF!" : ""));
  }

  ladrc_controller::AvoidanceMode currentAvoidanceMode() const
  {
    if (avoidance_mode_from_legacy_)
    {
      return this->get_parameter("enable_iapf_accel_feedforward").as_bool()
        ? ladrc_controller::AvoidanceMode::IAPF_DUAL
        : ladrc_controller::AvoidanceMode::IAPF_POSITION;
    }
    return ladrc_controller::parseAvoidanceMode(
      this->get_parameter("avoidance_mode").as_string());
  }

  double currentEnterDistance() const
  {
    if (profile_soft_safety_active_) return profile_iapf_enter_distance_;
    return this->get_parameter(
      enter_distance_from_legacy_
      ? "iapf_safe_distance"
      : "iapf_enter_distance").as_double();
  }

  void resetIAPFState()
  {
    filtered_iapf_position_offset_.setZero();
    filtered_iapf_acceleration_offset_.setZero();
    for (auto & item : neighbor_states_)
    {
      item.second.iapf_active = false;
    }
  }

  ladrc_controller::IAPFResult computeAvoidance(
      double x_meas, double y_meas, double z_meas,
      double active_safety_factor)
  {
    ladrc_controller::IAPFParameters parameters;
    parameters.violation_distance =
      this->get_parameter("iapf_violation_distance").as_double();
    parameters.enter_distance = currentEnterDistance();
    parameters.exit_distance = profile_soft_safety_active_
      ? profile_iapf_exit_distance_
      : this->get_parameter("iapf_exit_distance").as_double();
    parameters.repulsion_gain =
      this->get_parameter("iapf_repulsion_gain").as_double() *
      (profile_soft_safety_active_ ? profile_iapf_repulsion_scale_ : 1.0);
    parameters.distance_epsilon =
      this->get_parameter("iapf_distance_epsilon").as_double();
    parameters.position_gain =
      this->get_parameter("iapf_position_gain").as_double();
    parameters.position_limit =
      this->get_parameter("iapf_position_limit").as_double();
    parameters.acceleration_gain =
      this->get_parameter("iapf_accel_gain").as_double();
    parameters.acceleration_limit =
      this->get_parameter("iapf_accel_limit").as_double();
    parameters.escape_gain =
      this->get_parameter("iapf_escape_gain").as_double();

    std::vector<ladrc_controller::NeighborSample> neighbors;
    neighbors.reserve(configured_neighbor_ids_.size());
    const rclcpp::Time now = this->now();
    const double timeout = this->get_parameter("neighbor_timeout").as_double();
    if (timeout <= 0.0)
    {
      throw std::invalid_argument("neighbor_timeout must be positive");
    }
    for (const auto neighbor_id : configured_neighbor_ids_)
    {
      const auto state_iterator = neighbor_states_.find(neighbor_id);
      if (state_iterator == neighbor_states_.end())
      {
        neighbors.push_back({
          neighbor_id, Eigen::Vector3d::Zero(), Eigen::Vector3d::Zero(),
          false, false});
        continue;
      }
      const auto & state = state_iterator->second;
      neighbors.push_back({
        neighbor_id,
        state.position,
        state.velocity,
        (now - state.receive_time).seconds() <= timeout,
        state.iapf_active});
    }
    double my_off_x = this->get_parameter("enu_offset_x").as_double();
    double my_off_y = this->get_parameter("enu_offset_y").as_double();
    double my_off_z = this->get_parameter("enu_offset_z").as_double();
    Eigen::Vector3d pos_own(x_meas + my_off_x, y_meas + my_off_y, z_meas + my_off_z);
    const Eigen::Vector3d velocity_own(
      current_odom_.velocity[1],
      current_odom_.velocity[0],
      -current_odom_.velocity[2]);

    auto result = ladrc_controller::computeIAPF(
      pos_own, velocity_own, self_uav_id_, neighbors, currentAvoidanceMode(),
      ladrc_controller::parseEscapeMode(
        this->get_parameter("iapf_escape_mode").as_string()),
      parameters, active_safety_factor);

    for (auto & item : neighbor_states_)
    {
      item.second.iapf_active =
        std::find(
          result.active_neighbor_ids.begin(),
          result.active_neighbor_ids.end(),
          item.first) != result.active_neighbor_ids.end();
    }
    const double alpha =
      this->get_parameter("iapf_filter_alpha").as_double();
    if (currentAvoidanceMode() == ladrc_controller::AvoidanceMode::OFF)
    {
      resetIAPFState();
      result.position_offset.setZero();
      result.acceleration_offset.setZero();
      result.active = false;
    }
    else
    {
      filtered_iapf_position_offset_ = ladrc_controller::smoothOffset(
        result.position_offset, filtered_iapf_position_offset_, alpha);
      filtered_iapf_acceleration_offset_ = ladrc_controller::smoothOffset(
        result.acceleration_offset, filtered_iapf_acceleration_offset_, alpha);
      if (filtered_iapf_position_offset_.norm() < 1e-5)
      {
        filtered_iapf_position_offset_.setZero();
      }
      if (filtered_iapf_acceleration_offset_.norm() < 1e-5)
      {
        filtered_iapf_acceleration_offset_.setZero();
      }
      result.position_offset = filtered_iapf_position_offset_;
      result.acceleration_offset = filtered_iapf_acceleration_offset_;
      result.active = result.active ||
        !result.position_offset.isZero(1e-9) ||
        !result.acceleration_offset.isZero(1e-9);
    }
    if (result.active)
    {
      RCLCPP_WARN_THROTTLE(this->get_logger(), *this->get_clock(), 500,
          "%s 避障: nearest=U%d d=%.2fm Frep[%.1f,%.1f,%.1f]",
          ladrc_controller::toString(currentAvoidanceMode()).c_str(),
          result.nearest_neighbor_id, result.nearest_neighbor_distance,
          result.raw_repulsion.x(), result.raw_repulsion.y(),
          result.raw_repulsion.z());
    }
    return result;
  }

  static void setVector3(
      geometry_msgs::msg::Vector3 & output, const Eigen::Vector3d & value)
  {
    output.x = value.x();
    output.y = value.y();
    output.z = value.z();
  }

  static void setPoint(
      geometry_msgs::msg::Point & output, const Eigen::Vector3d & value)
  {
    output.x = value.x();
    output.y = value.y();
    output.z = value.z();
  }

  void publishIAPFDebug(
      const ladrc_controller::IAPFResult & result,
      const Eigen::Vector3d & nominal_reference,
      const Eigen::Vector3d & modulated_reference,
      const Eigen::Vector3d & nominal_acceleration,
      const Eigen::Vector3d & modulated_acceleration)
  {
    uav_swarm_interfaces::msg::IAPFDebug msg;
    msg.header.stamp = this->now();
    msg.header.frame_id = "world";
    msg.mission_id = mission_id_;
    msg.uav_id = self_uav_id_;
    msg.avoidance_mode =
      ladrc_controller::toString(currentAvoidanceMode());
    msg.has_nearest_neighbor = result.has_nearest_neighbor;
    msg.nearest_neighbor_id = result.nearest_neighbor_id;
    msg.nearest_neighbor_distance =
      static_cast<float>(result.nearest_neighbor_distance);
    msg.nearest_neighbor_closing_speed =
      static_cast<float>(result.nearest_neighbor_closing_speed);
    msg.iapf_active = result.active;
    msg.hysteresis_active = result.hysteresis_active;
    msg.active_neighbor_count =
      static_cast<uint16_t>(result.active_neighbor_ids.size());
    setVector3(msg.raw_repulsion, result.raw_repulsion);
    setVector3(msg.position_offset, result.position_offset);
    setVector3(msg.acceleration_offset, result.acceleration_offset);
    msg.position_saturated = result.position_saturated;
    msg.acceleration_saturated = result.acceleration_saturated;
    msg.valid_neighbor_count = result.valid_neighbor_count;
    msg.stale_neighbor_count = result.stale_neighbor_count;
    setPoint(msg.nominal_reference, nominal_reference);
    setPoint(msg.modulated_reference, modulated_reference);
    setVector3(msg.nominal_acceleration, nominal_acceleration);
    setVector3(msg.modulated_acceleration, modulated_acceleration);
    iapf_debug_pub_->publish(msg);
  }

  static void setArrayVector3(
      geometry_msgs::msg::Vector3 & output,
      const std::array<float, 3> & value)
  {
    output.x = value[0];
    output.y = value[1];
    output.z = value[2];
  }

  void publishControlTrackingDebug(
      const Eigen::Vector3d & nominal_reference,
      const Eigen::Vector3d & safe_reference,
      const Eigen::Vector3d & nominal_velocity,
      const Eigen::Vector3d & nominal_acceleration,
      const Eigen::Vector3d & safe_acceleration,
      const Eigen::Vector3d & ladrc_output,
      const Eigen::Vector3d & actual_position,
      const Eigen::Vector3d & actual_velocity,
      const px4_msgs::msg::TrajectorySetpoint & px4_setpoint)
  {
    uav_swarm_interfaces::msg::ControlTrackingDebug msg;
    msg.header.stamp = this->now();
    msg.header.frame_id = "local_enu";
    msg.mission_id = mission_id_;
    msg.uav_id = self_uav_id_;
    msg.control_mode = ladrc_controller::toString(control_mode_);
    msg.has_command = has_command_;
    setPoint(msg.nominal_position, nominal_reference);
    setPoint(msg.safe_position, safe_reference);
    setVector3(msg.nominal_velocity, nominal_velocity);
    setVector3(msg.nominal_acceleration, nominal_acceleration);
    setVector3(msg.safe_acceleration, safe_acceleration);
    setVector3(msg.ladrc_output, ladrc_output);

    const auto states_x = ladrc_x_->getEstimatedStates();
    const auto states_y = ladrc_y_->getEstimatedStates();
    const auto states_z = ladrc_z_->getEstimatedStates();
    setVector3(msg.leso_z1, Eigen::Vector3d(
      states_x[0], states_y[0], states_z[0]));
    setVector3(msg.leso_z2, Eigen::Vector3d(
      states_x[1], states_y[1], states_z[1]));
    setVector3(msg.leso_z3, Eigen::Vector3d(
      states_x[2], states_y[2], states_z[2]));

    setPoint(msg.actual_position, actual_position);
    setVector3(msg.actual_velocity, actual_velocity);
    setVector3(msg.tracking_error, safe_reference - actual_position);
    setArrayVector3(msg.px4_position_setpoint, px4_setpoint.position);
    setArrayVector3(msg.px4_velocity_setpoint, px4_setpoint.velocity);
    setArrayVector3(msg.px4_acceleration_setpoint, px4_setpoint.acceleration);
    control_tracking_debug_pub_->publish(msg);
  }

  // --- [Phase 1] 新增 UAVStatus 发布 ---
  void publishUAVStatus()
  {
    uav_swarm_interfaces::msg::UAVStatus msg;
    msg.uav_id = uav_id_;
    msg.is_hover_stable = is_hover_stable_;
    status_pub_->publish(msg);
  }

  void initializeTrajectoryMetrics(double p0_x, double p0_y, double p0_z,
                                   double target_global_x,
                                   double target_global_y,
                                   double target_global_z)
  {
    double off_x = this->get_parameter("enu_offset_x").as_double();
    double off_y = this->get_parameter("enu_offset_y").as_double();
    double off_z = this->get_parameter("enu_offset_z").as_double();

    metrics_msg_ = uav_swarm_interfaces::msg::TrajectoryMetrics();
    metrics_msg_.header.frame_id = "world";
    metrics_msg_.uav_id = uav_id_;
    metrics_msg_.start_pos.x = p0_x + off_x;
    metrics_msg_.start_pos.y = p0_y + off_y;
    metrics_msg_.start_pos.z = p0_z + off_z;
    metrics_msg_.target_pos.x = target_global_x;
    metrics_msg_.target_pos.y = target_global_y;
    metrics_msg_.target_pos.z = target_global_z;
    metrics_msg_.requested_duration = static_cast<float>(target_duration_);
    metrics_msg_.trajectory_duration = static_cast<float>(traj_x_.getDuration());
    metrics_msg_.motion_style = motion_style_;
    metrics_msg_.safety_factor = static_cast<float>(safety_factor_);

    double dx = target_pos_x_ - p0_x;
    double dy = target_pos_y_ - p0_y;
    double dz = target_pos_z_ - p0_z;
    double distance = std::sqrt(dx * dx + dy * dy + dz * dz);
    double duration = traj_x_.getDuration();
    double duration2 = duration * duration;
    double duration3 = duration2 * duration;
    double duration5 = duration3 * duration2;

    metrics_msg_.path_length = static_cast<float>(distance);
    metrics_msg_.max_velocity = static_cast<float>(1.875 * distance / duration);
    metrics_msg_.max_acceleration =
        static_cast<float>((10.0 * std::sqrt(3.0) / 3.0) * distance / duration2);
    metrics_msg_.max_jerk = static_cast<float>(60.0 * distance / duration3);
    metrics_msg_.integrated_squared_jerk =
        static_cast<float>(720.0 * distance * distance / duration5);
    metrics_msg_.elapsed_time = 0.0f;
    metrics_msg_.arrival_time_error =
        std::numeric_limits<float>::quiet_NaN();
    metrics_msg_.final_position_error =
        static_cast<float>(distance);
    metrics_msg_.is_finished = false;
    metrics_msg_.is_hover_stable = false;
    has_trajectory_metrics_ = true;

    RCLCPP_INFO(this->get_logger(),
        "轨迹指标: path=%.2fm vmax=%.2fm/s amax=%.2fm/s^2 jmax=%.2fm/s^3 ISJ=%.2f",
        metrics_msg_.path_length,
        metrics_msg_.max_velocity,
        metrics_msg_.max_acceleration,
        metrics_msg_.max_jerk,
        metrics_msg_.integrated_squared_jerk);
  }

  void publishTrajectoryMetrics(double elapsed,
                                double x_meas,
                                double y_meas,
                                double z_meas,
                                bool is_finished)
  {
    if (!has_trajectory_metrics_) return;

    double off_x = this->get_parameter("enu_offset_x").as_double();
    double off_y = this->get_parameter("enu_offset_y").as_double();
    double off_z = this->get_parameter("enu_offset_z").as_double();
    double x_global = x_meas + off_x;
    double y_global = y_meas + off_y;
    double z_global = z_meas + off_z;
    double dx = metrics_msg_.target_pos.x - x_global;
    double dy = metrics_msg_.target_pos.y - y_global;
    double dz = metrics_msg_.target_pos.z - z_global;

    metrics_msg_.header.stamp = this->now();
    metrics_msg_.elapsed_time = static_cast<float>(elapsed);
    metrics_msg_.arrival_time_error = static_cast<float>(arrival_time_error_);
    metrics_msg_.final_position_error =
        static_cast<float>(std::sqrt(dx * dx + dy * dy + dz * dz));
    metrics_msg_.is_finished = is_finished;
    metrics_msg_.is_hover_stable = is_hover_stable_;

    trajectory_metrics_pub_->publish(metrics_msg_);
  }

  std::string defaultControlAdaptationLogPath() const
  {
    std::filesystem::path source_path(__FILE__);
    if (source_path.is_relative())
    {
      source_path = std::filesystem::current_path() / source_path;
    }

    for (auto path = source_path.parent_path(); !path.empty(); path = path.parent_path())
    {
      if (std::filesystem::exists(path / ".git"))
      {
        return (path / "logs" / "control_adaptation_log.csv").string();
      }
      if (path == path.root_path())
      {
        break;
      }
    }

    return "logs/control_adaptation_log.csv";
  }

  void resetControlAdaptationRuntimeMetrics()
  {
    peak_velocity_ = 0.0;
    peak_acceleration_ = 0.0;
    tracking_error_squared_sum_ = 0.0;
    tracking_sample_count_ = 0;
    settling_time_ = std::numeric_limits<double>::quiet_NaN();
    previous_velocity_valid_ = false;
    control_adaptation_csv_written_ = false;
    has_control_adaptation_metrics_ = true;
  }

  void updateControlAdaptationRuntimeMetrics(double elapsed,
                                             double x_ref,
                                             double y_ref,
                                             double z_ref,
                                             double x_meas,
                                             double y_meas,
                                             double z_meas)
  {
    if (!has_control_adaptation_metrics_) return;
    latest_elapsed_time_ = elapsed;

    Eigen::Vector3d measured_velocity(
        current_odom_.velocity[0],
        current_odom_.velocity[1],
        current_odom_.velocity[2]);
    peak_velocity_ = std::max(peak_velocity_, measured_velocity.norm());

    if (previous_velocity_valid_ && dt_ > 1e-6)
    {
      double acceleration = (measured_velocity - previous_velocity_).norm() / dt_;
      peak_acceleration_ = std::max(peak_acceleration_, acceleration);
    }
    previous_velocity_ = measured_velocity;
    previous_velocity_valid_ = true;

    double error = std::sqrt(
        (x_ref - x_meas) * (x_ref - x_meas) +
        (y_ref - y_meas) * (y_ref - y_meas) +
        (z_ref - z_meas) * (z_ref - z_meas));
    tracking_error_squared_sum_ += error * error;
    ++tracking_sample_count_;
  }

  uav_swarm_interfaces::msg::ControlAdaptationLog buildControlAdaptationLogMsg()
  {
    uav_swarm_interfaces::msg::ControlAdaptationLog msg;
    msg.header.stamp = this->now();
    msg.header.frame_id = "world";
    msg.mission_id = mission_id_;
    msg.uav_id = uav_id_;
    msg.motion_style = motion_style_;
    msg.target_distance = static_cast<float>(target_distance_);
    msg.duration = static_cast<float>(target_duration_);
    msg.average_speed = static_cast<float>(average_speed_);
    msg.gain_multiplier = static_cast<float>(gain_multiplier_);
    msg.omega_o_x = static_cast<float>(omega_o_x_);
    msg.omega_o_y = static_cast<float>(omega_o_y_);
    msg.omega_o_z = static_cast<float>(omega_o_z_);
    msg.omega_c_x = static_cast<float>(omega_c_x_);
    msg.omega_c_y = static_cast<float>(omega_c_y_);
    msg.omega_c_z = static_cast<float>(omega_c_z_);
    msg.peak_velocity = static_cast<float>(peak_velocity_);
    msg.peak_acceleration = static_cast<float>(peak_acceleration_);
    msg.settling_time = static_cast<float>(settling_time_);
    msg.tracking_rmse =
        tracking_sample_count_ > 0
            ? static_cast<float>(std::sqrt(
                  tracking_error_squared_sum_ /
                  static_cast<double>(tracking_sample_count_)))
            : std::numeric_limits<float>::quiet_NaN();
    return msg;
  }

  void publishControlAdaptationLog()
  {
    if (!has_control_adaptation_metrics_) return;
    control_adaptation_pub_->publish(buildControlAdaptationLogMsg());
  }

  void writeControlAdaptationCsvRow()
  {
    if (!has_control_adaptation_metrics_ || control_adaptation_csv_written_)
    {
      return;
    }

    std::filesystem::path log_path(
        this->get_parameter("control_adaptation_log_path").as_string());
    if (!log_path.has_parent_path())
    {
      log_path = std::filesystem::current_path() / log_path;
    }

    std::error_code ec;
    auto parent = log_path.parent_path();
    if (!parent.empty())
    {
      std::filesystem::create_directories(parent, ec);
      if (ec)
      {
        RCLCPP_WARN(this->get_logger(),
            "无法创建控制适应日志目录 %s: %s",
            parent.string().c_str(), ec.message().c_str());
        return;
      }
    }

    bool write_header =
        !std::filesystem::exists(log_path) ||
        std::filesystem::file_size(log_path, ec) == 0;
    ec.clear();

    std::ofstream log_file(log_path, std::ios::app);
    if (!log_file.is_open())
    {
      RCLCPP_WARN(this->get_logger(),
          "无法打开控制适应日志文件: %s", log_path.string().c_str());
      return;
    }

    if (write_header)
    {
      log_file
          << "mission_id,uav_id,motion_style,target_distance,duration,"
          << "average_speed,gain_multiplier,omega_o_x,omega_o_y,omega_o_z,"
          << "omega_c_x,omega_c_y,omega_c_z,peak_velocity,peak_acceleration,"
          << "settling_time,tracking_rmse\n";
    }

    auto msg = buildControlAdaptationLogMsg();
    auto value = [](float number) {
      return std::isfinite(number) ? std::to_string(number) : std::string("nan");
    };

    log_file << std::fixed << std::setprecision(6)
             << msg.mission_id << ','
             << static_cast<int>(msg.uav_id) << ','
             << msg.motion_style << ','
             << value(msg.target_distance) << ','
             << value(msg.duration) << ','
             << value(msg.average_speed) << ','
             << value(msg.gain_multiplier) << ','
             << value(msg.omega_o_x) << ','
             << value(msg.omega_o_y) << ','
             << value(msg.omega_o_z) << ','
             << value(msg.omega_c_x) << ','
             << value(msg.omega_c_y) << ','
             << value(msg.omega_c_z) << ','
             << value(msg.peak_velocity) << ','
             << value(msg.peak_acceleration) << ','
             << value(msg.settling_time) << ','
             << value(msg.tracking_rmse) << '\n';

    control_adaptation_csv_written_ = true;
    RCLCPP_INFO(this->get_logger(),
        "控制适应日志已写入: %s (mission=%u, uav=%d)",
        log_path.string().c_str(), mission_id_, static_cast<int>(uav_id_));
  }

  void publishOffboardControlMode()
  {
    const auto msg = ladrc_controller::makeOffboardControlMode(
      control_mode_, this->get_clock()->now().nanoseconds() / 1000);
    offboard_mode_pub_->publish(msg);
  }

  px4_msgs::msg::TrajectorySetpoint publishTrajectorySetpoint(
                                  double px_enu, double py_enu, double pz_enu,
                                  double ax_enu, double ay_enu, double az_enu,
                                  double yaw_ref,
                                  bool publish_accel_feedforward = false)
  {
    const auto msg = ladrc_controller::makeTrajectorySetpoint(
      control_mode_, px_enu, py_enu, pz_enu,
      ax_enu, ay_enu, az_enu, yaw_ref,
      publish_accel_feedforward,
      this->get_clock()->now().nanoseconds() / 1000);
    trajectory_pub_->publish(msg);
    return msg;
  }

  // Member variables
  std::unique_ptr<ladrc_controller::LADRCController> ladrc_x_;
  std::unique_ptr<ladrc_controller::LADRCController> ladrc_y_;
  std::unique_ptr<ladrc_controller::LADRCController> ladrc_z_;

  // [Phase 1] Swarm 命令订阅 & 状态发布
  rclcpp::Subscription<uav_swarm_interfaces::msg::UAVSwarmCommand>::SharedPtr swarm_command_sub_;
  rclcpp::Subscription<uav_swarm_interfaces::msg::UAVExecutionCommand>::SharedPtr
      execution_command_sub_;
  rclcpp::Subscription<px4_msgs::msg::VehicleOdometry>::SharedPtr odom_sub_;
  rclcpp::Publisher<uav_swarm_interfaces::msg::UAVStatus>::SharedPtr status_pub_;
  rclcpp::Publisher<geometry_msgs::msg::Point>::SharedPtr odom_pub_;
  rclcpp::Publisher<nav_msgs::msg::Odometry>::SharedPtr swarm_state_pub_;
  rclcpp::Publisher<uav_swarm_interfaces::msg::TrajectoryMetrics>::SharedPtr
      trajectory_metrics_pub_;
  rclcpp::Publisher<uav_swarm_interfaces::msg::ControlAdaptationLog>::SharedPtr
      control_adaptation_pub_;
  rclcpp::Publisher<uav_swarm_interfaces::msg::IAPFDebug>::SharedPtr
      iapf_debug_pub_;
  rclcpp::Publisher<uav_swarm_interfaces::msg::ControlTrackingDebug>::SharedPtr
      control_tracking_debug_pub_;

  rclcpp::Publisher<px4_msgs::msg::OffboardControlMode>::SharedPtr offboard_mode_pub_;
  rclcpp::Publisher<px4_msgs::msg::TrajectorySetpoint>::SharedPtr trajectory_pub_;
  rclcpp::Publisher<px4_msgs::msg::VehicleCommand>::SharedPtr vehicle_command_pub_;

  rclcpp::TimerBase::SharedPtr control_timer_;
  rclcpp::TimerBase::SharedPtr command_timer_;

  // 自身 UAV ID（从命名空间自动提取）
  uint8_t self_uav_id_ = 0;

  // [Phase 1] Swarm command 数据
  uint32_t mission_id_ = 0;
  uint8_t uav_id_ = 0;
  double target_pos_x_ = 0.0;
  double target_pos_y_ = 0.0;
  double target_pos_z_ = 0.0;
  double target_duration_ = 0.0;
  std::string motion_style_ = "normal";
  double safety_factor_ = 0.0;
  bool has_command_ = false;
  ladrc_controller::ControlMode control_mode_{
    ladrc_controller::ControlMode::LADRC_ACCELERATION};
  bool active_new_profile_ = false;
  bool profile_soft_safety_active_ = false;
  double profile_iapf_enter_distance_ = 0.0;
  double profile_iapf_exit_distance_ = 0.0;
  double profile_iapf_repulsion_scale_ = 1.0;
  std::string active_profile_configuration_id_;

  // 悬停保持：用首次位置作为固定 setpoint，避免漂移正反馈
  bool hover_hold_set_ = false;
  double hover_hold_x_ = 0.0;
  double hover_hold_y_ = 0.0;
  double hover_hold_z_ = 0.0;

  // [Phase 2] 轨迹生成器
  ladrc_controller::MinimumJerkTrajectory traj_x_;
  ladrc_controller::MinimumJerkTrajectory traj_y_;
  ladrc_controller::MinimumJerkTrajectory traj_z_;
  rclcpp::Time command_start_time_;

  uav_swarm_interfaces::msg::TrajectoryMetrics metrics_msg_;
  bool has_trajectory_metrics_ = false;
  bool arrival_time_recorded_ = false;
  double arrival_time_error_ = std::numeric_limits<double>::quiet_NaN();
  int trajectory_metrics_pub_counter_ = 0;

  // 控制适应日志数据
  bool has_control_adaptation_metrics_ = false;
  bool control_adaptation_csv_written_ = false;
  double target_distance_ = 0.0;
  double average_speed_ = 0.0;
  double gain_multiplier_ = 1.0;
  double omega_o_x_ = 0.0;
  double omega_o_y_ = 0.0;
  double omega_o_z_ = 0.0;
  double omega_c_x_ = 0.0;
  double omega_c_y_ = 0.0;
  double omega_c_z_ = 0.0;
  double peak_velocity_ = 0.0;
  double peak_acceleration_ = 0.0;
  double settling_time_ = std::numeric_limits<double>::quiet_NaN();
  double latest_elapsed_time_ = 0.0;
  double tracking_error_squared_sum_ = 0.0;
  uint64_t tracking_sample_count_ = 0;
  Eigen::Vector3d previous_velocity_{0.0, 0.0, 0.0};
  bool previous_velocity_valid_ = false;

  // Odom 数据
  px4_msgs::msg::VehicleOdometry current_odom_;
  bool has_odom_ = false;

  // [Phase 3 预置] 悬停状态（Phase 1 默认为 false，Phase 3 完整实现）
  bool is_hover_stable_ = false;

  // Odom 发布计数器 (~10Hz throttle)
  int odom_pub_counter_ = 0;

  // [Phase 4] IAPF 邻居状态
  bool avoidance_mode_from_legacy_ = false;
  bool enter_distance_from_legacy_ = false;
  Eigen::Vector3d filtered_iapf_position_offset_{Eigen::Vector3d::Zero()};
  Eigen::Vector3d filtered_iapf_acceleration_offset_{Eigen::Vector3d::Zero()};
  std::vector<uint8_t> configured_neighbor_ids_;
  std::unordered_map<uint8_t, NeighborState> neighbor_states_;
  std::vector<rclcpp::Subscription<px4_msgs::msg::VehicleOdometry>::SharedPtr> neighbor_subs_;

  // 状态机
  std::atomic<FlightState> flight_state_;
  std::atomic<uint64_t> offboard_setpoint_counter_;

  double dt_;
};

int main(int argc, char **argv)
{
  rclcpp::init(argc, argv);
  rclcpp::spin(std::make_shared<LADRCPositionControllerNode>());
  rclcpp::shutdown();
  return 0;
}
