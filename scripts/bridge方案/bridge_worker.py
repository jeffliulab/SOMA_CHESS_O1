"""bridge_worker.py — XInput TCP bridge worker process.

Runs as a subprocess managed by bridge_gui.py.  If XInput DLL causes a
C-level crash here, only this process dies; the GUI process survives and
auto-restarts us.

Outputs newline-delimited JSON to stdout so the GUI can parse status:
  {"type":"log",    "msg":"..."}
  {"type":"status", "bridge":"...", "client":"...", "ctrl":"...", "axes":[...]}
"""

from __future__ import annotations

import json
import signal
import socket
import sys
import time

try:
    import XInput
except ImportError:
    print(json.dumps({"type": "log", "msg": "ERROR: pip install XInput-Python"}), flush=True)
    sys.exit(1)

# Ignore Ctrl+C so an accidental keypress in the parent terminal does not kill us.
signal.signal(signal.SIGINT, signal.SIG_IGN)

HOST = "127.0.0.1"
PORT = 65432
POLL_HZ = 50

BUTTON_ORDER = [
    "DPAD_UP", "DPAD_DOWN", "DPAD_LEFT", "DPAD_RIGHT",
    "LEFT_SHOULDER", "RIGHT_SHOULDER",
    "BACK", "START",
    "LEFT_THUMB", "RIGHT_THUMB",
    "A", "B", "X", "Y",
]


# ---------------------------------------------------------------------------
# Output helpers
# ---------------------------------------------------------------------------

def emit_log(msg: str) -> None:
    print(json.dumps({"type": "log", "msg": msg}), flush=True)


def emit_status(bridge: str, client: str, ctrl: str, axes: list) -> None:
    print(json.dumps({
        "type": "status",
        "bridge": bridge, "client": client,
        "ctrl": ctrl, "axes": axes,
    }), flush=True)


# ---------------------------------------------------------------------------
# Controller reading  (this is the function most likely to crash at C level)
# ---------------------------------------------------------------------------

def read_controller():
    state = XInput.get_state(0)
    (lx, ly_x), (rx, ry_x) = XInput.get_thumb_values(state)
    lt_x, rt_x = XInput.get_trigger_values(state)
    ly, ry = -ly_x, -ry_x
    lt, rt = lt_x * 2.0 - 1.0, rt_x * 2.0 - 1.0
    axes = [lx, ly, lt, rx, ry, rt]
    bvals = XInput.get_button_values(state)
    buttons = [int(bvals.get(n, False)) for n in BUTTON_ORDER]
    return axes, buttons


# ---------------------------------------------------------------------------
# Main bridge loop
# ---------------------------------------------------------------------------

def main() -> None:
    if not XInput.get_connected()[0]:
        emit_log("ERROR: No XInput controller detected.")
        sys.exit(2)

    emit_status("waiting", "disconnected", "ok", [0.0] * 6)

    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    try:
        server.bind((HOST, PORT))
    except OSError as e:
        emit_log(f"ERROR bind failed: {e}")
        sys.exit(3)
    server.listen(1)
    server.settimeout(1.0)
    emit_log(f"Listening on {HOST}:{PORT}")

    interval = 1.0 / POLL_HZ

    while True:
        # Accept
        try:
            conn, addr = server.accept()
        except socket.timeout:
            continue
        except OSError:
            break

        emit_log(f"WSL2 connected: {addr}")
        emit_status("streaming", "connected", "ok", [0.0] * 6)
        time.sleep(1.0)  # let XInput stabilise

        # Stream
        try:
            while True:
                t0 = time.perf_counter()
                # read_controller() may crash at C level — that's OK, this
                # process dies, gui restarts us
                axes, buttons = read_controller()
                emit_status("streaming", "connected", "ok", axes)
                line = (
                    json.dumps({"axes": axes, "buttons": buttons},
                               separators=(",", ":")) + "\n"
                )
                try:
                    conn.sendall(line.encode())
                except (BrokenPipeError, ConnectionResetError, OSError):
                    emit_log("WSL2 disconnected.")
                    break
                elapsed = time.perf_counter() - t0
                time.sleep(max(0.0, interval - elapsed))
        finally:
            conn.close()
            emit_status("waiting", "disconnected", "ok", [0.0] * 6)
            emit_log("Waiting for new connection...")

    server.close()


if __name__ == "__main__":
    main()
