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
  <img src="https://img.shields.io/badge/下棋-v2目标-8B4513" alt="下棋">
  <img src="https://img.shields.io/badge/状态-Active-brightgreen" alt="状态">
  <img src="https://img.shields.io/badge/许可证-Apache_2.0-green" alt="许可证">
</p>

<p>
  <strong>语言驱动的机械臂——自然语言 → LLM 任务解析 → ACT 技能执行 → 视觉验证，全程在真机上。v1：语音指令整理海绵和棋子；v2：下任意棋类。</strong>
</p>

<p>
  <a href="https://github.com/jeffliulab/ANIMA_O1"><img src="https://img.shields.io/badge/认知层-ANIMA_O1-purple" alt="ANIMA_O1"></a>
</p>

</div>

---

![工作站](docs/smart-robot-arm.jpg)

---

## 项目简介

**SOMA Chess O1** 是 SOMA 机械臂系列的首个开源版本——基于 [ANIMA](https://github.com/jeffliulab/ANIMA_O1) 认知框架的语言驱动操作系统。用户说出自然语言指令，由 Claude 驱动的 parser 将其转化为结构化任务规约（TaskSpec）；开放词汇感知（Grounding DINO + SAM2）把语言定位到场景中的物体；模仿学习策略（ACT，通过 LeRobot 在真机 teleop 数据上训练）在 4-DOF 机械臂上执行原语技能；视觉验证器在每一步之后确认结果，再向用户报告。

**v1 目标**：拾取两类物理特征不同的对象——泡沫海绵（宽容，练基础抓取）和棋子（精小，验证精度）——证明同一套认知层可以指挥不同抓取策略。

**v2 目标（闭源，未来独立仓库）**：实际下棋——棋盘状态识别、Stockfish + Claude 走子规划、物理落子执行，以及"通用棋类"接口（用自然语言描述规则就能下任意棋）。

## 项目亮点

- **语言 → 真机动作的端到端闭环**。说一句 `"把所有东西放进盒子"`，系统就能找到所有物体、规划任务、在真机上逐步执行并验证——全部在一台工作站上完成。
- **两类物体，一套认知层**。同一个 ANIMA pipeline 同时处理泡沫海绵和棋子，无需修改代码——只有夹爪宽度参数不同，展示了认知架构对不同物理对象的泛化能力。
- **可验证的认知层**。基于开源 ANIMA 框架：LLM-as-Parser（不是 LLM-as-Translator）输出结构化 TaskSpec，py_trees 行为树执行任务，test-and-check 验证器捕获失败并触发自然语言回复。
- **真实世界的模仿学习，不是仿真**。在真机上用 LeRobot 采集 teleop 演示，作为公开 LeRobotDataset 发布到 HuggingFace Hub，再训练 ACT (Action Chunking Transformer) 策略，给出每个技能的成功率指标。
- **开放词汇感知开箱即用**。Grounding DINO + SAM2 把任意文本查询（`"绿色海绵"`、`"棋子"`、`"空盒子"`）翻译成世界坐标，无需为每个物体单独训练模型。
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

ANIMA 四层架构（NLU → Planning → Execution → Policy）是机器人无关的。SOMA Chess O1 提供技能注册表、传感器配置和硬件驱动；ANIMA 负责从语言理解到技能调度的全部环节。同一套认知层可以复用到其他机器人本体上。

---

## 硬件配置

### 计算

| 组件 | 规格 |
|---|---|
| **工作站笔记本** | Windows 11 + RTX 4090 Laptop GPU (16 GB VRAM) |
| **开发环境** | WSL2 + Ubuntu 22.04 + CUDA passthrough |
| **USB 集成** | 长期推荐：`usbipd-win` 只把机械臂和手柄转发到 WSL2；C922 留在 Windows 原生侧采集，再通过轻量 TCP bridge 发到 WSL |

### 机器人

| 组件 | 规格 |
|---|---|
| **机械臂** | [Waveshare RoArm-M2-S](https://www.waveshare.com/roarm-m2-s.htm)——4-DOF, ~28 cm 工作半径, ~500 g payload, ESP32 + STS3215 舵机 |
| **安装方式** | C 形夹固定在工作台右侧 |
| **末端执行器** | 自带 2 指夹爪，开口 ~5–6 cm，仅 top-down 抓取 |

### 感知

| 组件 | 规格 |
|---|---|
| **相机** | Logitech C922 Pro Stream Webcam——USB UVC, 1080p @ 30 fps。当前正式路线是在 Windows 原生取图，再通过轻量 bridge 发到 WSL，因为这台机器上的 `usbipd + WSL` MJPG 链路会出现横向破图 |
| **相机支架** | JOBY GorillaPod 柔性三脚架，距工作区 ~50–60 cm |
| **工作区光照** | 独立 LED 桌面台灯，与环境光分离 |

### 工作台

| 项目 | 规格 |
|---|---|
| **工作台面** | ~60×50 cm 桌面 + 单色背景垫 |
| **操作物体** | 黄/绿双面海绵块（~4–5 cm）+ 棋子（v1 主要用兵+车，混合类型） |
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
| **数据采集** | LeRobot teleop pipeline；默认手柄路径为 WSL 直通 `evdev`，Windows TCP bridge 保留为回退方案 |
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
| `pick(x, y, object_class)` | 在指定世界坐标处 top-down 抓取；按物体类别选择夹爪宽度 |
| `place(x, y)` | 在指定世界坐标处释放 |
| `push(from, to)` | 两个坐标之间的非抓取式推动 |

### 任务能力

认知层把原语组合成不同复杂度的任务：

**单步语言 grounding**

- *"把绿色海绵放进盒子。"*
- *"拿起那个兵。"*

**多步长时程任务**

- *"把所有东西都放进盒子里。"* ← v1 旗舰任务：一条指令同时处理海绵和棋子
- *"把三块绿色海绵叠起来。"*
- *"把桌面收拾干净。"*

**条件 + 空间推理**

- *"如果左边有海绵就放进盒子，否则放棋子。"*
- *"把绿色海绵放到黄色海绵的左边。"*
- *"拿起不属于这里的那个。"*

**Test-and-check 与失败恢复**

- *"把所有东西放进盒子。"*
- → 拿起海绵 → 验证成功 → 拿棋子 → 夹爪滑脱
- → ANIMA 视觉验证：棋子仍在原位
- → 重试
- → 仍失败
- → 自然语言报告：*"我试了两次，棋子上夹爪都滑了。要不要再试一次？"*

Test-and-check 验证闭环是 ANIMA 的标志性特性，也是这个项目的差异化所在——目前几乎没有 LLM-on-robot 演示在做这件事。

---

## 项目结构

```
SOMA_CHESS_O1/
├── README.md                    # 英文版（GitHub 默认展示）
├── README_zh.md                 # 中文版（本文件）
├── LICENSE                      # Apache-2.0
├── CLAUDE.md                    # Claude Code 项目规范
├── docs/
│   ├── DEVELOPMENT.md
│   ├── FAQ-硬件与仿真.md
│   └── 机械臂技术文档.md        # RoArm-M2-S 协议 + ROS 2 接口 + 安全操作
└── src/                         # ROS 2 workspace（colcon build）
    ├── anima_node/              # ANIMA 认知层 wrapper
    ├── arm_description/         # URDF + Gazebo 验证场景
    ├── arm_driver/              # RoArm-M2-S USB 串口驱动 + MoveIt2 bridge
    ├── arm_teleop/              # PDP Xbox 手柄 teleop 节点
    └── arm_bringup/             # 顶层 launch
```

---

## 快速开始

> 假设已经装好 WSL2 + Ubuntu 22.04 + ROS 2 Humble + LeRobot。

### Build

```bash
cd ~/SOMA/SOMA_CHESS_O1
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
usbipd attach --wsl --busid <ROARM_BUSID>
usbipd attach --wsl --busid <PDP_GAMEPAD_BUSID>
```

正常工作流里，C922 不再 attach 到 WSL。

### Windows 相机 bridge

在 Windows 里运行：

```bat
scripts\bridge方案\start_camera_bridge.bat
```

WSL 里运行：

```bash
scripts/start_camera_bridge_wsl.sh
```

WSL 侧继续订阅：

- `/camera/image_raw`
- `/camera/camera_info`

完整使用流程见 [docs/Windows_TCP相机桥接.md](docs/Windows_TCP相机桥接.md)。

### 长期推荐的手柄方案（WSL 直通）

仓库内已经补齐这条路线需要的脚本与文档：

- `scripts/build_wsl_gamepad_kernel.sh`：构建与当前 WSL 版本匹配、开启 `JOYDEV + XPAD` 的自定义内核
- `scripts/attach_devices.bat`：Windows 侧一键把机械臂 + 手柄 attach 到 WSL
- `scripts/check_wsl_gamepad_support.sh`：检查当前内核是否真的具备手柄支持
- `scripts/start_teleop_wsl_gamepad.sh`：直接以 Linux 本地模式启动 teleop（`use_tcp_bridge:=false`）
- `docs/WSL_Xbox手柄直通.md`：完整实施指南

这条路线的关键优点是：手柄 attached 到 WSL 之后，Windows 将不再使用它，因此不会再干扰 Windows Terminal 或其他 UI。旧的 Windows bridge 备选方案已整理到 `scripts/bridge方案/` 下。

当前最短可用操作：

1. Windows 管理员 PowerShell 先跑 `usbipd list`
2. 确认当次开机下 RoArm 和 Xbox 手柄的 busid
3. 如果它们已经显示为 `Attached`，就不要重复 attach；这本来就是成功态
4. 否则运行：

```powershell
cd \\wsl$\Ubuntu-22.04\home\jeffliu\SOMA\SOMA_CHESS_O1\scripts
.\attach_devices.bat
```

5. WSL 里运行：

```bash
cd ~/SOMA/SOMA_CHESS_O1
scripts/start_teleop_wsl_gamepad.sh
```

6. 等日志出现 `Teleop target initialized from current /joint_states.`
7. 按一次 `Start`
8. 再看到 `Start pressed — re-enabled, going home` 后开始推摇杆

两个最容易踩的坑：

- `Attached` 不是失败，而是已经成功进 WSL
- `\\wsl$\\...` 路径只能在 Windows shell 里用；WSL 里要用 `~/SOMA/...`

当前默认 teleop 版本（2026-04-10 锁定）：

- `evdev` 是默认 Linux 输入后端
- 左摇杆使用硬单轴锁定，专门抑制这只手柄本身的串轴问题
- 默认关闭 motion smoothing：摇杆大小直接映射关节速度
- 纯夹爪动作走独立 `/gripper_command`，底层使用协议 `T:106`，不再重发整臂 `T:102`

---

## 关于

**作者**：[Jeff Liu Lab](https://jeffliulab.com)——[@jeffliulab](https://github.com/jeffliulab)。

**可复用的认知层**。[ANIMA 框架](https://github.com/jeffliulab/ANIMA_O1)作为独立的开源项目维护，可以复用到其他机器人本体上——SOMA Chess O1 是它的第一个参考实现。

**v1 → v2 路线图**。v1（本仓库，开源）实现语言驱动的海绵 + 棋子拾取整理。v2（闭源，未来独立仓库）增加实际下棋：棋盘状态识别、Stockfish + Claude 走子规划、物理落子、通用棋类接口（自然语言描述规则即可开始下棋）。

**长期愿景**。我开发 ANIMA 认知框架的目标，是为最终开发 SOMA 家务机器人服务的——我想做一个能协助做家务的家庭机器人，提升人们的生活幸福感。SOMA Chess O1 是这个未来家用机器人的机械臂能力层；当前固定式的工作站会在后续版本中集成到 mobile 平台上。

---

## 许可证

[Apache License 2.0](LICENSE)——Copyright 2026 Jeff Liu Lab（[jeffliulab.com](https://jeffliulab.com), GitHub [@jeffliulab](https://github.com/jeffliulab)）。

允许商用、私用、修改、分发，前提是保留版权和许可证声明，并标注修改内容。贡献者授予明确的专利使用权；对贡献者发起专利诉讼将自动终止你在本项目下的授权。
