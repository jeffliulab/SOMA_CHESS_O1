"""MoveIt2-side bridge node for the RoArm-M2-S.

Background — why this node exists
---------------------------------
Waveshare's upstream MoveIt2 setup (`roarm_moveit/`) plans trajectories
against a *mock* hardware interface (`mock_components/GenericSystem`). The mock
"executes" trajectories instantly, then `joint_state_broadcaster` republishes
the resulting "current" joint positions on `/joint_states`. The real arm is
driven via a side-channel: a small bridge node subscribes to `/joint_states`
and forwards the values to the real serial port.

This node *is* that side-channel bridge — but written by us, so the public
SmartRobotArm repo stays Apache-2.0 clean and reuses our existing protocol
layer (`roarm_protocol.py`) instead of duplicating it.

Architecture (only relevant when launching MoveIt2 — not used by our teleop)::

    RViz MotionPlanning  ──>  move_group  ──>  joint_trajectory_controller
                                                        │
                                                        ▼
                                          mock_components/GenericSystem
                                                        │
                                                        ▼
                                            joint_state_broadcaster
                                                        │
                                            publishes /joint_states
                                                        │
                                                        ▼
                                  THIS NODE  (moveit_bridge_node)
                                                        │
                                          set_joints_urdf via T:102
                                                        │
                                                        ▼
                                              RoArm-M2-S (real)

Topics:
    /joint_states  sensor_msgs/msg/JointState   subscribed
        Published by joint_state_broadcaster as a side-effect of MoveIt2
        execution. Used here as the *desired* joint position stream.

Parameters:
    serial_port    string  default '/dev/ttyUSB0'
    baud_rate      int     default 115200
    rate_limit_hz  double  default 50.0
        Maximum frequency at which we forward to the serial port. The
        joint_state_broadcaster typically publishes faster than the arm can
        absorb, so we throttle to avoid back-pressure on the ESP32.

⚠ DO NOT run this node at the same time as `arm_driver_node`. Both open the
same /dev/ttyUSB0 — only one process can hold the serial port at a time.
Use `arm_driver_node` for our own teleop / direct command pipeline, and
`moveit_bridge_node` for MoveIt2-driven motion.
"""

from __future__ import annotations

import time

import rclpy
from rclpy.node import Node
from sensor_msgs.msg import JointState

from .roarm_protocol import (
    DEFAULT_BAUD,
    DEFAULT_PORT,
    URDF_JOINT_NAMES,
    RoArmProtocol,
    clamp_urdf,
)


class MoveItBridgeNode(Node):
    def __init__(self) -> None:
        super().__init__("moveit_bridge")

        # ---------- parameters ----------
        self.declare_parameter("serial_port", DEFAULT_PORT)
        self.declare_parameter("baud_rate", DEFAULT_BAUD)
        self.declare_parameter("rate_limit_hz", 50.0)

        port = self.get_parameter("serial_port").get_parameter_value().string_value
        baud = self.get_parameter("baud_rate").get_parameter_value().integer_value
        rate_hz = self.get_parameter("rate_limit_hz").get_parameter_value().double_value
        self._min_period = 1.0 / max(1.0, rate_hz)

        # ---------- open serial ----------
        try:
            self.arm = RoArmProtocol(port=port, baud=baud)
        except Exception as e:
            self.get_logger().error(f"Cannot open {port}@{baud}: {e}")
            raise

        self.get_logger().info(f"MoveIt bridge connected to RoArm-M2-S at {port} @ {baud}")
        self.arm.startup()
        self.get_logger().info("Sent T:605 startup packet")

        # ---------- subscriber ----------
        self.create_subscription(JointState, "/joint_states", self._on_joint_states, 10)

        self._last_send_time = 0.0
        self._last_target: list[float] | None = None

        self.get_logger().info(
            "Subscribed to /joint_states. Waiting for MoveIt2 to publish... "
            f"(rate-limited to {rate_hz:.0f} Hz)"
        )

    # ----------------------------------------------------------------
    def _on_joint_states(self, msg: JointState) -> None:
        if not msg.name or not msg.position:
            return

        # Pick our 4 joints out of whatever order MoveIt sends them in
        try:
            indices = {n: i for i, n in enumerate(msg.name)}
            target = [float(msg.position[indices[name]]) for name in URDF_JOINT_NAMES]
        except KeyError as e:
            # MoveIt2 might publish a joint_states with extra/different joints during init
            self.get_logger().warn_once(
                f"Missing expected joint in /joint_states: {e}"
            ) if hasattr(self.get_logger(), "warn_once") else self.get_logger().warn(
                f"Missing expected joint in /joint_states: {e}"
            )
            return

        # Clamp to URDF joint limits (defense in depth — MoveIt should already respect these)
        target = clamp_urdf(target)

        # Rate limit
        now = time.time()
        if now - self._last_send_time < self._min_period:
            self._last_target = target
            return

        # Send to serial
        try:
            self.arm.set_joints_urdf(*target)
            self._last_send_time = now
            self._last_target = target
        except Exception as e:
            self.get_logger().error(f"set_joints_urdf failed: {e}")

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
        node = MoveItBridgeNode()
    except Exception as e:
        print(f"[moveit_bridge_node] startup failed: {e}")
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
