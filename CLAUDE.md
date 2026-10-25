# Project briefing for AI assistants (Codex, Claude Code)

You're helping a team at the IEEE SMC SAR 2026 Phase 2 competition, during a scheduled
robot slot. Read this fully before running anything. If the person you're helping
hasn't told you their slot time or which robot (`caffeine`/`dingo`/`seek`/`duchess`)
they're on, ask.

## What this repo is

A ROS 2 Jazzy stack for a Unitree Go2, built and validated against a *different*,
local Go2 on 2026-10-24/25 (not the competition robot). Everything here needs
re-verification on the actual competition robot before being trusted — thresholds and
behavior are properties of that specific robot's firmware/mechanics, not guaranteed to
transfer. Read `COMPETITION_DAY_STEPS.md` for the step-by-step; this file is the
"why" and the safety context behind those steps.

## The competition environment (from the organizers' TEAM_GUIDE, not in this repo)

- Robot computer: Jetson AGX Orin, ROS 2 Jazzy, CycloneDDS, **no sudo** — your own
  rootless Docker, run via their `sar-run` helper where possible.
- Robot network: `$SAR_ROBOT_IFACE` (192.168.123.0/24), domain 0, reachable only
  during the team's slot. **Never** run DDS on defaults (all interfaces, domain 0)
  over the shared arena Wi-Fi — bind CycloneDDS to `$SAR_ROBOT_IFACE` explicitly,
  every time, every shell:
  ```bash
  export RMW_IMPLEMENTATION=rmw_cyclonedds_cpp ROS_DOMAIN_ID=0
  export CYCLONEDDS_URI='<CycloneDDS><Domain><General><Interfaces><NetworkInterface name="'$SAR_ROBOT_IFACE'"/></Interfaces></General></Domain></CycloneDDS>'
  ```
- RealSense D435i camera + Go2-camera calibration is pre-installed read-only at
  `/opt/sar/` on the robot. Not used by anything in this repo yet — check whether the
  actual competition task needs it before assuming it's out of scope.
- Competition day itself is offline (no internet) — nothing here needs internet to
  build once cloned, this image only depends on apt packages from `ros:jazzy-ros-base`
  and the already-cloned source, but confirm that's still true if you add anything.

## Repo structure

```
image/
  Dockerfile            builds everything below into one image
  entrypoint.sh         sources ROS, binds CycloneDDS to $SAR_ROBOT_IFACE/ROBOT_IFACE
  src/
    lumen_sensor_tests/  ament_python: passive sensor diagnostics + timestamp retiming
    unitree_api/         ament_cmake: Unitree's Request/Response message definitions
    go2_cmd_vel_bridge/  ament_cmake: cmd_vel (Twist) -> Unitree sport-mode API bridge
  validation/            plain python3 scripts (NOT a colcon package), run directly:
                         keyboard_teleop.py, forward_pulse.py, move_distance.py,
                         rotate_angle.py, reactive_avoid.py
ADDING_PACKAGES.md       how to extend the image with more packages/scripts
COMPETITION_DAY_STEPS.md the step-by-step test sequence
```

Build: `cd image && docker build -t lumen-jazzy:initial .`

## What each piece actually does, and why it exists

**`lumen_sensor_tests`** — read-only diagnostics for lidar/IMU, plus
`receive_time_adapter`, which republishes a sensor topic with the *arrival* time as
`header.stamp` instead of whatever the sensor's own clock said. This exists because
the local Go2's lidar and IMU were both found to report a `header.stamp` thousands of
seconds in the past despite arriving in real time (`arrival_age_sec` tiny,
`measurement_age_sec` huge, `status: "Stale measurement timestamp"`). **Don't assume
the competition robot has this bug** — run the diagnostic first; only run the adapter
if the diagnostic actually shows staleness.

