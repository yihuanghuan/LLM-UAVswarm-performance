uint8 uav_id
uint32 mission_id
bool system_ready                 # 已完成 Armed + Offboard + 垂直起飞门控
bool is_hover_stable              # 到达目标点并稳定悬停时为 true
uint8 STABILITY_UNSTABLE=0
uint8 STABILITY_CANDIDATE=1
uint8 STABILITY_CONFIRMED=2
uint8 stability_state
float32 position_error
float32 speed                       # 位置差分低通速度，用于稳定判定
float32 raw_ekf_speed               # PX4 EKF 原始速度，仅供诊断
std_msgs/Header header
