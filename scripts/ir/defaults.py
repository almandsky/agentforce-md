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
    ),
    Variable(
        name="RoutableId",
        var_type="string",
        modifier=VariableModifier.LINKED,
        source="@MessagingSession.Id",
        description="Messaging Session ID",
    ),
    Variable(
        name="ContactId",
        var_type="string",
        modifier=VariableModifier.LINKED,
        source="@MessagingEndUser.ContactId",
        description="Contact ID",
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
    """Add standard linked variables for service agents if not already present."""
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


def add_back_to_menu_transitions(agent: AgentDefinition) -> None:
    """Add a back_to_menu transition to each topic that doesn't already have one.

    This allows users to return to the start_agent entry point from any topic,
    matching standard Agentforce patterns (Coral Cloud, sf-skills templates).
    """
    if not agent.topics:
        return

    entry_name = agent.start_agent.name

    for topic in agent.topics:
        # Skip if this topic already has a transition back
        existing_refs = {
            inv.action_ref for inv in topic.reasoning.action_invocations
        }
        back_ref = f"@utils.transition to @topic.{entry_name}"
        if back_ref in existing_refs:
            continue

        # Skip escalation topics (they hand off, not return)
        if "escalat" in topic.name.lower():
            continue

        topic.reasoning.action_invocations.append(
            ActionInvocation(
                name="back_to_menu",
                action_ref=back_ref,
                description="Return to main menu",
                transition_target=entry_name,
            )
        )


def apply_defaults(agent: AgentDefinition) -> None:
    """Apply all default enrichments to the agent definition."""
    add_linked_variables(agent)
    generate_start_agent(agent)
    add_back_to_menu_transitions(agent)
    add_connection_block(agent)
