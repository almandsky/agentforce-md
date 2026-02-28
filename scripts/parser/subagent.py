"""Parse .claude/agents/*.md sub-agent files into Topic IR."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from ..ir.models import (
    ActionDefinition,
    ActionInvocation,
    InstructionMode,
    ReasoningBlock,
    Topic,
)
from ..ir.naming import kebab_to_snake, tool_name_to_snake
from .frontmatter import parse_frontmatter
from .markdown_utils import split_scope_and_instructions

logger = logging.getLogger(__name__)

# Claude Code built-in tools that don't map to Agentforce actions
BUILTIN_TOOLS = {
    "Read", "Write", "Edit", "Glob", "Grep", "Bash",
    "Task", "WebFetch", "AskUserQuestion", "NotebookEdit",
}

# Frontmatter fields that are lossy (no Agent Script equivalent)
LOSSY_FIELDS = {"model", "permissionMode", "maxTurns", "memory", "background", "isolation"}


def parse_subagent(path: Path) -> Topic:
    """Parse a sub-agent markdown file into a Topic IR node.

    Expects YAML frontmatter with at least name and description,
    plus a markdown body with scope and instructions.
    """
    text = path.read_text(encoding="utf-8")
    frontmatter, body = parse_frontmatter(text)

    name = frontmatter.get("name", path.stem)
    description = frontmatter.get("description", "")

    # Warn about lossy fields
    for field_name in LOSSY_FIELDS:
        if field_name in frontmatter:
            logger.info(
                "Dropping unsupported field '%s' from sub-agent '%s'",
                field_name, name,
            )

    # Parse tools
    tools = _parse_tools(frontmatter.get("tools", ""))

    # Split body into scope + instruction lines
    scope, instruction_lines = split_scope_and_instructions(body)

    # Use scope as description if frontmatter description is empty
    if not description and scope:
        description = scope

    # Build action definitions (stubs) and invocations for non-builtin tools
    action_defs = []
    action_invocations = []
    for tool in tools:
        if tool in BUILTIN_TOOLS:
            continue
        snake_name = tool_name_to_snake(tool)
        action_defs.append(
            ActionDefinition(
                name=snake_name,
                description=f"{tool}",  # Placeholder
                target=None,  # Will be filled by SKILL.md if available
            )
        )
        action_invocations.append(
            ActionInvocation(
                name=snake_name,
                action_ref=f"@actions.{snake_name}",
                description=f"{tool}",
            )
        )

    # Determine instruction mode (use ARROW if there are multiple instruction lines)
    mode = InstructionMode.ARROW if instruction_lines else InstructionMode.PIPE

    # Combine scope + instruction_lines for the reasoning block
    all_lines = []
    if scope:
        all_lines.append(scope)
    all_lines.extend(instruction_lines)

    topic_name = kebab_to_snake(name)

    return Topic(
        name=topic_name,
        description=description,
        action_definitions=action_defs,
        reasoning=ReasoningBlock(
            mode=mode,
            instruction_lines=all_lines,
            action_invocations=action_invocations,
        ),
    )


def _parse_tools(tools_value: Any) -> list[str]:
    """Parse the tools field from frontmatter.

    Can be a comma-separated string or a YAML list.
    """
    if not tools_value:
        return []
    if isinstance(tools_value, list):
        return [str(t).strip() for t in tools_value if str(t).strip()]
    if isinstance(tools_value, str):
        return [t.strip() for t in tools_value.split(",") if t.strip()]
    return []


def discover_subagents(project_root: Path) -> list[Path]:
    """Find all sub-agent markdown files in the project."""
    agents_dir = project_root / ".claude" / "agents"
    if not agents_dir.is_dir():
        return []
    return sorted(agents_dir.glob("*.md"))
