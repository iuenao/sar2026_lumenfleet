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
