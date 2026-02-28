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
      label: "Check Order Status"
      require_user_confirmation: false
      include_in_progress_indicator: true
      progress_indicator_message: "Looking up your order..."
      source: "Get_Order_Details"
      inputs:
        order_id:
          type: string
          description: "The order number"
          label: "Order ID"
          is_user_input: true
          complex_data_type_name: "OrderIdType"
          default_value: "@knowledge.citations_url"
      outputs:
        status:
          type: string
          description: "Current order status"
          label: "Status"
          complex_data_type_name: "StatusType"
          filter_from_agent: false
          is_displayable: true
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
    inputs = _parse_inputs(ag.get("inputs", {}))
    outputs = _parse_outputs(ag.get("outputs", {}))

    return ActionDefinition(
        name=snake_name,
        description=description or name,
        target=target,
        inputs=inputs,
        outputs=outputs,
        label=ag.get("label"),
        require_user_confirmation=ag.get("require_user_confirmation", False),
        include_in_progress_indicator=ag.get("include_in_progress_indicator", False),
        progress_indicator_message=ag.get("progress_indicator_message"),
        source=ag.get("source"),
    )


def _parse_inputs(io_dict: dict) -> list[ActionInput]:
    """Parse inputs from the agentforce frontmatter section."""
    if not io_dict or not isinstance(io_dict, dict):
        return []

    result = []
    for field_name, field_spec in io_dict.items():
        if isinstance(field_spec, dict):
            result.append(ActionInput(
                name=field_name,
                input_type=field_spec.get("type", "string"),
                description=field_spec.get("description"),
                is_required=field_spec.get("required", True),
                label=field_spec.get("label"),
                is_user_input=field_spec.get("is_user_input", False),
                complex_data_type_name=field_spec.get("complex_data_type_name"),
                default_value=field_spec.get("default_value"),
            ))
        else:
            # Simple form: just a type string
            result.append(ActionInput(name=field_name, input_type=str(field_spec)))

    return result


def _parse_outputs(io_dict: dict) -> list[ActionOutput]:
    """Parse outputs from the agentforce frontmatter section."""
    if not io_dict or not isinstance(io_dict, dict):
        return []

    result = []
    for field_name, field_spec in io_dict.items():
        if isinstance(field_spec, dict):
            result.append(ActionOutput(
                name=field_name,
                output_type=field_spec.get("type", "string"),
                description=field_spec.get("description"),
                label=field_spec.get("label"),
                complex_data_type_name=field_spec.get("complex_data_type_name"),
                filter_from_agent=field_spec.get("filter_from_agent", False),
                is_displayable=field_spec.get("is_displayable", True),
            ))
        else:
            # Simple form: just a type string
            result.append(ActionOutput(name=field_name, output_type=str(field_spec)))

    return result


def discover_skills(project_root: Path) -> list[Path]:
    """Find all SKILL.md files in the project."""
    skills_dir = project_root / ".claude" / "skills"
    if not skills_dir.is_dir():
        return []
    return sorted(skills_dir.glob("*/SKILL.md"))
