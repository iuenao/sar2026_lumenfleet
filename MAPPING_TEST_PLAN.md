# Mapping — test plan

Real mapping validation is scheduled for **Thursday's dedicated slot**, not
tomorrow's. This doc exists so that decision and the reasoning behind it isn't lost
between now and then.

## Why mapping is deferred, not rushed into tomorrow

- Nothing in the current Docker image includes a SLAM package — not `rtabmap_slam`,
  not `slam_toolbox`, nothing. Adding one means new, currently-untested-on-Jazyy/
  aarch64 apt packages.
- The proven approach (`cyclonedds_ws/src/go2_bringup/launch/go2_mapping.launch.py`)
  only exists for the local Humble workspace, not the Jazzy competition stack.
- With a hard slot deadline and everything else already validated (sensors, cmd_vel,
  motion primitives), there wasn't enough runway to validate a new SLAM pipeline
  blind before tomorrow without risking the things that already work.

## If there's spare time tomorrow: optional RTAB-Map stretch goal

Not required, not scheduled — only attempt this if the planned checks (sensor
diagnostics, cmd_vel bridge, motion scripts) are already done with time left over.
Drop it immediately if it doesn't work cleanly within a few minutes; the real
attempt is Thursday, not tomorrow.

Install live in the running container (not baked into the image — no time to
validate a Dockerfile change blind):
```bash
apt-get update && apt-get install -y --no-install-recommends \
  ros-jazzy-rtabmap-slam ros-jazzy-rtabmap-viz ros-jazzy-nav2-map-server
```

Needs odometry retimed too, same pattern as cloud/IMU (not yet set up elsewhere in
this repo — add it alongside whichever adapter instance is already running):
```bash
ros2 run lumen_sensor_tests receive_time_adapter --ros-args \
  -p enabled:=true -p odom_input:=/utlidar/robot_odom -p odom_output:=/lumen/retimed/robot_odom
```

Then the same remap pattern already proven in `go2_bringup/launch/go2_mapping.launch.py`,
pointed at our topics instead of the old Humble-specific ones:
```bash
ros2 run rtabmap_slam rtabmap --ros-args \
  -r scan_cloud:=/lumen/retimed/cloud_base -r odom:=/lumen/retimed/robot_odom \
  -p subscribe_scan_cloud:=true -p subscribe_odom:=true \
  -p frame_id:=base_link -p odom_frame_id:=odom
```

## On `go2_ros2_sdk` (https://github.com/abizovnuralem/go2_ros2_sdk)

Claimed to produce a "quality map," but **this has not been tested by this team** —
it's someone else's claim, not a verified result. Don't switch mapping architecture
on that basis before Thursday. Known, confirmed-from-its-own-README facts that argue
for caution rather than adoption:
- WebRTC transport (built for adaptive best-effort media, not deterministic robotics
  control latency) rather than native CycloneDDS.
- Lidar at `7 Hz` (previously `2 Hz`), vs `~15.3 Hz` already measured on the native
  `utlidar` topics in this repo.
- No documented timestamp/clock-sync handling at all.

Mapping specifically tolerates a roughly-constant delay reasonably well (geometric
consistency between consecutive scans matters more than absolute timing for
scan-matching SLAM), so a "quality map" claim from it isn't implausible on its own —
but it's unverified, and real-time reactive control (not just mapping) is where its
WebRTC transport and low lidar rate would actually hurt, which is why this repo's
architecture (native CycloneDDS, `go2_cmd_vel_bridge`, the `validation/` motion
scripts) doesn't use it. If it's worth evaluating at all, do it properly on
Thursday — clone it, test it against the same scene/conditions as RTAB-Map, compare
results — rather than adopting it on reputation.
