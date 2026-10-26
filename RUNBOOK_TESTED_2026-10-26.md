# Runbook: what we tested on `seek` (2026-10-25/26)

Commands that ran on the competition robot `seek`, in the order to use them. Each section
says what was **verified**, what was only **partly checked**, and what is **not tested**.
Other robots may differ: re-check the values marked "robot-specific".

Paths below assume the repo is `~/lumen_fleet/sar2026_lumenfleet` and the user is `lumenfleet`.

## 0. Every shell: DDS setup

Run this in every new shell, host or container (`sar-run` passes it in, but check).
```bash
source /opt/ros/jazzy/setup.bash                 # host shells only
export RMW_IMPLEMENTATION=rmw_cyclonedds_cpp ROS_DOMAIN_ID=0
export CYCLONEDDS_URI='<CycloneDDS><Domain><General><Interfaces><NetworkInterface name="'$SAR_ROBOT_IFACE'"/></Interfaces></General></Domain></CycloneDDS>'
ros2 daemon stop
```
Verified on `seek` (robot-specific):
- `echo $SAR_ROBOT_IFACE` prints `end0`; `ip -br addr show end0` shows `UP 192.168.123.99/24`.
- `ping -c 3 192.168.123.161` reaches the Go2 (0% loss).
- `ros2 topic list` shows the Go2's topics. If it is empty, check, in order: ROS sourced,
  exports set (`echo $CYCLONEDDS_URI` contains `end0`), then `ros2 daemon stop`.
- `ros2 topic list | head` prints a harmless `BrokenPipeError`; use `grep` instead.

Pitfalls seen: pasted commands run together when copied without a newline; an expired
account (`Your account has expired`) means the slot is over.

## 1. Build and enter the image

```bash
cd ~/lumen_fleet/sar2026_lumenfleet/image
docker build -t lumen-jazzy:initial .
sar-run lumen-jazzy:initial bash          # root inside; your home is mounted at the same path
```
Verified inside the container:
```bash
ros2 pkg list | grep -E "lumen_sensor_tests|go2_cmd_vel_bridge|unitree_api"
ls /validation        # forward_pulse, keyboard_teleop, move_distance, reactive_avoid, rotate_angle
```
Container facts: the overlay is a merged install at `/opt/lumen_ws/install` (configs in
`/opt/lumen_ws/install/share/lumen_sensor_tests/config/`). Files created in the container
are owned by root. `/tmp` inside a container is lost on exit: keep scripts in the repo.

## 2. Sensor timing: check, then retime (read-only)

```bash
mkdir -p /home/lumenfleet/lumen_fleet/tmp/report
ros2 run lumen_sensor_tests timestamp_check --cloud-topic /utlidar/cloud_base --duration 30 \
  --output-dir /home/lumenfleet/lumen_fleet/tmp/report
ros2 run lumen_sensor_tests timestamp_check --imu-topic /utlidar/imu --duration 30 \
  --output-dir /home/lumenfleet/lumen_fleet/tmp/report
```
Result on `seek` (robot-specific): `/utlidar/cloud`, `/utlidar/cloud_base` and `/utlidar/imu`
all `PERSISTENT_OFFSET`, about 1760 s. The command exits non-zero when the assessment is not
`TIMING_PLAUSIBLE`; that is not a crash.

Retime (keep running in its own terminal or `tmux` window):
```bash
ros2 run lumen_sensor_tests receive_time_adapter --ros-args \
  -p enabled:=true \
  -p cloud_input:=/utlidar/cloud_base -p cloud_output:=/lumen/retimed/cloud_base \
  -p imu_input:=/utlidar/imu          -p imu_output:=/lumen/retimed/imu \
  -p odom_input:=/utlidar/robot_odom  -p odom_output:=/lumen/retimed/robot_odom
```
There is no offset parameter: it restamps with arrival time whatever the offset. Parameters
are read-only, so change them by restarting.

Verify (this was run for cloud and IMU and gave `TIMING_PLAUSIBLE`, offset about 1 ms):
```bash
ros2 run lumen_sensor_tests timestamp_check --cloud-topic /lumen/retimed/cloud_base --duration 20 \
  --output-dir /home/lumenfleet/lumen_fleet/tmp/report
ros2 run lumen_sensor_tests timestamp_check --imu-topic /lumen/retimed/imu --duration 20 \
  --output-dir /home/lumenfleet/lumen_fleet/tmp/report
```
Without the adapter running the retimed topics do not exist and the check reports `NO_DATA`.
Partly checked: `/lumen/retimed/robot_odom` runs at about 150 Hz; its raw timing was not
assessed.

## 3. Lidar orientation (stationary)

`lidar_orientation_check.launch.py` fails on the image (`package 'rviz2' not found`: the
image is `ros-base`). Run the node directly:
```bash
ros2 run lumen_sensor_tests lidar_orientation_check --ros-args \
  --params-file /opt/lumen_ws/install/share/lumen_sensor_tests/config/sensors.yaml \
  -p cloud_topic:=/lumen/retimed/cloud_base -p base_frame:=base_link -p expected_direction:=front
```
Result: it ran, but it needs a single isolated obstacle with the operator standing back
1.5-2 m. In the maze (walls on both sides) it gave MISMATCH/UNKNOWN, which says nothing about
the lidar. Orientation was judged visually in RViz instead (box on the right at -Y, left wall
at +Y, with an Axes display on `base_link`). Not verified with the checker.

## 4. Viewing

