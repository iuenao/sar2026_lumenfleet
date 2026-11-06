# Runbook: full setup on `unitree2-desktop` (2026-11-06)

Consolidating onto one Jetson instead of splitting camera (separate companion Jetson) and
compute (`unitree-desktop`) across two machines. Everything below was written from a
machine with **no Docker, ROS2 Humble already installed, interface `eno1`, 21G free on a
54G root disk** — adjust if any of those differ by the time you run this.

All ROS2/Docker commands below reuse exactly what was debugged live on `unitree-desktop`
on 2026-11-05 — same fixes already baked in (QoS, CPU/deepcopy fix, xstartup, etc.), not
re-derived from scratch.

## 0. One-time setup (only needed once on this machine)

### 0.1 Install Docker
```bash
curl -fsSL https://get.docker.com | sudo sh
sudo usermod -aG docker $USER
# log out and back in (or `newgrp docker`) for the group change to take effect
```
Verify:
```bash
docker --version
```

### 0.2 Install RealSense for Humble (runs on the host, not in Docker — the image has no
librealsense, same pattern as `unitree-desktop`)
```bash
sudo apt install -y ros-humble-realsense2-camera ros-humble-realsense2-camera-msgs
```
Verify:
```bash
source /opt/ros/humble/setup.bash
ros2 pkg list | grep realsense
```

### 0.3 Clone the repo — **the mapping/Nav2/RTAB-Map work lives on the
`mapping-nav-explore-hybrid` branch, not `main`**. Repo is private; use a fine-grained PAT
(Contents: read-only, scoped to this repo). Paste the real token in place of `<PAT>` only
when you run this; never save the token itself anywhere in the repo.
```bash
git clone https://<PAT>@github.com/iuenao/sar2026_lumenfleet.git ~/sar2026_lumenfleet
cd ~/sar2026_lumenfleet
git checkout mapping-nav-explore-hybrid
```

### 0.4 Build the image (one-time; rebuild later only if the source changes)
```bash
cd ~/sar2026_lumenfleet/image
docker build -t lumen-jazzy:nav .
```
Check it landed:
```bash
docker images lumen-jazzy
```

### 0.5 Create a persistent folder for RTAB-Map databases
No separate SD card on this machine yet — use the home directory for now (21G free is
enough; move this to dedicated storage once a card is added, same as `unitree-desktop`'s
`/mnt/sdcard` pattern):
```bash
mkdir -p ~/rtab_map_data
```

## 1. Every-session startup, in order

### 1.1 Confirm the robot link (host shell, not Docker)
```bash
ip -br addr show eno1
ping -c 3 192.168.123.161
```

### 1.2 Start the RealSense directly on this host (this is the "connect directly" change —
no separate companion Jetson needed anymore)
```bash
source /opt/ros/humble/setup.bash
export RMW_IMPLEMENTATION=rmw_cyclonedds_cpp
export CYCLONEDDS_URI='<CycloneDDS><Domain><General><Interfaces><NetworkInterface name="eno1"/></Interfaces></General></Domain></CycloneDDS>'
ros2 launch realsense2_camera rs_launch.py align_depth.enable:=true \
  rgb_camera.color_profile:=640,480,30 depth_module.depth_profile:=640,480,30
```
**Check its actual clock before trusting it** (the other Jetson's camera-adjacent compute
had a system clock stuck in 2022 — don't assume this one is correct):
```bash
date
```
If it's wrong, the `receive_time_adapter` step below (1.6) already works around it
regardless — no need to fix the clock itself, just confirm whether the workaround is
needed.

### 1.3 Run the container (new host terminal)
```bash
sudo docker run --rm -it --network host -e ROBOT_IFACE=eno1 -e ROS_DOMAIN_ID=0 \
  -v ~/rtab_map_data:/rtab_map_data \
  --name lumen_rtab lumen-jazzy:nav bash
```
This shell is Terminal A — the image's entrypoint already sources ROS. Run directly:
```bash
ros2 launch go2_bringup go2_online.launch.py driver:=true camera:=false camera_tf:=false rviz:=false
```

### 1.4 Every other terminal: `sudo docker exec -it lumen_rtab bash`, then this 4-line block
first (the entrypoint only runs for Terminal A, `exec` skips it — same gotcha as before):
```bash
source /opt/ros/jazzy/setup.bash
source /opt/lumen_ws/install/setup.bash
export CYCLONEDDS_URI='<CycloneDDS><Domain><General><Interfaces><NetworkInterface name="eno1"/></Interfaces></General></Domain></CycloneDDS>'
ros2 daemon stop
```

### 1.5 Terminal B — camera extrinsic TF
```bash
ros2 launch lumen_sensor_tests camera_tf.launch.py
```

### 1.6 Terminal E — camera retiming (works around a wrong camera-host clock regardless of
cause; `input_reliability:=reliable` is required — the camera publishes RELIABLE and this
specific CycloneDDS setup does not reliably connect a BEST_EFFORT subscriber to it despite
that being standard-compliant on paper, confirmed empirically on 2026-11-05)
```bash
ros2 run lumen_sensor_tests receive_time_adapter --ros-args \
  -p enabled:=true \
  -p input_reliability:=reliable \
  -p rgb_input:=/camera/color/image_raw        -p rgb_output:=/lumen/retimed/rgb \
  -p depth_input:=/camera/aligned_depth_to_color/image_raw -p depth_output:=/lumen/retimed/depth \
  -p rgb_info_input:=/camera/color/camera_info -p rgb_info_output:=/lumen/retimed/rgb_info
```
Verify data is actually flowing before moving on (don't trust silence):
```bash
ros2 topic hz /lumen/retimed/rgb
```

### 1.7 Terminal C — RTAB-Map
```bash
ros2 run rtabmap_slam rtabmap --ros-args \
  -p frame_id:=base_link -p odom_frame_id:=odom \
  -p subscribe_depth:=true -p subscribe_rgb:=true -p approx_sync:=true -p approx_sync_max_interval:=0.1 \
  -r rgb/image:=/lumen/retimed/rgb \
  -r depth/image:=/lumen/retimed/depth \
  -r rgb/camera_info:=/lumen/retimed/rgb_info \
  -r odom:=/utlidar/robot_odom_retimed \
  -p database_path:=/rtab_map_data/rtabmap_$(date +%H%M).db
```
If you see `rtabmap: Did not receive data since 5 seconds!` with the *correct* topic
names listed underneath, it's almost always the QoS issue from 1.6, not a real data
problem — confirm with `ros2 topic hz` on the retimed topics directly before assuming
anything else is wrong.

### 1.8 Terminal G — Nav2 (lidar obstacle detection via `body_filter` +
`pointcloud_to_laserscan`, included). **Starts in Stage 1 (`enable_motion:=false`) by
default — Nav2 plans but the robot physically cannot move. Stay here until you've
confirmed everything else is healthy.**
```bash
ros2 launch go2_bringup go2_navigation_rtabmap.launch.py
```
Verify all seven nodes came up active:
```bash
for n in controller_server planner_server smoother_server behavior_server bt_navigator velocity_smoother collision_monitor; do printf "%-20s " $n; ros2 service call /$n/get_state lifecycle_msgs/srv/GetState "{}"; done
```

