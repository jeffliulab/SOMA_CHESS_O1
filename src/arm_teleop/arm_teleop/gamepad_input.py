"""Backend-agnostic gamepad input helpers for arm teleop.

This module normalizes every supported input source into the same
`GamepadState` shape so teleop logic does not need to care whether the
controller is coming from:

  - direct Linux evdev input (`/dev/input/event*`)
  - the legacy Windows TCP bridge
  - legacy Linux pygame joystick input (debug / fallback only)
"""

from __future__ import annotations

from dataclasses import dataclass, replace
import json
import os
from pathlib import Path
import socket
import threading
import time
import sys
from typing import Optional

try:
    from evdev import AbsInfo, InputDevice, ecodes, list_devices
except ModuleNotFoundError:
    # ROS entry points may still run under the distro Python even when the
    # project venv is activated in the shell. Fall back to the repo-local venv
    # so WSL teleop can keep using `evdev` without requiring a system-wide apt
    # install.
    here = Path(__file__).resolve()
    for parent in here.parents:
        venv_lib = parent / ".venv" / "lib"
        if not venv_lib.is_dir():
            continue
        for site_packages in venv_lib.glob("python*/site-packages"):
            if str(site_packages) not in sys.path:
                sys.path.insert(0, str(site_packages))
        try:
            from evdev import AbsInfo, InputDevice, ecodes, list_devices
            break
        except ModuleNotFoundError:
            continue
    else:
        raise


DEFAULT_DEVICE_INDEX = 0
DEFAULT_BRIDGE_HOST = "127.0.0.1"
DEFAULT_BRIDGE_PORT = 65432
DEFAULT_POLL_HZ = 50
DEFAULT_DEAD_ZONE = 0.15
DEFAULT_TRIGGER_THRESHOLD = 0.15
LEFT_STICK_LOCK_RELEASE_THRESHOLD = 0.10

# Legacy bridge payload layout. Keep this stable so tcp_bridge remains a
# faithful control-path reference while we migrate Linux local input to evdev.
BRIDGE_AXIS_LEFT_X = 0
BRIDGE_AXIS_LEFT_Y = 1
BRIDGE_AXIS_LT = 2
BRIDGE_AXIS_RIGHT_Y = 4
BRIDGE_AXIS_RT = 5

BRIDGE_BUTTON_DPAD_LEFT = 2
BRIDGE_BUTTON_DPAD_RIGHT = 3
BRIDGE_BUTTON_LB = 4
BRIDGE_BUTTON_RB = 5
BRIDGE_BUTTON_BACK = 6
BRIDGE_BUTTON_START = 7


@dataclass
class GamepadState:
    left_x: float = 0.0
    left_y: float = 0.0
    right_y: float = 0.0
    lt: float = 0.0
    rt: float = 0.0
    lb: bool = False
    rb: bool = False
    start: bool = False
    back: bool = False
    dpad_left: bool = False
    dpad_right: bool = False

    def copy(self) -> "GamepadState":
        return replace(self)


def apply_deadzone(value: float, threshold: float) -> float:
    return 0.0 if abs(value) < threshold else value


def apply_trigger_threshold(value: float, threshold: float) -> float:
    return 0.0 if value < threshold else value


