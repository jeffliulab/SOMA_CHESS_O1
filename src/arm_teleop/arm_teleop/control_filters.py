"""Small control-side filters used by teleop."""

from __future__ import annotations

import math


class SlewRateLimiter:
    """Limit how quickly a command can change.

    This gives teleop a small amount of start/stop smoothing without turning
    the control feel into true "coast" or inertia.
    """

    def __init__(self, accel_rate: float, decel_rate: float) -> None:
        self._accel_rate = abs(float(accel_rate))
        self._decel_rate = abs(float(decel_rate))
        self._value = 0.0

    @property
    def value(self) -> float:
        return self._value

    def reset(self, value: float = 0.0) -> None:
        self._value = float(value)

    def step(self, target: float, dt: float) -> float:
        target = float(target)
        dt = max(0.0, float(dt))
        delta = target - self._value
        if delta == 0.0 or dt == 0.0:
            return self._value

        same_direction = self._value == 0.0 or target == 0.0 or math.copysign(1.0, self._value) == math.copysign(1.0, target)
        increasing_magnitude = abs(target) > abs(self._value)
        rate = self._accel_rate if same_direction and increasing_magnitude else self._decel_rate
        max_step = rate * dt
        if abs(delta) <= max_step:
            self._value = target
        else:
            self._value += math.copysign(max_step, delta)
        return self._value
