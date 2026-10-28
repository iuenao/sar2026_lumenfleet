# Competition day — step-by-step (slot 08:30)

Everything here was validated against the local Go2 on 2026-10-24/25. The real
robot (`caffeine`/`dingo`/`seek`/`duchess`) is a different machine; re-verify
each numbered check before trusting it, don't assume it'll just work.

## 0. Before you leave for the slot

- [ ] SSH key sent, Tailscale VPN joined, TurboVNC installed (TEAM_GUIDE §1) — already done.
- [x] Code pushed to the team's own private remote: https://github.com/iuenao/sar2026_lumenfleet.git
- [ ] Know your exact slot time and which robot you're assigned.

## 1. First five minutes on the robot: look before you touch

SSH in (`ssh yourteam@<robot>`), source ROS, bind CycloneDDS to the robot interface
(TEAM_GUIDE §3.5):
```bash
source /opt/ros/jazzy/setup.bash
export RMW_IMPLEMENTATION=rmw_cyclonedds_cpp ROS_DOMAIN_ID=0
export CYCLONEDDS_URI='<CycloneDDS><Domain><General><Interfaces><NetworkInterface name="'$SAR_ROBOT_IFACE'"/></Interfaces></General></Domain></CycloneDDS>'
```

**Before launching anything of ours**, check whether something is already driving the
robot (CHAMP or otherwise) via `cmd_vel`:
```bash
ros2 node list
ros2 topic info /cmd_vel -v
```
- Nothing there → proceed with our own `go2_cmd_vel_bridge` as below.
- Something already publishing/subscribing and clearly working → point commands at
  *that* topic directly via `--cmd-vel-topic`, skip our bridge entirely. Do not run
  both — two different controllers fighting for authority on the same robot is unsafe,
  not just redundant.

**Same check, one level lower, for `go2_driver` itself (new as of today's mapping/
nav additions).** `go2_driver` is what bridges the robot's native DDS into
`/utlidar/*` topics and the `/api/sport/request` command channel — if `/opt/sar/src/
unitree_ros2` (or anything else already on this Jetson) already runs an equivalent
driver, running our own on top risks either: (a) wasted/redundant sensor publishing
(harmless but pointless), or (b) a second path capable of commanding the robot
existing alongside whatever authority the organizer's stack already has (the
actual unsafe case — same "two controllers" problem as `/cmd_vel`, just lower in
the stack), or (c) a DDS participant/network-interface binding conflict with
whatever's already attached to the robot's onboard computer (untested, unknown
which way it fails).
```bash
ros2 node list | grep -i "driver\|go2\|unitree"
ros2 topic list | grep -i utlidar
ls /opt/sar/src/ 2>/dev/null
```
- Nothing running, no `/utlidar/*` topics yet → safe to launch our own `go2_driver`
  (via `go2_online.launch.py` / `go2_mapping_slam_toolbox.launch.py`) — that's the
  normal path to get from nothing to sensor data.