class TeleopInputFilter:
    """Apply teleop-facing input cleanup on top of normalized GamepadState.

    The raw controller signal can contain significant left-stick cross-axis
    bleed, even when the physical intent is clearly "move left" or "move up".
    To preserve the cleaner feel of the legacy bridge workflow, teleop uses a
    hard axis lock on the left stick:

      - once either X or Y wins, the other axis is forced to zero
      - the lock is only released after both axes return near center
    """

    def __init__(
        self,
        dead_zone: float = DEFAULT_DEAD_ZONE,
        trigger_threshold: float = DEFAULT_TRIGGER_THRESHOLD,
        *,
        left_stick_release_threshold: float = LEFT_STICK_LOCK_RELEASE_THRESHOLD,
    ) -> None:
        self._dead_zone = float(dead_zone)
        self._trigger_threshold = float(trigger_threshold)
        self._left_stick_release_threshold = float(left_stick_release_threshold)
        self._left_stick_lock = "none"

    @property
    def left_stick_lock(self) -> str:
        return self._left_stick_lock

    def reset(self) -> None:
        self._left_stick_lock = "none"

    def process(self, state: GamepadState) -> GamepadState:
        filtered = state.copy()
        filtered.left_x = apply_deadzone(filtered.left_x, self._dead_zone)
        filtered.left_y = apply_deadzone(filtered.left_y, self._dead_zone)
        filtered.right_y = apply_deadzone(filtered.right_y, self._dead_zone)
        filtered.lt = apply_trigger_threshold(filtered.lt, self._trigger_threshold)
        filtered.rt = apply_trigger_threshold(filtered.rt, self._trigger_threshold)
        self._apply_left_stick_lock(filtered)
        return filtered

    def _apply_left_stick_lock(self, state: GamepadState) -> None:
        left_x = state.left_x
        left_y = state.left_y

        if (
            self._left_stick_lock != "none"
            and abs(left_x) < self._left_stick_release_threshold
            and abs(left_y) < self._left_stick_release_threshold
        ):
            self._left_stick_lock = "none"

        if self._left_stick_lock == "none" and max(abs(left_x), abs(left_y)) >= self._dead_zone:
            self._left_stick_lock = "x" if abs(left_x) >= abs(left_y) else "y"

        if self._left_stick_lock == "x":
            state.left_y = 0.0
        elif self._left_stick_lock == "y":
            state.left_x = 0.0


def candidate_gamepad_paths() -> list[str]:
    return sorted(list_devices())


def detect_evdev_gamepad_path(requested_path: str = "") -> Optional[str]:
    if requested_path:
        return requested_path if os.path.exists(requested_path) else None

    candidates: list[tuple[int, str]] = []
    fallback_candidates: list[tuple[int, str]] = []
    for path in candidate_gamepad_paths():
        try:
            dev = InputDevice(path)
            caps = dev.capabilities()
            abs_codes = set(caps.get(ecodes.EV_ABS, []))
            key_codes = set(caps.get(ecodes.EV_KEY, []))
            name = (dev.name or "").lower()
            score = 0
            has_basic_sticks = {ecodes.ABS_X, ecodes.ABS_Y}.issubset(abs_codes)
            has_elbow_axis = ecodes.ABS_RY in abs_codes or ecodes.ABS_RX in abs_codes
            has_triggers = {ecodes.ABS_Z, ecodes.ABS_RZ}.issubset(abs_codes)
            if any(token in name for token in ("x-box", "xbox", "pad", "controller", "pdp")):
                score += 2
            if has_basic_sticks and has_elbow_axis:
                score += 1
            if has_basic_sticks and has_elbow_axis and has_triggers:
                score += 2
            if ecodes.ABS_HAT0X in abs_codes or {ecodes.BTN_DPAD_LEFT, ecodes.BTN_DPAD_RIGHT}.issubset(key_codes):
                score += 1
            if {ecodes.BTN_TL, ecodes.BTN_TR, ecodes.BTN_SELECT, ecodes.BTN_START}.issubset(key_codes):
                score += 2
            if score >= 4:
                candidates.append((score, path))
            elif has_basic_sticks and any(token in name for token in ("x-box", "xbox", "pad", "controller", "pdp")):
                fallback_candidates.append((score, path))
        except OSError:
            continue

    if candidates:
        candidates.sort(key=lambda item: (-item[0], item[1]))
        return candidates[0][1]
    if fallback_candidates:
        fallback_candidates.sort(key=lambda item: (-item[0], item[1]))
        return fallback_candidates[0][1]
    return None


def _normalize_signed(value: int, info: AbsInfo) -> float:
    center = (info.min + info.max) / 2.0
    half_range = max(float(info.max) - center, center - float(info.min), 1.0)
    norm = (float(value) - center) / half_range
    return max(-1.0, min(1.0, norm))


