#!/usr/bin/env bash
set -euo pipefail

CONFIG_TEXT=""
if [[ -f /proc/config.gz ]]; then
    CONFIG_TEXT="$(gzip -dc /proc/config.gz 2>/dev/null || true)"
elif [[ -f "/boot/config-$(uname -r)" ]]; then
    CONFIG_TEXT="$(cat "/boot/config-$(uname -r)")"
fi

config_state() {
    local sym="$1"
    if [[ -n "$CONFIG_TEXT" ]]; then
        if grep -q "^${sym}=y" <<<"$CONFIG_TEXT"; then
            echo "y"
            return
        fi
        if grep -q "^${sym}=m" <<<"$CONFIG_TEXT"; then
            echo "m"
            return
        fi
        if grep -q "^# ${sym} is not set" <<<"$CONFIG_TEXT"; then
            echo "n"
            return
        fi
    fi

    echo "unknown"
}

report_device() {
    local path="$1"
    if [[ -e "$path" ]]; then
        echo "[ok] $path exists"
    else
        echo "[missing] $path"
    fi
}

echo "== WSL Gamepad Support Check =="
echo "Kernel: $(uname -r)"
echo

echo "Kernel config:"
echo "  CONFIG_INPUT_JOYSTICK    = $(config_state CONFIG_INPUT_JOYSTICK)"
echo "  CONFIG_INPUT_EVDEV       = $(config_state CONFIG_INPUT_EVDEV)"
echo "  CONFIG_INPUT_JOYDEV      = $(config_state CONFIG_INPUT_JOYDEV)"
echo "  CONFIG_JOYSTICK_XPAD     = $(config_state CONFIG_JOYSTICK_XPAD)"
echo "  CONFIG_HID_MICROSOFT     = $(config_state CONFIG_HID_MICROSOFT)"
echo

echo "Input devices:"
report_device /dev/input/js0
report_device /dev/input/event0
first_event="$(compgen -G '/dev/input/event*' | head -n 1 || true)"
first_serial="$(compgen -G '/dev/ttyUSB*' | head -n 1 || true)"
if [[ -n "$first_event" && "$first_event" != "/dev/input/event0" ]]; then
    report_device "$first_event"
fi
if [[ -n "$first_serial" ]]; then
    report_device "$first_serial"
else
    report_device /dev/ttyUSB0
fi
if [[ -n "$first_event" ]]; then
    if [[ -r "$first_event" ]]; then
        echo "[ok] $first_event is readable by the current shell"
    else
        echo "[warn] $first_event exists but is not readable by the current shell (need input group)"
    fi
fi
echo

if command -v lsusb >/dev/null 2>&1; then
    echo "Relevant USB devices from lsusb:"
    lsusb 2>/dev/null | grep -Ei 'xbox|microsoft|pdp|controller' || echo "  (no obvious Xbox/PDP device found)"
    echo
fi

echo "Hint:"
if compgen -G "/dev/input/event*" > /dev/null; then
    echo "  evdev input is visible in WSL. Next: run scripts/start_teleop_wsl_gamepad.sh"
else
    echo "  /dev/input/event* is missing."
    echo "  Verify usbipd attach on Windows and make sure your custom WSL kernel enables INPUT_JOYSTICK + EVDEV + JOYDEV + XPAD."
fi