- `/utlidar/*` topics already present and populated → **do not launch our own
  `go2_driver`.** Point our mapping/nav stack at the already-published topics
  instead (our nodes don't care who published them) and skip the driver entirely.
  If unsure whether it's safe to also command the robot through our bridge on top
  of whatever's already running, ask before trying — this is exactly the kind of
  call that's cheap to get wrong on a physical robot.

## 2. Clone and build

Repo is private — clone with the fine-grained PAT (Contents: read-only, scoped to
this repo only). Paste the real token in place of `<PAT>` when you actually run this;
never save the token itself into this file or anywhere in the repo.
```bash
git clone https://<PAT>@github.com/iuenao/sar2026_lumenfleet.git ~/sar2026_lumenfleet
cd ~/sar2026_lumenfleet/image
docker build -t lumen-jazzy:initial .
```
No `sudo` on the robot — this is your own rootless Docker. Use `sar-run` (TEAM_GUIDE
§3.3) rather than raw `docker run` where possible; it wires up network/GPU/camera for
you. Raw `docker run` equivalent, if needed:
```bash
docker run --rm -it --network host -e SAR_ROBOT_IFACE -e ROS_DOMAIN_ID=0 lumen-jazzy:initial bash
```

## 3. Sensor checks (read-only, safe to run first)

Quick check with `lidar_test.launch.py`/`imu_test.launch.py` is enough to see if
something's obviously wrong (`status: "Stale measurement timestamp"`). For a
properly characterized answer, use `timestamp_check` on the *raw* topic first:
```bash
ros2 run lumen_sensor_tests timestamp_check \
  --cloud-topic /utlidar/cloud_base --duration 30 --output-dir ./reports
```
Read the `assessment` field:
- `TIMING_PLAUSIBLE` → this robot's clock is fine. Use `/utlidar/cloud_base` directly,
  **do not run the adapter** — nothing to fix.
- Anything else (`PERSISTENT_OFFSET`, `OFFSET_VARIABLE`, `OFFSET_CHANGING`,
  `SOURCE_TIMESTAMP_ANOMALY`) → there's a real issue, retime it:
  ```bash
  ros2 run lumen_sensor_tests receive_time_adapter --ros-args \
    -p enabled:=true -p cloud_input:=/utlidar/cloud_base -p cloud_output:=/lumen/retimed/cloud_base
  ```
  then re-point the diagnostic at `/lumen/retimed/cloud_base` and confirm `fresh: true`.

**The fix needs no measured value plugged in** — `receive_time_adapter` just
overwrites the stamp with arrival time unconditionally; it's the same operation
whether the original offset was 2 seconds or 2500 seconds. You only need to know
*whether* there's an issue (the `assessment` field), never *how big* it is, to decide
whether to enable the adapter.

Same pattern for IMU (`imu_test.launch.py`/`timestamp_check --imu-topic /utlidar/imu`,
add `-p imu_input:=/utlidar/imu -p imu_output:=/lumen/retimed/imu` to the same
adapter run if it's also flagged — don't assume it is just because the lidar was;
it was independently stale on the local robot, but confirm each sensor separately
here).

Don't assume the real robot has this bug at all — some robots won't. Check first,
retime only if the check shows it.

## 4. Orientation check (stationary only)

```bash
ros2 launch lumen_sensor_tests lidar_orientation_check.launch.py \
  cloud_topic:=/utlidar/cloud_base base_frame:=base_link expected_direction:=front
```
Repeat for `left`/`right`/`rear`. Stand back ~1.5-2m once the obstacle is placed —
the nearest-point detector will pick up a nearby operator instead of the obstacle
otherwise (seen today: oscillating MATCH/MISMATCH on an unchanged setup was the tell).

## 5. Motion — cmd_vel bridge

```bash
ros2 run go2_cmd_vel_bridge go2_cmd_vel_bridge --ros-args \
  -p enabled:=true -p cmd_vel_topic:=/lumen/teleop/cmd_vel \
  -p request_topic:=/api/sport/request \
  -p max_vx:=0.4 -p max_vy:=0.05 -p max_wz:=0.7
```
Validated on the local Go2 (re-confirm on the real one, thresholds are a robot/firmware
property, not guaranteed to transfer):
- Forward needs **both** sufficient speed and hold time — `0.2 m/s` held only 0.5s
  produced nothing useful; `0.2 m/s` held 1.5s produced 3 real steps. `0.4 m/s` worked
  smoothly once confirmed live.
- Rotation: `0.6 rad/s` worked smoothly; `0.3 rad/s` only partially turned.
- If commands appear to do nothing despite the bridge/network looking healthy, check
  whether something else (the physical joystick/remote) currently holds control
  authority — switching control sources can silently block API commands with no error
  on our side (`go2_cmd_vel_bridge` never checks `/api/sport/response` for ACKs).

Scripts, all under `/validation/` inside the container, all accept `--live`,
`--cmd-vel-topic` (override if step 1 found something already listening on a
different topic):
```bash
python3 /validation/move_distance.py --live --speed 0.4 --distance 1.0
python3 /validation/rotate_angle.py --live --angular-speed 0.6 --angle 90
python3 /validation/reactive_avoid.py --live --speed 0.4 --stop-range 0.4 --angle 90
```
All three are bounded (hard time/distance limits) and stop on Ctrl+C. Operator with
the physical controller ready before any of these, every time.

## 6. Known gotchas from today, so you don't re-debug them live

- `ros2 topic echo <topic> <explicit/type>` can fail with "message type is invalid" if
  the workspace overlay wasn't actually sourced in that exact shell — re-source and
  check `echo $PYTHONPATH` before assuming the package is broken.
- Running the host's ROS CLI against a differently-sourced daemon (e.g. Humble CLI vs
  a Jazzy-sourced shell) can throw a `TypeHash`/`ResponseError` that looks like a robot
  rejection but is just a decode mismatch. `ros2 daemon stop` and re-check from the
  correctly-sourced shell before concluding anything's actually broken.
