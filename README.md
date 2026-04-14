<div align="center">

[![en](https://img.shields.io/badge/lang-English-blue.svg)](README.md)
[![zh](https://img.shields.io/badge/lang-中文-red.svg)](README_zh.md)

<h1>SOMA Chess O1</h1>

<p>
  <img src="https://img.shields.io/badge/python-3.10+-blue?logo=python&logoColor=white" alt="Python">
  <img src="https://img.shields.io/badge/PyTorch-2.x-ee4c2c?logo=pytorch&logoColor=white" alt="PyTorch">
  <img src="https://img.shields.io/badge/ROS_2-Humble-22314E?logo=ros&logoColor=white" alt="ROS 2">
  <img src="https://img.shields.io/badge/LeRobot-HuggingFace-FFD21E?logo=huggingface&logoColor=black" alt="LeRobot">
  <img src="https://img.shields.io/badge/Claude-API-D97757?logo=anthropic&logoColor=white" alt="Claude API">
  <img src="https://img.shields.io/badge/Chess-v2_goal-8B4513" alt="Chess">
  <img src="https://img.shields.io/badge/Status-Active-brightgreen" alt="Status">
  <img src="https://img.shields.io/badge/License-Apache_2.0-green" alt="License">
</p>

<p>
  <strong>A language-driven robot arm — natural language → LLM task parsing → ACT skill execution → vision-based validation, on real hardware. v1: pick and sort objects (sponges + chess pieces) by voice command. v2: play any board game.</strong>
</p>

<p>
  <a href="https://github.com/jeffliulab/ANIMA_O1"><img src="https://img.shields.io/badge/Cognitive_Layer-ANIMA_O1-purple" alt="ANIMA_O1"></a>
</p>

</div>

---

![Workstation](docs/smart-robot-arm.jpg)

---

## Overview

**SOMA Chess O1** is the first open-source version of the SOMA robotic arm series — a language-driven manipulation system built on the [ANIMA](https://github.com/jeffliulab/ANIMA_O1) cognitive framework. A user speaks a natural-language instruction; a Claude-based parser turns it into a structured task spec; open-vocabulary perception (Grounding DINO + SAM2) grounds the language to objects in the scene; an imitation-learning policy (ACT, trained on real teleop demos via LeRobot) executes skill primitives on a 4-DOF arm; and a vision-based validator verifies each step before reporting back.

**v1 goal**: pick and sort two physically distinct object classes — foam sponge cubes (forgiving, for basic grasping) and chess pieces (smaller, demanding precision) — demonstrating that a single cognitive layer can orchestrate different grip strategies for different objects.

**v2 goal (closed-source, future)**: actual chess playing — board state recognition, move planning via Stockfish + Claude, physical move execution, and a "universal board game" interface where describing any game's rules in natural language is enough to play it.

## Highlights

- **Language → real-robot action loop, end to end.** Speak `"put everything in the bin"` and the system finds all objects, plans the task, executes skill primitives on real hardware, validates success after each step — all on a single workstation.
- **Two object classes, one cognitive layer.** The same ANIMA pipeline handles foam sponge cubes and chess pieces without code changes — only the gripper width parameter differs. This demonstrates that the cognitive architecture generalizes across physically distinct objects.
- **Cognitive layer with verifiable reasoning.** Built on the open-source ANIMA framework: LLM-as-Parser (not LLM-as-Translator) emits structured TaskSpecs, a py_trees behavior tree executes them, and a test-and-check validator catches failures and triggers natural-language recovery.
- **Real-world imitation learning, not just simulation.** Teleop demos collected on the actual hardware via LeRobot, published as public LeRobotDataset on HuggingFace Hub, and trained into ACT (Action Chunking Transformer) policies with quantified per-skill success rates.
- **Open-vocabulary perception out of the box.** Grounding DINO + SAM2 turn arbitrary text queries (`"the green sponge"`, `"the chess piece"`, `"the empty bin"`) into world coordinates with no per-object training.
- **Fully open source.** Apache-2.0, public dataset, public code, public model weights — anyone with a Logitech C922 and a hobby arm can reproduce it.

---

## Table of Contents

- [Overview](#overview)
- [Highlights](#highlights)
- [Architecture](#architecture)
- [Hardware](#hardware)
- [Software Stack](#software-stack)
- [What the Robot Can Do](#what-the-robot-can-do)
- [Project Structure](#project-structure)
- [Quick Start](#quick-start)
- [About](#about)
- [License](#license)

---

## Architecture

```
   user: "put the green sponge in the bin"
                       │
                       ▼
       ┌─────────────────────────────┐
       │  ANIMA LLM Parser           │  Claude API → structured TaskSpec JSON
       └──────────────┬──────────────┘
                      ▼
       ┌─────────────────────────────┐
       │  Grounding DINO + SAM2      │  text → object pixel mask → world (x, y)
       └──────────────┬──────────────┘
                      ▼
       ┌─────────────────────────────┐
       │  py_trees behavior tree     │  task decomposition + skill dispatch
       │  + skill registry           │  skills.yaml: affordances + preconditions
       └──────────────┬──────────────┘
                      ▼
       ┌─────────────────────────────┐
       │  ACT-trained primitives     │  pick / place / push, learned from
       │  (LeRobot, real-robot data) │  real-robot teleop demonstrations
       └──────────────┬──────────────┘
                      ▼
       ┌─────────────────────────────┐
       │  Test-and-check validator   │  vision-based success verification
       │                             │  → success / retry / report failure
       └─────────────────────────────┘
```

The four-layer ANIMA architecture (NLU → Planning → Execution → Policy) is robot-agnostic. SOMA Chess O1 provides the skill registry, sensor configuration, and hardware driver; ANIMA handles everything from language understanding to skill dispatch. The same cognitive layer can be reused on other robot embodiments.

---

## Hardware

### Compute

| Component | Spec |
|---|---|
| **Workstation laptop** | Windows 11 + RTX 4090 Laptop GPU (16 GB VRAM) |
| **Dev environment** | WSL2 + Ubuntu 22.04 + CUDA passthrough |
| **USB integration** | Long-term recommended path: `usbipd-win` forwards the arm and gamepad into WSL2; the C922 stays on native Windows and is bridged into WSL over a lightweight TCP camera bridge |

### Robot

| Component | Spec |
|---|---|
| **Arm** | [Waveshare RoArm-M2-S](https://www.waveshare.com/roarm-m2-s.htm) — 4-DOF, ~28 cm reach, ~500 g payload, ESP32 + STS3215 servos |
| **Mounting** | C-clamp, fixed to the right edge of the work table |
| **End effector** | Built-in 2-finger gripper, ~5–6 cm opening, top-down grasps |

### Perception

| Component | Spec |
|---|---|
| **Camera** | Logitech C922 Pro Stream Webcam — USB UVC, 1080p @ 30 fps. Captured natively on Windows and bridged into WSL because the `usbipd + WSL` MJPG path tears on this machine |
| **Camera mount** | JOBY GorillaPod flexible tripod, ~50–60 cm above the workspace |
| **Workspace lighting** | Dedicated LED desk lamp, independent from room lighting |

### Workspace

| Item | Spec |
|---|---|
| **Work surface** | ~60×50 cm tabletop with solid-color background mat |
| **Manipulation objects** | Yellow / green dual-sided sponge cubes (~4–5 cm) + chess pieces (pawns and rooks primarily for v1) |
| **Target container** | Plastic bin with green outer rim and white interior, ~15×12 cm |

### Teleop

| Component | Spec |
|---|---|
| **Input device** | PDP Wired Controller for Xbox — XInput protocol, 4 stick axes mapped 1:1 to the arm joints, shoulder buttons for the gripper, analog triggers for fine grasp speed control |

---

## Software Stack

| Layer | Component |
|---|---|
| **Cognition** | ANIMA — LLM-as-Parser (Claude API) + py_trees behavior tree + test-and-check validator |
| **Perception** | Grounding DINO 2 + SAM2 + pixel→world reprojection |
| **Motion planning** | MoveIt2 (4-DOF, IKFast / BioIK) |
| **Policy learning** | LeRobot ACT (Action Chunking Transformer), one model per primitive |
| **Hardware driver** | Custom Python driver for the Waveshare serial protocol, exposed as a ROS 2 node |
| **Data collection** | LeRobot teleop pipeline, with WSL-direct `evdev` as the default gamepad path and Windows TCP bridge kept as fallback |
| **Dataset format** | LeRobotDataset, published to HuggingFace Hub |
| **Middleware** | ROS 2 Humble Hawksbill (single-machine) |
| **Verification sim** | Gazebo (URDF visualization + cognitive layer dry-runs) |

### ROS 2 Packages

```
src/
├── anima_node/         # ANIMA cognitive layer ROS 2 wrapper
│   ├── nodes/          #   - anima_core_node    (LLM parser + TaskSpec validator)
│   │                   #   - skill_executor_node (behavior tree dispatcher)
│   ├── config/         #   - skills.yaml (skill registry + affordances)
│   └── launch/
├── arm_description/    # RoArm-M2-S URDF + Gazebo verification scene
│   ├── urdf/           #   - 4-DOF kinematic chain
│   ├── worlds/         #   - tabletop scene
│   └── launch/         #   - display.launch.py (RViz), gazebo.launch.py
└── arm_bringup/        # Top-level launch (description + ANIMA)
    └── launch/
```

---

## What the Robot Can Do

### Skill Primitives

ACT-trained atomic skills, exposed as building blocks for the cognitive layer:

| Primitive | Description |
|---|---|
| `pick(x, y, object_class)` | Top-down grasp at the given world coordinate; gripper width selected by object class |
| `place(x, y)` | Release at the given world coordinate |
| `push(from, to)` | Non-prehensile push between two coordinates |

### Task Capabilities

The cognitive layer composes primitives into tasks of increasing complexity:

**Single-step language grounding**

- *"Put the green sponge in the bin."*
- *"Pick up the pawn."*

**Multi-step long-horizon tasks**

- *"Sort everything into the bin."*  ← v1 flagship: handles both sponges and chess pieces in one command
- *"Stack the three green sponges."*
- *"Clean up the table."*

**Conditional and spatial reasoning**

- *"If there's a sponge on the left, put it in the bin. Otherwise put the chess piece in."*
- *"Put the green sponge to the left of the yellow one."*
- *"Pick up the piece that doesn't belong."*

**Test-and-check with failure recovery**

- *"Put everything in the bin."*
- → picks sponge → validator confirms → picks chess piece → gripper slips
- → ANIMA verifies via vision: chess piece still at original position
- → retry
- → still fails
- → natural-language report: *"I tried twice and the gripper slipped on the chess piece. Want me to retry?"*

The test-and-check loop is a signature feature of ANIMA and is rare among LLM-on-robot demonstrations.

---

## Project Structure

```
SOMA_CHESS_O1/                   # GitHub repo name
├── README.md                    # this file (English)
├── README_zh.md                 # Chinese version
├── LICENSE                      # Apache-2.0
├── CLAUDE.md                    # project conventions for Claude Code
├── docs/
│   ├── DEVELOPMENT.md
│   ├── FAQ-硬件与仿真.md
│   └── 机械臂技术文档.md        # RoArm-M2-S protocol + ROS 2 interface + safety
└── src/                         # ROS 2 workspace (colcon build)
    ├── anima_node/              # ANIMA cognitive layer wrapper
    ├── arm_description/         # URDF + Gazebo verification scene
    ├── arm_driver/              # RoArm-M2-S USB serial driver + MoveIt2 bridge
    ├── arm_teleop/              # PDP Xbox gamepad teleop node
    └── arm_bringup/             # top-level launch
```

---

## Quick Start

> Assumes WSL2 + Ubuntu 22.04 + ROS 2 Humble + LeRobot installed.

### Build

```bash
cd ~/SOMA/SOMA_CHESS_O1
colcon build --symlink-install
source install/setup.bash
```

### Visualize the URDF in RViz

```bash
ros2 launch arm_description display.launch.py
```

### Launch the arm and the cognitive layer

```bash
ros2 launch arm_bringup full_system.launch.py llm_backend:=mock
```

### Send a natural-language instruction

```bash
ros2 topic pub /user_instruction std_msgs/String \
  "data: 'put the green sponge in the bin'"
```

### USB device forwarding (Windows PowerShell, after every reboot)

```powershell
usbipd attach --wsl --busid <ROARM_BUSID>
usbipd attach --wsl --busid <PDP_GAMEPAD_BUSID>
```

Keep the C922 on native Windows in the normal workflow.

### Windows camera bridge

From Windows:

```bat
scripts\bridge方案\start_camera_bridge.bat
```

In WSL:

```bash
scripts/start_camera_bridge_wsl.sh
```

WSL then publishes and subscribes to:

- `/camera/image_raw`
- `/camera/camera_info`

The usage flow is documented in [docs/Windows_TCP相机桥接.md](docs/Windows_TCP相机桥接.md).

### Recommended long-term gamepad path (WSL direct attach)

This repo now includes the supporting pieces for the WSL-direct workflow:

- `scripts/build_wsl_gamepad_kernel.sh` builds a custom WSL kernel with `JOYDEV + XPAD`
- `scripts/attach_devices.bat` attaches the arm and the controller directly into WSL
- `scripts/check_wsl_gamepad_support.sh` verifies the running kernel and input devices
- `scripts/start_teleop_wsl_gamepad.sh` launches teleop in Linux-local mode (`use_tcp_bridge:=false`)
- `docs/WSL_Xbox手柄直通.md` documents the end-to-end setup

When the controller is attached to WSL, Windows can no longer use it. This is intentional and prevents controller input from driving Windows UI elements or terminal focus. The legacy Windows bridge fallback now lives under `scripts/bridge方案/`.

Current shortest working path:

1. In Windows Administrator PowerShell, run `usbipd list`
2. Confirm the RoArm and Xbox controller busids for the current boot
3. If they already show up as `Attached`, do not re-attach them; that is already the success state
4. Otherwise run:

```powershell
cd \\wsl$\Ubuntu-22.04\home\jeffliu\SOMA\SOMA_CHESS_O1\scripts
.\attach_devices.bat
```

5. In WSL run:

```bash
cd ~/SOMA/SOMA_CHESS_O1
scripts/start_teleop_wsl_gamepad.sh
```

6. Wait for `Teleop target initialized from current /joint_states.`
7. Press `Start` once
8. After `Start pressed — re-enabled, going home`, begin stick motion

Two easy mistakes to avoid:

- `Attached` is not an error; it means the device is already in WSL
- `\\wsl$\\...` paths are Windows-only; inside WSL always use `~/SOMA/...`

Current default teleop version (locked 2026-04-10):

- `evdev` is the default Linux input backend
- left stick uses a hard single-axis lock to suppress physical cross-axis bleed
- motion smoothing is **off by default** so stick magnitude maps directly to joint speed
- pure gripper motion uses a dedicated `/gripper_command` path backed by protocol `T:106`, not full-body `T:102`

---

## About

**Author**: [Jeff Liu Lab](https://jeffliulab.com) — [@jeffliulab](https://github.com/jeffliulab).

**Reusable cognitive layer**. The [ANIMA framework](https://github.com/jeffliulab/ANIMA_O1) is developed as a separate open-source project so it can be reused on other robot embodiments — SOMA Chess O1 is the first reference implementation.

**v1 → v2 roadmap**. v1 (this repo, open-source) delivers language-driven pick-and-sort for sponges and chess pieces. v2 (closed-source, future) adds actual chess playing: board state recognition, Stockfish + Claude move planning, physical move execution, and a "universal board game" interface — describe any game's rules in natural language and the robot can play it.

**Long-term vision**. The goal is the SOMA home robot — a household robot that helps with chores and makes everyday life happier. SOMA Chess O1 is the manipulator capability layer; the fixed-station form factor here will eventually be integrated onto a mobile platform.

---

## License

[Apache License 2.0](LICENSE) — Copyright 2026 Jeff Liu Lab ([jeffliulab.com](https://jeffliulab.com), GitHub [@jeffliulab](https://github.com/jeffliulab)).

You may use, modify, and redistribute this code commercially or privately, provided you keep the copyright and license notices and document any changes. Contributors grant an explicit patent license; suing a contributor over patents in this work terminates your license.
