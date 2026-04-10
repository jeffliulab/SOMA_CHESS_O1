from pathlib import Path
import sys


ARM_TELEOP_ROOT = Path(__file__).resolve().parents[1]
if str(ARM_TELEOP_ROOT) not in sys.path:
    sys.path.insert(0, str(ARM_TELEOP_ROOT))

from arm_teleop.gamepad_input import GamepadState, TeleopInputFilter


def test_left_stick_x_lock_zeroes_cross_axis():
    filt = TeleopInputFilter(dead_zone=0.15, trigger_threshold=0.15)

    state = filt.process(GamepadState(left_x=-0.95, left_y=0.27))

    assert state.left_x == -0.95
    assert state.left_y == 0.0
    assert filt.left_stick_lock == "x"


def test_left_stick_lock_holds_until_both_axes_return_to_center():
    filt = TeleopInputFilter(dead_zone=0.15, trigger_threshold=0.15)

    filt.process(GamepadState(left_x=-0.95, left_y=0.27))
    state = filt.process(GamepadState(left_x=0.05, left_y=0.30))

    assert state.left_x == 0.0
    assert state.left_y == 0.0
    assert filt.left_stick_lock == "x"


def test_left_stick_can_switch_axes_after_returning_to_center():
    filt = TeleopInputFilter(dead_zone=0.15, trigger_threshold=0.15)

    filt.process(GamepadState(left_x=-0.95, left_y=0.27))
    filt.process(GamepadState(left_x=0.05, left_y=0.05))
    state = filt.process(GamepadState(left_x=0.08, left_y=-0.92))

    assert state.left_x == 0.0
    assert state.left_y == -0.92
    assert filt.left_stick_lock == "y"


def test_right_stick_and_triggers_are_preserved():
    filt = TeleopInputFilter(dead_zone=0.15, trigger_threshold=0.15)

    state = filt.process(GamepadState(left_x=0.02, left_y=0.01, right_y=-0.75, lt=0.12, rt=0.8))

    assert state.left_x == 0.0
    assert state.left_y == 0.0
    assert state.right_y == -0.75
    assert state.lt == 0.0
    assert state.rt == 0.8
