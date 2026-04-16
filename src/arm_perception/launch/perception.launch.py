"""Launch the SOMA Arm perception/world-grounding scaffold."""

import os

from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node


def generate_launch_description():
    package_share = get_package_share_directory("arm_perception")
    defaults_yaml = os.path.join(package_share, "config", "perception_defaults.yaml")

    return LaunchDescription(
        [
            DeclareLaunchArgument("params_file", default_value=defaults_yaml),
            Node(
                package="arm_perception",
                executable="find_object_service",
                name="find_object_service",
                output="screen",
                parameters=[LaunchConfiguration("params_file")],
            ),
        ]
    )
