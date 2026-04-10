"""Thin serial protocol wrapper for the Waveshare RoArm-M2-S.

The arm speaks a JSON-line protocol over USB serial at 115200 8N1. Each command
is a single JSON object terminated by '\\n'. Each response is a single JSON line.

Reference: github.com/waveshareteam/roarm_ws_em0
  src/roarm_main/roarm_driver/roarm_driver/roarm_driver.py

T-code cheatsheet (only the ones we use; full list at the Waveshare wiki):

  Outgoing (host -> arm)
    {"T": 605, "cmd": 0}
        Startup / mode reset. Upstream driver sends this immediately on open.

    {"T": 102, "base": b, "shoulder": s, "elbow": e, "hand": h,
               "spd": 0, "acc": 10}
        Set all four joint angles at once. Angles in radians.
        spd = 0 means "use default servo speed". acc = 10 is a gentle accel.

    {"T": 106, "cmd": h, "spd": 0, "acc": 10}
        Set only the clamp / wrist joint angle. Angles in radians in the
        hardware frame, same convention as the `hand` field in T:102.

    {"T": 105}
        Query current state. Arm responds with one {"T": 1051, ...} line.

    {"T": 114, "led": value}
        Control the onboard LED (0.0 - 1.0 or integer 0-255). ✓ verified 2026-04-08.

  Incoming (arm -> host)
    {"T": 1051, "x": <mm>, "y": <mm>, "z": <mm>,
                "b": <rad>, "s": <rad>, "e": <rad>, "t": <rad>,
                "torB": ..., "torS": ..., "torE": ..., "torH": ...}
        x/y/z are TCP position in millimetres.
        b/s/e/t are joint angles in the arm's native frame (see sign notes).
        torX are torque feedback values.

Sign conventions (URDF vs hardware native, matches upstream driver):
    URDF joint "base_link_to_link1"    = -b (negated)
    URDF joint "link1_to_link2"        = -s (negated)
    URDF joint "link2_to_link3"        = +e
    URDF joint "link3_to_gripper_link" = pi - t  (offset by pi)

The helper functions `urdf_to_hw()` and `hw_to_urdf()` below apply these
conversions so the caller can always work in URDF-native coordinates.
"""

from __future__ import annotations

import json
import math
import threading
from dataclasses import dataclass
from typing import Optional

import serial


DEFAULT_PORT = "/dev/ttyUSB0"
DEFAULT_BAUD = 115200

# URDF joint names, in the order we always pass as [base, shoulder, elbow, hand]
URDF_JOINT_NAMES = [
    "base_link_to_link1",     # 0: base yaw
    "link1_to_link2",         # 1: shoulder pitch
    "link2_to_link3",         # 2: elbow pitch
    "link3_to_gripper_link",  # 3: gripper (0 closed ... 1.5 open)
]

# URDF joint limits (lower, upper) — keep in sync with soma_robot.urdf.xacro
JOINT_LIMITS = {
    "base_link_to_link1":    (-math.pi,      math.pi),
    "link1_to_link2":        (-math.pi / 2,  math.pi / 2),
    "link2_to_link3":        (-1.0,          math.pi),
    "link3_to_gripper_link": (0.0,           1.5),
}


@dataclass
class ArmState:
    """One snapshot of arm state as received via T:1051 response."""
    # TCP cartesian position in metres (converted from mm)
    x: float
    y: float
    z: float
    # Joint angles in URDF convention (radians)
    base_link_to_link1: float
    link1_to_link2: float
    link2_to_link3: float
    link3_to_gripper_link: float
    # Torque feedback (raw units from arm; just pass through)
    tor_base: float
    tor_shoulder: float
    tor_elbow: float
    tor_hand: float

    def joint_positions(self) -> list[float]:
        """Return joint positions in the canonical [base, shoulder, elbow, hand] order."""
        return [
            self.base_link_to_link1,
            self.link1_to_link2,
            self.link2_to_link3,
            self.link3_to_gripper_link,
        ]


def urdf_to_hw(base_urdf: float, shoulder_urdf: float,
               elbow_urdf: float, hand_urdf: float) -> tuple[float, float, float, float]:
    """Convert URDF joint positions to the arm's native hardware frame."""
    return (-base_urdf, -shoulder_urdf, elbow_urdf, math.pi - hand_urdf)


def hw_to_urdf(b: float, s: float, e: float, t: float) -> tuple[float, float, float, float]:
    """Convert hardware-frame joint readings back to URDF convention."""
    return (-b, -s, e, math.pi - t)


def clamp_urdf(positions: list[float]) -> list[float]:
    """Clamp a [base, shoulder, elbow, hand] URDF position list to the joint limits."""
    out = []
    for name, pos in zip(URDF_JOINT_NAMES, positions):
        lo, hi = JOINT_LIMITS[name]
        if pos < lo:
            pos = lo
        elif pos > hi:
            pos = hi
        out.append(pos)
    return out


