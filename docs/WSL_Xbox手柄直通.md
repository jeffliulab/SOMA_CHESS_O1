# WSL Xbox 手柄直通方案

## 目标

把 PDP Wired Controller for Xbox 直接 attach 到 WSL2，让 ROS 2 在 Linux 侧直接读取 `/dev/input/event*`（兼容 `evdev` 主路径，`/dev/input/js0` 仅保留为底层验证存在性）。这样可以避免 Windows UI、Terminal 或其他前台程序继续响应手柄输入。

这条路线是本项目长期推荐方案。Windows bridge 方案仍然保留在 `scripts/bridge方案/` 下，但只作为 stock WSL 内核下的备选方案。

## 方案概览

1. 用 `usbipd-win` 把手柄独占 attach 到 WSL
2. 给 WSL 换成与当前版本匹配的自定义内核
3. 在这个内核里启用 `JOYDEV + XPAD`
4. 在 WSL 内直接运行 teleop:

```bash
scripts/start_teleop_wsl_gamepad.sh
```

## 仓库内新增的辅助文件

- `scripts/build_wsl_gamepad_kernel.sh`
  作用：构建与当前 WSL 版本匹配的自定义内核，并生成 `.wslconfig` 片段
- `scripts/attach_devices.bat`
  作用：Windows 侧 attach 机械臂 + 手柄到 WSL
- `scripts/bridge方案/attach_devices_bridge_mode.bat`
  作用：桥接备选模式，只 attach 机械臂，手柄保留在 Windows
- `scripts/check_wsl_gamepad_support.sh`
  作用：检查当前 WSL 内核是否具备 `JOYDEV + XPAD`，以及 `/dev/input/event*` / `/dev/input/js0` 是否出现
- `scripts/start_teleop_wsl_gamepad.sh`
  作用：以 Linux 本地手柄模式启动 teleop（`use_tcp_bridge:=false`，默认 `evdev`）

## 推荐实施步骤

### 1. 构建自定义 WSL 内核

在 WSL 内执行：

```bash
cd ~/SOMA/SOMA_CHESS_O1
scripts/build_wsl_gamepad_kernel.sh
```

这会做几件事：

- 拉取官方 `WSL2-Linux-Kernel`
- 默认选用与你当前 `uname -r` 匹配的 tag
- 开启 `CONFIG_INPUT_EVDEV`
- 开启 `CONFIG_INPUT_JOYSTICK`
- 开启 `CONFIG_INPUT_JOYDEV`
- 开启 `CONFIG_JOYSTICK_XPAD`
- 开启 `CONFIG_HID_MICROSOFT`
- 构建 `bzImage`
- 生成 `modules.vhdx`
- 把结果复制到 Windows 可访问目录
- 生成 `.wslconfig` 片段

### 2. 配置 `%UserProfile%\.wslconfig`

把构建脚本生成的 `wslconfig.snippet.txt` 内容合并到 Windows 用户目录下的 `%UserProfile%\.wslconfig`。

也可以先参考仓库模板：

```text
scripts/wslconfig.gamepad.template
```

注意：

- `.wslconfig` 里的 Windows 路径要写成双反斜杠，例如 `C:\\Users\\jeffl\\wsl-kernels\\...`
- 如果误写成单反斜杠，WSL 可能会静默回退到默认内核；这种情况下 `uname -r` 往往还是没有 `+` 后缀的 stock kernel

完成后在 Windows PowerShell 执行：

```powershell
wsl --shutdown
```

然后重新打开 WSL。

### 3. Windows 侧 attach 设备

以管理员身份打开 PowerShell，运行：

```powershell
cd \\wsl$\Ubuntu-22.04\home\jeffliu\SOMA\SOMA_CHESS_O1\scripts
.\attach_devices.bat
```

注意：

- 首次使用前，需要先 `usbipd bind --busid <BUSID>`
- 当手柄 attached 到 WSL 后，Windows 将不再接收这个手柄输入
- 这正是本方案的核心价值之一

### 4. WSL 内验证

```bash
cd ~/SOMA/SOMA_CHESS_O1
scripts/check_wsl_gamepad_support.sh
```

你应该至少看到：

- `CONFIG_INPUT_JOYDEV = y` 或 `m`
- `CONFIG_JOYSTICK_XPAD = y` 或 `m`
- `/dev/input/event0 exists`
- `/dev/input/js0 exists`（如果 `JOYDEV` 打开，通常也会有）

### 5. 启动 Linux 本地 teleop

```bash
cd ~/SOMA/SOMA_CHESS_O1
scripts/start_teleop_wsl_gamepad.sh
```

这个脚本等价于：

```bash
srarm
ros2 launch arm_teleop teleop.launch.py use_tcp_bridge:=false
```

当前默认行为（2026-04-10 锁定）：

- `evdev` 是默认输入后端
- 左摇杆有单轴锁定，避免物理串轴直接变成底座+肩关节同时抖动
- 运动平滑默认关闭：摇杆大小直接映射速度，摇杆回中时速度立刻回零
- 纯夹爪动作走 `/gripper_command`，driver 底层使用官方 `T:106` 末端独立命令，不再重发整条手臂的 `T:102`

## 为什么这条路线更稳

- 控制链更短：手柄 -> Linux -> ROS 2 -> 机械臂
- 不再依赖 Windows 焦点、GUI、TCP bridge、XInput 子进程
- 手柄 attached 到 WSL 后，Windows 无法再消费这个设备，因此不会再干扰 Terminal、焦点切换、按钮触发

## 当前默认版本与备选切换

默认建议一直使用：

```bash
scripts/start_teleop_wsl_gamepad.sh
```

如果你想临时比较“有轻微起停平滑”的手感：

```bash
ros2 launch arm_teleop teleop.launch.py use_tcp_bridge:=false enable_motion_smoothing:=true
```

如果需要完全回退到旧的 Windows bridge：

- Windows：`scripts\bridge方案\attach_devices_bridge_mode.bat`
- Windows：`scripts\bridge方案\bridge_gui.py`
- WSL：`ros2 launch arm_teleop teleop.launch.py use_tcp_bridge:=true`

## 什么时候还需要 bridge 模式

只有两种情况建议继续用 bridge：

- 你暂时不想换 WSL 自定义内核
- 你需要快速回退到现有 Windows 手柄桥接链路

这时使用：

- Windows：`scripts\bridge方案\bridge_gui.py`
- Windows：`scripts\bridge方案\attach_devices_bridge_mode.bat`
- WSL：`ros2 launch arm_teleop teleop.launch.py use_tcp_bridge:=true`

## 常见排查

### `lsusb` 能看到手柄，但没有 `/dev/input/event0`

通常说明：

- 手柄已经 attach 到 WSL
- 但当前 WSL 内核没有启用 `JOYDEV + XPAD`

先运行：

```bash
scripts/check_wsl_gamepad_support.sh
```

### `scripts/start_teleop_wsl_gamepad.sh` 报 `No joystick found` 或 `event* is not readable`

先检查两件事：

1. Windows 侧是否真的执行了 `attach_devices.bat`
2. 当前自定义内核是否已经通过 `.wslconfig` 生效
3. 当前 WSL shell 是否真的在 `input` 组里（必要时 `newgrp input`）

### 想临时回退到旧方案

使用 bridge 备选路径：

- Windows 运行 `scripts\bridge方案\attach_devices_bridge_mode.bat`
- Windows 运行 `scripts\bridge方案\bridge_gui.py`
- WSL 运行 `ros2 launch arm_teleop teleop.launch.py use_tcp_bridge:=true`