### 1.9 Terminal I — frontier exploration
```bash
ros2 run go2_bringup hybrid_explorer.py
```

## 2. Before enabling real motion — read this every time

**Confirmed panic-stop command** (verified working 2026-11-05 — the direct
`ros2 lifecycle set /controller_server deactivate` approach does **not** work reliably,
the lifecycle manager silently re-activates it; this one does):
```bash
ros2 service call /lifecycle_manager_navigation/manage_nodes nav2_msgs/srv/ManageLifecycleNodes "{command: 3}"
```
To resume afterward:
```bash
ros2 service call /lifecycle_manager_navigation/manage_nodes nav2_msgs/srv/ManageLifecycleNodes "{command: 0}"
```
Keep this pre-typed in a spare terminal, not something to type from scratch in the
moment. The physical remote controller remains the real, software-independent backstop
regardless — keep it in hand.

**Unresolved from 2026-11-05, not yet root-caused**: the robot collapsed three times in a
row when Nav2 + `hybrid_explorer` were run together, even with a full battery (ruled out
as the cause). Current leading theories, neither confirmed yet:
1. The robot's own firmware-level obstacle avoidance (`/api/obstacles_avoid/*` topics
   exist on the robot) may be fighting our commands if it's enabled — untested.
2. The sport-mode control lease may still be held by the joystick after using it to
   stand the robot up, meaning our software's commands could be silently
   ignored/contested at the firmware level despite looking fine at the ROS2 level.
   **Planned test**: stand the robot up via `keyboard_control.py`'s `u` key instead of
   the joystick, so the same software client handles both stand-up and subsequent
   Nav2-driven motion — removes the joystick as a variable entirely.

**Do not relaunch Stage 2 (`enable_motion:=true`) until this is actually understood.**
Physically inspect the robot for damage before any further motion attempts after a fall.

Once ready to test Stage 2:
```bash
ros2 launch go2_bringup go2_navigation_rtabmap.launch.py enable_motion:=true
```

## 3. Known gotchas, so you don't re-debug them live

- `docker exec` does **not** run the image's entrypoint — every exec'd shell needs the
  4-line ROS+DDS block from 1.4 manually, every time.
- `ros2 topic list` returning only `/parameter_events`/`/rosout` despite correct DDS
  exports usually means a stale daemon from before the network was up — `ros2 daemon
  stop` fixes it.
- A theoretically-QoS-compatible subscriber (e.g. BEST_EFFORT against a RELIABLE
  publisher) can still silently receive zero messages on this CycloneDDS setup, with no
  error on either side. If a topic looks dead, check `ros2 topic info <topic> -v` for the
  actual QoS on both sides before assuming anything else is broken.
- If adding a new file to `go2_bringup`/`lumen_sensor_tests` into an **already-running**
  container without rebuilding, `docker cp` the file into its installed path instead —
  ament_python packages install under
  `/opt/lumen_ws/install/lib/python3.12/site-packages/<pkg>/`, ament_cmake packages
  (launch files, configs) under `/opt/lumen_ws/install/share/<pkg>/`.
