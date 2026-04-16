# SOMA Chess O1 — 系统架构与开发环境

> 本文档描述 v1（固定桌面操作器）的系统架构、硬件拓扑和开发环境配置。
> 决策理由详见 [docs/reference/locked-decisions.md](../reference/locked-decisions.md)。

---

## v1 系统架构

```
                    User natural language instruction
                                  │
                                  ▼
                    ┌──────────────────────────┐
                    │  ANIMA: LLM Parser       │  Claude API
                    │  → structured TaskSpec   │
                    └──────────────┬───────────┘
                                   │
                                   ▼
                    ┌──────────────────────────┐
                    │  Grounding DINO + SAM2   │  → object detection by language
                    │  pixel → world coords    │  ("find the red block")
                    └──────────────┬───────────┘
                                   │
                                   ▼
                    ┌──────────────────────────┐
                    │  ANIMA Behavior Tree     │  py_trees
                    │  + Skill Dispatcher      │
                    └──────────────┬───────────┘
                                   │
                                   ▼
                    ┌──────────────────────────┐
                    │  ACT Policy (trained on  │  LeRobot
                    │  teleop demos)           │
                    │  → RoArm-M2-S            │
                    └──────────────┬───────────┘
                                   │
                                   ▼
                    ┌──────────────────────────┐
                    │  ANIMA Validator         │  test-and-check via vision
                    │  (vision-based)          │  → success / retry / report
                    └──────────────────────────┘
```

**架构关键点**：
- **ANIMA = 主角**：LLM-as-Parser 解析意图，py_trees 行为树编排，validator 做 test-and-check（视觉验证闭环）
- **ACT = 低层 API**：每个原语是独立 ACT policy，对外暴露成"函数调用"
- **Grounding DINO + SAM2 = 感知桥梁**：将自然语言短语转为像素 → 世界坐标
- **MoveIt2 兜底**：即便 ACT 训练失败，硬编码 IK 原语仍可跑 demo

---

## 硬件拓扑

```
┌──────────────────────────────────┐
│  Workstation (Windows 11 + WSL2) │
│  ├─ ROS 2 Humble (Ubuntu 22.04)  │
│  ├─ LeRobot + PyTorch + CUDA     │
│  │   → RTX 4090 Laptop 16GB      │
│  │     (CUDA passthrough)        │
│  ├─ ANIMA + Claude API client    │
│  └─ MoveIt2 / py_trees           │
│         │                         │
│         │ USB / localhost         │
│         ├──────────────────────── │
│  ┌─────────────────────────────┐ │
│  │  Logitech C922 Pro          │ │  ← 头顶 ~60cm, ~60° 俯视
│  │  Windows 原生取图 → TCP     │ │    /camera/image_raw
│  └─────────────────────────────┘ │
│  ┌─────────────────────────────┐ │
│  │  RoArm-M2-S                 │ │  ← 桌沿 C 形夹固定
│  │  usbipd → /dev/ttyUSB*      │ │    /joint_states, /joint_command
│  └─────────────────────────────┘ │
│  ┌─────────────────────────────┐ │
│  │  PDP Xbox Controller        │ │  ← usbipd → /dev/input/event*
│  └─────────────────────────────┘ │
└──────────────────────────────────┘
```

---

## 开发环境配置

### 版本信息

| 项目 | 配置 |
|---|---|
| 宿主系统 | Windows 11 |
| 开发系统 | WSL2 + Ubuntu 22.04 |
| GPU 接入 | CUDA passthrough，RTX 4090 Laptop 16GB，性能 100% 无损 |
| USB 接入 | usbipd-win（机械臂 + 手柄） + TCP bridge（相机） |
| ROS 2 | Humble Hawksbill (LTS) |
| Python | 3.10（Ubuntu 22.04 默认） |
| ML 栈 | PyTorch (CUDA 12.4) + LeRobot + HuggingFace |
| 图形 | WSLg（Gazebo / RViz2 稍慢但可用） |