def _normalize_unsigned(value: int, info: AbsInfo) -> float:
    span = max(float(info.max) - float(info.min), 1.0)
    norm = (float(value) - float(info.min)) / span
    return max(0.0, min(1.0, norm))


class TcpBridgeBackend:
    def __init__(self, logger, host: str = DEFAULT_BRIDGE_HOST, port: int = DEFAULT_BRIDGE_PORT) -> None:
        self._log = logger
        self._host = host
        self._port = port
        self._lock = threading.Lock()
        self._state = GamepadState()
        self._connected = False
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def read(self) -> Optional[GamepadState]:
        with self._lock:
            if not self._connected:
                return None
            return self._state.copy()

    def close(self) -> None:
        self._stop.set()

    def _update(self, state: GamepadState, connected: bool) -> None:
        with self._lock:
            self._state = state
            self._connected = connected

    def _run(self) -> None:
        while not self._stop.is_set():
            try:
                self._log.info(f"Connecting to gamepad bridge {self._host}:{self._port}…")
                sock = socket.create_connection((self._host, self._port), timeout=5.0)
                sock.settimeout(None)
                self._update(GamepadState(), True)
                self._log.info("Gamepad bridge connected.")

                buffer = b""
                while not self._stop.is_set():
                    chunk = sock.recv(4096)
                    if not chunk:
                        break
                    buffer += chunk
                    while b"\n" in buffer:
                        line, buffer = buffer.split(b"\n", 1)
                        if not line:
                            continue
                        try:
                            payload = json.loads(line)
                        except json.JSONDecodeError:
                            continue
                        self._update(self._from_payload(payload), True)
                sock.close()
                self._log.warn("Bridge connection closed by remote.")
            except (ConnectionRefusedError, TimeoutError, OSError) as exc:
                self._log.warn(f"Bridge: {exc}  — retry in 2 s")
            finally:
                self._update(GamepadState(), False)
            time.sleep(2.0)

    @staticmethod
    def _from_payload(payload: dict) -> GamepadState:
        axes = payload.get("axes", [])
        buttons = payload.get("buttons", [])

        def axis(index: int) -> float:
            if index >= len(axes):
                return 0.0
            return float(axes[index])

        def button(index: int) -> bool:
            if index >= len(buttons):
                return False
            return bool(buttons[index])

        return GamepadState(
            left_x=axis(BRIDGE_AXIS_LEFT_X),
            left_y=axis(BRIDGE_AXIS_LEFT_Y),
            right_y=axis(BRIDGE_AXIS_RIGHT_Y),
            lt=max(0.0, (axis(BRIDGE_AXIS_LT) + 1.0) * 0.5),
            rt=max(0.0, (axis(BRIDGE_AXIS_RT) + 1.0) * 0.5),
            lb=button(BRIDGE_BUTTON_LB),
            rb=button(BRIDGE_BUTTON_RB),
            start=button(BRIDGE_BUTTON_START),
            back=button(BRIDGE_BUTTON_BACK),
            dpad_left=button(BRIDGE_BUTTON_DPAD_LEFT),
            dpad_right=button(BRIDGE_BUTTON_DPAD_RIGHT),
        )


