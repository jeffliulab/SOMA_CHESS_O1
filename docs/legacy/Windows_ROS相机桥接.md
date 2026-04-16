# Windows ROS 相机桥接

> 这份文档现在保留作备选探索路径，不是当前默认方案。  
> 当前默认方案请看 [Windows_TCP相机桥接.md](Windows_TCP相机桥接.md)。

> 2026-04-10 起，C922 的正式路线改为：Windows 原生取图 -> Windows ROS 2 发布 -> WSL 订阅。  
> 不再把 C922 作为默认工作流直接 `usbipd attach` 到 WSL。

## 为什么改路线

- C922 在 Windows Camera 里画面正常，说明硬件本体没问题。
- 同一台相机一旦走 `usbipd + WSL + UVC/MJPG`，在 `MJPG` 路径下会出现横向破图 / 帧损坏。
- 机械臂和手柄继续直通 WSL 没问题，但相机更适合留在 Windows 原生采集。

## Windows 侧前置条件

- 已安装 **ROS 2 Humble for Windows**
- Windows Python 里能导入：
  - `rclpy`
  - `sensor_msgs`
  - `cv2`
- 当前机器继续使用 **WSL mirrored networking**
- Windows 和 WSL 保持同一套 ROS 配置：
  - `ROS_DOMAIN_ID` 相同
  - `RMW_IMPLEMENTATION=rmw_fastrtps_cpp`
  - 不启用 `ROS_LOCALHOST_ONLY=1`

## 先做一次 ROS 通信冒烟

先确认 Windows ROS 节点和 WSL ROS 节点能互相发现，再上相机。

Windows 终端：

```bat
call C:\dev\ros2_humble\local_setup.bat
set ROS_DOMAIN_ID=0
set RMW_IMPLEMENTATION=rmw_fastrtps_cpp
set ROS_LOCALHOST_ONLY=
ros2 run demo_nodes_cpp talker
```

WSL 终端：

```bash
srarm
export ROS_DOMAIN_ID=0
export RMW_IMPLEMENTATION=rmw_fastrtps_cpp
unset ROS_LOCALHOST_ONLY
ros2 run demo_nodes_cpp listener
```

如果 listener 能收到 Windows 侧消息，说明 DDS 发现已经通了。

## 启动 Windows 相机发布节点

### 推荐方式

在 Windows 里直接运行：

```bat
scripts\bridge方案\start_camera_ros_publisher.bat
```

默认行为：

- 设备：`device_index=0`
- 图像：`1280x720 @ 30fps`
- ROS 图像话题：`/camera/image_raw`
- 相机信息话题：`/camera/camera_info`
- `frame_id=camera_optical_frame`
- 先尝试 `MSMF`，如果打开失败再 fallback 到 `DSHOW`
- 默认请求本地 `MJPG`，但会在 **Windows 本地先解码**，再发布 ROS 原始图像

### 常见自定义

显式改成 `DSHOW`：

```bat
scripts\bridge方案\start_camera_ros_publisher.bat --backend dshow
```

切到 `1080p30`：

```bat
scripts\bridge方案\start_camera_ros_publisher.bat --width 1920 --height 1080 --fps 30
```

## WSL 侧怎么验证

终端 A：

```bash
srarm
export ROS_DOMAIN_ID=0
export RMW_IMPLEMENTATION=rmw_fastrtps_cpp
unset ROS_LOCALHOST_ONLY
ros2 topic list | rg /camera
```

终端 B：

```bash
srarm
export ROS_DOMAIN_ID=0
export RMW_IMPLEMENTATION=rmw_fastrtps_cpp
unset ROS_LOCALHOST_ONLY
ros2 run rqt_image_view rqt_image_view
```

在 `rqt_image_view` 里选择：

- `/camera/image_raw`

如果想看频率：

```bash
srarm
export ROS_DOMAIN_ID=0
export RMW_IMPLEMENTATION=rmw_fastrtps_cpp
unset ROS_LOCALHOST_ONLY
ros2 topic hz /camera/image_raw
```

如果想继续确认“横向破图是不是还在原始图像里”，继续用：

```bash
srarm
export ROS_DOMAIN_ID=0
export RMW_IMPLEMENTATION=rmw_fastrtps_cpp
unset ROS_LOCALHOST_ONLY
python3 scripts/save_ros_image_frames.py --topic /camera/image_raw --count 10 --skip 10
```

输出目录默认在：

- `tmp/ros_camera_frames/`

## 现在什么不该做

- 不要把 C922 继续当成默认设备 attach 到 WSL。
- 不要再把 `camera_usb.launch.py` 当正式相机主路线；它只保留作旧路径参考和问题复现。
- 不要一边在 Windows Camera / OBS 里占用 C922，一边再启动 Windows ROS 相机发布节点。
