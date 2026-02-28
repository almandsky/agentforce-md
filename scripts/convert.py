"""Main orchestrator: discovers files, builds IR, generates output."""

from __future__ import annotations

import logging
from pathlib import Path

from .generator.agent_script import AgentScriptGenerator
from .generator.bundle_meta import generate_bundle_meta
from .generator.writer import write_bundle
from .ir.defaults import apply_defaults
from .ir.models import (
    AgentDefinition,
    AgentType,
    ConfigBlock,
    SystemBlock,
    Topic,
)
from .ir.naming import sanitize_developer_name
from .parser.claude_md import parse_claude_md
from .parser.skill_md import discover_skills, parse_skill_md
from .parser.subagent import discover_subagents, parse_subagent

logger = logging.getLogger(__name__)


def convert(
    project_root: Path,
    agent_name: str,
    agent_type: str = AgentType.SERVICE.value,
    default_agent_user: str = "",
    output_dir: Path | None = None,
    strict: bool = False,
) -> Path:
    """Full conversion pipeline: parse -> IR -> generate -> write.

    Args:
        project_root: Root of the Claude Code project containing CLAUDE.md, .claude/, etc.
        agent_name: Name for the generated agent (used as developer_name and folder name).
        agent_type: Agent type (AgentforceServiceAgent or AgentforceEmployeeAgent).
        default_agent_user: Default agent user email.
        output_dir: Where to write output. Defaults to project_root/force-app/main/default.
        strict: If True, fail when any tools lack agentforce: target in their SKILL.md.

    Returns:
        Path to the generated bundle directory.

    Raises:
        ValueError: In strict mode, if any actions are missing targets.
    """
    if output_dir is None:
        output_dir = Path.cwd() / "force-app" / "main" / "default"

    dev_name = sanitize_developer_name(agent_name)

    # 1. Parse CLAUDE.md for system instructions
    claude_md_path = project_root / "CLAUDE.md"
    system_instructions = parse_claude_md(claude_md_path)
    logger.info("Parsed CLAUDE.md: %d chars", len(system_instructions))

    # 2. Parse sub-agent files -> topics
    subagent_paths = discover_subagents(project_root)
    topics: list[Topic] = []
    for sa_path in subagent_paths:
        topic = parse_subagent(sa_path)
        topics.append(topic)
        logger.info("Parsed sub-agent '%s' -> topic '%s'", sa_path.name, topic.name)

    # 3. Parse SKILL.md files -> action definitions
    skill_paths = discover_skills(project_root)
    skill_actions = {}
    for sk_path in skill_paths:
        action_def = parse_skill_md(sk_path)
        if action_def:
            skill_actions[action_def.name] = action_def
            logger.info("Parsed skill '%s' -> action '%s'", sk_path.parent.name, action_def.name)

    # 4. Merge skill action definitions into topics
    unresolved_actions: list[tuple[str, str]] = []  # (topic_name, action_name)
    for topic in topics:
        for i, ad in enumerate(topic.action_definitions):
            if ad.name in skill_actions:
                skill_ad = skill_actions[ad.name]
                # Merge target, inputs, outputs from skill if available
                if skill_ad.target:
                    ad.target = skill_ad.target
                if skill_ad.inputs:
                    ad.inputs = skill_ad.inputs
                if skill_ad.outputs:
                    ad.outputs = skill_ad.outputs
                if skill_ad.description and ad.description == ad.name:
                    ad.description = skill_ad.description
            if not ad.target:
                unresolved_actions.append((topic.name, ad.name))

    if unresolved_actions:
        for topic_name, action_name in unresolved_actions:
            logger.warning(
                "Action '%s' in topic '%s' has no target. "
                "Create a SKILL.md with agentforce: target to resolve it.",
                action_name, topic_name,
            )
        if strict:
            names = ", ".join(f"{t}.{a}" for t, a in unresolved_actions)
            raise ValueError(
                f"Strict mode: {len(unresolved_actions)} action(s) missing targets: {names}"
            )

    # 5. Build the IR
    agent = AgentDefinition(
        config=ConfigBlock(
            developer_name=dev_name,
            agent_description=_derive_description(system_instructions, agent_name),
            agent_type=agent_type,
            default_agent_user=default_agent_user,
        ),
        system=SystemBlock(
            instructions=system_instructions,
        ),
        topics=topics,
    )

    # 6. Apply defaults (linked vars, start_agent, connection)
    apply_defaults(agent)

    # 7. Generate output
    generator = AgentScriptGenerator(agent)
    agent_content = generator.generate()
    bundle_meta_content = generate_bundle_meta()

    # 8. Write files
    bundle_dir = write_bundle(output_dir, dev_name, agent_content, bundle_meta_content)

    logger.info("Generated bundle at %s", bundle_dir)
    return bundle_dir


def _derive_description(instructions: str, agent_name: str) -> str:
    """Derive a short agent description from the system instructions."""
    if not instructions:
        return f"{agent_name} agent"

    # Use the first sentence of the instructions
    first_line = instructions.strip().splitlines()[0]
    # Truncate to something reasonable
    if len(first_line) > 200:
        first_line = first_line[:197] + "..."
    return first_line
