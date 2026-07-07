std_msgs/Header header

uint32 mission_id                 # 全局任务编号，对应调度器 task_sequence_id
uint8 uav_id                      # 无人机编号
geometry_msgs/Point target_pos    # 绝对目标坐标 [x, y, z]
float32 duration                  # 期望到达时间 (秒)
string motion_style               # "normal", "smooth", "aggressive"
float32 safety_factor             # IAPF 防撞缩放系数 (若无要求可传 0.0)