class EvdevBackend:
    def __init__(self, logger, device_path: str = "") -> None:
        self._log = logger
        self._requested_path = device_path
        self._lock = threading.Lock()
        self._state = GamepadState()
        self._connected = False
        self._stop = threading.Event()
        self._device: Optional[InputDevice] = None
        self._device_name = ""
        self._device_path = ""
        self._absinfo: dict[int, AbsInfo] = {}
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def read(self) -> Optional[GamepadState]:
        with self._lock:
            if not self._connected:
                return None
            return self._state.copy()

    def close(self) -> None:
        self._stop.set()
        if self._device is not None:
            try:
                self._device.close()
            except OSError:
                pass

    def _set_state(self, state: GamepadState, connected: bool) -> None:
        with self._lock:
            self._state = state
            self._connected = connected

    def _run(self) -> None:
        while not self._stop.is_set():
            path = detect_evdev_gamepad_path(self._requested_path)
            if path is None:
                self._set_state(GamepadState(), False)
                self._log.warn("No matching evdev gamepad device found — retry in 2 s")
                time.sleep(2.0)
                continue

            try:
                device = InputDevice(path)
                self._device = device
                self._device_name = device.name or path
                self._device_path = path
                self._absinfo = self._load_absinfo(device)
                initial_state = self._snapshot_device_state(device)
                self._set_state(initial_state, True)
                self._log.info(f"Opened evdev gamepad '{self._device_name}' on {self._device_path}")

                for event in device.read_loop():
                    if self._stop.is_set():
                        break
                    if event.type not in (ecodes.EV_ABS, ecodes.EV_KEY):
                        continue
                    self._handle_event(event)
            except OSError as exc:
                if getattr(exc, "errno", None) == 13:
                    self._log.warn(
                        "Cannot open evdev gamepad "
                        f"'{path}': permission denied. "
                        "Make sure this shell is in the 'input' group "
                        "(run `newgrp input` or open a fresh WSL shell after adding the group)."
                    )
                else:
                    self._log.warn(f"evdev gamepad disconnected: {exc}")
            finally:
                self._set_state(GamepadState(), False)
                if self._device is not None:
                    try:
                        self._device.close()
                    except OSError:
                        pass
                self._device = None
                self._absinfo = {}
            time.sleep(1.0)

    def _load_absinfo(self, device: InputDevice) -> dict[int, AbsInfo]:
        infos: dict[int, AbsInfo] = {}
        for code in (ecodes.ABS_X, ecodes.ABS_Y, ecodes.ABS_RY, ecodes.ABS_Z, ecodes.ABS_RZ, ecodes.ABS_HAT0X):
            try:
                infos[code] = device.absinfo(code)
            except OSError:
                continue
        return infos

    def _snapshot_device_state(self, device: InputDevice) -> GamepadState:
        active = set(device.active_keys())
        state = GamepadState(
            lb=ecodes.BTN_TL in active,
            rb=ecodes.BTN_TR in active,
            start=ecodes.BTN_START in active,
            back=ecodes.BTN_SELECT in active,
            dpad_left=ecodes.BTN_DPAD_LEFT in active,
            dpad_right=ecodes.BTN_DPAD_RIGHT in active,
        )
        for code, info in self._absinfo.items():
            if code == ecodes.ABS_X:
                state.left_x = _normalize_signed(info.value, info)
            elif code == ecodes.ABS_Y:
                state.left_y = _normalize_signed(info.value, info)
            elif code == ecodes.ABS_RY:
                state.right_y = _normalize_signed(info.value, info)
            elif code == ecodes.ABS_Z:
                state.lt = _normalize_unsigned(info.value, info)
            elif code == ecodes.ABS_RZ:
                state.rt = _normalize_unsigned(info.value, info)
            elif code == ecodes.ABS_HAT0X:
                state.dpad_left = info.value < 0
                state.dpad_right = info.value > 0
        return state

    def _handle_event(self, event) -> None:
        with self._lock:
            state = self._state.copy()
            if event.type == ecodes.EV_ABS:
                info = self._absinfo.get(event.code)
                if info is None and self._device is not None:
                    try:
                        info = self._device.absinfo(event.code)
                        self._absinfo[event.code] = info
                    except OSError:
                        info = None
                if event.code == ecodes.ABS_X and info is not None:
                    state.left_x = _normalize_signed(event.value, info)
                elif event.code == ecodes.ABS_Y and info is not None:
                    state.left_y = _normalize_signed(event.value, info)
                elif event.code == ecodes.ABS_RY and info is not None:
                    state.right_y = _normalize_signed(event.value, info)
                elif event.code == ecodes.ABS_Z and info is not None:
                    state.lt = _normalize_unsigned(event.value, info)
                elif event.code == ecodes.ABS_RZ and info is not None:
                    state.rt = _normalize_unsigned(event.value, info)
                elif event.code == ecodes.ABS_HAT0X:
                    state.dpad_left = event.value < 0
                    state.dpad_right = event.value > 0
            elif event.type == ecodes.EV_KEY:
                pressed = bool(event.value)
                if event.code == ecodes.BTN_TL:
                    state.lb = pressed
                elif event.code == ecodes.BTN_TR:
                    state.rb = pressed
                elif event.code == ecodes.BTN_START:
                    state.start = pressed
                elif event.code == ecodes.BTN_SELECT:
                    state.back = pressed
                elif event.code == ecodes.BTN_DPAD_LEFT:
                    state.dpad_left = pressed
                elif event.code == ecodes.BTN_DPAD_RIGHT:
                    state.dpad_right = pressed
            self._state = state


