# SmartRobotArm — 开发指南

> ⚠️ **这份文档是从 `soma_home_exp_v1` 继承的旧版本**，描述的是 **mobile manipulation + Nav2 + SLAM** 路线。
> v1 实际计划已改为**固定式桌面机械臂**（不做 mobile / 不做 Nav2 / 不做 SLAM）。
>
> **真正的执行计划**请看 [`../开发进度与待办事项.md`](../开发进度与待办事项.md)（8 周冲刺，是 single source of truth）。
> 本文档保留是因为 ROS 2 安装、URDF 验证、Gazebo 启动这些基础内容仍然有用，但请把所有 mobile / SLAM / Nav2 相关的章节当作 v2+ 的参考。
>
> 写给从未搭建过 ROS 2 项目的你。每个阶段都建立在前一阶段的基础上，请不要跳过任何阶段。

---

## 阶段 0：环境搭建（第 1 天）

### 安装 ROS 2 Humble

```bash
# 仅支持 Ubuntu 22.04
sudo apt update && sudo apt install -y locales
sudo locale-gen en_US en_US.UTF-8

sudo apt install -y software-properties-common
sudo add-apt-repository universe
sudo apt update && sudo apt install -y curl
sudo curl -sSL https://raw.githubusercontent.com/ros/rosdistro/master/ros.key \
  -o /usr/share/keyrings/ros-archive-keyring.gpg
echo "deb [arch=$(dpkg --print-architecture) signed-by=/usr/share/keyrings/ros-archive-keyring.gpg] \
  http://packages.ros.org/ros2/ubuntu $(. /etc/os-release && echo $UBUNTU_CODENAME) main" | \
  sudo tee /etc/apt/sources.list.d/ros2.list > /dev/null

sudo apt update
sudo apt install -y ros-humble-desktop
```

### 安装 Gazebo + Bridge

```bash
# Gazebo Harmonic（推荐）或 Fortress
sudo apt install -y ros-humble-ros-gz
# 或者安装 Gazebo Classic：
sudo apt install -y ros-humble-gazebo-ros-pkgs
```

### 安装 MoveIt2 和 Nav2

```bash
sudo apt install -y ros-humble-moveit ros-humble-nav2-bringup ros-humble-navigation2
sudo apt install -y ros-humble-robot-state-publisher ros-humble-joint-state-publisher-gui
sudo apt install -y ros-humble-xacro ros-humble-controller-manager
sudo apt install -y ros-humble-ros2-control ros-humble-ros2-controllers
sudo apt install -y ros-humble-diff-drive-controller
```

### 安装 Python 依赖

```bash
pip install torch torchvision --index-url https://download.pytorch.org/whl/cu118
pip install transformers  # 用于感知模型
pip install anthropic     # 或 openai，用于调用 LLM API
pip install py_trees      # 行为树库
pip install py_trees_ros  # ROS 2 行为树集成
```

### 构建工作空间

```bash
cd /path/to/soma_home_exp_v1
colcon build --symlink-install
source install/setup.bash

# 添加到 bashrc，这样每次打开终端都会自动加载
echo "source /path/to/soma_home_exp_v1/install/setup.bash" >> ~/.bashrc
```

---

## 阶段 1：在 Gazebo 中搭建机器人模型（第 1-2 周）

### 这个阶段要做什么

创建一个 URDF 机器人模型（自定义底盘 + RoArm-M2-S 机械臂 + 摄像头 + LiDAR），让它能在 Gazebo 中加载，并在 RViz 中可视化查看。

### 具体步骤

#### 1.1 创建 URDF 模型

机器人由以下组件构成：
```
soma_robot
├── base_link（底盘主体：300×250×150mm 铝合金箱体）
├── left_wheel（圆柱体，差速驱动左轮）
├── right_wheel（圆柱体，差速驱动右轮）
├── caster_wheel（万向轮，球体）
├── lidar_link（RPLiDAR A1，安装在顶部）
├── camera_link（RPi Camera Module 3，安装在顶部支架上）
└── arm_base_link（RoArm-M2-S 安装点）
    ├── arm_shoulder_link（关节1：360° 旋转）
    ├── arm_upper_link（关节2：肩部俯仰）
    ├── arm_forearm_link（关节3：肘部俯仰）
    └── arm_gripper_link（关节4：夹爪开合）
```

