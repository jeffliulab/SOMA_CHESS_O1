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
  <img src="https://img.shields.io/badge/Status-WIP-yellow" alt="Status">
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

## Highlights

- **Language → real-robot action loop**: speak `"put the green sponge in the bin"`, the system parses it via Claude, grounds the language to the scene with Grounding DINO + SAM2, dispatches an ACT-trained skill primitive on a real 4-DOF arm, and verifies success with vision.
- **Cognitive layer is the star**: built on the open-source [ANIMA](https://github.com/jeffliulab/ANIMA_O1) framework — LLM-as-Parser (not Translator), py_trees behavior tree, and a DIARC-inspired test-and-check + failure recovery loop.
- **Industry-canonical IL pipeline**: real-robot teleop with a wired Xbox gamepad, LeRobotDataset published to HuggingFace Hub, ACT (Action Chunking Transformer) trained from real demos. No simulation training.
- **Single-machine setup**: Logitech C922 + Waveshare RoArm-M2-S + PDP Xbox gamepad all plug straight into one desktop PC. No Pi, no WiFi, no multi-machine ROS DDS in v1.
- **Open source**: Apache-2.0, public dataset, public code, public model weights.

> **Status**: Pre-alpha. 8-week sprint in progress. APIs, package names and launch files will change without notice.

---

## Table of Contents

- [Highlights](#highlights)
- [Architecture](#architecture)
- [Hardware](#hardware)
- [Software stack](#software-stack)
- [Skill primitives and task tiers](#skill-primitives-and-task-tiers)
- [Project structure](#project-structure)
- [Quick start](#quick-start)
- [Roadmap](#roadmap)
- [Project lineage](#project-lineage)
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
       │  + skill registry           │  (skills.yaml: affordance + preconditions)
       └──────────────┬──────────────┘
                      ▼
       ┌─────────────────────────────┐
       │  ACT-trained primitives     │  pick / place / push, learned from
       │  (LeRobot, real-robot data) │  ~30 demos each via PDP gamepad teleop
       │  MoveIt2 hardcoded fallback │  Week 3 safety net
       └──────────────┬──────────────┘
                      ▼
       ┌─────────────────────────────┐
       │  Test-and-check validator   │  vision-based success verification
       │  (DIARC-inspired)           │  → success / retry / report failure
       └─────────────────────────────┘
```

The four-layer ANIMA design (NLU → Planning → Execution → Policy) is robot-agnostic. SmartRobotArm provides the skill registry, sensor configuration, and hardware driver; ANIMA handles everything from language to dispatch. See [`stacks/robotics.md`](https://github.com/jeffliulab/Agent规范) (private spec) for the full architecture rationale.

---

## Hardware

Full configuration locked on 2026-04-07 after the workstation was assembled.

### Compute

| Component | Spec | Role |
|---|---|---|
| **Desktop PC** | Windows 11 + RTX 4090 (24 GB VRAM) | Hosts everything: training, inference, perception, ROS 2, ANIMA, Claude API client |
| **Dev environment** | WSL2 + Ubuntu 22.04 + CUDA passthrough | Native Linux for ROS 2 / LeRobot ecosystem; CUDA passthrough preserves 100% RTX 4090 performance vs dual-boot |
| **USB forwarding** | `usbipd-win` (Windows) → `/dev/video0`, `/dev/ttyUSB0`, `/dev/input/js0` (WSL2) | All hardware plugs directly into the desktop; no Pi, no WiFi, no multi-machine |

### Robot

| Component | Spec | Role |
|---|---|---|
| **Arm** | [Waveshare RoArm-M2-S](https://www.waveshare.com/roarm-m2-s.htm) | 4-DOF, ~28 cm reach, ~500 g payload, ESP32 + STS3215 servos, USB serial |
| **Mounting** | C-clamp on the right edge of the work table | Rigid fixed installation; eye-to-hand calibration stays valid across sessions |
| **End effector** | Built-in 2-finger gripper, ~5–6 cm opening | Top-down grasps only |

### Perception

| Component | Spec | Role |
|---|---|---|
| **Camera** | Logitech C922 Pro Stream Webcam | USB UVC, 1080p @ 30 fps. Auto-exposure / white-balance / focus locked via `v4l2-ctl` for ACT training data consistency. ALOHA-canonical hardware for community reproducibility |
| **Camera mount** | JOBY GorillaPod flexible tripod | Wraps around the table edge, ~50–60 cm above the workspace, ~60° angle |
| **Workspace lighting** | Dedicated LED desk lamp | Independent from room lighting; gives consistent illumination across teleop sessions and ACT inference |

### Workspace and objects

| Item | Spec | Notes |
|---|---|---|
| **Work surface** | ~60×50 cm wood-grain table top | A solid-color background mat (black KT board, ~$3) is on the to-buy list to improve Grounding DINO + SAM2 reliability |
| **Manipulation objects** | Yellow / green dual-sided sponge cubes, ~4-5 cm | Compliant material is forgiving of the arm's ~1-2 mm hobby-servo repeatability; the two-color faces enable language tasks like "find the one with the green side up" |
| **Target container** | Plastic bin with green outer rim and white interior, ~15×12 cm | High-contrast interior makes vision-based "object placed in bin?" verification easy |

### Teleop and data collection

| Component | Spec | Role |
|---|---|---|
| **Teleop input** | PDP Wired Controller for Xbox ([pdp.com](https://pdp.com)) | XInput protocol, recognized natively by Linux `xpad` driver as `/dev/input/js0` after `usbipd attach`. 4 stick axes map 1:1 to the 4 arm joints; LB/RB control gripper open/close; LT/RT analog triggers modulate gripper speed for fine grasps |

### Out of scope for v1

| Component | Why not |
|---|---|
| ❌ **Raspberry Pi 5 / any SBC** | Workstation is fixed; the desktop PC handles everything via direct USB. Reserved for v2 embedded deployment |
| ❌ **Mobile base / wheels / motors** | v1 is a fixed manipulator. Mobile manipulation is a v2+ scope expansion |
| ❌ **LiDAR** | No navigation in v1 |
| ❌ **Depth camera (RealSense, etc.)** | Fixed overhead RGB camera + known table plane gives unique pixel→world coordinates without depth |
| ❌ **Force / torque sensors** | The RoArm-M2-S hobby servos don't expose force feedback. Manipulation strategy is "rigid top-down grasps only" |
| ❌ **Second arm** | Bimanual manipulation is a v2+ goal |

---

## Software stack

| Layer | Component | Role |
|---|---|---|
| **Cognition** | ANIMA LLM-as-Parser (Claude API) + py_trees + test-and-check validator | Natural language → structured TaskSpec → behavior tree → dispatch |
| **Perception** | Grounding DINO 2 + SAM2 + pixel→world reprojection | Open-vocabulary text query → object world coordinates |
| **Motion planning** | MoveIt2 (4-DOF, IKFast/BioIK) | Hardcoded primitive safety net (Week 3) |
| **Policy learning** | LeRobot ACT (Action Chunking Transformer) | Trained per primitive on real-robot teleop demos |
| **Hardware driver** | Custom thin Python driver for the Waveshare serial protocol | < 200 lines, exposed as a ROS 2 node |
| **Data collection** | LeRobot teleop pipeline + PDP Xbox gamepad (`pygame` / `python-evdev`) | LeRobotDataset format, published to HuggingFace Hub |
| **Middleware** | ROS 2 Humble Hawksbill | Single-machine; everything runs in WSL2 |
| **Verification sim** | Gazebo (URDF check + ANIMA dry-run only) | Not used for ML training |

### ROS 2 packages

```
src/
├── anima_node/         # ANIMA cognitive layer ROS 2 wrapper
│   ├── nodes/          #   - anima_core_node (LLM parser + TaskSpec validator)
│   │                   #   - skill_executor_node (skill dispatch via behavior tree)
│   ├── config/         #   - skills.yaml (skill registry + affordances)
│   └── launch/
├── arm_description/    # RoArm-M2-S URDF + Gazebo verification scene
│   ├── urdf/           #   - 4-DOF kinematic chain
│   ├── worlds/         #   - tabletop world for dry-runs
│   └── launch/         #   - display.launch.py (RViz), gazebo.launch.py
└── arm_bringup/        # Top-level launch (description + ANIMA)
    └── launch/
```

ROS 2 packages added later in the sprint:

- `arm_perception/` (Week 2) — Grounding DINO + SAM2 + pixel→world reprojection
- `arm_manipulation/` (Week 3) — MoveIt2 config + hardcoded primitive safety net

---

## Skill primitives and task tiers

### ACT-trained primitives

| Primitive | Input | Action | 4-DOF feasibility |
|---|---|---|---|
| `pick(x, y)` | Object pixel → world coord | Top-down grasp | ✅ core |
| `place(x, y)` | Target world coord | Release at target | ✅ core |
| `push(from, to)` | Start + end coord | Non-prehensile push | ✅ core |
| `sweep(area)` | Region | Gather multiple objects | ⚠️ stretch |
| `stack_on(target)` | Top of another object | Stacking | ⚠️ stretch (2-3 layers max) |

### Task tiers (what ANIMA orchestrates on top)

**Tier 1 — single-step language grounding** (the entry-level demo every project does)
- `"Put the green sponge in the bin."`
- `"Pick up the yellow one."`

**Tier 2 — multi-step long-horizon** (RT-1 / RT-2 level)
- `"Sort the sponges by color into the matching bins."`
- `"Stack the three green sponges."`
- `"Clean up the table."`

**Tier 3 — conditional + spatial reasoning** (ANIMA differentiator)
- `"If there's a green sponge, put it in the bin. Otherwise put the yellow one in."`
- `"Put the green sponge to the left of the yellow one."`
- `"Pick up the sponge that doesn't match the others."`

**Tier 4 — test-and-check + failure recovery** (DIARC signature, almost no LLM-robot demo does this)
- `"Pick up the green sponge."`
- → first attempt → fails
- → ANIMA verifies via vision: object still in original position
- → retry
- → still fails
- → natural-language report: *"I tried twice and the gripper slipped. Want me to try a different angle?"*

---

## Project structure

```
SmartRobotArm/
├── README.md                    # this file (English)
├── README_zh.md                 # Chinese version
├── LICENSE                      # Apache-2.0
├── CLAUDE.md                    # project conventions for Claude Code
├── 开发进度与待办事项.md         # 8-week sprint plan + progress tracking (single source of truth)
├── docs/
│   ├── DEVELOPMENT.md           # step-by-step dev guide (legacy, partially stale)
│   ├── FAQ-硬件与仿真.md         # hardware + sim FAQ (legacy, partially stale)
│   └── smart-robot-arm.jpg      # workstation photo
└── src/                         # ROS 2 workspace (colcon build)
    ├── anima_node/              # cognitive layer
    ├── arm_description/         # URDF + verification sim
    └── arm_bringup/             # top-level launch
```

---

## Quick start

> Assumes WSL2 + Ubuntu 22.04 + ROS 2 Humble. The full one-time environment setup is described in [`开发进度与待办事项.md`](开发进度与待办事项.md), section "开发环境".

### Build

```bash
cd ~/SmartRobotArm
colcon build --symlink-install
source install/setup.bash
```

### Sanity check the URDF in RViz

```bash
ros2 launch arm_description display.launch.py
```

### Launch the arm + ANIMA mock parser

```bash
ros2 launch arm_bringup full_system.launch.py llm_backend:=mock
```

### Send a test instruction

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

> **Tip**: drop these into an `attach_devices.bat` and put it on the desktop. Each Windows reboot detaches USB from WSL2.

---

## Roadmap

8-week sprint, single source of truth: [`开发进度与待办事项.md`](开发进度与待办事项.md).

| Week | Goal | Deliverable |
|---|---|---|
| **W1** | Dev environment + workstation + USB integration | Teleop the arm in WSL2; camera publishes to ROS 2; eye-to-hand calibration done |
| **W2** | Perception pipeline | Text query → world (x, y) via Grounding DINO + SAM2 |
| **W3** | MoveIt2 + hardcoded primitives (safety net) | Each primitive ≥ 80% success rate at known coordinates |
| **W4** | Teleop data collection | ~120 demos pushed to HuggingFace Hub as a public LeRobotDataset |
| **W5** | ACT training + real-robot eval | Per-primitive success rate table from 50 rollouts each |
| **W6** | ANIMA Tier 1 end-to-end | Natural-language `"put the green sponge in the bin"` works on the real arm |
| **W7** | Tier 2-3 + test-and-check loop | Multi-step task + failure recovery demo |
| **W8** | Demo video + portfolio | Resume bullets, demo video, public release |

### Industry buzzword coverage (resume claims)

The project deliberately follows the conventions of the embodied AI / IL community so every line on the resume is legible to the field:

- ✅ **Real-robot teleop data collection** (LeRobot)
- ✅ **LeRobotDataset format + HuggingFace Hub** dataset publishing
- ✅ **ACT (Action Chunking Transformer)** trained on real-robot data
- ✅ **Real-robot success rate evaluation** with quantitative metrics
- ✅ **Open-vocabulary perception** (Grounding DINO + SAM2)
- ✅ **LLM as task parser** (Claude API), not LLM-as-Translator
- ✅ **Behavior tree task executor** (py_trees)
- ✅ **ROS 2 system integration** (multi-package architecture)
- ✅ **MoveIt2 motion planning**
- ✅ **Test-and-check validation** + failure recovery loop (DIARC-inspired, **differentiator**)
- ✅ **Multi-step long-horizon task planning**
- ✅ **Spatial reasoning + LLM grounding**
- ✅ **Open source** on GitHub with full docs

What v1 deliberately does NOT do: RL, sim2real transfer, VLA fine-tuning, mobile manipulation on real hardware, garment / cloth manipulation, bimanual, custom perception model training. See the dev plan for the rationale.

---

## Project lineage

- **Cognitive layer**: built on [ANIMA_O1](https://github.com/jeffliulab/ANIMA_O1), an open-source cognitive framework for home robots, inspired by [DIARC](https://hrilab.tufts.edu/) (Tufts HRI Lab, where the developer was a Research Assistant in 2024–2025).
- **Migrated from**: [`soma_home_exp_v1`](https://github.com/jeffliulab/soma_home_exp_v1) (now archived). The original v1 plan was a mobile manipulation robot for garment sorting; on 2026-04-07 it was scoped down to a fixed tabletop manipulator. Shortly after, the repo was renamed/migrated to `SmartRobotArm` to better reflect the actual scope ("a smart arm, not a home robot"). The earlier commit on this repo (a brief SO-ARM100 + LEAP Hand + MediaPipe exploration) is unrelated and was rebuilt from scratch.
- **Long-term vision**: SmartRobotArm is the **manipulator capability layer** of the SOMA Homies family of home robots. Once the arm is reliable, it will be integrated onto a mobile platform to become Soma Home, the family's first complete robot.

---

## License

[Apache License 2.0](LICENSE) — Copyright 2026 Jeff Liu Lab ([jeffliulab.com](https://jeffliulab.com), GitHub [@jeffliulab](https://github.com/jeffliulab)).

You may use, modify, and redistribute this code commercially or privately, provided you keep the copyright and license notices and document any changes. Contributors grant an explicit patent license; suing a contributor over patents in this work terminates your license.
