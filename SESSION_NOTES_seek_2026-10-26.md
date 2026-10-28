# Session notes: robot `seek`, 2026-10-25/26

Findings from the first slot, so the next one starts from facts. Everything here was
observed on `seek` unless marked unverified.

## Setup
- `$SAR_ROBOT_IFACE` = `end0` (192.168.123.99/24); Go2 at 192.168.123.161, ping OK.
- `lumen-jazzy:initial` builds on the robot; run it with `sar-run lumen-jazzy:initial bash`.
- Packages `lumen_sensor_tests`, `go2_cmd_vel_bridge`, `unitree_api` and all `/validation`
  scripts are present in the image. The overlay is a merged install under `/opt/lumen_ws/install`
  (configs at `/opt/lumen_ws/install/share/lumen_sensor_tests/config/`).
- `ros:jazzy-ros-base` has no RViz: `lidar_orientation_check.launch.py` fails on `rviz2`.
  Run the node directly with `--params-file .../sensors.yaml` instead.
- No `/cmd_vel` topic on the robot. `/api/sport/request` has 10 bare-DDS publishers
  (idle/onboard status NOT checked) and 1 best-effort subscriber.

## Timing
- `/utlidar/cloud`, `/utlidar/cloud_base`, `/utlidar/imu`: `PERSISTENT_OFFSET`, about 1760 s.
- `receive_time_adapter` fixes it with no offset parameter. After retiming, cloud_base and
  imu are `TIMING_PLAUSIBLE` (about 1 ms).
- `/utlidar/robot_odom` runs at about 150 Hz; its timing assessment was not checked. Retimed
  copy: `/lumen/retimed/robot_odom`.

## Orientation / TF
- The orientation check in the maze gave MISMATCH/UNKNOWN because walls were on both sides
  (not a valid single-obstacle test). Cloud looked consistent in RViz.
- The robot publishes no TF (`/tf` has 0 publishers). `odom_tf.py` broadcasts odom->base_link
  from the retimed odometry.
- URDF-based camera chain: base_link -> Head_upper (0.285, 0, 0.01) -> front_camera
  (0.045, 0, 0.03, rpy -1.5708 0 -1.5708), i.e. base_link -> go2_front_camera_optical at
  (0.33, 0, 0.04) with that rpy. The URDF's own D435 mount disagrees with the organizers'
  calibration; use the calibration (`camera_tf.launch.py camera:=false`) for the RealSense.
- Odometry showed a steady pitch of about -5.7 deg at rest (yaw differed between readings).

## RTAB-Map
- Installed live in the container with apt (not in the Dockerfile).
- First run saved an empty database. Warnings: odom->base_link not found (TF script not
  running). `approx_sync:=true` suggested because each stream has its own arrival stamp.
- No map was confirmed this slot.

## Not done / next slot
- Motion scripts were never run. Clearance, idle `/api/sport/request` check, bridge first.
- `keyboard_control.py` is written but untested. Posture ids 1004/1005/1006 must be checked
  against `/opt/sar/src/unitree_ros2` (`ros2_sport_client.cpp`) before `--live`.
- Fetch anything committed on `seek` (`git fetch robot`), then push from the laptop.
