std_msgs/Header header

uint32 mission_id
uint8 uav_id
string control_mode
bool has_command

# 以下参考量和实测量均为无人机局部 ENU 坐标系
geometry_msgs/Point nominal_position
geometry_msgs/Point safe_position
geometry_msgs/Vector3 nominal_velocity
geometry_msgs/Vector3 nominal_acceleration
geometry_msgs/Vector3 safe_acceleration
geometry_msgs/Vector3 ladrc_output

# 三个向量分别保存 X/Y/Z 轴 LESO 对应的 z1、z2、z3
geometry_msgs/Vector3 leso_z1
geometry_msgs/Vector3 leso_z2
geometry_msgs/Vector3 leso_z3

geometry_msgs/Point actual_position
geometry_msgs/Vector3 actual_velocity
geometry_msgs/Vector3 tracking_error

# 实际写入 PX4 TrajectorySetpoint 的 NED 字段，未启用字段保持 NaN
geometry_msgs/Vector3 px4_position_setpoint
geometry_msgs/Vector3 px4_velocity_setpoint
geometry_msgs/Vector3 px4_acceleration_setpoint
