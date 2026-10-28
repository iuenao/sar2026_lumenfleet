#!/usr/bin/env python3

import os

from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, ExecuteProcess, IncludeLaunchDescription
from launch.launch_description_sources import PythonLaunchDescriptionSource
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node


def generate_launch_description():

    bringup_dir = get_package_share_directory('go2_bringup')
    rviz = LaunchConfiguration('rviz')

    delete_map_cmd = ExecuteProcess(
        cmd=['bash', '-c', 'rm -f /home/unitree/.ros/go2_slam_toolbox.*'],
        output='screen'
    )

    go2_online_cmd = IncludeLaunchDescription(
        PythonLaunchDescriptionSource(
            os.path.join(bringup_dir, 'launch', 'go2_online.launch.py')
        ),
        launch_arguments={'rviz': rviz}.items(),
    )

    # ── Body/leg-swing exclusion ─────────────────────────────────────────────
    # utlidar_to_laserscan has no self-exclusion at all; a walking gait swings
    # the legs through the same height band used for obstacle detection,
    # showing up as scattered false obstacles without this.
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
    # target_frame: base_link (robot body, ~35cm above ground)
    # min_height: -0.15 → measured via z_histogram.py on flat ground: the
    #   floor itself is a dominant cluster from -0.40 to -0.20 (68% of all
    #   points, a sharp cliff at -0.20). -0.35 sat inside that cluster,
    #   letting ~half the floor through as "obstacles" every scan.
    # max_height:  1.0  → captures walls and obstacles up to 1m above base_link
    # range_max: 20.0   → UTLidar range; matches go2_ros2_sdk
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
            # cloud_base is firmware-pre-transformed into base_link, unlike
            # cloud_deskewed (frame_id odom) -- avoids needing a TF lookup
            # at the arrival-retimed stamp to undo a world-fixed frame.
            ('cloud_in', '/utlidar/cloud_base_filtered'),
            ('scan',     '/utlidar/scan'),
        ]
    )

    # ── slam_toolbox async mapping ───────────────────────────────────────────
    slam_toolbox = Node(
        package='slam_toolbox',
        executable='async_slam_toolbox_node',
        name='slam_toolbox',
        output='screen',
        parameters=[os.path.join(bringup_dir, 'config', 'slam_toolbox_params.yaml')]
    )

    # ── Map saver server (call ros2 service to save) ─────────────────────────
    map_saver_server = Node(
        package='nav2_map_server',
        executable='map_saver_server',
        name='map_saver_server',
        output='screen',
        parameters=[{
            'save_map_timeout': 5.0,
            'free_thresh_default': 0.25,
            'occupied_thresh_default': 0.65,
        }]
    )

    return LaunchDescription([
        DeclareLaunchArgument('rviz', default_value='true',
                              description='Launch go2_online.launch.py\'s standard RViz'),
        delete_map_cmd,
        go2_online_cmd,
        body_filter,
        utlidar_to_laserscan,
        slam_toolbox,
        map_saver_server,
    ])
