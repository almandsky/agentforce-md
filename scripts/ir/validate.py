"""Validate an AgentDefinition before generation."""

from __future__ import annotations

from .models import AgentDefinition


def validate_agent(agent: AgentDefinition) -> list[str]:
    """Validate the agent IR and return a list of error messages.

    Returns an empty list if the agent is valid.
    """
    errors: list[str] = []

    # Developer name checks
    dev_name = agent.config.developer_name
    if not dev_name:
        errors.append("developer_name is empty")
    elif len(dev_name) > 80:
        errors.append(
            f"developer_name '{dev_name}' exceeds 80-character limit "
            f"({len(dev_name)} chars)"
        )
    elif not dev_name[0].isalpha():
        errors.append(
            f"developer_name '{dev_name}' must start with a letter"
        )

    # Agent description
    if not agent.config.agent_description:
        errors.append("agent_description is empty")

    # Duplicate topic names
    topic_names = [t.name for t in agent.topics]
    seen: set[str] = set()
    for name in topic_names:
        if name in seen:
            errors.append(f"Duplicate topic name: '{name}'")
        seen.add(name)

    # Topic-level checks
    for topic in agent.topics:
        if not topic.description:
            errors.append(f"Topic '{topic.name}' has an empty description")

        # Duplicate action definition names within a topic
        action_names: set[str] = set()
        for ad in topic.action_definitions:
            if ad.name in action_names:
                errors.append(
                    f"Duplicate action '{ad.name}' in topic '{topic.name}'"
                )
            action_names.add(ad.name)

    return errors
