# SmartRobotArm 仿真到实物：硬件 & 仿真 Q&A 指南

> ⚠️ **这份文档是从 `soma_home_exp_v1` 继承的旧版本**，描述的是带 LiDAR + 底盘的 mobile manipulator 硬件方案。
> v1 实际硬件已改为**固定式机械臂**（无底盘 / 无 LiDAR / 无 Pi 5）。
>
> 文档中关于 URDF 验证、4-DOF MoveIt2、感知模型选择、sim-to-real gap 的讨论**仍然有效**；
> 但所有底盘 / LiDAR / 多机通信相关的内容请视为 v2+ 的参考。
>
> v1 真实硬件清单见 [`../开发进度与待办事项.md`](../开发进度与待办事项.md) 中"硬件配置"一节。

---

---

## Q1: 真实硬件规格如何映射到仿真模型？URDF 够准确吗？

### 硬件到 URDF 的映射关系

| 真实硬件 | URDF 中对应的部分 | 关键参数 |
|---------|------------------|---------|
| TurtleBot3 底盘（改装） | `base_link` + 轮子 joints | 尺寸、质量、轮距、轮径 |
| Waveshare RoArm-M2-S | 4 个 revolute joints + links | 关节限位、连杆长度、质量 |
| Raspberry Pi Camera Module 3 | `camera_link` + Gazebo camera plugin | FOV、分辨率、畸变参数 |
| TurtleBot3 LiDAR | `lidar_link` + Gazebo ray plugin | 扫描范围、角分辨率、最大距离 |

### URDF 准确度核查清单

**必须精确的参数（直接影响 sim2real）：**

1. **关节限位（joint limits）**：RoArm-M2-S 每个舵机（STS3215）的实际转动范围是 0°~300°。你的 URDF 中每个 joint 的 `<limit lower="..." upper="..."/>` 必须和实际一致，否则仿真里能做到的动作现实中做不到。

2. **连杆长度（link lengths）**：总臂展 280mm，你需要从 Waveshare 官方图纸获取每段连杆的精确长度，误差应控制在 ±2mm。

3. **关节类型**：4 个 DOF 全部是 `revolute`（旋转关节），确认没有写成 `continuous` 或 `prismatic`。

4. **质量和惯性（mass & inertia）**：影响动力学仿真。RoArm-M2-S 整臂约 826g，载荷 0.5kg。每个 link 的 `<inertial>` 标签需要合理估算。

**可以近似的参数：**

- 底盘外形（用简单几何体近似）
- 摩擦系数（后续在实物上微调）
- 颜色和视觉外观

### 如何验证 URDF

```bash
# 1. 检查 URDF 语法
check_urdf robot.urdf

# 2. 可视化查看关节树
urdf_to_graphiz robot.urdf

# 3. 在 RViz2 中交互式查看
ros2 launch arm_description display.launch.py
# 拖动 joint_state_publisher_gui 的滑块，确认每个关节运动方向和范围正确
```

### 结论

对于 v1 阶段，URDF 不需要"完美"，但**关节限位和连杆长度必须准确**。其他参数可以先用估算值，到 v2 真机阶段再校准。

---

## Q2: MoveIt2 如何处理 4-DOF 机械臂？能做哪些抓取？

### 4-DOF 的本质限制

一个完整的 6-DOF 机械臂可以让末端执行器到达空间中任意位姿（position + orientation）。你的 RoArm-M2-S 只有 4-DOF，这意味着：

- **能控制的**：末端位置（x, y, z）+ 1 个姿态角（通常是 pitch 或 yaw）
- **不能控制的**：末端的另外 2 个姿态角

具体来说，你的臂大概率是这样的结构：

```
Base (yaw旋转) → Shoulder (pitch) → Elbow (pitch) → Gripper (开合)
```

这意味着**夹爪始终只能从特定角度接近物体**，不能像 6-DOF 臂那样从任意方向抓取。

### IK Solver 选择——这是关键

| Solver | 适用性 | 说明 |
|--------|-------|------|
| KDL (默认) | ⚠️ 不推荐 | KDL 对欠约束系统（<6 DOF）经常求解失败 |
| **IKFast** | ✅ 推荐 | 解析解，对 4-DOF 效果最好，但需要额外生成 |
| BioIK | ✅ 备选 | 数值优化方法，对低 DOF 友好 |
| TracIK | ⚠️ 一般 | 比 KDL 好，但不如 IKFast |

对于 4-DOF，IKFast 的 `iktype` 选择 `translation3d`（只控制位置）或 `translationdirection5d`（位置 + 接近方向）。

