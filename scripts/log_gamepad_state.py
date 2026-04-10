#!/usr/bin/env python3
"""Log normalized GamepadState samples for backend A/B comparison."""

from __future__ import annotations

import argparse
from dataclasses import asdict
import json
import logging
from pathlib import Path
import sys
import time


ROOT = Path(__file__).resolve().parents[1]
ARM_TELEOP_SRC = ROOT / "src" / "arm_teleop"
if str(ARM_TELEOP_SRC) not in sys.path:
    sys.path.insert(0, str(ARM_TELEOP_SRC))

from arm_teleop.gamepad_input import (  # noqa: E402
    DEFAULT_DEAD_ZONE,
    DEFAULT_TRIGGER_THRESHOLD,
    TeleopInputFilter,
    create_backend,
)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--backend", choices=("evdev", "tcp_bridge", "pygame_joystick"), default="evdev")
    parser.add_argument("--event-device-path", default="")
    parser.add_argument("--device-index", type=int, default=0)
    parser.add_argument("--tcp-bridge-host", default="127.0.0.1")
    parser.add_argument("--tcp-bridge-port", type=int, default=65432)
    parser.add_argument("--duration", type=float, default=30.0)
    parser.add_argument("--interval", type=float, default=0.02)
    parser.add_argument("--output", default="")
    parser.add_argument("--view", choices=("raw", "filtered"), default="raw")
    parser.add_argument("--dead-zone", type=float, default=DEFAULT_DEAD_ZONE)
    parser.add_argument("--trigger-threshold", type=float, default=DEFAULT_TRIGGER_THRESHOLD)
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(message)s")
    log = logging.getLogger("gamepad_state")
    backend = create_backend(
        args.backend,
        log,
        event_device_path=args.event_device_path,
        device_index=args.device_index,
        tcp_bridge_host=args.tcp_bridge_host,
        tcp_bridge_port=args.tcp_bridge_port,
    )
    state_filter = None
    if args.view == "filtered":
        state_filter = TeleopInputFilter(
            dead_zone=args.dead_zone,
            trigger_threshold=args.trigger_threshold,
        )

    out = open(args.output, "w", encoding="utf-8") if args.output else None
    end_time = time.time() + max(0.0, args.duration)
    last_payload = None

    try:
        while time.time() < end_time:
            state = backend.read()
            if state is None:
                time.sleep(args.interval)
                continue
            if state_filter is not None:
                state = state_filter.process(state)
            payload = asdict(state)
            if payload != last_payload:
                line = json.dumps({"t": time.time(), **payload}, ensure_ascii=False)
                print(line)
                if out is not None:
                    out.write(line + "\n")
                    out.flush()
                last_payload = payload
            time.sleep(args.interval)
    except KeyboardInterrupt:
        return 0
    finally:
        backend.close()
        if out is not None:
            out.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
