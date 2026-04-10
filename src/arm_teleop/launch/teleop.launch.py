"""One-shot teleop launch: start arm_driver + gamepad_teleop together.

Usage:
    # Preferred mode: controller attached directly into WSL and read via evdev.
    ros2 launch arm_teleop teleop.launch.py
    ros2 launch arm_teleop teleop.launch.py serial_port:=/dev/ttyUSB1
    ros2 launch arm_teleop teleop.launch.py event_device_path:=/dev/input/event0

    # Fallback mode: keep the controller on Windows and bridge via TCP.
    ros2 launch arm_teleop teleop.launch.py use_tcp_bridge:=true
"""

from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node


def generate_launch_description() -> LaunchDescription:
    return LaunchDescription([
        DeclareLaunchArgument("serial_port", default_value="/dev/ttyUSB0"),
        DeclareLaunchArgument("baud_rate", default_value="115200"),
        DeclareLaunchArgument("publish_rate", default_value="20.0"),
        DeclareLaunchArgument("dead_zone", default_value="0.15"),
        DeclareLaunchArgument("trigger_threshold", default_value="0.15"),
        DeclareLaunchArgument("control_hz", default_value="50.0"),
        DeclareLaunchArgument("enable_motion_smoothing", default_value="false"),
        DeclareLaunchArgument("input_backend", default_value="evdev"),
        DeclareLaunchArgument("event_device_path", default_value=""),
        DeclareLaunchArgument("device_index", default_value="0"),
        DeclareLaunchArgument("use_tcp_bridge", default_value="false"),
        DeclareLaunchArgument("tcp_bridge_host", default_value="127.0.0.1"),
        DeclareLaunchArgument("tcp_bridge_port", default_value="65432"),

        Node(
            package="arm_driver",
            executable="arm_driver_node",
            name="arm_driver",
            output="screen",
            parameters=[{
                "serial_port": LaunchConfiguration("serial_port"),
                "baud_rate": LaunchConfiguration("baud_rate"),
                "publish_rate": LaunchConfiguration("publish_rate"),
            }],
        ),
        Node(
            package="arm_teleop",
            executable="gamepad_teleop_node",
            name="gamepad_teleop",
            output="screen",
            parameters=[{
                "dead_zone": LaunchConfiguration("dead_zone"),
                "trigger_threshold": LaunchConfiguration("trigger_threshold"),
                "control_hz": LaunchConfiguration("control_hz"),
                "enable_motion_smoothing": LaunchConfiguration("enable_motion_smoothing"),
                "input_backend": LaunchConfiguration("input_backend"),
                "event_device_path": LaunchConfiguration("event_device_path"),
                "device_index": LaunchConfiguration("device_index"),
                "use_tcp_bridge": LaunchConfiguration("use_tcp_bridge"),
                "tcp_bridge_host": LaunchConfiguration("tcp_bridge_host"),
                "tcp_bridge_port": LaunchConfiguration("tcp_bridge_port"),
            }],
        ),
    ])
