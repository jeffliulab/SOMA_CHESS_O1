# SOMA Chess O1 — 项目指南针

> 本文件是 Claude Code 的导航索引。内容保持简洁；细节请查阅下方对应文档。

---

## 项目简介

**SOMA Chess O1** — 语言驱动的固定桌面操作器，v1 目标：在棋盘上识别可吃的子、理解棋规、执行吃子动作。认知层 ANIMA（Claude API + py_trees + 游戏引擎）解析指令，Grounding DINO + SAM2 做视觉定位，ACT（LeRobot）执行物理动作，validator 做 test-and-check 闭环。Apache-2.0，Jeff Liu Lab。

**当前版本**: V1.01（感知基础）  
**任务清单**: [`开发进度与待办事项.md`](开发进度与待办事项.md)

---

## 快速启动

```bash
srarm   # 进入 dev 模式（cd workspace + source ROS 2 + activate .venv + source overlay）

# 机械臂遥操（当前默认）
scripts/start_teleop_wsl_gamepad.sh

# 相机 bridge（当前默认）
# Windows: scripts\bridge方案\start_camera_bridge.bat
# WSL:     scripts/start_camera_bridge_wsl.sh

# 构建
colcon build --symlink-install
```

---

## 文档导航

| 想查什么 | 文件路径 |
|---|---|
| 硬件 / 软件 / 战略决策（已锁定）| [docs/reference/locked-decisions.md](docs/reference/locked-decisions.md) |
| 机械臂协议 + ROS 2 接口 + 安全操作 | [docs/reference/机械臂技术文档.md](docs/reference/机械臂技术文档.md) |
| 硬件与仿真 FAQ | [docs/reference/FAQ-硬件与仿真.md](docs/reference/FAQ-硬件与仿真.md) |
| 相机 bridge 操作（当前方案）| [docs/setup/Windows_TCP相机桥接.md](docs/setup/Windows_TCP相机桥接.md) |
| 手柄遥操 / 自定义 WSL 内核 | [docs/setup/WSL_Xbox手柄直通.md](docs/setup/WSL_Xbox手柄直通.md) |
| 开发环境搭建（完整步骤）| [docs/setup/DEVELOPMENT.md](docs/setup/DEVELOPMENT.md) |
| V1.01 验收标准 | [docs/testing/V1.01_验收清单.md](docs/testing/V1.01_验收清单.md) |
| V1.01 测试记录模板 | [docs/testing/V1.01_测试记录模板.md](docs/testing/V1.01_测试记录模板.md) |
| 旧 Windows ROS bridge（已废弃）| [docs/legacy/Windows_ROS相机桥接.md](docs/legacy/Windows_ROS相机桥接.md) |
| 全部常用命令 | [~/SOMA/常用命令.md](../常用命令.md) |
| 当前任务清单 | [开发进度与待办事项.md](开发进度与待办事项.md) |

---

## 遥操默认流程（agent 关键路径）

1. Windows 管理员 PowerShell: `usbipd list` — **每次重启都要先查 busid**
2. 确认 RoArm 串口和 Xbox busid（busid 每次重启都可能变）
3. 若设备已 `Attached` 则无需再 attach；否则运行 `scripts\attach_devices.bat`
4. WSL: `scripts/start_teleop_wsl_gamepad.sh`
5. 等待 `Teleop target initialized from current /joint_states.`
6. 按 `Start`，确认 `Start pressed — re-enabled, going home`
7. 然后才移动摇杆

**常见误区**: `Attached` 不是错误；`\\wsl$\...` 路径只在 Windows Shell 有效，WSL 里用 `~/SOMA/...`

---

## 相机默认路径（locked 2026-04-10）

- Windows: `scripts\bridge方案\start_camera_bridge.bat`
- WSL: `scripts/start_camera_bridge_wsl.sh`
- 发布 `/camera/image_raw` + `/camera/camera_info`（1280×720 @ 30fps，bridge host `127.0.0.1:65433`）
- C922 **不走** usbipd；保留在 Windows 侧通过 TCP bridge 传图

---

## v1 不做的事（DO NOT LIST）

遇到以下建议请礼貌推回——它们是 v2+ 范围，会偏离当前 sprint：

- ❌ 完整对弈（v1 只做吃子，不做最优走法选择）— v2 范围
- ❌ 移动底盘 / Nav2 / SLAM（真机）
- ❌ 衣物 / 柔性物体 / 力反馈 / 双臂
- ❌ MuJoCo / Isaac Sim / Isaac Lab（不用于 ML 训练）
- ❌ sim2real（只用真机 teleop 数据训练 ACT）
- ❌ 强化学习 / VLA fine-tuning
- ❌ 自定义感知模型训练（Grounding DINO + SAM2 零样本）
- ❌ Pi 5 嵌入式部署（v1 全部直插 PC）

---

## 开发约定

- **语言**: 代码 / ROS 包名 / commit 消息：英文；文档 / 注释 / 对话：中文（技术术语保留英文）
- **署名**: 始终用 **Jeff Liu Lab**（不省略 "Lab"）；jeffliulab.com，GitHub @jeffliulab
- **pre-alpha**: 不加 CI、packaging、contribution guide — 增加复杂度时须有真实理由
- **开发日志**: 每次有意义的工作后更新 `~/SOMA/docs/logs/SOMA_CHESS_O1/V1.01-开发日志.md`
- **常用命令**: 工作流或启动方式有变化时同步更新 `~/SOMA/常用命令.md`
- **外部上游代码**: 不要 vendor 进本 repo（license 隔离）；放在 `~/SOMA/DRIVERS/`

**License**: Apache-2.0, Copyright 2026 Jeff Liu Lab.
