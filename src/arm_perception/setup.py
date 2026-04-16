from glob import glob
from setuptools import find_packages, setup

package_name = "arm_perception"


setup(
    name=package_name,
    version="0.1.0",
    packages=find_packages(),
    data_files=[
        ("share/ament_index/resource_index/packages", ["resource/" + package_name]),
        ("share/" + package_name, ["package.xml"]),
        ("share/" + package_name + "/launch", glob("launch/*.launch.py")),
        ("share/" + package_name + "/config", glob("config/*.yaml")),
    ],
    install_requires=["setuptools"],
    zip_safe=True,
    maintainer="Jeff Liu Lab",
    maintainer_email="contact@jeffliulab.com",
    description="Calibration-aware perception and world-grounding scaffolding.",
    license="Apache-2.0",
    entry_points={
        "console_scripts": [
            "find_object_service = arm_perception.nodes.find_object_service_node:main",
        ],
    },
)
