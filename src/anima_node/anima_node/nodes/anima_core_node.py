"""
ANIMA Core Node — The cognitive brain of SOMA Arm.

Pipeline:
  1. Receive natural language instruction (String topic)
  2. Parse with LLM → structured TaskSpec JSON
  3. Validate TaskSpec (test-and-check)
  4. Generate behavior tree from TaskSpec
  5. Execute behavior tree (dispatches to skill nodes)
  6. Report results back to user

This is Layer 1 + Layer 2 of the ANIMA architecture (see github.com/jeffliulab/anima).
SOMA Arm is a fixed tabletop manipulator (Waveshare RoArm-M2-S, 4-DOF).
"""

import json
import rclpy
from rclpy.node import Node
from std_msgs.msg import String


# TaskSpec schema for validation
TASK_SPEC_SCHEMA = {
    "required_fields": ["task_type", "steps"],
    "valid_task_types": [
        "pick_and_place",
        "navigate_to",
        "detect_objects",
        "clean_surface",
    ],
    "valid_skills": [
        "detect_object",
        "navigate_to",
        "pick_object",
        "place_object",
        "say",
    ],
}

# System prompt for LLM parser
SYSTEM_PROMPT = """You are the ANIMA task parser for SOMA Arm, a fixed tabletop manipulator.

The robot has these capabilities:
- Detect objects on the workspace using a fixed overhead camera (detect_object)
- Pick up small lightweight objects with a top-down grasp (pick_object)
- Place objects at target locations on the workspace (place_object)
- Push objects across the workspace surface (push_object)
- Report status via speech (say)

Hardware constraints:
- Waveshare RoArm-M2-S, 4-DOF arm, ~0.5kg payload, ~28cm reach.
- Fixed at one edge of an A4-sized workspace.
- Top-down grasps only (no side or angled approaches).
- Cannot fold cloth, open doors, lift heavy objects, or move its base.

Given a user instruction, output a JSON TaskSpec:
{
  "task_type": "pick_and_place",
  "description": "human readable description of the task",
  "steps": [
    {"skill": "detect_object", "params": {"target": "red toy"}},
    {"skill": "pick_object", "params": {"target": "red toy"}},
    {"skill": "place_object", "params": {"target": "red toy", "destination": "blue bin"}}
  ],
  "success_criteria": "red toy is in the blue bin"
}

Output ONLY valid JSON. No markdown, no explanation."""