### 4-DOF 能做的抓取类型

| 抓取方式 | 可行性 | 说明 |
|---------|-------|------|
| 从上方垂直抓取（top-down grasp） | ✅ 最适合 | 夹爪朝下，从物体正上方抓取 |
| 从侧面水平抓取 | ⚠️ 受限 | 只能从臂展平面方向抓，不能绕到物体背面 |
| 任意角度抓取 | ❌ 不可能 | 需要 6-DOF |
| 从下方抓取 | ❌ 不可能 | 结构上做不到 |

### 抓取策略建议

```python
# 在 MoveIt2 中设置抓取姿态约束
from moveit_msgs.msg import Constraints, OrientationConstraint

# 限制夹爪始终朝下（top-down approach）
ocm = OrientationConstraint()
ocm.link_name = "gripper_link"
ocm.header.frame_id = "base_link"
ocm.orientation.x = 0.0  # 夹爪朝下
ocm.orientation.y = 1.0
ocm.orientation.z = 0.0
ocm.orientation.w = 0.0
ocm.absolute_x_axis_tolerance = 0.1
ocm.absolute_y_axis_tolerance = 0.1
ocm.absolute_z_axis_tolerance = 3.14  # 允许绕 z 轴任意旋转
```

---

## Q3: 零训练可用的预训练感知模型有哪些？怎么跑？

### 推荐模型一览

| 模型 | 用途 | 速度 (RTX 4090) | 推荐度 |
|------|------|-----------------|-------|
| YOLOv8 / YOLOv11 | 物体检测 + 分割 | ~2ms/frame | ★★★★★ |
| Grounding DINO | 开放词汇检测（文本→检测） | ~50ms/frame | ★★★★★ |
| SAM2 | 通用分割 | ~30ms/frame | ★★★★ |
| Grounded SAM2 | DINO + SAM2 组合 | ~80ms/frame | ★★★★★ |
| DepthAnything v2 | 单目深度估计 | ~15ms/frame | ★★★ |

### YOLOv8/v11 — 最简单上手

```bash
pip install ultralytics
```

```python
from ultralytics import YOLO

model = YOLO("yolo11n.pt")  # nano版，最快，自动下载
results = model("/path/to/image.jpg")

for r in results:
    for box in r.boxes:
        cls = model.names[int(box.cls)]  # 类别名 ("bottle", "cup", etc.)
        conf = float(box.conf)
        print(f"{cls}: {conf:.2f}")
```

支持 COCO 80 类家庭常见物品。不认识"袜子"、"充电线"等非 COCO 类别时，用 Grounding DINO。

### Grounding DINO — 用自然语言指定检测什么

这是 ANIMA 框架最重要的感知工具，因为 LLM 可以直接生成检测 prompt。

```python
from groundingdino.util.inference import load_model, load_image, predict

model = load_model(config_path, weights_path)
image_source, image = load_image("scene.jpg")

# 用自然语言描述要检测的物体
TEXT_PROMPT = "red sock . blue t-shirt . USB cable . storage box"

boxes, logits, phrases = predict(
    model=model, image=image, caption=TEXT_PROMPT,
    box_threshold=0.3, text_threshold=0.25
)
```

**关键优势**：不需要训练，LLM 说"找到红色袜子"，直接把 "red sock" 传给 Grounding DINO。

### 推荐的感知 Pipeline

```
Camera Image
    │
    ├─→ YOLOv8（快速检测已知物体，如 bottle, cup）
    │
    └─→ Grounding DINO + SAM2（LLM 指定的未知物体）
            │
            └─→ 物体 mask + bounding box
                    │
                    └─→ 结合深度图 → 3D 位置 → MoveIt2 抓取
```

所有模型都跑在 **PC（RTX 4090）** 上，RPi 只负责采集图像并通过 ROS 2 topic 传输。

---

## Q4: Gazebo 仿真端到端数据流是怎样的？

### 完整数据流图