class PygameJoystickBackend:
    def __init__(self, logger, device_index: int = DEFAULT_DEVICE_INDEX) -> None:
        self._log = logger
        self._device_index = int(device_index)
        os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
        import pygame

        self._pygame = pygame
        pygame.init()
        pygame.joystick.init()
        if pygame.joystick.get_count() == 0:
            raise RuntimeError("no joystick")

        self._js = pygame.joystick.Joystick(self._device_index)
        self._js.init()
        self._hat_count = self._js.get_numhats()
        self._log.info(
            f"Opened legacy pygame joystick '{self._js.get_name()}' "
            f"(axes={self._js.get_numaxes()}, buttons={self._js.get_numbuttons()}, hats={self._hat_count})"
        )

    def read(self) -> Optional[GamepadState]:
        self._pygame.event.pump()
        dpad_left = False
        dpad_right = False
        if self._hat_count > 0:
            hat_x, _hat_y = self._js.get_hat(0)
            dpad_left = hat_x < 0
            dpad_right = hat_x > 0
        return GamepadState(
            left_x=float(self._js.get_axis(BRIDGE_AXIS_LEFT_X)),
            left_y=float(self._js.get_axis(BRIDGE_AXIS_LEFT_Y)),
            right_y=float(self._js.get_axis(BRIDGE_AXIS_RIGHT_Y)),
            lt=max(0.0, (float(self._js.get_axis(BRIDGE_AXIS_LT)) + 1.0) * 0.5),
            rt=max(0.0, (float(self._js.get_axis(BRIDGE_AXIS_RT)) + 1.0) * 0.5),
            lb=bool(self._js.get_button(BRIDGE_BUTTON_LB)),
            rb=bool(self._js.get_button(BRIDGE_BUTTON_RB)),
            start=bool(self._js.get_button(BRIDGE_BUTTON_START)),
            back=bool(self._js.get_button(BRIDGE_BUTTON_BACK)),
            dpad_left=dpad_left or bool(self._js.get_button(BRIDGE_BUTTON_DPAD_LEFT)),
            dpad_right=dpad_right or bool(self._js.get_button(BRIDGE_BUTTON_DPAD_RIGHT)),
        )

    def close(self) -> None:
        try:
            self._pygame.joystick.quit()
            self._pygame.quit()
        except Exception:
            pass


def create_backend(
    backend_name: str,
    logger,
    *,
    device_index: int = DEFAULT_DEVICE_INDEX,
    event_device_path: str = "",
    tcp_bridge_host: str = DEFAULT_BRIDGE_HOST,
    tcp_bridge_port: int = DEFAULT_BRIDGE_PORT,
):
    if backend_name == "evdev":
        return EvdevBackend(logger, device_path=event_device_path)
    if backend_name == "tcp_bridge":
        return TcpBridgeBackend(logger, host=tcp_bridge_host, port=tcp_bridge_port)
    if backend_name == "pygame_joystick":
        return PygameJoystickBackend(logger, device_index=device_index)
    raise ValueError(f"Unsupported input backend: {backend_name}")
