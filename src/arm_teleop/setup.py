from setuptools import find_packages, setup
from glob import glob

package_name = 'arm_teleop'

setup(
    name=package_name,
    version='0.1.0',
    packages=find_packages(exclude=['test']),
    data_files=[
        ('share/ament_index/resource_index/packages',
            ['resource/' + package_name]),
        ('share/' + package_name, ['package.xml']),
        ('share/' + package_name + '/launch', glob('launch/*.launch.py')),
    ],
    install_requires=['setuptools', 'pygame', 'evdev'],
    zip_safe=True,
    maintainer='Jeff Liu Lab',
    maintainer_email='jeff@jeffliulab.com',
    description='Gamepad teleoperation of RoArm-M2-S via ROS 2.',
    license='Apache-2.0',
    tests_require=['pytest'],
    entry_points={
        'console_scripts': [
            'gamepad_teleop_node = arm_teleop.gamepad_teleop_node:main',
        ],
    },
)