class AnimaCoreNode(Node):
    """ANIMA cognitive core: language understanding + task planning."""

    def __init__(self):
        super().__init__('anima_core')

        # Subscribe to user instructions
        self.instruction_sub = self.create_subscription(
            String, '/user_instruction', self.on_instruction, 10
        )

        # Publish task spec for skill executor
        self.task_pub = self.create_publisher(String, '/task_spec', 10)

        # Publish status updates
        self.status_pub = self.create_publisher(String, '/anima_status', 10)

        # LLM backend config
        self.declare_parameter('llm_backend', 'mock')  # 'mock', 'anthropic', 'openai'
        self.declare_parameter('llm_model', 'claude-sonnet-4-20250514')

        self.get_logger().info('ANIMA Core Node started. Waiting for instructions...')

    def on_instruction(self, msg: String):
        """Process a natural language instruction."""
        instruction = msg.data
        self.get_logger().info(f'Received instruction: "{instruction}"')
        self.publish_status(f'Parsing instruction: "{instruction}"')

        # Step 1: Parse with LLM
        task_spec = self.parse_instruction(instruction)
        if task_spec is None:
            self.publish_status('ERROR: Failed to parse instruction')
            return

        # Step 2: Validate (test-and-check)
        if not self.validate_task_spec(task_spec):
            self.publish_status('ERROR: TaskSpec validation failed')
            return

        # Step 3: Publish for execution
        self.get_logger().info(f'TaskSpec: {json.dumps(task_spec, indent=2)}')
        self.publish_status(f'Executing task: {task_spec["description"]}')

        task_msg = String()
        task_msg.data = json.dumps(task_spec)
        self.task_pub.publish(task_msg)

    def parse_instruction(self, instruction: str) -> dict | None:
        """Parse natural language instruction into TaskSpec JSON using LLM."""
        backend = self.get_parameter('llm_backend').value

        if backend == 'mock':
            return self.mock_parse(instruction)
        elif backend == 'anthropic':
            return self.llm_parse_anthropic(instruction)
        elif backend == 'openai':
            return self.llm_parse_openai(instruction)
        else:
            self.get_logger().error(f'Unknown LLM backend: {backend}')
            return None

    def mock_parse(self, instruction: str) -> dict:
        """Mock parser for testing without LLM API.

        Handles a few hardcoded instructions for development.
        """
        instruction_lower = instruction.lower()

        if 'pen' in instruction_lower and ('box' in instruction_lower or 'put' in instruction_lower):
            return {
                "task_type": "pick_and_place",
                "description": "Pick up the pen and place it in the storage box",
                "steps": [
                    {"skill": "detect_object", "params": {"target": "pen", "location": "table"}},
                    {"skill": "navigate_to", "params": {"target": "table"}},
                    {"skill": "pick_object", "params": {"target": "pen"}},
                    {"skill": "navigate_to", "params": {"target": "storage_box"}},
                    {"skill": "place_object", "params": {"target": "pen", "destination": "storage_box"}},
                ],
                "success_criteria": "pen is in the storage box",
            }

        if 'clean' in instruction_lower or 'tidy' in instruction_lower:
            return {
                "task_type": "clean_surface",
                "description": "Clean up all objects from the table",
                "steps": [
                    {"skill": "navigate_to", "params": {"target": "table"}},
                    {"skill": "detect_object", "params": {"target": "all", "location": "table"}},
                    {"skill": "say", "params": {"text": "I found objects on the table. Starting cleanup."}},
                    {"skill": "pick_object", "params": {"target": "first_detected"}},
                    {"skill": "navigate_to", "params": {"target": "storage_box"}},
                    {"skill": "place_object", "params": {"target": "first_detected", "destination": "storage_box"}},
                ],
                "success_criteria": "table is clear",
            }

        if 'what' in instruction_lower and 'see' in instruction_lower:
            return {
                "task_type": "detect_objects",
                "description": "Report what objects are visible",
                "steps": [
                    {"skill": "detect_object", "params": {"target": "all", "location": "current_view"}},
                    {"skill": "say", "params": {"text": "Reporting detected objects."}},
                ],
                "success_criteria": "objects reported to user",
            }

        # Default: try to interpret as pick-and-place
        return {
            "task_type": "pick_and_place",
            "description": f"Execute: {instruction}",
            "steps": [
                {"skill": "say", "params": {"text": f"I received: {instruction}. Attempting to execute."}},
                {"skill": "detect_object", "params": {"target": "unknown", "location": "nearby"}},
            ],
            "success_criteria": "task attempted",
        }

    def llm_parse_anthropic(self, instruction: str) -> dict | None:
        """Parse using Anthropic Claude API."""
        try:
            import anthropic
            client = anthropic.Anthropic()
            model = self.get_parameter('llm_model').value

            response = client.messages.create(
                model=model,
                max_tokens=1024,
                system=SYSTEM_PROMPT,
                messages=[{"role": "user", "content": instruction}],
            )

            text = response.content[0].text
            return json.loads(text)
        except Exception as e:
            self.get_logger().error(f'Anthropic API error: {e}')
            return None

    def llm_parse_openai(self, instruction: str) -> dict | None:
        """Parse using OpenAI API."""
        try:
            from openai import OpenAI
            client = OpenAI()
            model = self.get_parameter('llm_model').value

            response = client.chat.completions.create(
                model=model,
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": instruction},
                ],
                response_format={"type": "json_object"},
            )

            text = response.choices[0].message.content
            return json.loads(text)
        except Exception as e:
            self.get_logger().error(f'OpenAI API error: {e}')
            return None

    def validate_task_spec(self, spec: dict) -> bool:
        """Test-and-Check validation of TaskSpec."""
        # Check required fields
        for field in TASK_SPEC_SCHEMA["required_fields"]:
            if field not in spec:
                self.get_logger().error(f'TaskSpec missing field: {field}')
                return False

        # Check task type
        if spec["task_type"] not in TASK_SPEC_SCHEMA["valid_task_types"]:
            self.get_logger().warn(
                f'Unknown task type: {spec["task_type"]}. Proceeding anyway.'
            )

        # Check skills
        for step in spec.get("steps", []):
            if step.get("skill") not in TASK_SPEC_SCHEMA["valid_skills"]:
                self.get_logger().error(f'Unknown skill: {step.get("skill")}')
                return False
            if "params" not in step:
                self.get_logger().error(f'Step missing params: {step}')
                return False

        self.get_logger().info('TaskSpec validation passed.')
        return True

    def publish_status(self, text: str):
        msg = String()
        msg.data = text
        self.status_pub.publish(msg)
        self.get_logger().info(f'[STATUS] {text}')


def main(args=None):
    rclpy.init(args=args)
    node = AnimaCoreNode()
    rclpy.spin(node)
    node.destroy_node()
    rclpy.shutdown()


if __name__ == '__main__':
    main()
