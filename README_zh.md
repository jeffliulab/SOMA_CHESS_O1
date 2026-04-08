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
  <img src="https://img.shields.io/badge/状态-Active-brightgreen" alt="状态">
  <img src="https://img.shields.io/badge/许可证-Apache_2.0-green" alt="许可证">
</p>

<p>
  <strong>语言驱动的智能机械臂——自然语言 → LLM 任务解析 → ACT 技能执行 → 视觉验证，全程在真机上。</strong>
</p>

<p>
  <a href="https://github.com/jeffliulab/ANIMA_O1"><img src="https://img.shields.io/badge/认知层-ANIMA_O1-purple" alt="ANIMA_O1"></a>
</p>

</div>

---

![工作站](docs/smart-robot-arm.jpg)

---

## 项目简介

SmartRobotArm 是一个语言驱动的真机操作演示。用户说出自然语言指令，由 Claude 驱动的 parser 将其转化为结构化任务规约（TaskSpec）；开放词汇感知（Grounding DINO + SAM2）把语言定位到场景中的物体；模仿学习策略（ACT，通过 LeRobot 在真机 teleop 数据上训练）在 4-DOF 机械臂上执行原语技能；视觉验证器在每一步之后确认结果，再向用户报告。

项目基于开源认知框架 [ANIMA](https://github.com/jeffliulab/ANIMA_O1)——一种以 LLM-as-Parser + 行为树 + test-and-check 验证闭环为核心的架构。

## 项目亮点

- **语言 → 真机动作的端到端闭环**。说一句 `"把绿色海绵放进盒子"`，系统就能完成语言理解、任务分解、真机执行和视觉验证——全部在一台桌面工作站上完成。
- **可验证的认知层**。基于开源 ANIMA 框架：LLM-as-Parser（不是 LLM-as-Translator）输出结构化 TaskSpec，py_trees 行为树执行任务，test-and-check 验证器捕获失败并触发自然语言回复。
- **真实世界的模仿学习，不是仿真**。在真机上用 LeRobot 采集 teleop 演示，作为公开 LeRobotDataset 发布到 HuggingFace Hub，再训练 ACT (Action Chunking Transformer) 策略，给出每个技能的成功率指标。
- **开放词汇感知开箱即用**。Grounding DINO + SAM2 把任意文本查询（`"绿色海绵"`、`"空盒子"`）翻译成世界坐标，无需为每个物体单独训练模型。
- **完全开源**。Apache-2.0 协议，公开数据集 + 公开代码 + 公开模型权重——任何拥有 Logitech C922 和入门级机械臂的人都能复现。

---

## 目录

- [项目简介](#项目简介)
- [项目亮点](#项目亮点)
- [系统架构](#系统架构)
- [硬件配置](#硬件配置)
- [软件栈](#软件栈)
- [机器人能做什么](#机器人能做什么)
- [项目结构](#项目结构)
- [快速开始](#快速开始)
- [关于](#关于)
- [许可证](#许可证)

---

## 系统架构

```
   用户："把绿色海绵放进盒子"
                       │
                       ▼
       ┌─────────────────────────────┐
       │  ANIMA LLM Parser           │  Claude API → 结构化 TaskSpec JSON
       └──────────────┬──────────────┘
                      ▼
       ┌─────────────────────────────┐
       │  Grounding DINO + SAM2      │  文本 → 物体像素 mask → 世界坐标 (x, y)
       └──────────────┬──────────────┘
                      ▼
       ┌─────────────────────────────┐
       │  py_trees 行为树             │  任务分解 + 技能调度
       │  + 技能注册表                │  skills.yaml: affordances + 前置条件
       └──────────────┬──────────────┘
                      ▼
       ┌─────────────────────────────┐
       │  ACT 训练的原语              │  pick / place / push, 从真机
       │  (LeRobot, 真机数据)         │  teleop 演示中学习
       └──────────────┬──────────────┘
                      ▼
       ┌─────────────────────────────┐
       │  Test-and-check 验证器       │  基于视觉的执行结果验证
       │                              │  → 成功 / 重试 / 报告失败
       └─────────────────────────────┘
```

ANIMA 四层架构（NLU → Planning → Execution → Policy）是机器人无关的。SmartRobotArm 提供技能注册表、传感器配置和硬件驱动；ANIMA 负责从语言理解到技能调度的全部环节。同一套认知层可以复用到其他机器人本体上。

---

## 硬件配置

### 计算

| 组件 | 规格 |
|---|---|
| **桌面 PC** | Windows 11 + RTX 4090 (24 GB VRAM) |
| **开发环境** | WSL2 + Ubuntu 22.04 + CUDA passthrough |
| **USB 集成** | `usbipd-win` 把相机、机械臂、手柄直接转发到 WSL2 |

### 机器人

| 组件 | 规格 |
|---|---|
| **机械臂** | [Waveshare RoArm-M2-S](https://www.waveshare.com/roarm-m2-s.htm)——4-DOF, ~28 cm 工作半径, ~500 g payload, ESP32 + STS3215 舵机 |
| **安装方式** | C 形夹固定在工作台右侧 |
| **末端执行器** | 自带 2 指夹爪，开口 ~5–6 cm，仅 top-down 抓取 |

### 感知

| 组件 | 规格 |
|---|---|
| **相机** | Logitech C922 Pro Stream Webcam——USB UVC, 1080p @ 30 fps。通过 `v4l2-ctl` 锁定自动曝光 / 自动白平衡 / 自动对焦，保证训练数据一致性 |
| **相机支架** | JOBY GorillaPod 柔性三脚架，距工作区 ~50–60 cm |
| **工作区光照** | 独立 LED 桌面台灯，与环境光分离 |

### 工作台

| 项目 | 规格 |
|---|---|
| **工作台面** | ~60×50 cm 桌面 + 单色背景垫 |
| **操作物体** | 黄/绿双面海绵块，~4–5 cm |
| **目标容器** | 绿色外圈 + 白色内壁塑料盒，~15×12 cm |

### 遥操作

| 组件 | 规格 |
|---|---|
| **输入设备** | PDP Wired Controller for Xbox——XInput 协议，4 摇杆轴 1:1 映射到机械臂关节，肩键控制夹爪开合，扳机模拟量控制夹爪开合速度 |

---

## 软件栈

| 层 | 组件 |
|---|---|
| **认知** | ANIMA——LLM-as-Parser (Claude API) + py_trees 行为树 + test-and-check 验证器 |
| **感知** | Grounding DINO 2 + SAM2 + 像素→世界坐标重投影 |
| **运动规划** | MoveIt2 (4-DOF, IKFast / BioIK) |
| **策略学习** | LeRobot ACT (Action Chunking Transformer)，每个原语单独训练 |
| **硬件驱动** | 自写 Python driver 包装 Waveshare 串口协议，封装为 ROS 2 节点 |
| **数据采集** | LeRobot teleop pipeline，手柄通过 `pygame` / `python-evdev` 接入 |
| **数据集格式** | LeRobotDataset，发布到 HuggingFace Hub |
| **中间件** | ROS 2 Humble Hawksbill（单机部署） |
| **验证用仿真** | Gazebo（URDF 可视化 + 认知层干跑） |

### ROS 2 包

```
src/
├── anima_node/         # ANIMA 认知层 ROS 2 wrapper
│   ├── nodes/          #   - anima_core_node    (LLM parser + TaskSpec 验证器)
│   │                   #   - skill_executor_node (行为树调度器)
│   ├── config/         #   - skills.yaml (技能注册表 + affordances)
│   └── launch/
├── arm_description/    # RoArm-M2-S URDF + Gazebo 验证场景
│   ├── urdf/           #   - 4-DOF 运动学链
│   ├── worlds/         #   - 桌面场景
│   └── launch/         #   - display.launch.py (RViz)、gazebo.launch.py
└── arm_bringup/        # 顶层 launch（description + ANIMA）
    └── launch/
```

---

## 机器人能做什么

### 技能原语

ACT 训练的原子技能，作为认知层的可组合积木：

| 原语 | 描述 |
|---|---|
| `pick(x, y)` | 在指定世界坐标处 top-down 抓取 |
| `place(x, y)` | 在指定世界坐标处释放 |
| `push(from, to)` | 两个坐标之间的非抓取式推动 |

### 任务能力

认知层把原语组合成不同复杂度的任务：

**单步语言 grounding**

- *"把绿色海绵放进盒子。"*
- *"拿起黄色那块。"*

**多步长时程任务**

- *"把海绵按颜色分到对应盒子里。"*
- *"把三块绿色海绵叠起来。"*
- *"把桌面收拾干净。"*

**条件 + 空间推理**

- *"如果有绿色海绵就放进盒子，否则放黄色那块。"*
- *"把绿色海绵放到黄色海绵的左边。"*
- *"拿起和其它不一样的那块。"*

**Test-and-check 与失败恢复**

- *"拿起绿色海绵。"*
- → 第一次尝试 → 失败
- → ANIMA 视觉验证：物体仍在原位
- → 重试
- → 仍失败
- → 自然语言报告：*"我试了两次，夹爪都滑了。要不要试试不同角度？"*

Test-and-check 验证闭环是 ANIMA 的标志性特性，也是这个项目的差异化所在——目前几乎没有 LLM-on-robot 演示在做这件事。

---

## 项目结构

```
SmartRobotArm/
├── README.md                    # 英文版（GitHub 默认展示）
├── README_zh.md                 # 中文版（本文件）
├── LICENSE                      # Apache-2.0
├── CLAUDE.md                    # Claude Code 项目规范
├── docs/
│   ├── DEVELOPMENT.md
│   ├── FAQ-硬件与仿真.md
│   └── smart-robot-arm.jpg      # 工作站照片
└── src/                         # ROS 2 workspace（colcon build）
    ├── anima_node/              # 认知层
    ├── arm_description/         # URDF + 验证用仿真
    └── arm_bringup/             # 顶层 launch
```

---

## 快速开始

> 假设已经装好 WSL2 + Ubuntu 22.04 + ROS 2 Humble + LeRobot。

### Build

```bash
cd ~/SmartRobotArm
colcon build --symlink-install
source install/setup.bash
```

### 在 RViz 里可视化 URDF

```bash
ros2 launch arm_description display.launch.py
```

### 启动机械臂 + 认知层

```bash
ros2 launch arm_bringup full_system.launch.py llm_backend:=mock
```

### 发一条自然语言指令

```bash
ros2 topic pub /user_instruction std_msgs/String \
  "data: 'put the green sponge in the bin'"
```

### USB 设备转发（每次 Windows 重启后在 PowerShell 跑一次）

```powershell
usbipd attach --wsl --busid <C922_BUSID>
usbipd attach --wsl --busid <ROARM_BUSID>
usbipd attach --wsl --busid <PDP_GAMEPAD_BUSID>
```

---

## 关于

**作者**：[Jeff Liu Lab](https://jeffliulab.com)——[@jeffliulab](https://github.com/jeffliulab)。

**可复用的认知层**。[ANIMA 框架](https://github.com/jeffliulab/ANIMA_O1)作为独立的开源项目维护，可以复用到其他机器人本体上——SmartRobotArm 是它的第一个参考实现。

**长期愿景**。我开发 ANIMA 认知框架的目标，是为最终开发 SOMA 家务机器人服务的——我想做一个能协助做家务的家庭机器人，提升人们的生活幸福感。SmartRobotArm 是这个未来家用机器人的机械臂能力层；当前固定式的工作站会在后续版本中集成到 mobile 平台上。

---

## 许可证

[Apache License 2.0](LICENSE)——Copyright 2026 Jeff Liu Lab（[jeffliulab.com](https://jeffliulab.com), GitHub [@jeffliulab](https://github.com/jeffliulab)）。

允许商用、私用、修改、分发，前提是保留版权和许可证声明，并标注修改内容。贡献者授予明确的专利使用权；对贡献者发起专利诉讼将自动终止你在本项目下的授权。