URDF 文件位于 `src/arm_description/urdf/soma_robot.urdf.xacro`。

关键尺寸（来自 RoArm-M2-S 规格书）：
- 机械臂底座宽度：约 87×91mm
- 机械臂水平伸展范围：约 280mm
- 机械臂重量：约 826g
- 底盘尺寸：约 300×250×150mm（自定义，可根据需要调整）
- 轮子直径：约 65mm（与 TurtleBot3 级别的电机匹配）

#### 1.2 添加 Gazebo 插件

URDF 中需要配置以下 Gazebo 插件：
- `diff_drive`：让轮子响应 `/cmd_vel` 速度指令
- `ray_sensor`（或 `gpu_ray`）：模拟 LiDAR 传感器 → 发布 `/scan` 话题
- `camera`：模拟 RGB 摄像头 → 发布 `/camera/image_raw` 话题
- `joint_state_publisher`：发布机械臂关节状态

#### 1.3 在 RViz 中验证

```bash
ros2 launch arm_description display.launch.py
# 你应该能在 RViz 中看到机器人模型，并且可以通过滑块控制关节运动
```

#### 1.4 在 Gazebo 中加载

```bash
ros2 launch arm_description gazebo.launch.py
# 机器人应该出现在 Gazebo 中，轮子应该能响应以下命令：
ros2 topic pub /cmd_vel geometry_msgs/msg/Twist "{linear: {x: 0.2}, angular: {z: 0.0}}"
```

### 里程碑清单

- [ ] 机器人在 RViz 中可见，TF 树正确
- [ ] 机器人能在 Gazebo 中成功加载
- [ ] 轮子能响应 `/cmd_vel` 指令
- [ ] LiDAR 发布 `/scan` 话题（可在 RViz 中查看）
- [ ] 摄像头发布 `/camera/image_raw` 话题
- [ ] 机械臂关节可通过 `joint_state_publisher_gui` 控制

---

## 阶段 2：使用 Nav2 实现自主导航（第 3-4 周）

### 这个阶段要做什么

让机器人能在模拟的家庭环境中利用 LiDAR SLAM 实现自主导航。

### 具体步骤

#### 2.1 创建家庭环境

在 Gazebo 中使用 SDF 格式搭建一个简单的家庭场景：
- 1-2 个带墙壁的房间（客厅 + 走廊）
- 一张桌子，上面放一些物体
- 地上放一个收纳箱/盒子
- 基础家具（沙发、架子）作为障碍物

先从简单的开始！用方块代替家具完全没问题，逼真的外观以后再加。

#### 2.2 SLAM 建图

```bash
# 启动仿真环境 + SLAM
ros2 launch arm_navigation slam.launch.py

# 在另一个终端中，通过键盘遥控机器人来建图
ros2 run teleop_twist_keyboard teleop_twist_keyboard

# 保存地图
ros2 run nav2_map_server map_saver_cli -f maps/home_map
```

#### 2.3 自主导航

```bash
# 使用保存的地图启动仿真环境 + Nav2
ros2 launch arm_navigation navigation.launch.py map:=maps/home_map.yaml

# 在 RViz 中，使用 "2D Goal Pose" 工具来设定导航目标点
# 或者通过命令行发送目标：
ros2 action send_goal /navigate_to_pose nav2_msgs/action/NavigateToPose \
  "{pose: {pose: {position: {x: 2.0, y: 1.0}}}}"
```

### 里程碑清单

- [ ] 家庭场景在 Gazebo 中正常加载
- [ ] SLAM 成功生成环境地图
- [ ] 机器人能无碰撞地导航到目标位置
- [ ] 恢复行为正常工作（卡住时能自动旋转、后退）

---

## 阶段 3：使用 MoveIt2 实现抓取和放置（第 5-6 周）

### 这个阶段要做什么

让机械臂能从已知位置抓起一个物体，再放到另一个位置。

### 理解整体思路

对于一个 4 自由度（4-DOF）机械臂，我们使用**经典逆运动学**（IK）来计算，而不是学习策略：

```
目标物体位置 (x, y, z)
        |
        v
    IK 求解器（KDL / 解析法）
        |
        v
    关节角度 [q1, q2, q3, q4]
        |
        v
    MoveIt2 轨迹规划
        |
        v
    执行轨迹（避免碰撞）
        |
        v
    闭合夹爪
```

