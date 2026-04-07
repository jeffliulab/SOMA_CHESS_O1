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
  <img src="https://img.shields.io/badge/状态-开发中-yellow" alt="状态">
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

## 项目亮点

- **语言 → 真机动作闭环**：说一句 `"把绿色海绵放进盒子"`，系统通过 Claude 解析意图，用 Grounding DINO + SAM2 把语言定位到场景中的物体，在真实 4-DOF 机械臂上调用 ACT 训练好的技能原语执行，再用视觉验证是否成功。
- **认知层是主角**：基于开源框架 [ANIMA](https://github.com/jeffliulab/ANIMA_O1) 构建——LLM-as-Parser（不是 Translator）、py_trees 行为树、DIARC 风格的 test-and-check 验证 + 失败恢复闭环。
- **业界标准的 IL pipeline**：用有线 Xbox 手柄做真机 teleop，把 LeRobotDataset 发布到 HuggingFace Hub，从真实示教数据训练 ACT (Action Chunking Transformer)。**v1 完全不用仿真训练**。
- **单机系统**：Logitech C922 + Waveshare RoArm-M2-S + PDP Xbox 手柄全部直接插到一台 PC 上。v1 不用 Pi、不用 WiFi、不用多机 ROS DDS。
- **完全开源**：Apache-2.0，公开数据集、公开代码、公开模型权重。

> **状态**：pre-alpha，8 周冲刺中。API、ROS package 名、launch 文件**会在没有警告的情况下变更**。

---

## 目录

- [项目亮点](#项目亮点)
- [系统架构](#系统架构)
- [硬件配置](#硬件配置)
- [软件栈](#软件栈)
- [技能原语与任务分级](#技能原语与任务分级)
- [项目结构](#项目结构)
- [快速开始](#快速开始)
- [开发路线](#开发路线)
- [项目沿革](#项目沿革)
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
       │  + 技能注册表                │  (skills.yaml: affordance + 前置条件)
       └──────────────┬──────────────┘
                      ▼
       ┌─────────────────────────────┐
       │  ACT 训练的原语              │  pick / place / push, 每个 ~30 条
       │  (LeRobot, 真机数据)         │  PDP 手柄 teleop 采集
       │  MoveIt2 硬编码兜底          │  Week 3 安全网
       └──────────────┬──────────────┘
                      ▼
       ┌─────────────────────────────┐
       │  Test-and-check 验证器       │  基于视觉验证执行结果
       │  (DIARC 风格)                │  → 成功 / 重试 / 报告失败
       └─────────────────────────────┘
```

ANIMA 四层设计（NLU → Planning → Execution → Policy）是机器人无关的。SmartRobotArm 提供技能注册表、传感器配置和硬件驱动；ANIMA 负责从语言理解到技能调度的全部环节。

---

## 硬件配置

完整配置已于 2026-04-07 工作站搭建完成时锁定。

### 计算

| 组件 | 规格 | 角色 |
|---|---|---|
| **桌面 PC** | Windows 11 + RTX 4090 (24 GB VRAM) | 承载所有计算：训练、推理、感知、ROS 2、ANIMA、Claude API client |
| **开发系统** | WSL2 + Ubuntu 22.04 + CUDA passthrough | 原生 Linux 跑 ROS 2 / LeRobot 生态；CUDA passthrough 让 RTX 4090 性能 100% 无损（双系统 Linux 反而会损失） |
| **USB 转发** | `usbipd-win`（Windows 端）→ WSL2 看到 `/dev/video0`、`/dev/ttyUSB0`、`/dev/input/js0` | 所有硬件直插桌面 PC，不需要 Pi、不需要 WiFi、不需要多机 |

### 机器人

| 组件 | 规格 | 角色 |
|---|---|---|
| **机械臂** | [Waveshare RoArm-M2-S](https://www.waveshare.com/roarm-m2-s.htm) | 4-DOF, ~28 cm 工作半径, ~500 g payload, ESP32 + STS3215 舵机, USB serial |
| **安装方式** | C 形夹固定在工作台右侧边沿 | 刚性固定，eye-to-hand 标定结果跨 session 有效 |
| **末端执行器** | 自带 2 指夹爪，开口 ~5–6 cm | 仅 top-down 抓取 |

### 感知

| 组件 | 规格 | 角色 |
|---|---|---|
| **相机** | Logitech C922 Pro Stream Webcam | USB UVC, 1080p @ 30 fps。通过 `v4l2-ctl` 锁定自动曝光 / 自动白平衡 / 自动对焦，保证 ACT 训练数据的视觉一致性。**ALOHA 同款**，社区可复现性好 |
| **相机支架** | JOBY GorillaPod 柔性三脚架 | 缠绕在桌沿，相机距工作区 ~50–60 cm，约 60° 俯视 |
| **工作区光照** | 独立 LED 桌面台灯 | 独立于环境光，保证 teleop session 和 ACT 推理时光照一致 |

### 工作台与物体

| 项目 | 规格 | 备注 |
|---|---|---|
| **工作台面** | ~60×50 cm 木纹色桌面 | 待加纯色背景垫（黑色 KT 板，~$3），提升 Grounding DINO + SAM2 的稳定性 |
| **操作物体** | 黄/绿双面海绵块，~4-5 cm | 柔顺材质对舵机 1-2 mm 重复定位精度更宽容；双面颜色不同 → 可以设计"找出绿面朝上的那块"这种语言任务 |
| **目标容器** | 绿色外圈 + 白色内壁的塑料盒，~15×12 cm | 高对比内壁让"物体是否进入盒子"的视觉验证容易做 |

### Teleop 与数据采集

| 组件 | 规格 | 角色 |
|---|---|---|
| **Teleop 输入** | PDP Wired Controller for Xbox（[pdp.com](https://pdp.com)） | XInput 协议，Linux `xpad` 内核驱动原生支持，`usbipd attach` 后识别为 `/dev/input/js0`。4 摇杆轴 1:1 映射 4 个机械臂关节；LB/RB 控制夹爪开合；LT/RT 模拟量扳机控制夹爪开合速度 |

### 不在 v1 范围内的硬件

| 组件 | 不用的原因 |
|---|---|
| ❌ **Raspberry Pi 5 / 任何 SBC** | 工作台是固定的，桌面 PC 通过 USB 直接接管所有事情。Pi 5 留给 v2 嵌入式部署阶段 |
| ❌ **底盘 / 轮子 / 电机** | v1 是固定机械臂。Mobile manipulation 是 v2+ 的目标 |
| ❌ **LiDAR** | v1 不做导航 |
| ❌ **深度相机（RealSense 等）** | 固定俯视 RGB + 已知桌面平面 = 唯一的像素→世界坐标，不需要深度 |
| ❌ **力 / 力矩传感器** | RoArm-M2-S 的 hobby 舵机不暴露力反馈。操作策略限定为"刚性 top-down 抓取" |
| ❌ **第二只机械臂** | Bimanual 是 v2+ 的目标 |

---

## 软件栈

| 层 | 组件 | 角色 |
|---|---|---|
| **认知** | ANIMA LLM-as-Parser (Claude API) + py_trees + test-and-check 验证器 | 自然语言 → 结构化 TaskSpec → 行为树 → 调度 |
| **感知** | Grounding DINO 2 + SAM2 + 像素→世界坐标重投影 | 开放词汇文本查询 → 物体世界坐标 |
| **运动规划** | MoveIt2（4-DOF, IKFast/BioIK） | 硬编码原语兜底（Week 3） |
| **策略学习** | LeRobot ACT (Action Chunking Transformer) | 每个原语在真机 teleop 数据上单独训练 |
| **硬件驱动** | 自写薄 Python driver 包装 Waveshare 串口协议 | < 200 行，作为 ROS 2 节点暴露 |
| **数据采集** | LeRobot teleop pipeline + PDP Xbox 手柄（`pygame` / `python-evdev`） | LeRobotDataset 格式，发布到 HuggingFace Hub |
| **中间件** | ROS 2 Humble Hawksbill | 单机；全部跑在 WSL2 |
| **验证用仿真** | Gazebo（仅 URDF 验证 + ANIMA 干跑） | **不用于 ML 训练** |

### ROS 2 包

```
src/
├── anima_node/         # ANIMA 认知层 ROS 2 wrapper
│   ├── nodes/          #   - anima_core_node (LLM parser + TaskSpec 验证器)
│   │                   #   - skill_executor_node (通过行为树调度技能)
│   ├── config/         #   - skills.yaml (技能注册表 + affordances)
│   └── launch/
├── arm_description/    # RoArm-M2-S URDF + Gazebo 验证场景
│   ├── urdf/           #   - 4-DOF 运动学链
│   ├── worlds/         #   - 用于干跑的桌面场景
│   └── launch/         #   - display.launch.py (RViz)、gazebo.launch.py
└── arm_bringup/        # 顶层 launch（description + ANIMA）
    └── launch/
```

后续 sprint 中新增的 ROS 2 包：

- `arm_perception/`（Week 2）—— Grounding DINO + SAM2 + 像素→世界坐标重投影
- `arm_manipulation/`（Week 3）—— MoveIt2 配置 + 硬编码原语安全网

---

## 技能原语与任务分级

### ACT 训练的原语

| 原语 | 输入 | 动作 | 4-DOF 可行性 |
|---|---|---|---|
| `pick(x, y)` | 物体像素 → 世界坐标 | top-down 抓取 | ✅ 核心 |
| `place(x, y)` | 目标世界坐标 | 在目标处释放 | ✅ 核心 |
| `push(from, to)` | 起点 + 终点 | 非抓取式推动 | ✅ 核心 |
| `sweep(area)` | 区域 | 多物体聚拢 | ⚠️ stretch |
| `stack_on(target)` | 目标物体顶部 | 堆叠 | ⚠️ stretch（最多 2-3 层）|

### 任务分级（ANIMA 在原语之上编排出的任务复杂度）

**Tier 1 — 单步语言 grounding**（业内人人在做的入门 demo）
- `"把绿色海绵放进盒子。"`
- `"拿起黄色那块。"`

**Tier 2 — 多步长时程**（RT-1 / RT-2 级别）
- `"把海绵按颜色分到对应盒子里。"`
- `"把三块绿色海绵叠起来。"`
- `"把桌面收拾干净。"`

**Tier 3 — 条件 + 空间推理**（ANIMA 差异化点）
- `"如果有绿色海绵就放进盒子，否则放黄色那块。"`
- `"把绿色海绵放到黄色海绵的左边。"`
- `"拿起和其它不一样的那块。"`

**Tier 4 — Test-and-check + 失败恢复**（DIARC 签名特性，几乎没有 LLM-robot demo 在做）
- `"拿起绿色海绵。"`
- → 第一次尝试 → 失败
- → ANIMA 视觉验证：物体仍在原位
- → 重试
- → 仍失败
- → 自然语言报告：*"我试了两次，夹爪都滑了。要不要试试不同角度？"*

---

## 项目结构

```
SmartRobotArm/
├── README.md                    # 英文版（GitHub 默认展示）
├── README_zh.md                 # 中文版（本文件）
├── LICENSE                      # Apache-2.0
├── CLAUDE.md                    # Claude Code 项目规范
├── 开发进度与待办事项.md         # 8 周冲刺计划 + 进度追踪（single source of truth）
├── docs/
│   ├── DEVELOPMENT.md           # 分阶段开发指南（继承自旧 repo，部分内容已 stale）
│   ├── FAQ-硬件与仿真.md         # 硬件 + 仿真 FAQ（继承自旧 repo，部分内容已 stale）
│   └── smart-robot-arm.jpg      # 工作站照片
└── src/                         # ROS 2 workspace（colcon build）
    ├── anima_node/              # 认知层
    ├── arm_description/         # URDF + 验证用仿真
    └── arm_bringup/             # 顶层 launch
```

---

## 快速开始

> 假设已经装好 WSL2 + Ubuntu 22.04 + ROS 2 Humble。完整一次性环境配置见 [`开发进度与待办事项.md`](开发进度与待办事项.md) 的"开发环境"小节。

### Build

```bash
cd ~/SmartRobotArm
colcon build --symlink-install
source install/setup.bash
```

### 在 RViz 里 sanity check URDF

```bash
ros2 launch arm_description display.launch.py
```

### 启动机械臂 + ANIMA mock parser

```bash
ros2 launch arm_bringup full_system.launch.py llm_backend:=mock
```

### 发一条测试指令

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

> **小技巧**：把上面三行打包成 `attach_devices.bat` 放到桌面。Windows 每次重启后 USB 都需要重新 attach 到 WSL2。

---

## 开发路线

8 周冲刺，single source of truth 是 [`开发进度与待办事项.md`](开发进度与待办事项.md)。

| 周 | 目标 | 交付物 |
|---|---|---|
| **W1** | 开发环境 + 工作站 + USB 集成 | WSL2 里能遥操机械臂；相机能发布到 ROS 2；eye-to-hand 标定完成 |
| **W2** | 感知 pipeline | 文本查询 → 世界坐标 (x, y)，通过 Grounding DINO + SAM2 |
| **W3** | MoveIt2 + 硬编码原语（安全网） | 每个原语在已知坐标下成功率 ≥ 80% |
| **W4** | Teleop 数据采集 | 约 120 条 demo 推送到 HuggingFace Hub 作为公开 LeRobotDataset |
| **W5** | ACT 训练 + 真机评测 | 每个原语 50 次 rollout 的成功率表 |
| **W6** | ANIMA Tier 1 端到端 | `"把绿色海绵放进盒子"` 在真机上成功 |
| **W7** | Tier 2-3 + test-and-check 闭环 | 多步任务 + 失败恢复 demo |
| **W8** | Demo 视频 + 简历 | 简历 bullet、demo 视频、公开发布 |

### 简历对照清单

项目刻意遵循具身智能 / IL 社区的事实标准，让简历上每一行都能被业内人秒懂：

- ✅ **真机 teleop 数据采集**（LeRobot 框架）
- ✅ **LeRobotDataset 格式 + HuggingFace Hub** 数据集发布
- ✅ **ACT (Action Chunking Transformer)** 在真机数据上训练
- ✅ **真机成功率定量评测**
- ✅ **开放词汇感知**（Grounding DINO + SAM2）
- ✅ **LLM as task parser**（Claude API），不是 LLM-as-Translator
- ✅ **行为树任务执行器**（py_trees）
- ✅ **ROS 2 系统集成**（多包架构）
- ✅ **MoveIt2 运动规划**
- ✅ **Test-and-check 验证 + 失败恢复**（DIARC 风格，**核心差异化卖点**）
- ✅ **多步长时程任务规划**
- ✅ **空间推理 + LLM grounding**
- ✅ **GitHub 完全开源 + 完整文档**

v1 刻意不做的：RL、sim2real transfer、VLA 微调、真机 mobile manipulation、衣物 / 软体操作、双臂、自训练感知模型。原因详见开发计划文档。

---

## 项目沿革

- **认知层**：基于 [ANIMA_O1](https://github.com/jeffliulab/ANIMA_O1)——一个开源的家用机器人认知框架，灵感来自 [DIARC](https://hrilab.tufts.edu/)（Tufts HRI Lab，作者 2024–2025 在那里做 Research Assistant）。
- **迁移自**：[`soma_home_exp_v1`](https://github.com/jeffliulab/soma_home_exp_v1)（已归档）。最早 v1 计划是 mobile manipulation 衣物分拣机器人；2026-04-07 缩减为固定式桌面机械臂。之后不久仓库被改名/迁移到 `SmartRobotArm`，更准确反映当前阶段的范围（"智能机械臂"，而不是"完整家用机器人"）。本仓库更早的那次 commit 是无关的 SO-ARM100 + LEAP Hand + MediaPipe 早期探索，已从零重建。
- **长期愿景**：SmartRobotArm 是 SOMA Homies 家用机器人系列的**机械臂能力层**。当机械臂足够稳定后，会被集成到 mobile platform 上变成完整的 Soma Home，也就是这个家族的第一台完整机器人。

---

## 许可证

[Apache License 2.0](LICENSE)——Copyright 2026 Jeff Liu Lab（[jeffliulab.com](https://jeffliulab.com), GitHub [@jeffliulab](https://github.com/jeffliulab)）。

允许商用、私用、修改、分发，前提是保留版权和许可证声明，并标注修改内容。贡献者授予明确的专利使用权；对贡献者发起专利诉讼将自动终止你在本项目下的授权。
