#!/usr/bin/env python3
"""Probe Linux gamepad input without touching the robot.

Default mode reads raw evdev events, which matches the production WSL-local
teleop path. Pass `--backend pygame` only if you explicitly want to compare
against the legacy joystick API.
"""

from __future__ import annotations

import argparse
from pathlib import Path
import sys
import time

from evdev import InputDevice, ecodes


ROOT = Path(__file__).resolve().parents[1]
ARM_TELEOP_SRC = ROOT / "src" / "arm_teleop"
if str(ARM_TELEOP_SRC) not in sys.path:
    sys.path.insert(0, str(ARM_TELEOP_SRC))

from arm_teleop.gamepad_input import detect_evdev_gamepad_path  # noqa: E402


def probe_evdev(device_path: str) -> int:
    path = detect_evdev_gamepad_path(device_path)
    if not path:
        print("No matching evdev gamepad device found.")
        return 1

    device = InputDevice(path)
    print(f"device={device.path} name={device.name}")
    print("Press Ctrl+C to exit.")

    try:
        for event in device.read_loop():
            if event.type == ecodes.EV_ABS:
                print(f"abs[{ecodes.bytype[ecodes.EV_ABS].get(event.code, event.code)}]={event.value}")
            elif event.type == ecodes.EV_KEY:
                print(f"key[{ecodes.bytype[ecodes.EV_KEY].get(event.code, event.code)}]={event.value}")
    except KeyboardInterrupt:
        return 0
    finally:
        try:
            device.close()
        except OSError:
            pass


def probe_pygame() -> int:
    import pygame

    pygame.init()
    pygame.joystick.init()

    count = pygame.joystick.get_count()
    print(f"joystick_count={count}")
    if count == 0:
        print("No joystick found.")
        pygame.quit()
        return 1

    js = pygame.joystick.Joystick(0)
    js.init()
    print(
        f"name={js.get_name()} axes={js.get_numaxes()} "
        f"buttons={js.get_numbuttons()} hats={js.get_numhats()}"
    )
    print("Press Ctrl+C to exit.")

    last_axes = [None] * js.get_numaxes()
    last_buttons = [None] * js.get_numbuttons()
    last_hats = [None] * js.get_numhats()

    try:
        while True:
            pygame.event.pump()
            for i in range(js.get_numaxes()):
                value = round(js.get_axis(i), 3)
                if last_axes[i] != value:
                    last_axes[i] = value
                    print(f"axis[{i}]={value:+.3f}")
            for i in range(js.get_numbuttons()):
                value = js.get_button(i)
                if last_buttons[i] != value:
                    last_buttons[i] = value
                    print(f"button[{i}]={value}")
            for i in range(js.get_numhats()):
                value = js.get_hat(i)
                if last_hats[i] != value:
                    last_hats[i] = value
                    print(f"hat[{i}]={value}")
            time.sleep(0.02)
    except KeyboardInterrupt:
        return 0
    finally:
        pygame.quit()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--backend", choices=("evdev", "pygame"), default="evdev")
    parser.add_argument("--event-device-path", default="")
    args = parser.parse_args()

    if args.backend == "pygame":
        return probe_pygame()
    return probe_evdev(args.event_device_path)


if __name__ == "__main__":
    raise SystemExit(main())
