cmake_minimum_required(VERSION 3.8)
project(ladrc_controller)

if(CMAKE_COMPILER_IS_GNUCXX OR CMAKE_CXX_COMPILER_ID MATCHES "Clang")
  add_compile_options(-Wall -Wextra -Wpedantic)
endif()

# Find dependencies
find_package(ament_cmake REQUIRED)
find_package(rclcpp REQUIRED)
find_package(geometry_msgs REQUIRED)
find_package(nav_msgs REQUIRED)
find_package(builtin_interfaces REQUIRED)
find_package(std_msgs REQUIRED)
find_package(px4_msgs REQUIRED)
find_package(uav_swarm_interfaces REQUIRED)
find_package(Eigen3 REQUIRED)

# Include directories
include_directories(include)
include_directories(${EIGEN3_INCLUDE_DIRS})

# LADRC Library
add_library(ladrc_lib
  src/ladrc_core.cpp
  src/leso.cpp
  src/lsef.cpp
  src/iapf_core.cpp
)

ament_target_dependencies(ladrc_lib
  rclcpp
)

# LADRC Controller Node
add_executable(ladrc_position_controller_node
  src/ladrc_position_controller_node.cpp
)

target_link_libraries(ladrc_position_controller_node
  ladrc_lib
)

ament_target_dependencies(ladrc_position_controller_node
  rclcpp
  geometry_msgs
  nav_msgs
  std_msgs
  px4_msgs
  uav_swarm_interfaces
)

# Install
install(TARGETS
  ladrc_lib
  ARCHIVE DESTINATION lib
  LIBRARY DESTINATION lib
  RUNTIME DESTINATION bin
)

install(TARGETS
  ladrc_position_controller_node
  DESTINATION lib/${PROJECT_NAME}
)

install(DIRECTORY
  include/
  DESTINATION include
)

install(DIRECTORY
  config/
  DESTINATION share/${PROJECT_NAME}/config
)

install(DIRECTORY
  launch/
  DESTINATION share/${PROJECT_NAME}/launch
)

if(BUILD_TESTING)
  find_package(ament_cmake_gtest REQUIRED)
  ament_add_gtest(test_iapf_core test/test_iapf_core.cpp)
  target_link_libraries(test_iapf_core ladrc_lib)
  ament_add_gtest(test_control_setpoint test/test_control_setpoint.cpp)
  ament_target_dependencies(test_control_setpoint px4_msgs)
  target_link_libraries(test_control_setpoint ladrc_lib)
  ament_add_gtest(
    test_execution_profile_guard test/test_execution_profile_guard.cpp)
  ament_add_gtest(
    test_minimum_jerk_trajectory test/test_minimum_jerk_trajectory.cpp)
  ament_add_gtest(test_swarm_state_builder test/test_swarm_state_builder.cpp)
  ament_target_dependencies(
    test_swarm_state_builder nav_msgs px4_msgs builtin_interfaces)
endif()

ament_package()