- `eth1` (or `$SAR_ROBOT_IFACE`) showing `DOWN` just means the robot isn't physically
  connected/powered — not a config bug.
- **QoS mismatches fail silently.** Nav2's costmap topics (`/local_costmap/costmap`,
  `/global_costmap/costmap`) and `/map` publish as `RELIABLE` + `TRANSIENT_LOCAL`. A
  subscriber with the wrong QoS (including rclpy's plain default) connects at the
  discovery level but receives *zero messages*, with no error on either side — looks
  identical to "nothing is happening." If a new node/tool shows nothing on a Nav2 topic:
  check `ros2 topic info <topic> -v` for the actual profile and match it explicitly
  (`rclpy.qos.QoSProfile(reliability=RELIABLE, durability=TRANSIENT_LOCAL, depth=1)`).
  `hybrid_explorer.py` already does this; a brand new script may not.
- Similarly, `/utlidar/scan` triggered `pointcloud_to_laserscan_node`'s own
  "requesting incompatible QoS. No messages will be sent to it" warning for at least
  one Nav2 subscriber on the local robot. **Explicitly verify `collision_monitor` is
  actually receiving scan data** before trusting its StopZone/SlowZone as a safety
  net on the competition robot — don't assume it's fine just because it started
  without errors.

## 7. Rebuild the image — mapping/Nav2/exploration now included

As of 2026-10-28 the image also bundles `slam_toolbox`, full Nav2, `explore_lite`,
and this team's own `go2_bringup` (driver/camera/description + mapping/nav launch
files + `hybrid_explorer.py`). **None of this has been tested in the Jazzy/Docker
environment yet** — it is only validated on the local Humble robot
(`cyclonedds_ws`). Treat tomorrow as the first real test of this stack, not a
known-working rerun.
```bash
cd ~/sar2026_lumenfleet/image
docker build -t lumen-jazzy:nav .
docker run --rm -it --network host -e SAR_ROBOT_IFACE -e ROS_DOMAIN_ID=0 lumen-jazzy:nav bash
```
If you want RViz visible via the robot's TurboVNC desktop, add X11 passthrough to
the `docker run` (rviz2 is included in the image):
```bash
docker run --rm -it --network host -e SAR_ROBOT_IFACE -e ROS_DOMAIN_ID=0 \
  -e DISPLAY=$DISPLAY -v /tmp/.X11-unix:/tmp/.X11-unix:rw \
  lumen-jazzy:nav bash
```
Without that, use `use_rviz:=false` on the nav launch below and skip visualization,
or run a second container the same way just for `rviz2`.

## 8. Keyboard control (direct sport API, bypasses cmd_vel entirely)

```bash
python3 /validation/keyboard_control.py --live
```
Refuses to start if `go2_cmd_vel_bridge` is already running (checked in-code) — that's
intentional, not a bug; two command sources is unsafe. Keys: WASD move, Q/E rotate in
place, U stand up, Y stand down, R recovery stand. Operator with the physical
controller ready before starting, same as every other motion test.

## 9. Reactive navigation (longer run, fine-tune thresholds on this robot)

