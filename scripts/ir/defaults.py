"""Apply default values and auto-generated blocks to an AgentDefinition."""

from __future__ import annotations

import logging

from .models import (
    ActionInvocation,
    AgentDefinition,
    AgentType,
    ConnectionBlock,
    InstructionMode,
    ReasoningBlock,
    StartAgent,
    Variable,
    VariableModifier,
)

logger = logging.getLogger(__name__)

# Standard linked variables for service agents
SERVICE_AGENT_LINKED_VARS = [
    Variable(
        name="EndUserId",
        var_type="string",
        modifier=VariableModifier.LINKED,
        source="@MessagingSession.MessagingEndUserId",
        description="Messaging End User ID",
        visibility="External",
    ),
    Variable(
        name="RoutableId",
        var_type="string",
        modifier=VariableModifier.LINKED,
        source="@MessagingSession.Id",
        description="Messaging Session ID",
        visibility="External",
    ),
    Variable(
        name="ContactId",
        var_type="string",
        modifier=VariableModifier.LINKED,
        source="@MessagingEndUser.ContactId",
        description="Contact ID",
        visibility="External",
    ),
]


def _has_escalation(agent: AgentDefinition) -> bool:
    """Check if any topic has an escalation action."""
    for topic in agent.topics:
        for inv in topic.reasoning.action_invocations:
            if "@utils.escalate" in inv.action_ref:
                return True
    return False


def add_linked_variables(agent: AgentDefinition) -> None:
    """Add standard linked variables for service agents if not already present.

    User-defined variables (from CLAUDE.md frontmatter) take precedence over
    the auto-generated defaults.  If the user already defined EndUserId with
    a custom source, we keep the user's version.
    """
    if agent.config.agent_type != AgentType.SERVICE.value:
        return

    existing_names = {v.name for v in agent.variables}
    for var in SERVICE_AGENT_LINKED_VARS:
        if var.name not in existing_names:
            agent.variables.append(var)


def generate_start_agent(agent: AgentDefinition) -> None:
    """Auto-generate the start_agent block with transitions to all topics."""
    if not agent.topics:
        return

    instruction_lines = [
        "Determine what the customer needs help with.",
        "Route them to the appropriate topic.",
    ]

    invocations = []
    for topic in agent.topics:
        inv_name = f"go_{topic.name}"
        invocations.append(
            ActionInvocation(
                name=inv_name,
                action_ref=f"@utils.transition to @topic.{topic.name}",
                description=topic.description,
                transition_target=topic.name,
                available_when=topic.available_when,
            )
        )

    agent.start_agent = StartAgent(
        name="entry",
        description="Entry point - route to appropriate topic",
        reasoning=ReasoningBlock(
            mode=InstructionMode.ARROW,
            instruction_lines=instruction_lines,
            action_invocations=invocations,
        ),
    )


def add_connection_block(agent: AgentDefinition) -> None:
    """Add a connection block if escalation exists and no connection is set."""
    if agent.connection is not None:
        return
    if _has_escalation(agent):
        agent.connection = ConnectionBlock()



def apply_defaults(agent: AgentDefinition) -> None:
    """Apply all default enrichments to the agent definition."""
    add_linked_variables(agent)
    generate_start_agent(agent)
    add_connection_block(agent)
