uint8 uav_id
uint32 mission_id
bool is_hover_stable              # 到达目标点并稳定悬停时为 true
uint8 STABILITY_UNSTABLE=0
uint8 STABILITY_CANDIDATE=1
uint8 STABILITY_CONFIRMED=2
uint8 stability_state
float32 position_error
float32 speed
std_msgs/Header header