不需要任何训练数据。MoveIt2 通过解析方式计算关节角度。

### 具体步骤

#### 3.1 配置 MoveIt2

使用 MoveIt Setup Assistant 生成 MoveIt2 配置：
```bash
ros2 launch moveit_setup_assistant setup_assistant.launch.py
```

或者手动为 4-DOF 机械臂创建 SRDF 和 kinematics.yaml 配置文件。

关键配置项：
- 规划组：`arm`（关节 1-3）+ `gripper`（关节 4）
- IK 求解器：KDLKinematicsPlugin 或解析求解器
- 规划管线：OMPL（默认）

#### 3.2 编写基础抓放脚本

```python
# 抓取和放置的伪代码
def pick_and_place(object_pose, place_pose):
    # 1. 将机械臂移动到物体上方
    arm.go_to_pose(pre_grasp_pose(object_pose))

    # 2. 下降到物体位置
    arm.go_to_pose(object_pose)

    # 3. 闭合夹爪
    gripper.close()

    # 4. 抬起
    arm.go_to_pose(pre_grasp_pose(object_pose))

    # 5. 移动到放置位置上方
    arm.go_to_pose(pre_grasp_pose(place_pose))

    # 6. 下降并松开
    arm.go_to_pose(place_pose)
    gripper.open()
```

#### 3.3 在 Gazebo 中测试

- 在桌面上放置一个小物体（圆柱体/方块）
- 使用硬编码的位置坐标运行抓放程序
- 验证夹爪能正确抓取和释放物体

### 4-DOF 的局限性

由于只有 4 个自由度，机械臂**无法**实现任意的末端执行器姿态。
抓取方式仅限于**从上方垂直抓取**（夹爪竖直朝下）。
对于从平面上抓取物体来说，这已经足够了。

### 里程碑清单

- [ ] MoveIt2 能为机械臂规划有效的运动轨迹
- [ ] 机械臂在 Gazebo 中能移动到目标位姿
- [ ] 夹爪能正常开合
- [ ] 使用硬编码位姿的抓放流程能正常运行
- [ ] 运动过程中不发生自碰撞

---

## 阶段 4：感知流水线（第 7 周）

### 这个阶段要做什么

从摄像头图像中检测物体，获取它们的 3D 位置，并提供给操控模块使用。

### 方案：使用预训练模型（无需训练）

```
摄像头 RGB 图像（/camera/image_raw）
        |
        v
    Grounding DINO（零样本检测）
    输入：图像 + 文本提示，如 "pen, remote, toy"
    输出：边界框 + 标签
        |
        v
    深度估计（使用 Gazebo 提供的真值或单目深度估计）
    2D 边界框 → 摄像头坐标系下的 3D 位置
        |
        v
    TF2 坐标变换：camera_frame → base_link 坐标系
        |
        v
    发布话题：/detections（Detection3DArray）
```

### 在仿真环境中

Gazebo 可以直接提供**物体位置的真值**——你可以通过 Gazebo 的话题/服务直接读取。这让阶段 4 在仿真中变得简单很多：

```
方案 A（快速测试操控 + ANIMA 用）：
  直接使用 Gazebo 的真值位姿 → 跳过感知模块

方案 B（测试完整流水线用）：
  使用摄像头图像 → 运行实际的检测模型 → 获取 3D 位姿
```

建议：先用方案 A 跑通，之后再加方案 B。

### 里程碑清单

- [ ] 可以通过 ROS 2 获取 Gazebo 中物体的真值位姿
- [ ] （可选）YOLO/DINO 检测模型能在摄像头图像上运行
- [ ] 物体的 3D 位置发布到 `/detections` 话题
- [ ] TF 坐标变换正确：物体在 base_link 坐标系下的位置准确

---

## 阶段 5：ANIMA 认知框架（第 8-9 周）

### 这个阶段要做什么

搭建机器人的"大脑"——理解自然语言指令，并协调导航与操控模块完成任务。

### 架构概览

