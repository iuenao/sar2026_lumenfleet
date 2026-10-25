# SAR 2026 — Lumen Fleet

Deployable ROS 2 Jazyy stack for the IEEE SMC SAR 2026 Phase 2 competition robots.

| | |
|---|---|
| **[`COMPETITION_DAY_STEPS.md`](COMPETITION_DAY_STEPS.md)** | Step-by-step for the actual slot: network check, sensor diagnostics, motion. Read this first on the robot. |
| **[`ADDING_PACKAGES.md`](ADDING_PACKAGES.md)** | How to add a new ROS package or script to the Docker image. |
| [`image/`](image/) | The `Dockerfile` + everything it bakes in (`lumen_sensor_tests`, `unitree_api`, `go2_cmd_vel_bridge`, the `/validation` trial scripts). This is what you actually build and run on the robot. |

## Quick start on a competition robot

```bash
git clone https://github.com/iuenao/sar2026_lumenfleet.git ~/sar2026_lumenfleet
cd ~/sar2026_lumenfleet/image
docker build -t lumen-jazzy:initial .
```
Then follow `COMPETITION_DAY_STEPS.md`.

## Source of truth

The packages under `image/src/` and the scripts under `image/validation/` are synced
copies of the real source, developed and tested against the local Go2 in
`~/unitree_ros2/smc2026_ws` (that workspace is not part of this repo). See
`ADDING_PACKAGES.md` for the sync commands if you need to pull in further changes
from there.
