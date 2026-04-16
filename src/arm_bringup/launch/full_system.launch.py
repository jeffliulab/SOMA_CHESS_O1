"""Launch the full SmartRobotArm system: arm description + Gazebo (verification) + ANIMA cognitive layer.

Note: v1 is a fixed tabletop manipulator. The Gazebo launch is kept for URDF verification
and ANIMA dry-runs only — real ML training is done on the real arm via LeRobot, not in sim.
Perception (W2) and manipulation (W3) packages are added later in the 8-week sprint.
"""

import os
from launch import LaunchDescription
from launch.actions import IncludeLaunchDescription, DeclareLaunchArgument
from launch.conditions import IfCondition
from launch.launch_description_sources import PythonLaunchDescriptionSource
from launch.substitutions import LaunchConfiguration
from ament_index_python.packages import get_package_share_directory


def generate_launch_description():
    return LaunchDescription([
        DeclareLaunchArgument('llm_backend', default_value='mock'),
        DeclareLaunchArgument('enable_perception', default_value='false'),

        # 1. Robot description + Gazebo simulation (URDF verification + ANIMA dry-run only)
        IncludeLaunchDescription(
            PythonLaunchDescriptionSource([
                os.path.join(
                    get_package_share_directory('arm_description'),
                    'launch', 'gazebo.launch.py'
                )
            ]),
        ),

        # 2. ANIMA cognitive framework
        IncludeLaunchDescription(
            PythonLaunchDescriptionSource([
                os.path.join(
                    get_package_share_directory('anima_node'),
                    'launch', 'anima.launch.py'
                )
            ]),
            launch_arguments={
                'llm_backend': LaunchConfiguration('llm_backend'),
            }.items(),
        ),

        IncludeLaunchDescription(
            PythonLaunchDescriptionSource([
                os.path.join(
                    get_package_share_directory('arm_perception'),
                    'launch', 'perception.launch.py'
                )
            ]),
            condition=IfCondition(LaunchConfiguration('enable_perception')),
        ),

        # 4. Manipulation (W3): moveit2 + hardcoded primitives — added in Week 3
        # 5. Teleop / data collection (W4): lerobot teleop with PDP Xbox controller — added in Week 4
        # 6. ACT inference (W5): trained policy executor — added in Week 5
    ])