```
用户："把红色的笔捡起来放到盒子里"
                |
                v
    ┌─────────────────────────┐
    │  第 1 层：NLU（LLM）       │
    │  "红色的笔" → 目标物体    │
    │  "盒子" → 目标位置        │
    │  → TaskSpec JSON          │
    └────────────┬────────────┘
                 v
    ┌─────────────────────────┐
    │  第 2 层：任务规划器       │
    │  TaskSpec → BehaviorTree │
    │  执行序列：               │
    │   1. detect("red pen")   │
    │   2. navigate_to(pen)    │
    │   3. pick(pen)           │
    │   4. navigate_to(box)    │
    │   5. place(pen, box)     │
    └────────────┬────────────┘
                 v
    ┌─────────────────────────┐
    │  第 3 层：技能执行器       │
    │  每个技能 = 一个 ROS 2    │
    │  Action Client 调用      │
    │  detect → /detect_object │
    │  navigate → /navigate..  │
    │  pick → /pick_object     │
    │  place → /place_object   │
    └─────────────────────────┘
```

### 具体实现

#### 5.1 TaskSpec 格式

```json
{
  "task": "pick_and_place",
  "target": {
    "object": "red pen",
    "description": "a red pen on the table"
  },
  "destination": {
    "location": "box",
    "description": "the storage box on the floor"
  },
  "constraints": []
}
```

#### 5.2 LLM 解析器（第 1 层）

调用 Claude/GPT API，通过系统提示词让 LLM 输出 TaskSpec JSON。
无需训练——纯粹的提示词工程。

#### 5.3 行为树（第 2 层）

使用 `py_trees` 根据 TaskSpec 动态构建行为树。
每个叶子节点对应一个 ROS 2 Action Client。

#### 5.4 技能注册表（第 3 层）

```python
SKILLS = {
    "detect_object":  DetectObjectSkill,   # 调用感知模块
    "navigate_to":    NavigateToSkill,      # 调用 Nav2
    "pick_object":    PickObjectSkill,      # 调用 MoveIt2
    "place_object":   PlaceObjectSkill,     # 调用 MoveIt2
    "say":            SpeakSkill,           # 语音合成或文本输出
}
```

### 里程碑清单

- [ ] LLM 能将自然语言解析为有效的 TaskSpec JSON
- [ ] 能根据 TaskSpec 生成行为树
- [ ] 各技能能正确调用对应的 ROS 2 Action
- [ ] 完整链路跑通：文本指令 → 导航 → 抓取 → 放置

---

## 阶段 6：完整系统演示（第 10 周）

### 这个阶段要做什么

端到端演示：输入一条语音/文字指令 → 机器人自主导航、抓取物体并送达目标位置。

### 演示场景

1. **基础场景**："把桌上的笔捡起来放到盒子里"
2. **多物体场景**："把桌子收拾干净"（检测所有物体，分类，分别归位）
3. **对话场景**："桌子上有什么？" → 机器人汇报 → "把红色的那个拿过来"

### 录制演示

```bash
# 录制 RViz + Gazebo 画面作为演示视频
# 使用 ros2 bag 记录数据日志
ros2 bag record -a -o demo_recording
```

### 里程碑清单

- [ ] 3 个演示场景全部端到端跑通
- [ ] 在仿真（受控环境）中成功率 > 80%
- [ ] 演示视频已录制
- [ ] 系统能连续运行 10 分钟以上不崩溃

---

## 常见问题排查

### 常见问题一览

| 问题 | 解决方案 |
|------|----------|
| Gazebo 启动时崩溃 | 检查 GPU 驱动：`nvidia-smi`。如果不行，使用 `LIBGL_ALWAYS_SOFTWARE=1` 作为临时方案 |
| 机器人穿过地板掉下去 | 检查 URDF 中的碰撞几何体。增大 `<mu>` 摩擦力参数 |
| 机械臂抖动/震荡 | 调整 ros2_control 配置中的 PID 增益参数。降低 `<max_effort>` 值 |
| Nav2 无法启动 | 确认地图文件、`base_link→odom` TF 变换和 `/scan` 话题都存在 |
| MoveIt2 报 "no IK solution" | 4-DOF 机械臂工作空间有限，检查目标位姿是否在可达范围内 |
| LLM 返回的 JSON 格式不对 | 在提示词中加入 JSON Schema。如果 API 支持，使用 `response_format: json` |

### 常用调试命令

```bash
# 查看所有话题
ros2 topic list

# 查看 TF 坐标树
ros2 run tf2_tools view_frames

# 查看某个话题的数据（只看一条）
ros2 topic echo /scan --once

# 查看节点连接图
ros2 run rqt_graph rqt_graph
```
