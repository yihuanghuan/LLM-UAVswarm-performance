#include <rclcpp/rclcpp.hpp>
#include <px4_msgs/msg/vehicle_odometry.hpp>
#include <px4_msgs/msg/offboard_control_mode.hpp>
#include <px4_msgs/msg/trajectory_setpoint.hpp>
#include <px4_msgs/msg/vehicle_command.hpp>
#include <px4_msgs/msg/vehicle_control_mode.hpp>
#include <uav_swarm_interfaces/msg/uav_swarm_command.hpp>
#include <uav_swarm_interfaces/msg/uav_status.hpp>
#include <geometry_msgs/msg/point.hpp>
#include "ladrc_controller/ladrc_core.hpp"
#include "ladrc_controller/minimum_jerk_trajectory.hpp"
#include <cmath>
#include <chrono>
#include <atomic>
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
public:
  LADRCPositionControllerNode()
      : Node("ladrc_position_controller")
  {
    // 声明参数
    this->declare_parameter("control_frequency", 50.0);
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

    // Gazebo 多机 spawn 偏移量（sitl_multiple_run.sh 默认 Y=3*instance）
    this->declare_parameter("enu_offset_x", 0.0);
    this->declare_parameter("enu_offset_y", 0.0);
    this->declare_parameter("enu_offset_z", 0.0);

    // [Phase 4] IAPF 避障参数
    this->declare_parameter("iapf_safe_distance", 1.0);
    this->declare_parameter("iapf_repulsion_gain", 1.0);
    this->declare_parameter("neighbor_uav_ids", std::vector<int64_t>{});

    // 获取参数
    double control_freq = this->get_parameter("control_frequency").as_double();
    dt_ = 1.0 / control_freq;

    // 初始化 LADRC 控制器
    initializeControllers();

    // --- [Phase 1] 订阅 swarm_command（相对话题，自动拼接到命名空间） ---
    swarm_command_sub_ = this->create_subscription<uav_swarm_interfaces::msg::UAVSwarmCommand>(
        "swarm_command", rclcpp::QoS(10),
        std::bind(&LADRCPositionControllerNode::swarmCommandCallback, this, std::placeholders::_1));

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

      auto callback = [this, neighbor_id](const px4_msgs::msg::VehicleOdometry::SharedPtr msg) {
        // 存入邻居位置 map：全局 ENU（本地 + spawn 偏移 Y=3*id）
        neighbor_positions_[neighbor_id] = Eigen::Vector3d(
            msg->position[1],   // NED.y → ENU.x
            msg->position[0] + 3.0 * neighbor_id,   // NED.x → ENU.y + offset
            -msg->position[2]   // -NED.z → ENU.z
        );
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

  // --- [Phase 2] swarm_command 回调（含轨迹初始化） ---
  void swarmCommandCallback(const uav_swarm_interfaces::msg::UAVSwarmCommand::SharedPtr msg)
  {
    RCLCPP_INFO(this->get_logger(),
        "UAV%d swarm_cmd 回调触发 (目标=[%.1f,%.1f,%.1f])",
        self_uav_id_, msg->target_pos.x, msg->target_pos.y, msg->target_pos.z);

    // 状态机未就绪或未收到里程计，静默忽略命令
    if (flight_state_.load() != FlightState::RUNNING_TRAJECTORY || !has_odom_)
    {
      RCLCPP_WARN_THROTTLE(this->get_logger(), *this->get_clock(), 5000,
          "UAV%d 尚未就绪（状态=%d, odom=%d），忽略命令", msg->uav_id,
          (int)flight_state_.load(), has_odom_);
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
                          msg->motion_style == motion_style_);
      if (same_target && same_params)
      {
        return;  // 静默忽略重复消息
      }
      RCLCPP_INFO(this->get_logger(),
          "收到新任务指令 (UAV%d)，目标/参数已变更，覆盖旧任务", msg->uav_id);
    }

    uav_id_ = msg->uav_id;
    target_duration_ = msg->duration;
    motion_style_ = msg->motion_style;
    safety_factor_ = msg->safety_factor;
    has_command_ = true;

    // 全局 ENU → 本地 ENU：减去 spawn 偏移量
    double off_x = this->get_parameter("enu_offset_x").as_double();
    double off_y = this->get_parameter("enu_offset_y").as_double();
    double off_z = this->get_parameter("enu_offset_z").as_double();
    target_pos_x_ = msg->target_pos.x - off_x;
    target_pos_y_ = msg->target_pos.y - off_y;
    target_pos_z_ = msg->target_pos.z - off_z;

    // 提取当前实际位置作为轨迹起点 (ENU)
    double p0_x = current_odom_.position[1];  // NED.y → ENU.x
    double p0_y = current_odom_.position[0];  // NED.x → ENU.y
    double p0_z = -current_odom_.position[2]; // -NED.z → ENU.z

    // 初始化三个轴的 Minimum Jerk 轨迹
    traj_x_.initialize(p0_x, target_pos_x_, target_duration_);
    traj_y_.initialize(p0_y, target_pos_y_, target_duration_);
    traj_z_.initialize(p0_z, target_pos_z_, target_duration_);

    // Warm start LESO: 用当前测量位置初始化观测器 z1 状态，避免从 0 开始导致瞬态反向指令
    ladrc_x_->setObserverInitialState(p0_x, 0.0, 0.0);
    ladrc_y_->setObserverInitialState(p0_y, 0.0, 0.0);
    ladrc_z_->setObserverInitialState(p0_z, 0.0, 0.0);

    // 记录命令接收时间
    command_start_time_ = this->now();

    // [Phase 3] 动态增益调节
    applyDynamicGains();

    // 重置悬停状态
    is_hover_stable_ = false;

    RCLCPP_INFO(this->get_logger(),
        ">>> UAV%d 全局[%.1f,%.1f,%.1f]→本地[%.1f,%.1f,%.1f] T=%.1fs %s",
        uav_id_,
        msg->target_pos.x, msg->target_pos.y, msg->target_pos.z,
        target_pos_x_, target_pos_y_, target_pos_z_,
        target_duration_, motion_style_.c_str());
  }

  void odomCallback(const px4_msgs::msg::VehicleOdometry::SharedPtr msg)
  {
    RCLCPP_INFO_ONCE(this->get_logger(), "已接收到 vehicle_odometry 消息");
    current_odom_ = *msg;
    has_odom_ = true;
  }

  // --- 状态机逻辑 ---
  void publishVehicleCommand(uint16_t command, float param1 = 0.0, float param2 = 0.0, float param7 = 0.0)
  {
    px4_msgs::msg::VehicleCommand msg{};
    msg.command = command;
    msg.param1 = param1;
    msg.param2 = param2;
    msg.param7 = param7;
    msg.target_system = 0;     // 广播到所有系统，多机模式下各实例 MAV_SYS_ID 不同
    msg.target_component = 0;  // 广播到所有组件
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

    // 若无命令，发布首次测量位置作为固定悬停保持 setpoint
    if (!has_command_)
    {
      if (!hover_hold_set_)
      {
        hover_hold_x_ = x_meas;
        hover_hold_y_ = y_meas;
        hover_hold_z_ = z_meas;
        hover_hold_set_ = true;
        RCLCPP_INFO(this->get_logger(),
            "UAV%d 悬停保持锁定: [%.2f, %.2f, %.2f]", self_uav_id_, x_meas, y_meas, z_meas);
      }
      publishTrajectorySetpoint(hover_hold_x_, hover_hold_y_, hover_hold_z_,
                                0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0);
      // 悬停保持时也定期输出位置（10s 节流）
      RCLCPP_INFO_THROTTLE(this->get_logger(), *this->get_clock(), 10000,
          "UAV%d 悬停保持 Pos[%.2f,%.2f,%.2f]", self_uav_id_, x_meas, y_meas, z_meas);
      return;
    }
    hover_hold_set_ = false;  // 收到命令，清除悬停保持

    // 2. 计算已用时间并从轨迹生成器获取参考值
    double elapsed = (this->now() - command_start_time_).seconds();
    bool x_finished = traj_x_.isFinished(elapsed);
    bool y_finished = traj_y_.isFinished(elapsed);
    bool z_finished = traj_z_.isFinished(elapsed);
    (void)x_finished; (void)y_finished; (void)z_finished;

    auto ref_x = traj_x_.evaluate(elapsed);
    auto ref_y = traj_y_.evaluate(elapsed);
    auto ref_z = traj_z_.evaluate(elapsed);

    double x_ref = ref_x.position;
    double y_ref = ref_y.position;
    double z_ref = ref_z.position;
    double vx_ref = ref_x.velocity;
    double vy_ref = ref_y.velocity;
    double vz_ref = ref_z.velocity;
    double ax_ref = ref_x.acceleration;
    double ay_ref = ref_y.acceleration;
    double az_ref = ref_z.acceleration;

    // [Phase 3] 悬停稳定检测
    bool all_finished = x_finished && y_finished && z_finished;
    if (all_finished)
    {
      double pos_err = std::sqrt(
          (x_ref - x_meas) * (x_ref - x_meas) +
          (y_ref - y_meas) * (y_ref - y_meas) +
          (z_ref - z_meas) * (z_ref - z_meas));
      double vel_mag = std::sqrt(
          current_odom_.velocity[0] * current_odom_.velocity[0] +
          current_odom_.velocity[1] * current_odom_.velocity[1] +
          current_odom_.velocity[2] * current_odom_.velocity[2]);

      if (pos_err < 0.3 && vel_mag < 0.3)
      {
        if (!is_hover_stable_)
        {
          is_hover_stable_ = true;
          RCLCPP_INFO(this->get_logger(),
              "悬停稳定! pos_err=%.2fm, vel=%.2fm/s → is_hover_stable=true",
              pos_err, vel_mag);
        }
      }
    }

    // 3. LADRC 观测器静默运行（状态估计，供监控）
    double ax_cmd = ladrc_x_->update(x_ref, vx_ref, ax_ref, x_meas);
    double ay_cmd = ladrc_y_->update(y_ref, vy_ref, ay_ref, y_meas);
    double az_cmd = ladrc_z_->update(z_ref, vz_ref, az_ref, z_meas);

    // [Phase 4] IAPF 避障：计算斥力，叠加到加速度前馈
    Eigen::Vector3d iapf = computeIAPF(x_meas, y_meas, z_meas);
    double iapf_x = iapf.x();
    double iapf_y = iapf.y();
    double iapf_z = iapf.z();

    // 4. 发布 UAVStatus
    publishUAVStatus();

    // 5. 发布轨迹设定点：位置+加速度 + IAPF 斥力
    const double IAPF_POS_GAIN = 0.05;
    publishTrajectorySetpoint(
        x_ref + IAPF_POS_GAIN * iapf_x,
        y_ref + IAPF_POS_GAIN * iapf_y,
        z_ref + IAPF_POS_GAIN * iapf_z,
        vx_ref, vy_ref, vz_ref,
        ax_ref + iapf_x, ay_ref + iapf_y, az_ref + iapf_z, 0.0);

    // 日志（当 IAPF 激活时附加 "!IAPF!" 标记）
    RCLCPP_INFO_THROTTLE(this->get_logger(), *this->get_clock(), 1000,
        "UAV%d Ref[%.1f,%.1f,%.1f] Pos[%.2f,%.2f,%.2f] Cmd[%.1f,%.1f,%.1f]%s",
        uav_id_, x_ref, y_ref, z_ref,
        x_meas, y_meas, z_meas,
        ax_cmd, ay_cmd, az_cmd,
        (iapf.norm() > 0.1 ? " !IAPF!" : ""));
  }

  // --- [Phase 3] 动态增益调节 ---
  void applyDynamicGains()
  {
    double gain_mult = 1.0;
    if (motion_style_ == "smooth") {
      gain_mult = 0.7;
    } else if (motion_style_ == "aggressive") {
      gain_mult = 1.5;
    }

    // 读取配置文件的基值，乘以增益系数后应用到各轴
    auto apply_axis = [this, gain_mult](
        std::unique_ptr<ladrc_controller::LADRCController>& ctrl,
        const std::string& param_o, const std::string& param_c)
    {
      double base_omega_o = this->get_parameter(param_o).as_double();
      double base_omega_c = this->get_parameter(param_c).as_double();
      ctrl->setObserverBandwidth(base_omega_o * gain_mult);
      ctrl->setControllerBandwidth(base_omega_c * gain_mult);
    };

    apply_axis(ladrc_x_, "omega_o_x", "omega_c_x");
    apply_axis(ladrc_y_, "omega_o_y", "omega_c_y");
    apply_axis(ladrc_z_, "omega_o_z", "omega_c_z");

    RCLCPP_INFO_THROTTLE(this->get_logger(), *this->get_clock(), 5000,
        "动态增益: %s → multiplier=%.1f (ωo, ωc adjusted)",
        motion_style_.c_str(), gain_mult);
  }

  // --- [Phase 4] IAPF 斥力计算 ---
  // 返回总斥力向量 (ENU)，safety_factor=0 时返回零向量
  Eigen::Vector3d computeIAPF(double x_meas, double y_meas, double z_meas)
  {
    Eigen::Vector3d F_rep(0.0, 0.0, 0.0);
    if (safety_factor_ <= 0.0 || neighbor_positions_.empty()) return F_rep;

    double R_safe = this->get_parameter("iapf_safe_distance").as_double();
    double K_rep = this->get_parameter("iapf_repulsion_gain").as_double();

    double my_off_x = this->get_parameter("enu_offset_x").as_double();
    double my_off_y = this->get_parameter("enu_offset_y").as_double();
    double my_off_z = this->get_parameter("enu_offset_z").as_double();
    Eigen::Vector3d pos_own(x_meas + my_off_x, y_meas + my_off_y, z_meas + my_off_z);

    for (const auto& [nbr_id, nbr_pos] : neighbor_positions_)
    {
      double d = (pos_own - nbr_pos).norm();
      if (d <= 0.01 || d >= R_safe) continue;

      Eigen::Vector3d dir = (pos_own - nbr_pos).normalized();

      // IAPF 斥力：F = K_rep * (1/d - 1/R_safe) / d^2
      // 加入微小 Z 轴侧向力 (+5%)，避免局部极小值死锁
      double mag = K_rep * (1.0 / d - 1.0 / R_safe) / (d * d);
      Eigen::Vector3d force = dir * mag;
      force.z() += mag * 0.05;  // 引导从上下错开
      F_rep += force;

      RCLCPP_WARN_THROTTLE(this->get_logger(), *this->get_clock(), 500,
          "IAPF 避障: U%d d=%.2fm Frep[%.1f,%.1f,%.1f]",
          nbr_id, d, force.x(), force.y(), force.z());
    }

    return F_rep * safety_factor_;
  }

  // --- [Phase 1] 新增 UAVStatus 发布 ---
  void publishUAVStatus()
  {
    uav_swarm_interfaces::msg::UAVStatus msg;
    msg.uav_id = uav_id_;
    msg.is_hover_stable = is_hover_stable_;
    status_pub_->publish(msg);
  }

  void publishOffboardControlMode()
  {
    px4_msgs::msg::OffboardControlMode msg{};
    msg.timestamp = this->get_clock()->now().nanoseconds() / 1000;
    msg.position = true;
    msg.velocity = false;
    msg.acceleration = false;
    msg.attitude = false;
    msg.body_rate = false;

    offboard_mode_pub_->publish(msg);
  }

  void publishTrajectorySetpoint(double px_enu, double py_enu, double pz_enu,
                                  double vx_enu, double vy_enu, double vz_enu,
                                  double ax_enu, double ay_enu, double az_enu, double yaw_ref)
  {
    px4_msgs::msg::TrajectorySetpoint msg{};
    msg.timestamp = this->get_clock()->now().nanoseconds() / 1000;

    // 位置参考 (ENU → NED)：纯位置模式，PX4 位置控制器独立完成轨迹跟踪
    msg.position = {
        static_cast<float>(py_enu),      // NED North = ENU y
        static_cast<float>(px_enu),      // NED East = ENU x
        static_cast<float>(-pz_enu)};    // NED Down = -ENU z

    // 速度和加速度留空 (NaN)，让 PX4 独立计算，避免多模式耦合干扰
    msg.velocity = {NAN, NAN, NAN};
    msg.acceleration = {NAN, NAN, NAN};

    msg.yaw = static_cast<float>(yaw_ref);

    trajectory_pub_->publish(msg);
  }

  // Member variables
  std::unique_ptr<ladrc_controller::LADRCController> ladrc_x_;
  std::unique_ptr<ladrc_controller::LADRCController> ladrc_y_;
  std::unique_ptr<ladrc_controller::LADRCController> ladrc_z_;

  // [Phase 1] Swarm 命令订阅 & 状态发布
  rclcpp::Subscription<uav_swarm_interfaces::msg::UAVSwarmCommand>::SharedPtr swarm_command_sub_;
  rclcpp::Subscription<px4_msgs::msg::VehicleOdometry>::SharedPtr odom_sub_;
  rclcpp::Publisher<uav_swarm_interfaces::msg::UAVStatus>::SharedPtr status_pub_;
  rclcpp::Publisher<geometry_msgs::msg::Point>::SharedPtr odom_pub_;

  rclcpp::Publisher<px4_msgs::msg::OffboardControlMode>::SharedPtr offboard_mode_pub_;
  rclcpp::Publisher<px4_msgs::msg::TrajectorySetpoint>::SharedPtr trajectory_pub_;
  rclcpp::Publisher<px4_msgs::msg::VehicleCommand>::SharedPtr vehicle_command_pub_;

  rclcpp::TimerBase::SharedPtr control_timer_;
  rclcpp::TimerBase::SharedPtr command_timer_;

  // 自身 UAV ID（从命名空间自动提取）
  uint8_t self_uav_id_ = 0;

  // [Phase 1] Swarm command 数据
  uint8_t uav_id_ = 0;
  double target_pos_x_ = 0.0;
  double target_pos_y_ = 0.0;
  double target_pos_z_ = 0.0;
  double target_duration_ = 0.0;
  std::string motion_style_ = "normal";
  double safety_factor_ = 0.0;
  bool has_command_ = false;

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

  // Odom 数据
  px4_msgs::msg::VehicleOdometry current_odom_;
  bool has_odom_ = false;

  // [Phase 3 预置] 悬停状态（Phase 1 默认为 false，Phase 3 完整实现）
  bool is_hover_stable_ = false;

  // Odom 发布计数器 (~10Hz throttle)
  int odom_pub_counter_ = 0;

  // [Phase 4] IAPF 邻居状态
  std::unordered_map<uint8_t, Eigen::Vector3d> neighbor_positions_;
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
