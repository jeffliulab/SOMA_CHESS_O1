import pytest
from pathlib import Path
import sys


ARM_TELEOP_ROOT = Path(__file__).resolve().parents[1]
if str(ARM_TELEOP_ROOT) not in sys.path:
    sys.path.insert(0, str(ARM_TELEOP_ROOT))

from arm_teleop.control_filters import SlewRateLimiter


def test_slew_rate_limiter_ramps_up_instead_of_jumping_to_target():
    limiter = SlewRateLimiter(accel_rate=2.0, decel_rate=4.0)

    value = limiter.step(1.0, 0.1)

    assert value == 0.2


def test_slew_rate_limiter_decelerates_faster_than_it_accelerates():
    limiter = SlewRateLimiter(accel_rate=2.0, decel_rate=6.0)

    limiter.step(1.0, 0.2)  # -> 0.4
    value = limiter.step(0.0, 0.05)

    assert value == pytest.approx(0.1)


def test_slew_rate_limiter_can_reset():
    limiter = SlewRateLimiter(accel_rate=2.0, decel_rate=6.0)

    limiter.step(1.0, 0.2)
    limiter.reset()

    assert limiter.value == 0.0
