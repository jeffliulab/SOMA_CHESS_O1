# SOMA Arm — 锁定决策参考

> 本文档记录 v1 开发中所有已锁定的硬件、软件、战略决策，以及明确废弃的备选方案。
> 决策锁定日期：2026-04-07（部分更新至 2026-04-16）。
> **如需修改任何决策，请先和项目负责人确认方向变化。**

---

## 硬件决策（已锁定）

| # | 项目 | 选型 | 状态 | 理由 |
|---|---|---|---|---|
| 1 | **机械臂** | Waveshare RoArm-M2-S | ✅ 已有 | 4-DOF, ~28cm reach, ~500g payload, ESP32 + STS3215 servos, USB serial (CP2102N) |
| 2 | **臂安装方式** | C 形夹固定在工作台右侧 | ✅ | 刚性固定，eye-to-hand 标定结果跨 session 有效 |
| 3 | **相机** | Logitech C922 Pro Stream Webcam | ✅ 已有 | USB UVC, 1080p@30, ALOHA 同款，社区经验丰富，可复现性好 |
| 4 | **相机支架** | JOBY GorillaPod 柔性三脚架 | ✅ | 缠绕桌沿，~50–60cm 俯视，~60° 角，稳定固定 |
| 5 | **工作区光照** | 独立 LED 桌面台灯 | ✅ | 独立于环境光，跨 session 一致 |
| 6 | **桌面物体集** | 国际象棋棋子（标准尺寸） | ✅ 已有 | V1 目标已升级为棋子吃子；海绵块不再使用 |
| 7 | **棋盘** | 标准国际象棋棋盘 | ✅ 已有 | 棋盘格提供天然坐标系和视觉参考 |
| 8 | **背景垫** | 黑色 KT 板（A3, ~$3） | 📋 待购 | 当前木纹色桌面背景对感知模型不友好 |
| 9 | **Teleop 输入** | PDP Wired Controller for Xbox | ✅ 已有 | XInput, Linux xpad 原生支持, 4 摇杆轴 1:1 映射 4-DOF |
| 10 | **训练/推理 PC** | 工作站笔记本 + **RTX 4090 Laptop (16 GB VRAM)**, Windows 11 | ✅ 已有 | 注意：是 Laptop 16GB 版，非桌面 24GB 版（2026-04-08 修正） |
| 11 | **SBC** | v1 不使用 Pi 5 | — | 全部 USB 直插 PC，无 SBC 参与，省掉多机通信 debug |

**不在 v1 的硬件**：Pi 5 / SBC、移动底盘、LiDAR、RealSense 深度相机、力传感器、第二条机械臂 — 全部推迟到 v2+。

---

## 软件 / 开发环境决策（已锁定）

| 项目 | 选型 | 理由 |
|---|---|---|
| 宿主 OS | Windows 11 | 用户主力 OS，GPU 已知满血 |
| 开发 OS | **WSL2 + Ubuntu 22.04** | 原生 Linux for ROS 2 / LeRobot；避免双系统 GPU 性能损失 |
| GPU 接入 | **CUDA passthrough** via Windows NVIDIA driver | 用户硬件在双系统 Linux 下 GPU 性能受限；passthrough 保留 RTX 4090 Laptop 100% 性能（2026-04-08 验证 `torch.cuda.is_available()=True`） |
| USB 接入 | **分路方案**：`usbipd-win` 转发机械臂+手柄；C922 留在 Windows 侧走 TCP bridge | 避免 `usbipd + WSL MJPG` 路径的横向破图问题，不需要 Windows 侧 ROS 2 |
| ROS 2 | Humble Hawksbill (LTS) | 与 LeRobot 生态最对齐 |
| Python 环境 | **venv with `--system-site-packages`** at `~/SOMA/soma-arm/.venv/` | 不用 conda（ROS 2 + conda 有路径/解释器 bug）；`--system-site-packages` 让 venv 能 import 系统 `rclpy` |
| 模仿学习 | **LeRobot + ACT** | HuggingFace 生态，数据集发布到 HF Hub |
| 认知层 | **ANIMA**（LLM-as-Parser, py_trees BT, test-and-check validator） | 项目差异化核心；使用 Claude API |
| 感知 | **Grounding DINO + SAM2**（open-vocab, pretrained） | 零样本，v1 不做感知模型训练 |
| 运动规划 | **MoveIt2**（4-DOF, IKFast/BioIK） | 硬编码原语安全网 |
| ANIMA 位置 | **独立 Python 库** `~/SOMA/anima/`，`pip install -e` 接入 | 不是 soma-arm 的子文件夹；保持机器人无关性；两个 repo = 更强的 portfolio 叙事 |

