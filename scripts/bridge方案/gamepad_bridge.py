"""gamepad_bridge.py — Windows XInput gamepad bridge for WSL2 ROS 2 teleop.

Reads the PDP Xbox controller via the Windows XInput API (XInput-Python)
and streams axis/button data as JSON lines over TCP to the WSL2 ROS 2
gamepad_teleop_node.

Why XInput-Python instead of pygame: pygame's SDL2 backend on Windows
sometimes returns all-zero axes for XInput controllers due to event-loop
quirks; XInput-Python queries the driver directly, bypassing SDL2.

Requirements (Windows Python, NOT WSL2):
    pip install XInput-Python

Usage:
    1. Keep the PDP controller on Windows (do NOT usbipd-attach it to WSL2).
    2. Run:  python gamepad_bridge.py
    3. In WSL2: ros2 launch arm_teleop teleop.launch.py use_tcp_bridge:=true

This is the fallback path for stock WSL kernels. The preferred long-term
workflow is to attach the controller directly into WSL with usbipd-win and
use a custom WSL kernel that enables JOYDEV + XPAD.

Axis layout sent (matches DEFAULT_AXIS_* in gamepad_teleop_node.py):
    index 0  Left stick X    -1.0 (left)  … +1.0 (right)
    index 1  Left stick Y    +1.0 (up)    … -1.0 (down)   ← pygame convention (inverted)
    index 2  Left trigger    -1.0 (rest)  … +1.0 (full)   ← remapped from XInput 0..1
    index 3  Right stick X   -1.0 (left)  … +1.0 (right)
    index 4  Right stick Y   +1.0 (up)    … -1.0 (down)   ← pygame convention (inverted)
    index 5  Right trigger   -1.0 (rest)  … +1.0 (full)   ← remapped from XInput 0..1

Button layout (indices match DEFAULT_BUTTON_* in gamepad_teleop_node.py):
    0 DPAD_UP   1 DPAD_DOWN   2 DPAD_LEFT   3 DPAD_RIGHT
    4 LB        5 RB          6 BACK        7 START
    8 L3        9 R3          10 A  11 B  12 X  13 Y
"""

import json
import logging
import signal
import socket
import sys
import time
from pathlib import Path

# Ignore Ctrl+C in the bridge process — stop by closing the window instead.
# This prevents accidental Ctrl+C from killing the bridge mid-session.
signal.signal(signal.SIGINT, signal.SIG_IGN)

try:
    import XInput
except ImportError:
    sys.exit("XInput-Python not found.  Run:  pip install XInput-Python")

# Log to Windows temp dir (reliable native path, not \\wsl$\)
import tempfile as _tempfile
_log_path = Path(_tempfile.gettempdir()) / "gamepad_bridge.log"
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler(_log_path, encoding="utf-8"),
    ],
)
log = logging.getLogger("bridge")

HOST = "127.0.0.1"   # WSL2 mirrored-networking: same as localhost in WSL2
PORT = 65432
POLL_HZ = 50

# Ordered list of button names → list index matches DEFAULT_BUTTON_* in teleop node.
# LB=4, RB=5, BACK=6, START=7
BUTTON_ORDER = [
    "DPAD_UP", "DPAD_DOWN", "DPAD_LEFT", "DPAD_RIGHT",
    "LEFT_SHOULDER", "RIGHT_SHOULDER",
    "BACK", "START",
    "LEFT_THUMB", "RIGHT_THUMB",
    "A", "B", "X", "Y",
]


def read_controller() -> tuple[list[float], list[int]]:
    state = XInput.get_state(0)
    (lx, ly_xinput), (rx, ry_xinput) = XInput.get_thumb_values(state)
    lt_xinput, rt_xinput = XInput.get_trigger_values(state)

    # XInput Y: +1=up, -1=down.  pygame convention: -1=up, +1=down.
    # Teleop node applies (-ly) to get "shoulder up", so we match pygame convention.
    ly = -ly_xinput
    ry = -ry_xinput

    # Triggers: XInput 0..1 → remap to -1..1 (teleop node remaps back: (v+1)*0.5)
    lt = lt_xinput * 2.0 - 1.0
    rt = rt_xinput * 2.0 - 1.0

    axes = [lx, ly, lt, rx, ry, rt]

    bvals = XInput.get_button_values(state)
    buttons = [int(bvals.get(name, False)) for name in BUTTON_ORDER]

    return axes, buttons


def main() -> None:
    connected = XInput.get_connected()
    if not connected[0]:
        sys.exit(
            "No XInput controller detected on index 0.\n"
            "Make sure the PDP controller is plugged in (NOT attached to WSL2)."
        )
    log.info(f"XInput controller 0 detected.")
    log.info(f"Log file: {_log_path}")
    log.info(f"Listening on {HOST}:{PORT}  (waiting for WSL2 ROS node...)")

    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server.bind((HOST, PORT))
    server.listen(1)

    interval = 1.0 / POLL_HZ
    while True:
        try:
            conn, addr = server.accept()
            log.info(f"Client connected: {addr}")
            _stream(conn, interval)
        except KeyboardInterrupt:
            log.info("Shutting down (Ctrl+C).")
            break
        except BaseException as e:
            log.exception(f"Unexpected error: {type(e).__name__}: {e}")
            time.sleep(1.0)

    server.close()


def _stream(conn: socket.socket, interval: float) -> None:
    log.info("Stream started — waiting 1 s for XInput to stabilise...")
    time.sleep(1.0)
    log.info("Polling controller.")
    try:
        while True:
            t0 = time.perf_counter()
            try:
                axes, buttons = read_controller()
            except Exception as e:
                log.exception(f"Controller read error: {e}")
                return
            line = (
                json.dumps({"axes": axes, "buttons": buttons}, separators=(",", ":"))
                + "\n"
            )
            try:
                conn.sendall(line.encode())
            except (BrokenPipeError, ConnectionResetError):
                log.warning("Client disconnected — waiting for reconnect.")
                return
            elapsed = time.perf_counter() - t0
            time.sleep(max(0.0, interval - elapsed))
    except BaseException as e:
        log.exception(f"Stream crashed: {type(e).__name__}: {e}")
        raise
    finally:
        conn.close()
        log.info("Stream ended.")


if __name__ == "__main__":
    main()
