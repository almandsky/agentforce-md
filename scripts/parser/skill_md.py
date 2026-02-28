"""Parse .claude/skills/*/SKILL.md files for action definitions."""

from __future__ import annotations

import logging
from pathlib import Path

from ..ir.models import ActionDefinition, ActionInput, ActionOutput
from ..ir.naming import tool_name_to_snake
from .frontmatter import parse_frontmatter

logger = logging.getLogger(__name__)


def parse_skill_md(path: Path) -> ActionDefinition | None:
    """Parse a SKILL.md file into an ActionDefinition.

    Looks for an optional `agentforce:` section in the frontmatter:
    ```yaml
    ---
    name: check-order-status
    description: Check the status of a customer order
    agentforce:
      target: "flow://Get_Order_Details"
      inputs:
        order_id:
          type: string
          description: "The order number"
      outputs:
        status:
          type: string
          description: "Current order status"
    ---
    ```

    If no `agentforce:` section exists, a stub ActionDefinition is created.
    """
    text = path.read_text(encoding="utf-8")
    frontmatter, _body = parse_frontmatter(text)

    if not frontmatter:
        return None

    name = frontmatter.get("name", path.parent.name)
    description = frontmatter.get("description", "")
    snake_name = tool_name_to_snake(name)

    ag = frontmatter.get("agentforce", {})
    if not ag:
        # Return a stub definition
        return ActionDefinition(
            name=snake_name,
            description=description or name,
            target=None,
        )

    target = ag.get("target")
    inputs = _parse_io(ag.get("inputs", {}), ActionInput)
    outputs = _parse_io(ag.get("outputs", {}), ActionOutput)

    return ActionDefinition(
        name=snake_name,
        description=description or name,
        target=target,
        inputs=inputs,
        outputs=outputs,
    )


def _parse_io(io_dict: dict, cls: type) -> list:
    """Parse inputs or outputs from the agentforce frontmatter section."""
    if not io_dict or not isinstance(io_dict, dict):
        return []

    result = []
    for field_name, field_spec in io_dict.items():
        if isinstance(field_spec, dict):
            if cls is ActionInput:
                result.append(ActionInput(
                    name=field_name,
                    input_type=field_spec.get("type", "string"),
                    description=field_spec.get("description"),
                    is_required=field_spec.get("required", True),
                ))
            else:
                result.append(ActionOutput(
                    name=field_name,
                    output_type=field_spec.get("type", "string"),
                    description=field_spec.get("description"),
                ))
        else:
            # Simple form: just a type string
            if cls is ActionInput:
                result.append(ActionInput(name=field_name, input_type=str(field_spec)))
            else:
                result.append(ActionOutput(name=field_name, output_type=str(field_spec)))

    return result


def discover_skills(project_root: Path) -> list[Path]:
    """Find all SKILL.md files in the project."""
    skills_dir = project_root / ".claude" / "skills"
    if not skills_dir.is_dir():
        return []
    return sorted(skills_dir.glob("*/SKILL.md"))