- **RViz2** runs on the robot host in a TurboVNC desktop, not in the container:
  `vglrun rviz2`. Fixed Frame `base_link`; PointCloud2 on `/lumen/retimed/cloud_base`.
  Worked.
- **Foxglove** desktop in a VirtualBox VM fails with `Error creating WebGL context` (no 3D
  acceleration). Not usable for the 3D panel there.
- The robot publishes **no TF** (`/tf` has 0 publishers); `view_frames` shows an empty graph.
  The cloud is already in `base_link`, so RViz works without it.

## 5. TF (all of it is ours to publish)

`odom` -> `base_link` from the retimed odometry (ran, `tf2_echo odom base_link` printed a live
transform; needs the adapter's odom stream running first):
```bash
python3 /home/lumenfleet/lumen_fleet/sar2026_lumenfleet/image/validation/odom_tf.py
ros2 run tf2_ros tf2_echo odom base_link
```
Only one source may publish this transform. RTAB-Map prints
`Could not find a connection between 'odom' and 'base_link'` whenever the script is not running.

Camera frames: the organizers' calibration link (ran as part of the example launch):
```bash
ros2 launch sar_go2_example camera_tf.launch.py camera:=false    # TF only
```
The workspace comes from `/opt/sar/examples/native_ros` (copy to `~/sar_ws`, `colcon build`).
Joining `base_link`: from the URDF, front camera at (0.33, 0, 0.04), rpy (-1.5708, 0, -1.5708).
Applied during the session; the lidar and camera frames looked aligned in RViz (visual only):
```bash
ros2 run tf2_ros static_transform_publisher \
  --x 0.33 --y 0 --z 0.04 --roll -1.5708 --pitch 0 --yaw -1.5708 \
  --frame-id base_link --child-frame-id go2_front_camera_optical
```
The URDF's own RealSense mount disagrees with the calibration; use the calibration.

## 6. Camera

The example launch started the RealSense and published the calibration TF. Images were not
viewed in detail. The driver runs on the host (the image has no librealsense); one process
at a time may stream (`pgrep -a realsense`).
```bash
ros2 launch sar_go2_example camera_tf.launch.py        # driver (1280x720 colour) + calibration TF
```
Not tested: aligned depth for RTAB-Map (the example launch cannot pass `align_depth.enable`;
use `rs_launch.py` directly with `camera_tf.launch.py camera:=false`; profile format is `640,480,30`).

## 7. RTAB-Map (partly tested, no map confirmed)

Installed live in the container (internet needed; lost when the container exits):
```bash
apt-get update && apt-get install -y --no-install-recommends \
  ros-jazzy-rtabmap-slam ros-jazzy-rtabmap-viz ros-jazzy-nav2-map-server
mkdir -p /home/lumenfleet/lumen_fleet/rtab_map_data      # the database cannot open without it
ros2 run rtabmap_slam rtabmap --ros-args \
  -r scan_cloud:=/lumen/retimed/cloud_base -r odom:=/lumen/retimed/robot_odom \
  -p subscribe_scan_cloud:=true -p subscribe_odom:=true \
  -p frame_id:=base_link -p odom_frame_id:=odom \
  -p approx_sync:=true -p approx_sync_max_interval:=0.1 \
  -p database_path:=/home/lumenfleet/lumen_fleet/rtab_map_data/rtabmap_$(date +%H%M).db
```
What happened: it started and opened the database once the folder existed; the first run
saved a 0 MB database. The TF warnings came from `odom_tf.py` not running. Whether `approx_sync`
fixes the empty map is untested, and the robot was never moved during mapping. Keep
`rtab_map_data/` and `tmp/` out of git.

## 8. Motion: NOT tested

Nothing has moved the robot yet. Before the first command:
1. `ros2 topic hz /api/sport/request` at rest. On `seek` there are 10 bare-DDS publishers and
   1 best-effort subscriber (the Go2); whether any of the 10 send was not checked.
2. Echo `/api/sport/request` while the operator uses the remote, to see which `api_id` it uses.
3. Measure free space ahead (the maze walls were about 0.9 m on each side).
4. Operator with the physical controller in hand and eyes on the robot.
5. Bridge, then the smallest test:
```bash
ros2 run go2_cmd_vel_bridge go2_cmd_vel_bridge --ros-args \
  -p enabled:=true -p cmd_vel_topic:=/lumen/teleop/cmd_vel -p request_topic:=/api/sport/request \
  -p max_vx:=0.4 -p max_vy:=0.05 -p max_wz:=0.7
python3 /validation/move_distance.py --live --speed 0.4 --distance 0.5
```
The bridge sends StopMove at 50 Hz while idle, so do not run it together with
`keyboard_control.py`.

`validation/keyboard_control.py` (stand up `u`, recovery `r`, stand down `j`+`y`, walking
`wasdqe`) was written but never run. Its posture api ids (1004/1005/1006) must be checked
against `/opt/sar/src/unitree_ros2` (`example/src/common/ros2_sport_client.cpp`) first.
Test without `--live` before using it on the robot.

## 9. Saving work

```bash
git add <specific files> && git commit -m "..."      # on the robot; the clone token is read-only
git remote add robot lumenfleet@seek:/home/lumenfleet/lumen_fleet/sar2026_lumenfleet   # on the laptop
git fetch robot && git merge robot/main && git push origin main
```
Home directories are not backed up and access ends with the slot, so commit and copy off
(`scp`) before it closes. Push from the laptop over SSH with a GitHub key; never put tokens in
a remote URL or file.
