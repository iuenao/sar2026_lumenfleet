#!/usr/bin/env python3
#
# Navigation stack for Unitree Go2 -- RTAB-Map mapping source variant.
#
# Unlike go2_navigation_slam.launch.py (slam_toolbox + lidar as the /map
# source), this assumes RTAB-Map (depth camera) is ALREADY running
# separately and already publishing /map (nav_msgs/OccupancyGrid) -- this
# file does NOT launch go2_online, slam_toolbox, or any mapping at all.
# It only adds what Nav2 + hybrid_explorer.py need on top of an
# already-running mapping session:
#
#   body_filter + utlidar_to_laserscan  →  /utlidar/scan (lidar, for
#                                           obstacle avoidance -- independent
#                                           of whatever produces /map)
#   Nav2 stack                          →  global costmap's static_layer
#                                           subscribes to RTAB-Map's /map,
#                                           same as it would slam_toolbox's
#   collision_monitor                   →  safety stop / slowdown zones
#   velocity_smoother                   →  smooth acceleration, hard cap
#   go2_cmd_vel_bridge                  →  /cmd_vel -> /api/sport/request
#
# Prerequisites already running before this launch file:
#   go2_online.launch.py (driver + retime_utlidar + robot_state_publisher)
#   RTAB-Map (or anything else) publishing /map and odom -> base_link TF

import os

from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument
from launch.conditions import IfCondition
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node
from launch_ros.parameter_descriptions import ParameterValue


def generate_launch_description():

    bringup_dir = get_package_share_directory('go2_bringup')
    nav2_params_file = LaunchConfiguration('params_file')
    use_rviz = LaunchConfiguration('use_rviz')
    enable_motion = LaunchConfiguration('enable_motion')

    # ── Body/leg-swing exclusion ─────────────────────────────────────────────
    body_filter = Node(
        package='go2_bringup',
        executable='body_filter.py',
        name='body_filter',
        output='screen',
        parameters=[{
            'input_topic': '/utlidar/cloud_base_retimed',
            'output_topic': '/utlidar/cloud_base_filtered',
        }],
    )

    # ── UTLidar → LaserScan ──────────────────────────────────────────────────
    utlidar_to_laserscan = Node(
        package='pointcloud_to_laserscan',
        executable='pointcloud_to_laserscan_node',
        name='utlidar_to_laserscan',
        output='screen',
        parameters=[{
            'target_frame':       'base_link',
            'transform_tolerance': 0.05,
            'min_height':         -0.15,
            'max_height':          1.0,
            'angle_min':          -3.14159,
            'angle_max':           3.14159,
            'angle_increment':     0.00873,
            'scan_time':           0.1,
            'range_min':           0.10,
            'range_max':          20.0,
            'use_inf':             True,
        }],
        remappings=[
            ('cloud_in', '/utlidar/cloud_base_filtered'),
            ('scan',     '/utlidar/scan'),
        ]
    )

    # ── Navigation RViz ──────────────────────────────────────────────────────
    # Default false: pair this with a separately-run RViz already showing the
    # RTAB-Map session (same ROS graph, --network host makes it transparent).
    rviz_nav = Node(
        package='rviz2',
        executable='rviz2',
        name='rviz2',
        output='screen',
        arguments=['-d', os.path.join(bringup_dir, 'config', 'nav2_rviz.rviz')],
        condition=IfCondition(use_rviz)
    )

    # ── Nav2 core nodes ──────────────────────────────────────────────────────
    controller_server = Node(
        package='nav2_controller',
        executable='controller_server',
        name='controller_server',
        output='screen',
        parameters=[nav2_params_file],
        remappings=[('cmd_vel', 'cmd_vel_nav')]
    )

    smoother_server = Node(
        package='nav2_smoother',
        executable='smoother_server',
        name='smoother_server',
        output='screen',
        parameters=[nav2_params_file]
    )

    planner_server = Node(
        package='nav2_planner',
        executable='planner_server',
        name='planner_server',
        output='screen',
        parameters=[nav2_params_file]
    )

    behavior_server = Node(
        package='nav2_behaviors',
        executable='behavior_server',
        name='behavior_server',
        output='screen',
        parameters=[nav2_params_file]
    )

    bt_navigator = Node(
        package='nav2_bt_navigator',
        executable='bt_navigator',
        name='bt_navigator',
        output='screen',
        parameters=[nav2_params_file]
    )

    velocity_smoother = Node(
        package='nav2_velocity_smoother',
        executable='velocity_smoother',
        name='velocity_smoother',
        output='screen',
        parameters=[nav2_params_file],
        remappings=[
            ('cmd_vel',         'cmd_vel_nav'),
            ('cmd_vel_smoothed', 'cmd_vel_smoothed'),
        ]
    )

    collision_monitor = Node(
        package='nav2_collision_monitor',
        executable='collision_monitor',
        name='collision_monitor',
        output='screen',
        parameters=[nav2_params_file]
    )

    lifecycle_manager_nav = Node(
        package='nav2_lifecycle_manager',
        executable='lifecycle_manager',
        name='lifecycle_manager_navigation',
        output='screen',
        parameters=[nav2_params_file]
    )

    # ── Go2 cmd_vel bridge ───────────────────────────────────────────────────
    go2_cmd_vel_bridge = Node(
        package='go2_cmd_vel_bridge',
        executable='go2_cmd_vel_bridge',
        name='go2_cmd_vel_bridge',
        output='screen',
        parameters=[{
            'enabled': ParameterValue(enable_motion, value_type=bool),
            'cmd_vel_topic': '/cmd_vel',
            'request_topic': '/api/sport/request',
            'max_vx': 0.40,
            'max_vy': 0.25,
            'max_wz': 0.80,
            'cmd_timeout_s': 0.25,
        }]
    )

    return LaunchDescription([
        DeclareLaunchArgument(
            'params_file',
            default_value=os.path.join(bringup_dir, 'config', 'nav2_params_slam.yaml'),
            description='Full path to Nav2 parameters file'
        ),
        DeclareLaunchArgument(
            'enable_motion',
            default_value='false',
            description='Let the bridge command the robot. false = Nav2 plans but nothing moves'
        ),
        DeclareLaunchArgument(
            'use_rviz',
            default_value='false',
            description='Launch a second RViz for Nav2 -- leave false if one is already running'
        ),

        body_filter,
        utlidar_to_laserscan,
        rviz_nav,
        controller_server,
        smoother_server,
        planner_server,
        behavior_server,
        bt_navigator,
        velocity_smoother,
        collision_monitor,
        lifecycle_manager_nav,
        go2_cmd_vel_bridge,
    ])
