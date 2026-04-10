"""ROS 2 node wrapping the Waveshare RoArm-M2-S USB serial driver.

Topics (all use URDF-positive joint convention — sign conversion to the arm's
native frame happens inside `roarm_protocol.RoArmProtocol`):

  Published:
    /joint_states  sensor_msgs/JointState   @ ~publish_rate Hz
        Real joint angles read from the arm via T:105 / T:1051.
        'name' uses the 4 URDF joint names (see roarm_protocol.URDF_JOINT_NAMES).

  Subscribed:
    /joint_command sensor_msgs/JointState
        Desired joint positions. The node looks up each name in URDF_JOINT_NAMES,
        clamps to joint limits, and forwards via T:102.
        Unspecified joints keep their last commanded value.

    /gripper_command std_msgs/Float32
        Convenience shortcut to move only the gripper.
        Value 0.0 = fully closed, 1.5 = fully open.
        Equivalent to publishing a JointState with only 'link3_to_gripper_link'.

  Parameters:
    serial_port    string  default '/dev/ttyUSB0'
    baud_rate      int     default 115200
    publish_rate   double  default 20.0   (Hz for /joint_states polling)
    send_on_init   bool    default True   (send T:605 at startup)
"""

from __future__ import annotations

import math
import threading
from typing import List

import rclpy
from rclpy.node import Node
from sensor_msgs.msg import JointState
from std_msgs.msg import Float32

from .roarm_protocol import (
    DEFAULT_BAUD,
    DEFAULT_PORT,
    JOINT_LIMITS,
    URDF_JOINT_NAMES,
    RoArmProtocol,
    clamp_urdf,
)


HOME_POSE = [0.0, 0.0, math.pi / 2, 0.75]  # safe midpoint, gripper half-open


class ArmDriverNode(Node):
    def __init__(self) -> None:
        super().__init__("arm_driver")

        # ---------- parameters ----------
        self.declare_parameter("serial_port", DEFAULT_PORT)
        self.declare_parameter("baud_rate", DEFAULT_BAUD)
        self.declare_parameter("publish_rate", 20.0)
        self.declare_parameter("send_on_init", True)

        port = self.get_parameter("serial_port").get_parameter_value().string_value
        baud = self.get_parameter("baud_rate").get_parameter_value().integer_value
        rate = self.get_parameter("publish_rate").get_parameter_value().double_value
        do_init = self.get_parameter("send_on_init").get_parameter_value().bool_value

        # ---------- open serial port ----------
        try:
            self.arm = RoArmProtocol(port=port, baud=baud)
        except Exception as e:
            self.get_logger().error(f"Cannot open {port}@{baud}: {e}")
            raise

        self.get_logger().info(f"Connected to RoArm-M2-S at {port} @ {baud}")
        if do_init:
            self.arm.startup()
            self.get_logger().info("Sent T:605 startup packet")

        # ---------- state ----------
        # Last commanded URDF-convention joint positions (preserved between partial commands)
        self._last_cmd: List[float] = list(HOME_POSE)
        self._latest_state: List[float] | None = None
        self._cmd_lock = threading.Lock()

        # ---------- publishers ----------
        self.joint_states_pub = self.create_publisher(JointState, "/joint_states", 10)

        # ---------- subscribers ----------
        self.create_subscription(JointState, "/joint_command", self._on_joint_command, 10)
        self.create_subscription(Float32, "/gripper_command", self._on_gripper_command, 10)
        self.create_subscription(Float32, "/led_command", self._on_led_command, 10)

        # ---------- polling timer ----------
        period = 1.0 / max(1.0, rate)
        self._poll_timer = self.create_timer(period, self._poll_state)
        self.get_logger().info(f"Polling /joint_states @ {rate:.1f} Hz")

    # ----------------------------------------------------------------
    # Polling loop
    # ----------------------------------------------------------------
    def _poll_state(self) -> None:
        try:
            state = self.arm.fetch_state()
        except Exception as e:
            self.get_logger().warn(f"fetch_state failed: {e}")
            return
        if state is None:
            # arm may still be booting, or the ESP32 is busy — don't spam logs
            return

        msg = JointState()
        msg.header.stamp = self.get_clock().now().to_msg()
        msg.name = list(URDF_JOINT_NAMES)
        msg.position = list(state.joint_positions())
        msg.effort = [state.tor_base, state.tor_shoulder, state.tor_elbow, state.tor_hand]
        with self._cmd_lock:
            self._latest_state = list(msg.position)
        self.joint_states_pub.publish(msg)

    # ----------------------------------------------------------------
    # Joint command handling
    # ----------------------------------------------------------------
    def _on_joint_command(self, msg: JointState) -> None:
        if not msg.name or not msg.position:
            self.get_logger().warn("joint_command has empty name/position")
            return
        if len(msg.name) != len(msg.position):
            self.get_logger().warn("joint_command name/position length mismatch")
            return

        with self._cmd_lock:
            for name, pos in zip(msg.name, msg.position):
                if name not in URDF_JOINT_NAMES:
                    self.get_logger().warn(f"Unknown joint in command: '{name}'")
                    continue
                idx = URDF_JOINT_NAMES.index(name)
                self._last_cmd[idx] = float(pos)

            clamped = clamp_urdf(self._last_cmd)
            if clamped != self._last_cmd:
                for i, (raw, cl) in enumerate(zip(self._last_cmd, clamped)):
                    if raw != cl:
                        lo, hi = JOINT_LIMITS[URDF_JOINT_NAMES[i]]
                        self.get_logger().warn(
                            f"{URDF_JOINT_NAMES[i]} clamped {raw:+.3f} -> {cl:+.3f} "
                            f"(limit [{lo:+.3f}, {hi:+.3f}])"
                        )
                self._last_cmd = clamped

        try:
            self.arm.set_joints_urdf(*self._last_cmd)
        except Exception as e:
            self.get_logger().error(f"set_joints_urdf failed: {e}")

    def _on_led_command(self, msg: Float32) -> None:
        try:
            self.arm.set_led(float(msg.data))
        except Exception as e:
            self.get_logger().error(f"set_led failed: {e}")

    def _on_gripper_command(self, msg: Float32) -> None:
        # Use the arm's dedicated EOAT command so pure gripper control does not
        # resend a full-body T:102 target and disturb the other joints.
        with self._cmd_lock:
            self._last_cmd[3] = float(msg.data)
            self._last_cmd = clamp_urdf(self._last_cmd)
        try:
            self.arm.set_gripper_urdf(self._last_cmd[3])
        except Exception as e:
            self.get_logger().error(f"set_gripper_urdf failed: {e}")

    # ----------------------------------------------------------------
    # Shutdown
    # ----------------------------------------------------------------
    def destroy_node(self) -> bool:
        try:
            self.arm.close()
        except Exception:
            pass
        return super().destroy_node()


def main(args=None) -> None:
    rclpy.init(args=args)
    try:
        node = ArmDriverNode()
    except Exception as e:
        print(f"[arm_driver_node] startup failed: {e}")
        rclpy.shutdown()
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