```
用户指令: "把桌上的红色杯子放到储物箱里"
         │
         ▼
┌─────────────────────────────────────┐
│  ANIMA 认知框架                       │
│  ┌─────────────────────────────┐    │
│  │ LLM Parser (Claude / GPT)  │    │  ← 自然语言 → 结构化任务
│  └──────────┬──────────────────┘    │
│             ▼                       │
│  ┌─────────────────────────────┐    │
│  │ Behavior Tree Executor      │    │  ← 任务分解为子动作序列
│  │ 1. navigate_to(table)       │    │
│  │ 2. detect("red cup")       │    │
│  │ 3. pick(cup_pose)          │    │
│  │ 4. navigate_to(box)        │    │
│  │ 5. place(box_pose)         │    │
│  └──────────┬──────────────────┘    │
└─────────────┼───────────────────────┘
              │
    ┌─────────┴──────────────────────────────┐
    │                                         │
    ▼                                         ▼
┌──────────────┐                    ┌──────────────────┐
│ Nav2         │                    │ MoveIt2          │
│ 输入: 目标位姿 │                    │ 输入: 抓取位姿     │
│ 输出: cmd_vel │                    │ 输出: joint 轨迹   │
└──────┬───────┘                    └────────┬─────────┘
       │                                     │
       ▼                                     ▼
┌─────────────────────────────────────────────────────┐
│  Gazebo Simulation                                  │
│  物理引擎(ODE) + 渲染引擎 + 传感器模拟                  │
│  Camera → /camera/image_raw                         │
│  LiDAR  → /scan                                    │
└─────────────────────────────────────────────────────┘
```

### 关键 ROS 2 Topics

```bash
# 核心 topics:
/cmd_vel                    # 底盘速度指令
/scan                       # LiDAR 数据
/camera/image_raw           # 相机图像
/joint_states               # 当前关节角度
/tf                         # 坐标变换树

# 调试命令
ros2 topic list             # 查看所有 topic
ros2 topic echo /scan --once  # 查看一帧 LiDAR 数据
ros2 run rqt_image_view rqt_image_view  # 查看相机图像
ros2 run tf2_tools view_frames          # 查看 TF 树
```

---

## Q5: 仿真与真实硬件的关键差异

### 按严重程度排序

#### 1. 物理交互（最大差异）

| 方面 | Gazebo 仿真 | 真实世界 |
|------|------------|---------|
| 抓取软物体（衣物） | 物理引擎几乎无法模拟布料 | 布料变形、滑动、褶皱 |
| 摩擦力 | 简单 Coulomb 模型 | 材质相关，差异巨大 |
| 碰撞 | 刚体碰撞，计算精确 | 有弹性、不确定性 |

#### 2. 传感器噪声

| 传感器 | Gazebo | 真实 |
|--------|--------|------|
| Camera | 完美图像，无噪声 | 运动模糊、光照变化 |
| LiDAR | 精确距离 | 玻璃反射错误、噪点 |
| 关节编码器 | 精确角度 | 有误差和漂移 |

可在 Gazebo 传感器 plugin 中添加高斯噪声来缓解。

#### 3. 通信延迟

| 路径 | Gazebo | 真实 |
|------|--------|------|
| 图像传输 | 本地内存 ~0ms | Pi→PC WiFi 20-100ms |
| 控制指令 | 本地 ~0ms | PC→Pi→舵机 5-20ms |

---

## Q6: 从仿真 (v1) 到真实硬件 (v2) 的过渡路线

### 核心原则

**仿真和真机使用同一套 ROS 2 节点**，只替换最底层的硬件接口。

```
仿真: gazebo.launch.py（在 Gazebo 中生成机器人）
真机: hardware.launch.py（连接真实传感器和执行器）

Nav2、MoveIt2、ANIMA 的代码不需要改！
```

### 过渡步骤

| 步骤 | 内容 | 预估时间 |
|------|------|---------|
| 1 | RPi 5 安装 Ubuntu + ROS 2，配置相机和 LiDAR | 1 周 |
| 2 | 写 RoArm-M2-S 的 ros2_control HardwareInterface（封装舵机串口通信）| 1-2 周 |
| 3 | ROS 2 多机通信配置（PC ↔ RPi，同一 WiFi + `ROS_DOMAIN_ID`） | 2-3 天 |
| 4 | 逐个替换：先底盘动 → 加 LiDAR 导航 → 加手臂 → 加感知 | 2-3 周 |
| 5 | 调参：Nav2 速度、MoveIt2 关节限制、相机内参标定 | 持续 |

### 建议

1. **先做刚体抓取**：先抓杯子、瓶子等刚体，确认流程跑通后再尝试衣物
2. **衣物抓取是 hard problem**：考虑用简单策略（"从上方抓一把"而不是精确抓取特定部位）
3. **多录视频**：真机调试时多录像，方便回看分析问题
4. **用 ros2 bag 记录**：可以离线回放调试

```bash
ros2 bag record -a -o my_experiment_001  # 录制
ros2 bag play my_experiment_001           # 回放
```
