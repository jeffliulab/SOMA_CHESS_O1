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
cd \\wsl$\Ubuntu-22.04\home\jeffliu\SOMA\soma-arm\scripts\bridge方案
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

## W1.4 相机参数稳定化怎么做

当前默认路线下，**锁参数要在 Windows sender 这一侧做**，而不是继续依赖旧的 WSL `v4l2-ctl` 脚本。

建议把 W1.4 分成两步：

1. **先调参**：打开 Windows 原生相机设置页，把自动曝光 / 自动白平衡 / 自动对焦关掉，再微调到你满意的画面
2. **再冻结**：平时启动 bridge 时继续走低延迟 `540p`，并带上 “freeze auto” 配置，保证采集链路尽量稳定

这一步现在对应 `V1.01` 里的：

- `W1.4A`：手动锁参与稳定成像 baseline
- `W1.4B`：在 baseline 上再挂任务驱动 / 图像质量驱动的自适应控制

### 第一步：打开调参版 sender

```powershell
cd \\wsl$\Ubuntu-22.04\home\jeffliu\SOMA\soma-arm\scripts\bridge方案
.\start_camera_bridge_tuning_540p.bat
```

这条入口做了几件事：

- 固定用当前这台机器更稳的 `DSHOW + 960x540`
- 自动应用 `c922_freeze_auto` 配置
  - 尝试把自动白平衡关掉
  - 尝试把白平衡温度先拉到 `4000`
  - 尝试把自动对焦关掉
  - 在 `DSHOW` 下把自动曝光切到 manual
- 打开 Windows 原生的 DirectShow 相机设置对话框
- 启动时把当前可读到的 control 值打到日志里

### 在设置对话框里重点看什么

- Exposure / Auto Exposure
- White Balance / Auto White Balance
- Focus / Auto Focus

目标不是一次把所有数字调到“理论最优”，而是先拿到一个**跨 session 不会自己乱飘**的状态：

- 手从画面里进出时，亮度不要明显抽动
- 棋盘和工作区颜色不要一会儿偏蓝、一会儿偏黄
- 棋子和桌面边缘在正常工作距离下保持清楚

如果你在窗口里调完了这些项，**建议关掉 sender，再重新启动一次**，这样启动日志里的 control readback 才更接近最终锁住的状态。

### 第二步：日常运行锁参版 sender

```powershell
cd \\wsl$\Ubuntu-22.04\home\jeffliu\SOMA\soma-arm\scripts\bridge方案
.\start_camera_bridge_locked_540p.bat
```

这条入口不会再主动弹设置框，但会继续：

- 走 `DSHOW + 960x540 + jpeg_quality=70 + drop_stale_grabs=4`
- 应用 `c922_freeze_auto`
- 打印当前 control readback

如果后面你想继续微调，也可以直接在这条命令后追加 raw OpenCV 参数，例如：

```powershell
.\start_camera_bridge_locked_540p.bat --wb-temperature 4200
.\start_camera_bridge_locked_540p.bat --focus 20
.\start_camera_bridge_locked_540p.bat --exposure -6
```

注意：这些数值是 **Windows/OpenCV 的 raw property 值**，不一定和旧的 Linux `v4l2-ctl` 数字一致，所以不要直接照搬 `156 / 4000 / focus_absolute` 那套语义。

### 第三步：可选的自适应 sender

如果 `W1.4A` 已经有一个稳定 baseline，接下来要验证 `W1.4B`，可以直接起：

```powershell
cd \\wsl$\Ubuntu-22.04\home\jeffliu\SOMA\soma-arm\scripts\bridge方案
.\start_camera_bridge_adaptive_540p.bat
```

这条入口会继续沿用 locked baseline，但额外挂一个 sender 内部的自适应控制器：

- 只动 `exposure / gain / white balance / focus`
- 默认看固定工作区 ROI 的 `mean luma / overexposed ratio / contrast / sharpness / color cast`
- 带 `eval interval / cooldown / hysteresis`，避免参数来回振荡
- 关闭 adaptive 后，行为应当退回和 `start_camera_bridge_locked_540p.bat` 一致

如果后面 perception 稳定了，WSL 侧还可以通过本机 `127.0.0.1:65434` 发一条 newline-delimited JSON 反馈给 sender，字段默认约定为：

```json
{
  "timestamp_ms": 1776300845000,
  "board_visible": true,
  "board_confidence": 0.82,
  "corners_detected": 28,
  "object_confidence": 0.73,
  "mean_luma": 116.4,
  "overexposed_ratio": 0.004,
  "sharpness": 182.0,
  "requested_mode": "normal"
}
```

sender 当前已经能监听这条 feedback 通道；如果没有任何客户端连接，它会继续只靠图像质量指标运行。

### 旧的 `lock_c922_params.sh` 现在怎么用

`scripts/lock_c922_params.sh` 还保留着，但它是给 **旧的 WSL 直通 V4L2 路线** 用的。

在当前默认桥接路线下：

- 它不是主入口
- 可以当作历史参考
- 不应该再作为 W1.4 的默认执行路径

## Windows 侧启动发送端

在 Windows Terminal / PowerShell 里：

```bat
cd \\wsl$\Ubuntu-22.04\home\jeffliu\SOMA\soma-arm\scripts\bridge方案
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
.\start_camera_bridge_locked_540p.bat
.\start_camera_bridge_adaptive_540p.bat
.\start_camera_bridge_tuning_540p.bat
```

`start_camera_bridge.bat` 会优先使用这个专用 venv；如果找不到，再 fallback 到系统 `py`。

## WSL 侧启动 ROS 接收端

```bash
cd ~/SOMA/soma-arm
scripts/start_camera_bridge_wsl.sh
```

默认情况下，这个 receiver 现在会优先尝试读取：

- `config/calibration/camera_intrinsics.yaml`

如果文件存在而且不再是 `pending_calibration`，`/camera/camera_info` 会直接带上正式内参；如果还没完成标定，它会自动退回占位版相机信息，不会阻塞图像发布。

如果想手动指定 host / port：

```bash
cd ~/SOMA/soma-arm
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