class RoArmProtocol:
    """Thread-safe wrapper around the pyserial connection to a RoArm-M2-S."""

    def __init__(self, port: str = DEFAULT_PORT, baud: int = DEFAULT_BAUD,
                 timeout: float = 0.2):
        self.port = port
        self.baud = baud
        self.ser = serial.Serial(port, baud, timeout=timeout)
        self._buf = bytearray()
        self._lock = threading.Lock()

    def close(self) -> None:
        try:
            self.ser.close()
        except Exception:
            pass

    # ---------- low-level I/O ----------

    def _send(self, cmd: dict) -> None:
        line = (json.dumps(cmd) + "\n").encode("utf-8")
        with self._lock:
            self.ser.write(line)

    def _readline(self) -> Optional[bytes]:
        """Read one newline-terminated line (may return None on timeout)."""
        # Fast path: we already have a full line buffered
        i = self._buf.find(b"\n")
        if i >= 0:
            line = bytes(self._buf[:i])
            del self._buf[:i + 1]
            return line
        # Slow path: pull bytes until we see a newline or timeout
        with self._lock:
            while True:
                chunk = self.ser.read(max(1, self.ser.in_waiting or 1))
                if not chunk:
                    return None  # timeout
                self._buf.extend(chunk)
                j = self._buf.find(b"\n")
                if j >= 0:
                    line = bytes(self._buf[:j])
                    del self._buf[:j + 1]
                    return line

    def reset_input(self) -> None:
        with self._lock:
            self.ser.reset_input_buffer()
            self._buf.clear()

    # ---------- high-level commands ----------

    def startup(self) -> None:
        """Send the T:605 init packet the upstream driver uses on open."""
        self._send({"T": 605, "cmd": 0})

    def set_joints_urdf(self, base: float, shoulder: float, elbow: float, hand: float,
                        spd: int = 0, acc: int = 10) -> None:
        """Set all four joint targets in URDF-positive convention.

        Args are radians. `spd=0` means default servo speed, `acc=10` is gentle.
        """
        b, s, e, t = urdf_to_hw(base, shoulder, elbow, hand)
        self._send({"T": 102, "base": b, "shoulder": s, "elbow": e, "hand": t,
                    "spd": spd, "acc": acc})

    def set_gripper_urdf(self, hand: float, spd: int = 0, acc: int = 10) -> None:
        """Set only the clamp / wrist joint target in URDF-positive convention."""
        _b, _s, _e, t = urdf_to_hw(0.0, 0.0, 0.0, hand)
        self._send({"T": 106, "cmd": t, "spd": spd, "acc": acc})

    def query_state(self) -> None:
        """Ask the arm to report current state (T:105). Response arrives as T:1051."""
        self._send({"T": 105})

    def read_state_response(self, max_attempts: int = 5) -> Optional[ArmState]:
        """Read lines until we see a T:1051 response; return parsed ArmState."""
        for _ in range(max_attempts):
            raw = self._readline()
            if raw is None:
                return None
            try:
                obj = json.loads(raw.decode("utf-8", errors="ignore"))
            except json.JSONDecodeError:
                continue
            if obj.get("T") != 1051:
                continue
            b = float(obj.get("b", 0.0))
            s = float(obj.get("s", 0.0))
            e = float(obj.get("e", 0.0))
            t = float(obj.get("t", 0.0))
            base_u, sh_u, el_u, ha_u = hw_to_urdf(b, s, e, t)
            return ArmState(
                x=float(obj.get("x", 0.0)) / 1000.0,
                y=float(obj.get("y", 0.0)) / 1000.0,
                z=float(obj.get("z", 0.0)) / 1000.0,
                base_link_to_link1=base_u,
                link1_to_link2=sh_u,
                link2_to_link3=el_u,
                link3_to_gripper_link=ha_u,
                tor_base=float(obj.get("torB", 0.0)),
                tor_shoulder=float(obj.get("torS", 0.0)),
                tor_elbow=float(obj.get("torE", 0.0)),
                tor_hand=float(obj.get("torH", 0.0)),
            )
        return None

    def fetch_state(self) -> Optional[ArmState]:
        """Convenience: send T:105 and parse the next T:1051 response."""
        self.reset_input()
        self.query_state()
        return self.read_state_response()

    def set_led(self, value: float) -> None:
        """Set the onboard LED (value in [0, 1] or raw 0..255)."""
        self._send({"T": 114, "led": value})


# -------------------------------------------------------------------------
# Standalone probe CLI — useful before the ROS 2 layer is brought up.
# -------------------------------------------------------------------------

def _cli_probe() -> None:  # pragma: no cover
    """Entry point: `arm_driver probe` — query and print one arm state.

    Usage:
        python -m arm_driver.roarm_protocol               # default /dev/ttyUSB0
        python -m arm_driver.roarm_protocol /dev/ttyACM0  # custom port
    """
    import sys
    port = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_PORT
    print(f"[probe] opening {port} @ {DEFAULT_BAUD}")
    arm = RoArmProtocol(port=port)
    try:
        arm.startup()
        state = arm.fetch_state()
        if state is None:
            print("[probe] no T:1051 response within timeout")
            return
        print(f"[probe] TCP (m): x={state.x:.4f} y={state.y:.4f} z={state.z:.4f}")
        print(f"[probe] joints (URDF rad): "
              f"base={state.base_link_to_link1:+.3f}  "
              f"sh={state.link1_to_link2:+.3f}  "
              f"el={state.link2_to_link3:+.3f}  "
              f"hand={state.link3_to_gripper_link:+.3f}")
        print(f"[probe] torque: B={state.tor_base} S={state.tor_shoulder} "
              f"E={state.tor_elbow} H={state.tor_hand}")
    finally:
        arm.close()


if __name__ == "__main__":  # pragma: no cover
    _cli_probe()