**`go2_cmd_vel_bridge`** — subscribes to a `Twist` topic, republishes as
`unitree_api/msg/Request` on `/api/sport/request` (`api_id 1008` = Move with
`{"x","y","z"}` = vx/vy/wz; `api_id 1003` = StopMove on zero/timeout). This is a thin
pass-through to the Go2's own onboard sport-mode firmware — it does NOT compute gait,
IK, or balance itself (that's what CHAMP-style controllers do instead; this repo
does not use CHAMP). **It never checks `/api/sport/response` for an acknowledgment** —
a "successful" publish from this bridge does not mean the robot executed it. If
commands appear to do nothing despite everything looking healthy, check whether
something else (the physical joystick/remote) currently holds control authority —
that can silently block API commands with zero error anywhere in this stack.

**Before launching this bridge at all**, check whether something is already
subscribed to a `cmd_vel`-like topic and already driving the robot (the organizers
separately pointed teams at a CHAMP-based reference repo — unclear whether that's
pre-wired on the real robot or just a template):
```bash
ros2 node list
ros2 topic info /cmd_vel -v
```
If something's there and working, use that topic directly (every script below takes
`--cmd-vel-topic`) and skip this bridge. **Never run two different controllers
against the robot at once** — that's a safety problem, not just redundancy.

## Validated facts from the local Go2 (recheck all of these on the real one)

- Forward motion needs both sufficient speed AND hold time, not just speed:
  `0.2 m/s` held 0.5s produced nothing useful (below the gait-engagement threshold);
  the same `0.2 m/s` held 1.5s produced 3 real walking steps. `0.4 m/s` walked
  smoothly.
- Rotation: `0.6 rad/s` worked smoothly; `0.3 rad/s` only partially turned.
- Lidar/IMU orientation convention is REP-103 (`+X` forward, `+Y` left) in `base_link`.
  The obstacle-direction checker can mistake a nearby *operator* for the test
  obstacle — stand back 1.5-2m before trusting a `MISMATCH` as a real orientation bug.
- A `ros2 topic echo <type>` "message type is invalid" error, or a `TypeHash`/
  `ResponseError` from `ros2 topic info`, were both environment issues (unsourced
  overlay; Humble CLI talking to a Jazzy-sourced daemon) on the day, not real bugs —
  re-source/`ros2 daemon stop` and recheck before concluding something's broken.
- `$SAR_ROBOT_IFACE`/`eth1` showing `DOWN` just means the robot isn't connected/
  powered — not a config problem to debug.

## Test sequence (see COMPETITION_DAY_STEPS.md for the literal commands)

1. Bind CycloneDDS to `$SAR_ROBOT_IFACE` (above).
2. Check for a pre-existing `cmd_vel` controller (above) before launching anything.
3. Sensor diagnostics (lidar, then IMU) — retime only if the check shows staleness.
4. Orientation check, stationary only, operator standing back.
5. `go2_cmd_vel_bridge`, then the bounded motion scripts in `validation/`, operator
   with the physical controller ready before every one. All of them accept `--live`
   (required to run on the real robot, a deliberate guard against accidentally
   commanding motion in the wrong ROS_DOMAIN_ID) and `--cmd-vel-topic`.

## Foxglove (for visualizing point clouds / camera images without VNC)

Already installed natively on the robot, independent of this repo/Docker image.
On the robot:
```bash
ros2 launch foxglove_bridge foxglove_bridge_launch.xml
```
Run it inside `tmux` (SSH can drop when the robot walks out of Wi-Fi range — that
doesn't stop anything already running, but it does kill anything running in the
foreground of that terminal):
```bash
tmux new -s foxglove
ros2 launch foxglove_bridge foxglove_bridge_launch.xml
# Ctrl-b d to detach
```
On the laptop: Foxglove desktop app -> Open Connection -> Foxglove WebSocket ->
`ws://<robot-name>:8765`. Add a 3D panel for point cloud topics, an Image panel for
camera topics, a Raw Messages panel for `/lumen/diagnostics`. Prefer this over
RViz-over-VNC for point clouds/images; reach for `vglrun rviz2` over TurboVNC only for
things Foxglove's panels don't show well.

## Cloning this repo on the robot

It's a private repo. Use a fine-grained PAT (Contents: read-only, scoped to just this
repo) pasted directly into the clone URL — **never write the actual token into any
file in this repo**, it only belongs typed into the command at the moment of cloning:
```bash
git clone https://<PAT>@github.com/iuenao/sar2026_lumenfleet.git ~/sar2026_lumenfleet
```