---

## 软件栈与数据流

| 模块 | 组件 | 运行位置 |
|---|---|---|
| 认知 | ANIMA LLM-as-Parser (Claude API) + py_trees + validator | WSL2 (4090 PC) |
| 感知 | Grounding DINO + SAM2 + 像素→世界坐标 | WSL2 (4090 PC) |
| 运动规划 | MoveIt2 (4-DOF, IKFast/BioIK) | WSL2 (4090 PC) |
| 学习策略 | LeRobot ACT (per-primitive model 或 multi-task) | WSL2 (4090 PC)；推理直接通过 USB 串口下发关节指令 |
| 硬件驱动 | 自写薄层 Python driver，封装 Waveshare 串口协议（~200 行） | WSL2 (USB serial 直连) |
| 数据采集 | LeRobot teleop pipeline + PDP Xbox 手柄 | WSL2 (4090 PC) |
| 数据集 | LeRobotDataset 格式，发布到 HuggingFace Hub | HF Hub（公共 artifact） |
| 仿真 | Gazebo — 仅 URDF 验证 + ANIMA dry-run；**不用于 ML 训练** | WSL2 (4090 PC) |

---

## ACT 技能原语

ACT 学习的原子技能，作为 ANIMA 行为树的叶节点。

| Primitive | 输入 | 动作 | 4-DOF 可行性 | 优先级 |
|---|---|---|---|---|
| `chess_pick(square)` | 棋盘格坐标 → 世界坐标 | top-down 抓取棋子 | ✅ | **核心** |
| `chess_place(square)` | 目标棋盘格坐标 | 将棋子放到指定格子 | ✅ | **核心** |

ACT 训练目标（V1.02）：`act_chess_pick` / `act_chess_place` 两个检查点。

---

## 任务分级

ANIMA 在 ACT 原语之上编排不同复杂度的任务。

| Tier | 说明 | 示例 |
|---|---|---|
| **Tier 1** | 单步棋子操作 | "Pick up the pawn on e4." |
| **Tier 2** | 吃子操作（两步）| "Capture: move captured piece off board, then move capturing piece to target square." |
| **Tier 3** | 引擎驱动吃子（感知+推理+执行）| 识别棋盘 → 查询引擎可吃的子 → 执行吃子 |
| **Tier 4** | Test-and-check + 失败恢复（视觉验证闭环）| 吃子后视觉验证棋盘状态 → 成功 / 重试 / 报告 |

Tier 4 是项目核心差异化卖点——业内几乎没有 LLM-robot demo 在做 test-and-check 验证闭环。

---

## 游戏引擎框架（2026-04-16 新增）

| 项目 | 决定 | 理由 |
|---|---|---|
| 框架位置 | `~/SOMA/anima/` 内作为子模块 | ANIMA 保持机器人无关性；引擎是认知层的一部分 |
| 接口抽象 | `GameEngine.legal_moves(board_state) → List[Move]` | ANIMA 不关心具体棋类规则，只调用引擎接口 |
| 第一个插件 | 国际象棋（可用 python-chess 库） | 项目名就叫 Chess O1 |
| 可扩展性 | 每种棋类一个 engine 插件（围棋/中国象棋/将棋/麻将等） | 用户长期愿景：通用桌游机器人 |

---

## 战略范围决策

