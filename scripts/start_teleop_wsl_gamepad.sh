#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SERIAL_PORT="/dev/ttyUSB0"
EVENT_DEVICE=""
LAUNCH_PATTERN="ros2 launch arm_teleop teleop.launch.py"

if [[ $# -gt 0 && "$1" == /dev/* ]]; then
    SERIAL_PORT="$1"
    shift
fi

resolve_serial_port() {
    local requested="$1"
    local base candidate

    base="$(basename "$requested")"
    if [[ -e "/sys/class/tty/${base}" ]]; then
        echo "$requested"
        return 0
    fi

    for candidate in /sys/class/tty/ttyUSB* /sys/class/tty/ttyACM*; do
        [[ -e "$candidate" ]] || continue
        echo "/dev/$(basename "$candidate")"
        return 0
    done

    echo "$requested"
    return 0
}

resolve_event_device() {
    local candidate
    for candidate in /dev/input/event*; do
        [[ -e "$candidate" ]] || continue
        echo "$candidate"
        return 0
    done
    return 1
}

SERIAL_PORT="$(resolve_serial_port "$SERIAL_PORT")"
EVENT_DEVICE="$(resolve_event_device || true)"

if ! compgen -G "/dev/input/event*" > /dev/null; then
    echo "ERROR: no /dev/input/event* device found." >&2
    echo "Attach the controller to WSL with usbipd and make sure the WSL kernel enables EVDEV + XPAD." >&2
    echo "If sysfs sees the device but /dev nodes are missing, run: sudo scripts/ensure_wsl_devnodes.sh" >&2
    exit 1
fi

if [[ ! -e "$SERIAL_PORT" ]]; then
    echo "ERROR: ${SERIAL_PORT} not found." >&2
    echo "If sysfs sees ttyUSB/ttyACM but /dev is stale, run: sudo scripts/ensure_wsl_devnodes.sh" >&2
    exit 1
fi

if [[ -n "$EVENT_DEVICE" && ! -r "$EVENT_DEVICE" ]]; then
    echo "ERROR: ${EVENT_DEVICE} exists but is not readable by the current shell." >&2
    echo "Open a fresh WSL shell after adding yourself to the 'input' group, or run: newgrp input" >&2
    exit 1
fi

existing_launch="$(pgrep -af "$LAUNCH_PATTERN" || true)"
if [[ -n "$existing_launch" ]]; then
    echo "ERROR: arm_teleop is already running." >&2
    echo "$existing_launch" >&2
    echo "Stop the existing teleop/arm_driver instance before starting a new one." >&2
    exit 1
fi

cd "$ROOT_DIR"
echo "Using serial port: ${SERIAL_PORT}"
if [[ -n "$EVENT_DEVICE" ]]; then
    echo "Using event device: ${EVENT_DEVICE}"
fi

# ROS setup scripts assume certain vars may be unset; source them with nounset disabled.
set +u
source /opt/ros/humble/setup.bash
source .venv/bin/activate
source install/setup.bash
set -u

exec ros2 launch arm_teleop teleop.launch.py \
    serial_port:="$SERIAL_PORT" \
    event_device_path:="$EVENT_DEVICE" \
    use_tcp_bridge:=false \
    "$@"
