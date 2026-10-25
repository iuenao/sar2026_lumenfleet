FROM ros:jazzy-ros-base

ENV DEBIAN_FRONTEND=noninteractive
ENV RMW_IMPLEMENTATION=rmw_cyclonedds_cpp
ENV ROS_DOMAIN_ID=0

SHELL ["/bin/bash", "-c"]

# Build tools, diagnostic dependencies, and recording/playback tools.
RUN apt-get update && apt-get install -y --no-install-recommends \
    python3-colcon-common-extensions \
    python3-numpy \
    python3-yaml \
    python3-setuptools \
    ros-jazzy-ament-index-python \
    ros-jazzy-rclpy \
    ros-jazzy-rcl-interfaces \
    ros-jazzy-sensor-msgs \
    ros-jazzy-nav-msgs \
    ros-jazzy-geometry-msgs \
    ros-jazzy-diagnostic-msgs \
    ros-jazzy-tf2-ros \
    ros-jazzy-tf2-ros-py \
    ros-jazzy-launch \
    ros-jazzy-launch-ros \
    ros-jazzy-rmw-cyclonedds-cpp \
    ros-jazzy-ros2bag \
    ros-jazzy-rosbag2-transport \
    ros-jazzy-rosbag2-storage-default-plugins \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /opt/lumen_ws

COPY src/lumen_sensor_tests/ src/lumen_sensor_tests/
COPY src/unitree_api/ src/unitree_api/
COPY src/go2_cmd_vel_bridge/ src/go2_cmd_vel_bridge/

RUN source /opt/ros/jazzy/setup.bash \
    && colcon build \
        --merge-install \
        --packages-select lumen_sensor_tests unitree_api go2_cmd_vel_bridge \
    && rm -rf build log

# Standalone trial scripts (not a colcon package); run directly with python3,
# e.g. `python3 /validation/move_distance.py --live ...`.
COPY validation/ /validation/

COPY entrypoint.sh /lumen_entrypoint.sh
RUN chmod +x /lumen_entrypoint.sh

ENTRYPOINT ["/lumen_entrypoint.sh"]
CMD ["bash"]
