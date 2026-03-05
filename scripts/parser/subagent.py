"""Parse .claude/agents/*.md sub-agent files into Topic IR."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from ..ir.models import (
    ActionDefinition,
    ActionInvocation,
    AfterReasoningDirective,
    InstructionMode,
    PostActionBranch,
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

    # Parse agentforce-specific overrides
    ag = frontmatter.get("agentforce", {}) or {}
    topic_label = ag.get("label")
    topic_available_when = ag.get("available_when")
    after_reasoning_directives = _parse_after_reasoning(ag.get("after_reasoning"))

    # Parse tools
    tools = _parse_tools(frontmatter.get("tools", ""))

    # Split body into scope + instruction lines
    scope, instruction_lines = split_scope_and_instructions(body)

    # Use scope as description if frontmatter description is empty
    if not description and scope:
        description = scope

    # Parse action-variable bindings from agentforce section
    bindings = ag.get("bindings", {}) or {}

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

        # Look up bindings by the original tool name (PascalCase)
        tool_bindings = bindings.get(tool, {}) or {}
        with_bindings = {}
        set_bindings = {}
        post_branches: list[PostActionBranch] = []
        if isinstance(tool_bindings, dict):
            raw_with = tool_bindings.get("with", {}) or {}
            if isinstance(raw_with, dict):
                with_bindings = {k: str(v) for k, v in raw_with.items()}
            raw_set = tool_bindings.get("set", {}) or {}
            if isinstance(raw_set, dict):
                set_bindings = {k: str(v) for k, v in raw_set.items()}
            # Parse post-action branches (if/transition_to)
            after = tool_bindings.get("after")
            if isinstance(after, dict) and "if" in after:
                post_branches.append(PostActionBranch(
                    condition=str(after["if"]),
                    transition_to=kebab_to_snake(str(after["transition_to"])),
                ))
            elif isinstance(after, list):
                for branch in after:
                    if isinstance(branch, dict) and "if" in branch:
                        post_branches.append(PostActionBranch(
                            condition=str(branch["if"]),
                            transition_to=kebab_to_snake(str(branch["transition_to"])),
                        ))

        action_invocations.append(
            ActionInvocation(
                name=snake_name,
                action_ref=f"@actions.{snake_name}",
                description=f"{tool}",
                with_bindings=with_bindings,
                set_bindings=set_bindings,
                post_branches=post_branches,
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
        after_reasoning_directives=after_reasoning_directives,
        label=topic_label,
        available_when=topic_available_when,
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


def _parse_after_reasoning(raw: Any) -> list[AfterReasoningDirective]:
    """Parse the agentforce.after_reasoning list into AfterReasoningDirective objects.

    Each list entry may have:
      - ``if``: guard condition string (optional)
      - ``run``: tool/action name (optional; converted to snake_case @actions ref)
      - ``with``: dict of param → value bindings (only meaningful with ``run``)
      - ``set``: dict of @variables.x → @outputs.y (only meaningful with ``run``)
      - ``transition_to``: kebab-case topic name (optional; converted to snake_case)
    """
    if not raw or not isinstance(raw, list):
        return []

    directives = []
    for entry in raw:
        if not isinstance(entry, dict):
            continue

        condition = str(entry["if"]) if "if" in entry else None

        run_ref = None
        with_bindings: dict[str, str] = {}
        set_bindings: dict[str, str] = {}
        if "run" in entry:
            run_ref = f"@actions.{tool_name_to_snake(str(entry['run']))}"
            raw_with = entry.get("with", {}) or {}
            if isinstance(raw_with, dict):
                with_bindings = {k: str(v) for k, v in raw_with.items()}
            raw_set = entry.get("set", {}) or {}
            if isinstance(raw_set, dict):
                set_bindings = {k: str(v) for k, v in raw_set.items()}

        transition_to = None
        if "transition_to" in entry:
            transition_to = kebab_to_snake(str(entry["transition_to"]))

        directives.append(AfterReasoningDirective(
            condition=condition,
            run=run_ref,
            with_bindings=with_bindings,
            set_bindings=set_bindings,
            transition_to=transition_to,
        ))

    return directives


def discover_subagents(project_root: Path) -> list[Path]:
    """Find all sub-agent markdown files in the project."""
    agents_dir = project_root / ".claude" / "agents"
    if not agents_dir.is_dir():
        return []
    return sorted(agents_dir.glob("*.md"))