Same script as step 5, run it longer / with an actual obstacle course this time to
check whether the locally-validated thresholds (`--speed 0.4`, `--stop-range 0.6`,
`--rotate-safety-range 0.3`) still hold on this robot's lidar mount and chassis:
```bash
ros2 run go2_cmd_vel_bridge go2_cmd_vel_bridge --ros-args \
  -p cmd_vel_topic:=/lumen/teleop/cmd_vel -p request_topic:=/api/sport/request \
  -p max_vx:=0.4 -p max_vy:=0.25 -p max_wz:=0.80
python3 /validation/reactive_avoid.py --live --speed 0.4 --stop-range 0.6 \
  --rotate-safety-range 0.3 --angle 90 --angular-speed 0.6
```
If it collides on stop, the first thing to check is the lidar mount offset from
`base_link` on *this* robot (not assumed equal to the local one) — that's what drove
the `stop-range` increase last time, not the speed.

## 10. Mapping test (slam_toolbox, navigates while mapping)

```bash
ros2 launch go2_bringup go2_mapping_slam_toolbox.launch.py rviz:=false
```
Walk the robot around manually (teleop or reactive_avoid) while this runs; watch for:
- `/map` actually growing (`ros2 topic echo /map --field info` or watch it in RViz if
  you have a display) — not just TF/odom moving with an empty map.
- No `serialization::Read: Failed to open requested file` panic — that line is
  expected/harmless on a first run (no prior saved map), not a real error.
- Floor/leg contamination in the scan: if the map fills with noise close to the
  robot's own footprint, re-check `body_filter`'s `EXCLUSION_BOX` and
  `utlidar_to_laserscan`'s `min_height` against *this* robot's lidar mount height —
  both were tuned empirically on the local robot's geometry, not guaranteed identical.

## 11. RViz-based waypoint navigation

```bash
ros2 launch go2_bringup go2_navigation_slam.launch.py use_rviz:=false
```
In another shell (or another container), send goals either by clicking in RViz
(`config/nav2_rviz.rviz` if you have a display) or directly:
```bash
ros2 run go2_bringup waypoint_nav.py
```
Edit `WAYPOINTS` in that script first — the ones checked in are the local robot's
room coordinates and mean nothing on this map. Watch `xy_goal_tolerance: 0.15` and
`rolling_window` costmaps (both tuned against local-robot behavior) for anything
that looks obviously wrong (robot never "arrives," costmap warnings) before assuming
it's just slow.

## 12. Frontier exploration + hybrid algorithm — this is the fine-tuning target

Two options, don't run both at once (same single-command-source rule as everywhere
else in this doc):

**A. `explore_lite`** (frontier-based) — known issue on the local robot: gets stuck
re-sending an already-reached goal near walls/corners (confirmed in its own source,
not fixed, not worth chasing further). Still worth trying here in case this robot's
geometry/environment avoids the specific corner case:
```bash
ros2 run explore_lite explore --ros-args --params-file \
  $(ros2 pkg prefix explore_lite)/share/explore_lite/config/params.yaml
```

**B. `hybrid_explorer.py`** (this team's own node, replaces explore_lite) — reactive
drive by default, consults the local costmap to detect "something close ahead" and
the cumulative `/map` to pick the turn direction with the most unexplored space.
Never publishes `cmd_vel` directly, only sends `navigate_to_pose` goals, so it's safe
to leave `collision_monitor` running underneath:
```bash
ros2 run go2_bringup hybrid_explorer.py
```
Known limitation, not yet fixed: if every sampled heading (every 30° across ±90°) is
blocked at once, it logs `Obstacle ahead but no clear candidate heading -- waiting`
and just sits there — no back-up behavior. If you hit this tomorrow, that's the next
thing to add, not a sign something else is broken.

Tuning knobs (all ROS params, no code changes needed), if default behavior isn't
good for this environment:
```bash
ros2 run go2_bringup hybrid_explorer.py --ros-args \
  -p forward_step:=1.0 -p avoid_step:=1.0 \
  -p obstacle_check_ahead:=0.70 -p obstacle_check_width:=0.45 \
  -p obstacle_cost_threshold:=50 -p unknown_check_radius:=2.0
```