### 一次性配置（W1.0，已完成）

```powershell
# Windows PowerShell (管理员)
wsl --install -d Ubuntu-22.04
wsl --update
winget install --interactive --exact dorssel.usbipd-win
```

```bash
# WSL2 Ubuntu 22.04
# CUDA toolkit（不装 nvidia-driver，Windows 已有）
wget https://developer.download.nvidia.com/compute/cuda/repos/wsl-ubuntu/x86_64/cuda-keyring_1.1-1_all.deb
sudo dpkg -i cuda-keyring_1.1-1_all.deb && sudo apt update
sudo apt install -y cuda-toolkit-12-4
nvidia-smi   # 应显示 RTX 4090

# ROS 2 Humble
sudo apt install -y software-properties-common curl
sudo add-apt-repository universe
sudo curl -sSL https://raw.githubusercontent.com/ros/rosdistro/master/ros.key \
  -o /usr/share/keyrings/ros-archive-keyring.gpg
echo "deb [arch=$(dpkg --print-architecture) signed-by=/usr/share/keyrings/ros-archive-keyring.gpg] \
  http://packages.ros.org/ros2/ubuntu $(. /etc/os-release && echo $UBUNTU_CODENAME) main" | \
  sudo tee /etc/apt/sources.list.d/ros2.list > /dev/null
sudo apt update && sudo apt install -y ros-humble-desktop python3-rosdep python3-colcon-common-extensions
sudo apt install -y ros-humble-moveit
sudo apt install --only-upgrade ros-humble-ompl  # 必须升到 1.7.0，否则 move_group segfault

# Python venv（--system-site-packages 让 venv 能 import 系统 rclpy）
cd ~/SOMA/SOMA_CHESS_O1
python3 -m venv --system-site-packages .venv
source .venv/bin/activate
pip install lerobot pygame pyserial
```

```bash
# ~/.bashrc 添加 srarm 函数
srarm() {
  cd ~/SOMA/SOMA_CHESS_O1
  source /opt/ros/humble/setup.bash
  source .venv/bin/activate
  [ -f install/setup.bash ] && source install/setup.bash
}
```

### USB 转发（每次 Windows 重启后）

```powershell
# Windows PowerShell (管理员)
usbipd list                                    # 永远先查当前 busid
usbipd attach --wsl --busid <ROARM_BUSID>     # busid 每次重启都可能变
usbipd attach --wsl --busid <XBOX_BUSID>
# C922 不 attach，保留在 Windows 侧走 TCP bridge
```

---

## ROS 2 包结构

```
src/
├── anima_node/       # ANIMA 认知层 ROS 2 wrapper（legacy from soma_home_exp_v1）
├── arm_description/  # RoArm-M2-S URDF + Gazebo 验证场景
├── arm_bringup/      # 顶层 launch 文件
├── arm_driver/       # ★ RoArm-M2-S USB 串口驱动 + MoveIt2 bridge
├── arm_teleop/       # ★ PDP Xbox 手柄遥操节点
├── arm_interfaces/   # 自定义 ROS 2 消息/服务（FindObject.srv, PerceptionFeedback.msg）
└── arm_perception/   # ★ Grounding DINO + SAM2 感知节点，/find_object service
```

V1.02+ 新增：
- `arm_manipulation/` — MoveIt2 config + hardcoded pick/place/push 原语

---

## 外部上游工作空间

`~/SOMA/DRIVERS/roarm_ws_em0/`（Waveshare 官方 ROS 2 + MoveIt2 config）保存在 gitignored 目录，不进公开 repo（license 隔离）。

MoveIt2 sidecar 模式时，需要先在另一个终端里：
```bash
source ~/SOMA/DRIVERS/roarm_ws_em0/install/setup.bash
ros2 launch roarm_moveit interact.launch.py
```
