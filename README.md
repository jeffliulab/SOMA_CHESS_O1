<div align="center">

[![en](https://img.shields.io/badge/lang-English-blue.svg)](README.md)
[![zh](https://img.shields.io/badge/lang-中文-red.svg)](README_zh.md)

<h1>SmartRobotArm</h1>

<p>
  <img src="https://img.shields.io/badge/python-3.10+-blue?logo=python&logoColor=white" alt="Python">
  <img src="https://img.shields.io/badge/PyTorch-2.x-ee4c2c?logo=pytorch&logoColor=white" alt="PyTorch">
  <img src="https://img.shields.io/badge/ROS_2-Humble-22314E?logo=ros&logoColor=white" alt="ROS 2">
  <img src="https://img.shields.io/badge/LeRobot-HuggingFace-FFD21E?logo=huggingface&logoColor=black" alt="LeRobot">
  <img src="https://img.shields.io/badge/Claude-API-D97757?logo=anthropic&logoColor=white" alt="Claude API">
  <img src="https://img.shields.io/badge/Status-Active-brightgreen" alt="Status">
  <img src="https://img.shields.io/badge/License-Apache_2.0-green" alt="License">
</p>

<p>
  <strong>A language-driven smart robot arm — natural language → LLM task parsing → ACT skill execution → vision-based validation, on real hardware.</strong>
</p>

<p>
  <a href="https://github.com/jeffliulab/ANIMA_O1"><img src="https://img.shields.io/badge/Cognitive_Layer-ANIMA_O1-purple" alt="ANIMA_O1"></a>
</p>

</div>

---

![Workstation](docs/smart-robot-arm.jpg)

---

## Overview

SmartRobotArm is a real-robot demonstration of language-driven manipulation. A user speaks a natural-language instruction; a Claude-based parser turns it into a structured task spec; open-vocabulary perception (Grounding DINO + SAM2) grounds the language to objects in the scene; an imitation-learning policy (ACT, trained on real teleop demos via LeRobot) executes skill primitives on a 4-DOF arm; and a vision-based validator verifies each step before reporting back.

The project is built around the open-source [ANIMA](https://github.com/jeffliulab/ANIMA_O1) cognitive framework — an LLM-as-Parser, behavior-tree-based architecture with a test-and-check validation loop.

## Highlights

- **Language → real-robot action loop, end to end.** Speak `"put the green sponge in the bin"` and the system grounds the language, plans the task, executes the skill on real hardware, and verifies success — all on a single workstation.
- **Cognitive layer with verifiable reasoning.** Built on the open-source ANIMA framework: LLM-as-Parser (not LLM-as-Translator) emits structured TaskSpecs, a py_trees behavior tree executes them, and a test-and-check validator catches failures and triggers natural-language recovery.
- **Real-world imitation learning, not just simulation.** Teleop demos collected on the actual hardware via LeRobot, published as public LeRobotDataset on HuggingFace Hub, and trained into ACT (Action Chunking Transformer) policies with quantified per-skill success rates.
- **Open-vocabulary perception out of the box.** Grounding DINO + SAM2 turn arbitrary text queries (`"the green sponge"`, `"the empty bin"`) into world coordinates with no per-object training.
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

The four-layer ANIMA architecture (NLU → Planning → Execution → Policy) is robot-agnostic. SmartRobotArm provides the skill registry, sensor configuration, and hardware driver; ANIMA handles everything from language understanding to skill dispatch. The same cognitive layer can be reused on other robot embodiments.

---

## Hardware

### Compute

| Component | Spec |
|---|---|
| **Desktop PC** | Windows 11 + RTX 4090 (24 GB VRAM) |
| **Dev environment** | WSL2 + Ubuntu 22.04 + CUDA passthrough |
| **USB integration** | `usbipd-win` forwards camera, arm, and gamepad directly into WSL2 |

### Robot

| Component | Spec |
|---|---|
| **Arm** | [Waveshare RoArm-M2-S](https://www.waveshare.com/roarm-m2-s.htm) — 4-DOF, ~28 cm reach, ~500 g payload, ESP32 + STS3215 servos |
| **Mounting** | C-clamp, fixed to the right edge of the work table |
| **End effector** | Built-in 2-finger gripper, ~5–6 cm opening, top-down grasps |

### Perception

| Component | Spec |
|---|---|
| **Camera** | Logitech C922 Pro Stream Webcam — USB UVC, 1080p @ 30 fps. Auto-exposure / white-balance / focus locked via `v4l2-ctl` for training data consistency |
| **Camera mount** | JOBY GorillaPod flexible tripod, ~50–60 cm above the workspace |
| **Workspace lighting** | Dedicated LED desk lamp, independent from room lighting |

### Workspace

| Item | Spec |
|---|---|
| **Work surface** | ~60×50 cm tabletop with solid-color background mat |
| **Manipulation objects** | Yellow / green dual-sided sponge cubes, ~4–5 cm |
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
| **Data collection** | LeRobot teleop pipeline, gamepad input via `pygame` / `python-evdev` |
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
| `pick(x, y)` | Top-down grasp at the given world coordinate |
| `place(x, y)` | Release at the given world coordinate |
| `push(from, to)` | Non-prehensile push between two coordinates |

### Task Capabilities

The cognitive layer composes primitives into tasks of increasing complexity:

**Single-step language grounding**

- *"Put the green sponge in the bin."*
- *"Pick up the yellow one."*

**Multi-step long-horizon tasks**

- *"Sort the sponges by color into the matching bins."*
- *"Stack the three green sponges."*
- *"Clean up the table."*

**Conditional and spatial reasoning**

- *"If there's a green sponge, put it in the bin. Otherwise put the yellow one in."*
- *"Put the green sponge to the left of the yellow one."*
- *"Pick up the sponge that doesn't match the others."*

**Test-and-check with failure recovery**

- *"Pick up the green sponge."*
- → first attempt → fails
- → ANIMA verifies via vision: object still in original position
- → retry
- → still fails
- → natural-language report: *"I tried twice and the gripper slipped. Want me to try a different angle?"*

The test-and-check loop is a signature feature of ANIMA and is rare among LLM-on-robot demonstrations.

---

## Project Structure

```
SmartRobotArm/
├── README.md                    # this file (English)
├── README_zh.md                 # Chinese version
├── LICENSE                      # Apache-2.0
├── CLAUDE.md                    # project conventions for Claude Code
├── docs/
│   ├── DEVELOPMENT.md
│   ├── FAQ-硬件与仿真.md
│   └── smart-robot-arm.jpg      # workstation photo
└── src/                         # ROS 2 workspace (colcon build)
    ├── anima_node/              # cognitive layer
    ├── arm_description/         # URDF + verification sim
    └── arm_bringup/             # top-level launch
```

---

## Quick Start

> Assumes WSL2 + Ubuntu 22.04 + ROS 2 Humble + LeRobot installed.

### Build

```bash
cd ~/SmartRobotArm
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
usbipd attach --wsl --busid <C922_BUSID>
usbipd attach --wsl --busid <ROARM_BUSID>
usbipd attach --wsl --busid <PDP_GAMEPAD_BUSID>
```

---

## About

**Author**: [Jeff Liu Lab](https://jeffliulab.com) — [@jeffliulab](https://github.com/jeffliulab).

**Reusable cognitive layer**. The [ANIMA framework](https://github.com/jeffliulab/ANIMA_O1) is developed as a separate open-source project so it can be reused on other robot embodiments — SmartRobotArm is the first reference implementation.

**Long-term vision**. The goal of building the ANIMA cognitive framework is to eventually realize the SOMA home robot — a household robot that helps with chores and makes everyday life happier. SmartRobotArm is the manipulator capability layer of that future home robot; the fixed-station workstation here will eventually be integrated onto a mobile platform.

---

## License

[Apache License 2.0](LICENSE) — Copyright 2026 Jeff Liu Lab ([jeffliulab.com](https://jeffliulab.com), GitHub [@jeffliulab](https://github.com/jeffliulab)).

You may use, modify, and redistribute this code commercially or privately, provided you keep the copyright and license notices and document any changes. Contributors grant an explicit patent license; suing a contributor over patents in this work terminates your license.