| 决策项 | 决定 | 理由 |
|---|---|---|
| 机器人形态 | **固定桌面操作器** | 不做 mobile；ALOHA / RT-1 / OpenVLA / LeRobot 全部从固定站起步 |
| 任务域 | **棋盘上识别可吃的子 + 理解棋规 + 执行吃子** | 不需要完整对弈；不做衣物/柔性物体 |
| 仿真使用 | **Gazebo 仅 URDF 验证 + ANIMA dry-run** | 不用于 ML 训练；ACT 只训真机 teleop 数据 |
| 训练方式 | **真机 teleop only** | 无 sim2real，无 RL，无 VLA fine-tuning（v1） |
| v1/v2 边界 | v1（本仓库）= 棋子吃子（识别+规则+执行）；v2 = 完整对弈 + 多棋类 | v1 不需要完整对弈；v2 加 Stockfish/Claude 选最优走法 |
| ANIMA 位置 | 独立子模块 `~/SOMA/anima/` | 保持机器人无关性，两个公开 repo = 更强 portfolio 叙事 |

---

## 已废弃备选（不要再提出）

| 备选 | 废弃原因 |
|---|---|
| ~~SpaceMouse Compact~~ | 6-DOF 输入浪费 2 轴；PDP 手柄 4 摇杆 1:1 匹配 4-DOF |
| ~~Pi Camera Module 3~~ | CSI 接口必须经过 Pi + WiFi；libcamera 不在 LeRobot 工具链；auto-WB 锁起来麻烦 |
| ~~Intel RealSense D435~~ | 俯视固定相机 + 已知桌面 = 深度信息冗余；多花 $200 买用不到的功能 |
| ~~双系统 Ubuntu~~ | 用户硬件双系统 GPU 性能受限；WSL2 CUDA passthrough 100% 无损 |
| ~~conda~~ | ROS 2 + conda 有路径/解释器 bug |
| ~~MuJoCo / Isaac Sim / Isaac Lab~~ | v1 不做仿真训练 |
| ~~Mobile manipulation 真机~~ | 集成成本数月；IL/ACT 范式全部从固定站起步 |
| ~~衣物 / cloth manipulation~~ | 需要 ALOHA 级双臂 + 力反馈 + Isaac Sim 布料物理 |
| ~~强化学习~~ | ACT/IL 路线不用 RL |
| ~~自定义感知模型训练~~ | Grounding DINO + SAM2 零样本，v1 不训感知模型 |
| ~~Gazebo mobile manipulation 仿真~~ | v1 sprint 时间紧，仿真不出现在 demo 视频 |
| ~~ANIMA 放进 soma-arm 子文件夹~~ | 破坏框架的机器人无关性 |

---

## 风险与缓解

| 风险 | 缓解措施 |
|---|---|
| RoArm-M2-S 精度低（hobby 舵机 ~1-2mm 重复定位） | 棋子尺寸适中，保守抓取，仅 top-down |
| RoArm-M2-S 没有官方 ROS 2 驱动 | 自写薄层 Python driver（< 200 行），已完成 |
| ACT 从 teleop 数据迁移到自主执行效果差 | 采更多 demo，提升 teleop 质量；demo 时可 fallback 到硬编码 MoveIt2 原语 |
| LLM parser 产生非法 TaskSpec | ANIMA validator 捕获 + 重试；Claude constrained generation |
| 物理工作区可达性不足 | Week 1 早期验证（W1.8），必要时调整物体位置或臂安装方式 |
| 光照变化破坏感知 | 漫射光源 + 固定白平衡；在不同光照条件下测试 |

---

## 推迟决定

| 决策项 | 推迟到 |
|---|---|
| VLA fine-tuning 对照（SmolVLA / OpenVLA）| Week 8，视进度决定 |
| 背景垫具体颜色（黑色 vs 深绿 vs 深蓝 KT 板） | 购买时挑现货 |
| 操作员仪表盘整合（所有 viz 拼成一个 .rviz layout） | V1.02+ |
