"""Gamepad teleoperation of RoArm-M2-S.

Primary workflow:
  - Xbox/PDP controller is attached directly into WSL via usbipd-win
  - Linux reads the controller from `/dev/input/event*`
  - `evdev` normalizes raw events into a canonical `GamepadState`
  - teleop integrates that state into a single joint target vector and
    publishes `/joint_command`

Fallback workflow:
  - keep the controller on Windows
  - run `scripts/bridge方案/bridge_gui.py`
  - launch with `use_tcp_bridge:=true`

Visible control mapping is the same across backends:

    Left stick X      -> base yaw
    Left stick Y      -> shoulder
    Right stick Y     -> elbow
    LB or RB          -> gripper close
    LT or RT          -> gripper open
    Start             -> re-enable + go home
    Back              -> emergency stop
    DPAD left/right   -> LED brightness
"""

from __future__ import annotations

import time

import rclpy
from rclpy.node import Node
from sensor_msgs.msg import JointState
from std_msgs.msg import Float32

from arm_driver.roarm_protocol import URDF_JOINT_NAMES, clamp_urdf

from .control_filters import SlewRateLimiter
from .gamepad_input import (
    DEFAULT_DEAD_ZONE,
    DEFAULT_TRIGGER_THRESHOLD,
    TeleopInputFilter,
    create_backend,
)


HOME_POSE = [0.0, 0.0, 1.5708, 0.75]

DEAD_ZONE = DEFAULT_DEAD_ZONE
TRIGGER_THRESHOLD = DEFAULT_TRIGGER_THRESHOLD
LED_STEP = 0.1

MAX_VEL_BASE = 1.2
MAX_VEL_SHOULDER = 0.9
MAX_VEL_ELBOW = 1.0
BASE_ACCEL_RATE = 3.0
BASE_DECEL_RATE = 7.0
SHOULDER_ACCEL_RATE = 2.5
SHOULDER_DECEL_RATE = 6.0
ELBOW_ACCEL_RATE = 2.5
ELBOW_DECEL_RATE = 6.0
GRIPPER_BASE_SPEED = 1.0
CONTROL_HZ = 50.0
ENABLE_MOTION_SMOOTHING = False


