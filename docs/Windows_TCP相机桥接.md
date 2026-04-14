# Windows TCP 相机桥接

> 当前默认相机路线：Windows 原生取图 -> TCP bridge -> WSL ROS 2 发布。  
> 这样可以绕开这台机器上 `usbipd + WSL + UVC/MJPG` 直通相机时出现的横向破图。

## 这条路线怎么理解

- **Windows 侧**：只负责打开 C922、压成 JPEG，然后通过 TCP 发给 WSL
- **WSL 侧**：接收 JPEG、解码、发布 ROS 2 图像话题
- **后面的感知 / 标定 / 数据采集**：继续订阅
  - `/camera/image_raw`
  - `/camera/camera_info`

也就是说，后面的 ROS 接口不变，变的只是“图像从哪里来”。

## 先决条件

- C922 **不要** attach 到 WSL
- C922 留在 Windows 原生侧
- 机械臂和手柄继续按原来的 `usbipd` 路线进 WSL
- 当前机器继续使用 WSL mirrored networking
- 只要你准备碰 `usbipd attach` 或任何 Windows 侧 USB 转发脚本，默认第一步都先跑 `usbipd list`，不要直接相信旧文档里的 busid

## 先准备 Windows bridge 专用环境

这套环境现在统一放在 `DRIVERS/windows_envs` 管理，但实际 venv 会创建在 Windows 本机路径：

- `%LOCALAPPDATA%\SOMA\windows_envs\camera_bridge`

在 Windows PowerShell 里先运行：

```powershell
Set-ExecutionPolicy -Scope Process Bypass
& "\\wsl$\Ubuntu-22.04\home\jeffliu\SOMA\DRIVERS\windows_envs\camera_bridge\bootstrap_camera_bridge_env.ps1"
```

当前最小依赖只有：

- `opencv-python`

## 先确认 C922 在 Windows 里的设备索引

如果你看到的不是 C922，而是笔记本前置摄像头，说明默认 `device_index=0` 不对。

这时先扫一遍：

```powershell
cd \\wsl$\Ubuntu-22.04\home\jeffliu\SOMA\SOMA_CHESS_O1\scripts\bridge方案
.\probe_windows_cameras.bat
```

常见情况是：

- `index=0` 是前置摄像头
- `index=1` 或 `index=2` 才是 C922

当前这台机器在 2026-04-10 的实际结果是：

- `index=0` = 前置摄像头
- `index=1` = C922

确认之后，启动 bridge 时显式指定：

```powershell
.\start_camera_bridge.bat --device-index 1
```

当前这台机器上，更推荐直接从这条“已经达到可用水平”的预设开始：

```powershell
.\start_camera_bridge_low_latency_540p.bat
```

它等价于：

```powershell
.\start_camera_bridge.bat --device-index 1 --backend dshow --width 960 --height 540 --jpeg-quality 70 --drop-stale-grabs 4
```

现在这份 sender 已经改成了“后台持续抓最新帧，只发送最新画面”的模式。  
WSL 接收端现在也改成了“网络读线程持续收包，但 ROS 发布只发布当前最新帧”的模式。  
如果你前面已经起过 bridge，请把 Windows 发送端和 WSL 接收端都完全重启一次，再看延迟有没有明显下降。

## Windows 侧启动发送端

在 Windows Terminal / PowerShell 里：

```bat
cd \\wsl$\Ubuntu-22.04\home\jeffliu\SOMA\SOMA_CHESS_O1\scripts\bridge方案
.\start_camera_bridge.bat
```

默认参数：

- `127.0.0.1:65433`
- `1280x720 @ 30fps`
- 优先 `MSMF`，失败 fallback 到 `DSHOW`
- 默认请求本地 `MJPG`
- 默认会优先保留最新画面，不再按顺序慢慢吃旧帧
- WSL 端运行日志会额外打印 `end_to_end_age_ms`，方便直接看当前画面离实时有多远

常见自定义：

```bat
.\start_camera_bridge.bat --backend dshow
.\start_camera_bridge.bat --width 1920 --height 1080 --fps 30
.\start_camera_bridge_low_latency_540p.bat
```

`start_camera_bridge.bat` 会优先使用这个专用 venv；如果找不到，再 fallback 到系统 `py`。

## WSL 侧启动 ROS 接收端

```bash
cd ~/SOMA/SOMA_CHESS_O1
scripts/start_camera_bridge_wsl.sh
```

如果想手动指定 host / port：

```bash
cd ~/SOMA/SOMA_CHESS_O1
scripts/start_camera_bridge_wsl.sh --host 127.0.0.1 --port 65433
```

## WSL 侧验证

看 topic：

```bash
srarm
ros2 topic list | rg /camera
ros2 topic hz /camera/image_raw
```

看画面：

```bash
srarm
ros2 run rqt_image_view rqt_image_view
```

在 `rqt_image_view` 里选：

- `/camera/image_raw`

如果你只是想更直接地看桥接后的实时画面，也可以不用 `rqt_image_view`，而是直接开这个轻量预览：

```bash
srarm
python3 scripts/preview_ros_image_stream.py --topic /camera/image_raw
```

如果想继续确认“横向破图是不是还在原始图像里”，继续用：

```bash
srarm
python3 scripts/save_ros_image_frames.py --topic /camera/image_raw --count 10 --skip 10
```

默认输出目录：

- `tmp/ros_camera_frames/`

## 当前推荐顺序

1. Windows 起 `start_camera_bridge.bat`
2. WSL 起 `scripts/start_camera_bridge_wsl.sh`
3. WSL 用 `rqt_image_view` 看 `/camera/image_raw`
4. 再用 `save_ros_image_frames.py` 落几帧，确认图像干净

## 现在不建议做什么

- 不要继续把 C922 当成默认设备 attach 到 WSL
- 不要先为这个相机问题去装 Linux 双系统
- 不要再把 Windows ROS 2 安装当成本轮相机打通的前置条件
