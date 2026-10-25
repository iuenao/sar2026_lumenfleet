# Adding packages to this Docker image

The image is built from `image/Dockerfile`. Docker images are immutable once built —
"adding a package" means editing the `Dockerfile` and rebuilding, not patching a
running container. A running container can be modified live (`apt install`, build
into a bind-mounted folder) for quick iteration, but none of that persists once the
container exits — don't rely on it for anything you need tomorrow.

## Current layout

```
image/
  Dockerfile
  entrypoint.sh
  src/
    lumen_sensor_tests/     (ament_python — diagnostics, retiming adapter)
    unitree_api/            (ament_cmake — Unitree's Request/Response messages)
    go2_cmd_vel_bridge/      (ament_cmake — cmd_vel -> sport-mode API bridge)
  validation/                (plain python3 scripts, not a colcon package;
                               run directly, e.g. python3 /validation/move_distance.py)
```

Each `src/<pkg>` here is a synced copy, not a symlink, of the real source:
- `lumen_sensor_tests` ← `smc2026_ws/src/lumen_sensor_tests`
- `unitree_api`, `go2_cmd_vel_bridge` ← `smc2026_ws/teleop_validation/src/...`
- `validation/*.py` ← `smc2026_ws/teleop_validation/*.py`

**If you edit the real source, re-sync before rebuilding** — the Dockerfile only sees
what's physically inside `image/`:
```bash
rsync -a --delete --exclude='__pycache__' --exclude='.pytest_cache' \
  ~/unitree_ros2/smc2026_ws/src/lumen_sensor_tests/ image/src/lumen_sensor_tests/
rsync -a --delete \
  ~/unitree_ros2/smc2026_ws/teleop_validation/src/unitree_api/ image/src/unitree_api/
rsync -a --delete \
  ~/unitree_ros2/smc2026_ws/teleop_validation/src/go2_cmd_vel_bridge/ image/src/go2_cmd_vel_bridge/
rsync -a --delete --exclude='__pycache__' \
  ~/unitree_ros2/smc2026_ws/teleop_validation/*.py image/validation/
```

## Adding a new ROS package built from source (ament_python or ament_cmake)

1. Copy its source into `image/src/<package_name>/` (same sync pattern as above).
2. Add a `COPY` line in the `Dockerfile`, next to the existing ones:
   ```dockerfile
   COPY src/<package_name>/ src/<package_name>/
   ```
3. Add it to the `--packages-select` list in the `colcon build` step:
   ```dockerfile
   RUN source /opt/ros/jazzy/setup.bash \
       && colcon build --merge-install \
           --packages-select lumen_sensor_tests unitree_api go2_cmd_vel_bridge <package_name> \
       && rm -rf build log
   ```
   colcon resolves build order from each package's `package.xml` `<depend>` tags —
   you don't need to order the list yourself.
4. If it needs a dependency not already installed (check its `package.xml`), add the
   matching `ros-jazzy-<name>` (dashes, not underscores) to the `apt-get install` list.
   Don't add packages speculatively — only what the new package's manifest actually
   declares; the existing list was arrived at by actually building `unitree_api` and
   `go2_cmd_vel_bridge` successfully, not by guessing.

## Adding a prebuilt ROS package (no source, just `apt install`)

Add `ros-jazzy-<package-name>` to the existing `apt-get install -y --no-install-recommends`
list in the `Dockerfile`. Nothing else needed — no `COPY`, no `colcon build` entry.

## Adding a standalone script (not a ROS package)

Drop the `.py` file into `image/validation/` (or wherever makes sense) — it's already
`COPY`'d wholesale via `COPY validation/ /validation/`. No Dockerfile change needed
unless you're adding a new top-level directory.

## Rebuild and verify

```bash
cd image
docker build -t lumen-jazzy:test .
docker run --rm -it --network host -e ROBOT_IFACE=eth1 -e ROS_DOMAIN_ID=0 lumen-jazzy:test bash
```
Inside the container:
```bash
ros2 pkg list | grep <package_name>              # new ROS package built
python3 -c "import <python_package>; print('ok')" # new python-importable package
ls /validation/                                   # new standalone script
```
Only retag it `lumen-jazzy:initial` (replacing what's actually used) once these
checks pass — don't overwrite the working tag with an unverified build.