class GamepadTeleopNode(Node):
    def __init__(self) -> None:
        super().__init__("gamepad_teleop")

        self.declare_parameter("device_index", 0)
        self.declare_parameter("dead_zone", DEAD_ZONE)
        self.declare_parameter("trigger_threshold", TRIGGER_THRESHOLD)
        self.declare_parameter("control_hz", CONTROL_HZ)
        self.declare_parameter("enable_motion_smoothing", ENABLE_MOTION_SMOOTHING)
        self.declare_parameter("base_accel_rate", BASE_ACCEL_RATE)
        self.declare_parameter("base_decel_rate", BASE_DECEL_RATE)
        self.declare_parameter("shoulder_accel_rate", SHOULDER_ACCEL_RATE)
        self.declare_parameter("shoulder_decel_rate", SHOULDER_DECEL_RATE)
        self.declare_parameter("elbow_accel_rate", ELBOW_ACCEL_RATE)
        self.declare_parameter("elbow_decel_rate", ELBOW_DECEL_RATE)
        self.declare_parameter("input_backend", "evdev")
        self.declare_parameter("event_device_path", "")
        self.declare_parameter("use_tcp_bridge", False)
        self.declare_parameter("tcp_bridge_host", "127.0.0.1")
        self.declare_parameter("tcp_bridge_port", 65432)

        p = self.get_parameter
        self._dead_zone = float(p("dead_zone").value)
        self._trigger_threshold = float(p("trigger_threshold").value)
        self._control_hz = max(1.0, float(p("control_hz").value))
        self._enable_motion_smoothing = bool(p("enable_motion_smoothing").value)
        self._base_accel_rate = float(p("base_accel_rate").value)
        self._base_decel_rate = float(p("base_decel_rate").value)
        self._shoulder_accel_rate = float(p("shoulder_accel_rate").value)
        self._shoulder_decel_rate = float(p("shoulder_decel_rate").value)
        self._elbow_accel_rate = float(p("elbow_accel_rate").value)
        self._elbow_decel_rate = float(p("elbow_decel_rate").value)
        self._input_backend = str(p("input_backend").value).strip() or "evdev"
        self._event_device_path = str(p("event_device_path").value).strip()
        self._use_tcp_bridge = bool(p("use_tcp_bridge").value)
        self._tcp_bridge_host = str(p("tcp_bridge_host").value)
        self._tcp_bridge_port = int(p("tcp_bridge_port").value)
        self._device_index = int(p("device_index").value)

        if self._use_tcp_bridge and self._input_backend != "tcp_bridge":
            self.get_logger().info(
                "use_tcp_bridge:=true requested — forcing input_backend=tcp_bridge."
            )
            self._input_backend = "tcp_bridge"

        self._backend = create_backend(
            self._input_backend,
            self.get_logger(),
            device_index=self._device_index,
            event_device_path=self._event_device_path,
            tcp_bridge_host=self._tcp_bridge_host,
            tcp_bridge_port=self._tcp_bridge_port,
        )
        self._input_filter = TeleopInputFilter(
            dead_zone=self._dead_zone,
            trigger_threshold=self._trigger_threshold,
        )
        self._base_limiter = SlewRateLimiter(self._base_accel_rate, self._base_decel_rate)
        self._shoulder_limiter = SlewRateLimiter(
            self._shoulder_accel_rate, self._shoulder_decel_rate
        )
        self._elbow_limiter = SlewRateLimiter(self._elbow_accel_rate, self._elbow_decel_rate)

        self.cmd_pub = self.create_publisher(JointState, "/joint_command", 10)
        self.gripper_pub = self.create_publisher(Float32, "/gripper_command", 10)
        self.led_pub = self.create_publisher(Float32, "/led_command", 10)
        self.create_subscription(JointState, "/joint_states", self._on_joint_states, 10)

        self._target = list(HOME_POSE)
        self._current_joint_state: list[float] | None = None
        self._target_initialized = False
        self._last_pub_target = list(self._target)
        self._last_tick = time.time()
        self._estop = False
        self._led_level = 0.5
        self._prev_start = False
        self._prev_back = False
        self._prev_dpad_left = False
        self._prev_dpad_right = False

        self.create_timer(1.0 / self._control_hz, self._tick)
        self.get_logger().info(
            f"Teleop ready with backend={self._input_backend}. "
            "Waiting for /joint_states before taking control. "
            "Left=base/shoulder, Right=elbow, LB/RB=gripper close, "
            "LT/RT=gripper open, Start=home, Back=e-stop. "
            f"motion_smoothing={'on' if self._enable_motion_smoothing else 'off'}."
        )

    def _on_joint_states(self, msg: JointState) -> None:
        if not msg.name or not msg.position:
            return
        try:
            indices = {name: i for i, name in enumerate(msg.name)}
            current = [float(msg.position[indices[name]]) for name in URDF_JOINT_NAMES]
        except KeyError:
            return

        self._current_joint_state = current
        if not self._target_initialized:
            self._target = list(current)
            self._last_pub_target = list(current)

    def _ensure_target_initialized(self) -> bool:
        if self._target_initialized:
            return True
        if self._current_joint_state is None:
            self.get_logger().warn(
                "Teleop input ignored: waiting for first /joint_states sample from arm_driver."
            )
            return False
        self._target = list(self._current_joint_state)
        self._last_pub_target = list(self._current_joint_state)
        self._target_initialized = True
        self.get_logger().info("Teleop target initialized from current /joint_states.")
        return True

    def _tick(self) -> None:
        now = time.time()
        dt = max(0.001, min(now - self._last_tick, 2.0 / self._control_hz))
        self._last_tick = now

        raw_state = self._backend.read()
        if raw_state is None:
            return
        state = self._input_filter.process(raw_state)

        if state.dpad_right and not self._prev_dpad_right:
            self._led_level = min(1.0, self._led_level + LED_STEP)
            self.led_pub.publish(Float32(data=self._led_level))
            self.get_logger().info(f"LED brightness: {self._led_level:.1f}")
        if state.dpad_left and not self._prev_dpad_left:
            self._led_level = max(0.0, self._led_level - LED_STEP)
            self.led_pub.publish(Float32(data=self._led_level))
            self.get_logger().info(f"LED brightness: {self._led_level:.1f}")

        if state.back and not self._prev_back:
            if not self._estop:
                self.get_logger().warn("EMERGENCY STOP — press Start (≡) to recover")
            self._estop = True
            self._remember_buttons(state)
            return

        if state.start and not self._prev_start:
            if not self._ensure_target_initialized():
                self._remember_buttons(state)
                return
            self.get_logger().info("Start pressed — re-enabled, going home")
            self._estop = False
            self._reset_motion_limiters()
            self._target = list(HOME_POSE)
            self._publish_target()
            self._remember_buttons(state)
            return

        if self._estop:
            self._reset_motion_limiters()
            self._remember_buttons(state)
            return

        desired_base_vel = state.left_x * MAX_VEL_BASE
        desired_shoulder_vel = (-state.left_y) * MAX_VEL_SHOULDER
        desired_elbow_vel = state.right_y * MAX_VEL_ELBOW
        if self._enable_motion_smoothing:
            base_vel = self._base_limiter.step(desired_base_vel, dt)
            shoulder_vel = self._shoulder_limiter.step(desired_shoulder_vel, dt)
            elbow_vel = self._elbow_limiter.step(desired_elbow_vel, dt)
        else:
            base_vel = desired_base_vel
            shoulder_vel = desired_shoulder_vel
            elbow_vel = desired_elbow_vel

        arm_motion_requested = any(
            abs(v) > 1e-6 for v in (base_vel, shoulder_vel, elbow_vel)
        )
        gripper_open = max(state.lt, state.rt)
        gripper_requested = state.lb or state.rb or gripper_open > 0.0
        if (arm_motion_requested or gripper_requested) and not self._ensure_target_initialized():
            self._remember_buttons(state)
            return

        if arm_motion_requested:
            self._target[0] += base_vel * dt
            self._target[1] += shoulder_vel * dt
            self._target[2] += elbow_vel * dt

            self._apply_gripper_delta(state, gripper_open, dt)
            self._target = clamp_urdf(self._target)
            if self._target != self._last_pub_target:
                self._publish_target()
        elif gripper_requested:
            # Keep teleop's body target aligned to the latest measured pose so
            # returning from a gripper-only gesture does not resurrect an older
            # base/shoulder/elbow target.
            if self._current_joint_state is not None:
                self._target[:3] = self._current_joint_state[:3]
            self._apply_gripper_delta(state, gripper_open, dt)
            self._target = clamp_urdf(self._target)
            if self._target[3] != self._last_pub_target[3]:
                self._publish_gripper_target()
            self._was_moving = False

        self._remember_buttons(state)

    def _remember_buttons(self, state) -> None:
        self._prev_start = state.start
        self._prev_back = state.back
        self._prev_dpad_left = state.dpad_left
        self._prev_dpad_right = state.dpad_right

    def _publish_target(self) -> None:
        msg = JointState()
        msg.header.stamp = self.get_clock().now().to_msg()
        msg.name = list(URDF_JOINT_NAMES)
        msg.position = list(self._target)
        self.cmd_pub.publish(msg)
        self._last_pub_target = list(self._target)

    def _publish_gripper_target(self) -> None:
        self.gripper_pub.publish(Float32(data=float(self._target[3])))
        self._last_pub_target[3] = self._target[3]

    def _apply_gripper_delta(self, state, gripper_open: float, dt: float) -> None:
        if state.lb or state.rb:
            self._target[3] -= GRIPPER_BASE_SPEED * dt
        elif gripper_open > 0.0:
            self._target[3] += GRIPPER_BASE_SPEED * gripper_open * dt

    def _reset_motion_limiters(self) -> None:
        self._base_limiter.reset()
        self._shoulder_limiter.reset()
        self._elbow_limiter.reset()

    def destroy_node(self) -> bool:
        try:
            self._backend.close()
        except Exception:
            pass
        return super().destroy_node()


def main(args=None) -> None:
    rclpy.init(args=args)
    try:
        node = GamepadTeleopNode()
    except Exception as exc:
        print(f"[gamepad_teleop_node] startup failed: {exc}")
        rclpy.try_shutdown()
        return
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        try:
            node.destroy_node()
        except Exception:
            pass
        try:
            rclpy.try_shutdown()
        except Exception:
            pass


if __name__ == "__main__":
    main()
