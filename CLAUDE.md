# SOMA Chess O1 — Project conventions

> This file is read by Claude Code at the start of every conversation. Keep it accurate and concise.

## What this project is

**SOMA Chess O1** is the first open-source version of the SOMA robotic arm series — a fixed tabletop manipulator powered by natural language. The user speaks an instruction, the [ANIMA](https://github.com/jeffliulab/ANIMA_O1) cognitive layer parses it via Claude API into a structured task spec, perception (Grounding DINO + SAM2) grounds language to world coordinates, a py_trees behavior tree dispatches ACT-trained skill primitives, and a test-and-check validator confirms success or triggers recovery.

**v1 goal (this repo, open-source, Apache-2.0)**: pick-and-sort two object classes — foam sponge cubes and chess pieces — into a bin, driven by natural language, with error detection and retry.

**v2 goal (separate private repo, future)**: actual chess playing — board state recognition, Stockfish + Claude move planning, physical move execution, and a "universal board game" interface where describing any game's rules in natural language is enough to play it.

This is a **portfolio / job-hunting project**, public Apache-2.0, written by Jeff Liu Lab. Optimize all decisions for **legibility to a hiring manager in the embodied AI / robotics space**, not for academic novelty or production hardening.

## Repo lineage and current scope

- **Migrated from** [`soma_home_exp_v1`](https://github.com/jeffliulab/soma_home_exp_v1) (now archived) on 2026-04-07. ANIMA nodes, URDF, launch files, and the 8-week sprint plan all came from there.
- **Cognitive framework dependency**: [`ANIMA_O1`](https://github.com/jeffliulab/ANIMA_O1) — separate Python framework repo. SOMA Chess O1 wraps ANIMA in ROS 2 nodes.
- **Long-term design context**: lives in `SOMA_HOME_EXP/` and `ANIMA_FRAMEWORK/` design folders (private monorepo, not public). Some of those documents are STALE because they predate the pivot — check `SOMA_HOME_EXP/CLAUDE.md` for which files are current.
- **Earlier commit on this repo** is unrelated SO-ARM100 + LEAP Hand + MediaPipe exploration that was rebuilt from scratch. Don't reference any of it.

## Single source of truth for v1 execution

[`开发进度与待办事项.md`](开发进度与待办事项.md) is the **single source of truth** for the 8-week sprint plan. Always check it before recommending tasks. Update its progress tracker after completing meaningful work.

## Hardware (locked 2026-04-07)

- **Arm**: Waveshare RoArm-M2-S — 4-DOF, USB serial via CP2102N, ESP32 + ST3215 servos, ~280mm reach, ~500g payload, ~826g
- **Camera**: Logitech C922 Pro Stream Webcam — USB UVC, fixed overhead
- **Teleop input**: PDP Wired Controller for Xbox — XInput, user already owns (busid `1-3` on this machine)
- **Compute**: Workstation laptop, **RTX 4090 Laptop GPU (16 GB VRAM)** — note: NOT the desktop 24 GB variant; this was misdocumented earlier
- **No Pi 5, no mobile base, no LiDAR in v1** — everything plugs directly into the host PC
- **Object set v1**: yellow/green dual-sided sponge cubes (~4-5cm) + chess pieces (pawns and rooks primary; mixed types for demo) + green-rim white-interior plastic bin

## Development environment (locked 2026-04-07)

- **Host**: Windows 11 (user's primary OS, GPU known to perform at full capacity here)
- **Dev**: WSL2 + Ubuntu 22.04 — chosen over dual-boot Linux because the user's hardware suffers GPU performance loss on dual-boot. WSL2 + CUDA passthrough preserves full RTX 4090 Laptop performance.
- **Python venv**: `~/SOMA/SOMA_CHESS_O1/.venv/`, created with `python3 -m venv --system-site-packages .venv`. The `--system-site-packages` flag is **mandatory** so the venv can import the system `rclpy` from `/opt/ros/humble/...`. LeRobot, pygame, pyserial, torch (with CUDA) are installed inside this venv.
- **USB**: Long-term recommended path is `usbipd-win` forwarding RoArm (busid `1-4`, CP2102N), PDP gamepad (busid `1-3`), and optionally C922 into WSL2 as `/dev/ttyUSB*`, `/dev/input/event*`, `/dev/video*`. This requires a custom WSL kernel with `JOYDEV + XPAD`; see [docs/WSL_Xbox手柄直通.md](docs/WSL_Xbox手柄直通.md) and [scripts/attach_devices.bat](scripts/attach_devices.bat). The Windows TCP bridge remains a fallback only.
- **ROS 2**: Humble Hawksbill (LTS, best LeRobot compat). MoveIt2 installed via `apt install ros-humble-moveit`. Note: must `apt install --only-upgrade ros-humble-ompl` to get OMPL 1.7.0+ (provides `libompl.so.18`), otherwise `move_group` segfaults — known ROS Humble apt packaging mismatch.
- **Graphics**: WSLg (Gazebo / RViz2 work but slower — fine since they're not the bottleneck)
- **Shell helper**: `srarm` function in `~/.bashrc` — one command to enter dev mode (cd into workspace + source ROS 2 + activate venv + source overlay)
- **External upstream workspaces**: `~/SOMA/DRIVERS/roarm_ws_em0/` (Waveshare's ROS 2 + MoveIt2 config, only for the MoveIt2 mock+sidecar mode). Kept outside this repo and outside any git tracking. **Do not vendor third-party code into this repo** — license risk on a public Apache-2.0 portfolio repo.

## Repository structure

```
SOMA_CHESS_O1/
├── README.md, LICENSE, CLAUDE.md, .gitignore
├── 开发进度与待办事项.md     # 8-week sprint plan (source of truth, gitignored as private)
├── .venv/                   # Python venv (gitignored), --system-site-packages
├── docs/
│   ├── DEVELOPMENT.md
│   ├── FAQ-硬件与仿真.md
│   └── 机械臂技术文档.md   # RoArm-M2-S 协议 + ROS 2 接口 + 安全操作(W1.5 产物)
├── scripts/
│   ├── attach_devices.bat   # Windows-side usbipd attach script (RoArm + gamepad direct to WSL)
│   ├── build_wsl_gamepad_kernel.sh
│   ├── check_wsl_gamepad_support.sh
│   ├── start_teleop_wsl_gamepad.sh
│   └── bridge方案/
│       ├── attach_devices_bridge_mode.bat
│       ├── bridge_gui.py, bridge_worker.py
│       └── gamepad_bridge.py, start_bridge.bat
└── src/                     # ROS 2 workspace, build with colcon
    ├── anima_node/          # ANIMA cognitive layer ROS 2 wrapper (legacy from soma_home_exp_v1)
    ├── arm_description/     # URDF + Gazebo verification scene
    ├── arm_bringup/         # Top-level launch
    ├── arm_driver/          # ★ W1.5: RoArm-M2-S USB serial driver
    │                        #   - roarm_protocol.py     pure Python protocol layer
    │                        #   - arm_driver_node       /joint_command + /joint_states + /gripper_command
    │                        #   - moveit_bridge_node    bridges MoveIt2 mock joint_states to real serial
    │                        #   - probe                 standalone CLI for protocol smoke test
    └── arm_teleop/          # ★ W1.7: PDP Xbox gamepad teleoperation
        ├── gamepad_input.py      unified GamepadState + evdev/tcp_bridge/pygame backends
        ├── control_filters.py    teleop-side filters (left-stick axis lock, optional smoothing)
        └── gamepad_teleop_node   default = WSL-direct evdev, publishes /joint_command or /gripper_command
```

ROS 2 packages added later in the sprint (W2-W3):
- `arm_perception/` — Grounding DINO + SAM2
- `arm_manipulation/` — MoveIt2 config + hardcoded primitives (we'll generate our own MoveIt2 config to replace the borrowed Waveshare one)

## Conventions

- **Language**: docs and comments are mostly Chinese (Simplified). Code, ROS package names, identifiers, and config keys stay in English. The 开发进度与待办事项.md follows this convention.
- **License headers**: not added to every source file in v1. The repo-level LICENSE is sufficient until we tag a release.
- **Naming**: ROS packages have NO `soma_` prefix anymore. They use `anima_node`, `arm_description`, `arm_bringup`, etc.
- **Author / copyright**: always **"Jeff Liu Lab"** (jeffliulab.com, GitHub @jeffliulab). Don't drop the "Lab" suffix.
- **Don't over-engineer**: this is pre-alpha. No CI, no packaging, no contribution guides, no code-of-conduct. Add them when there's a real reason.

## Common commands

```bash
# Enter dev mode (defined in ~/.bashrc)
srarm

# Build
colcon build --symlink-install
# (already sourced by srarm if install/ exists)

# ---------- arm hardware ----------

# Standalone protocol probe (no ROS — sanity check serial + read 1 state)
python -m arm_driver.roarm_protocol            # default /dev/ttyUSB0
python -m arm_driver.roarm_protocol /dev/ttyACM0

# Mode A: direct ROS 2 driver (use this for our own teleop / direct command pipeline)
ros2 launch arm_driver arm_driver.launch.py
# In another shell:
ros2 topic echo /joint_states --once
ros2 topic pub --once /joint_command sensor_msgs/msg/JointState \
  '{name: ["base_link_to_link1","link1_to_link2","link2_to_link3","link3_to_gripper_link"],
    position: [0.0, 0.0, 1.5708, 0.75]}'
ros2 topic pub --once /gripper_command std_msgs/msg/Float32 '{data: 1.5}'  # open
ros2 topic pub --once /gripper_command std_msgs/msg/Float32 '{data: 0.0}'  # close

# Mode B: gamepad teleop (preferred current workflow: WSL-direct + evdev)
scripts/start_teleop_wsl_gamepad.sh
# Equivalent lower-level form:
ros2 launch arm_teleop teleop.launch.py use_tcp_bridge:=false

# Optional comparison mode: same teleop, but enable gentle motion smoothing
ros2 launch arm_teleop teleop.launch.py use_tcp_bridge:=false enable_motion_smoothing:=true

# Fallback mode: keep the controller on Windows and bridge over TCP
ros2 launch arm_teleop teleop.launch.py use_tcp_bridge:=true

# Mode C: MoveIt2 + RViz drag-the-orange-ball (uses upstream Waveshare config)
# Terminal A:
source ~/SOMA/DRIVERS/roarm_ws_em0/install/setup.bash
ros2 launch roarm_moveit interact.launch.py
# Terminal B:
srarm
ros2 run arm_driver moveit_bridge_node

# ⚠ Modes A / B / C are mutually exclusive — only one process at a time can hold /dev/ttyUSB*.

# ---------- visualization ----------
ros2 launch arm_description display.launch.py        # URDF in RViz only

# ---------- USB device forwarding (Windows PowerShell, after each Windows reboot) ----------
usbipd attach --wsl --busid 1-4    # RoArm-M2-S (CP2102N)
usbipd attach --wsl --busid 1-3    # PDP Xbox gamepad (preferred long-term path)
# Or just double-click scripts/attach_devices.bat from the Windows desktop.
```

## Current teleop default (locked 2026-04-10)

- **Default operator-facing path**: `scripts/start_teleop_wsl_gamepad.sh`
- **Default backend**: `evdev` on `/dev/input/event*`
- **Current control semantics**:
  - left stick X/Y = base / shoulder
  - right stick Y = elbow
  - LB/RB = gripper close
  - LT/RT = gripper open
  - Start = home + re-enable
  - Back = e-stop
  - DPAD left/right = LED
- **Important filters / behavior**:
  - left stick uses a hard single-axis lock to suppress physical cross-axis bleed
  - motion smoothing is **off by default**; stick magnitude maps directly to joint speed
  - pure gripper teleop uses `/gripper_command`, and the driver sends dedicated protocol `T:106` instead of resending full-body `T:102`
- **Known current state**:
  - system is now usable and should be treated as the default version
  - remaining issue is minor body micro-jitter during arm motion; do not revert the current direct stick-to-velocity semantics without a good reason

## Teleop fallback matrix

- **Primary**: `scripts/start_teleop_wsl_gamepad.sh`
- **Direct WSL + smoothing on**:
  - `ros2 launch arm_teleop teleop.launch.py use_tcp_bridge:=false enable_motion_smoothing:=true`
- **Windows bridge fallback**:
  - Windows: `scripts\\bridge方案\\attach_devices_bridge_mode.bat`
  - Windows: `scripts\\bridge方案\\bridge_gui.py`
  - WSL: `ros2 launch arm_teleop teleop.launch.py use_tcp_bridge:=true`

## What NOT to do (deliberately scoped out of v1)

When recommending features or tasks, push back if any of these come up — they are v2+ and would derail the 8-week sprint:

- ❌ Mobile manipulation on real hardware (Gazebo dry-run is allowed)
- ❌ Garment / cloth / cable / deformable object handling
- ❌ Bimanual / force feedback / 6-DOF arm
- ❌ Custom base / Nav2 / SLAM on real hardware
- ❌ Multi-machine ROS 2 DDS (everything is single PC)
- ❌ Pi 5 embedded deployment
- ❌ MuJoCo / Isaac Sim / Isaac Lab
- ❌ Sim2real transfer (real robot data only)
- ❌ Reinforcement learning of any kind
- ❌ Custom perception model training (Grounding DINO + SAM2 are pretrained)
- ❌ VLA fine-tuning (Week 8 stretch only)
- ❌ Actual chess playing (board state → legal move → physical move execution) — this is **v2**, in a separate private repo

If the user wants to do any of these, treat it as a scope change worth discussing — don't silently agree.

## License

[Apache-2.0](LICENSE), Copyright 2026 Jeff Liu Lab.
