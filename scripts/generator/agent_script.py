"""Generate Agent Script (.agent) file content from IR."""

from __future__ import annotations

import logging

from ..ir.models import (
    ActionDefinition,
    ActionInvocation,
    AgentDefinition,
    InstructionMode,
    PostActionBranch,
    ReasoningBlock,
    StartAgent,
    Topic,
    Variable,
    VariableModifier,
)

logger = logging.getLogger(__name__)

# Agent Script uses 4-space indentation
INDENT = "    "


class AgentScriptGenerator:
    """Generates Agent Script (.agent) file content from an AgentDefinition IR."""

    def __init__(self, agent: AgentDefinition):
        self.agent = agent

    def generate(self) -> str:
        """Generate the complete .agent file content."""
        sections = []

        sections.append(self._render_system())
        sections.append(self._render_config())
        sections.append(self._render_language())

        vars_block = self._render_variables()
        if vars_block:
            sections.append(vars_block)

        knowledge_block = self._render_knowledge()
        if knowledge_block:
            sections.append(knowledge_block)

        if self.agent.connection:
            sections.append(self._render_connection())

        sections.append(self._render_start_agent())

        for topic in self.agent.topics:
            sections.append(self._render_topic(topic))

        return "\n\n".join(sections) + "\n"

    def _render_config(self) -> str:
        c = self.agent.config
        lines = ["config:"]
        if c.agent_label:
            lines.append(f'{INDENT}agent_label: "{_escape(c.agent_label)}"')
        lines.append(f'{INDENT}developer_name: "{c.developer_name}"')
        lines.append(f'{INDENT}description: "{_escape(c.description)}"')
        lines.append(f'{INDENT}agent_type: "{c.agent_type}"')
        if c.default_agent_user:
            lines.append(f'{INDENT}default_agent_user: "{c.default_agent_user}"')
        return "\n".join(lines)

    def _render_system(self) -> str:
        s = self.agent.system
        lines = ["system:"]
        if s.instructions:
            # Check if multi-line
            if "\n" in s.instructions:
                lines.append(f"{INDENT}instructions: |")
                for instr_line in s.instructions.splitlines():
                    lines.append(f"{INDENT}{INDENT}{instr_line}")
            else:
                lines.append(f'{INDENT}instructions: "{_escape(s.instructions)}"')
        lines.extend([
            f"{INDENT}messages:",
            f'{INDENT}{INDENT}welcome: "{_escape(s.welcome_message)}"',
            f'{INDENT}{INDENT}error: "{_escape(s.error_message)}"',
        ])
        return "\n".join(lines)

    def _render_variables(self) -> str:
        if not self.agent.variables:
            return ""

        lines = ["variables:"]
        for var in self.agent.variables:
            lines.extend(self._render_variable(var))
        return "\n".join(lines)

    def _render_variable(self, var: Variable) -> list[str]:
        lines = []
        if var.modifier == VariableModifier.MUTABLE:
            default = _format_default(var.var_type, var.default)
            lines.append(f"{INDENT}{var.name}: mutable {var.var_type} = {default}")
        else:
            # Linked variable
            lines.append(f"{INDENT}{var.name}: linked {var.var_type}")
            if var.source:
                lines.append(f"{INDENT}{INDENT}source: {var.source}")
        if var.description:
            lines.append(f'{INDENT}{INDENT}description: "{_escape(var.description)}"')
        if var.visibility:
            lines.append(f'{INDENT}{INDENT}visibility: "{var.visibility}"')
        if var.label:
            lines.append(f'{INDENT}{INDENT}label: "{_escape(var.label)}"')
        return lines

    def _render_knowledge(self) -> str:
        if self.agent.knowledge is None:
            return ""
        lines = [
            "knowledge:",
            f"{INDENT}citations_enabled: {_bool(self.agent.knowledge.citations_enabled)}",
        ]
        return "\n".join(lines)

    def _render_connection(self) -> str:
        conn = self.agent.connection
        lines = [
            f"connection {conn.channel}:",
            f'{INDENT}outbound_route_type: "{conn.outbound_route_type}"',
            f'{INDENT}outbound_route_name: "{conn.outbound_route_name}"',
            f'{INDENT}escalation_message: "{_escape(conn.escalation_message)}"',
            f"{INDENT}adaptive_response_allowed: {_bool(conn.adaptive_response_allowed)}",
        ]
        return "\n".join(lines)

    def _render_language(self) -> str:
        lang = self.agent.language
        lines = [
            "language:",
            f'{INDENT}default_locale: "{lang.default_locale}"',
            f'{INDENT}additional_locales: "{lang.additional_locales}"',
            f"{INDENT}all_additional_locales: {_bool(lang.all_additional_locales)}",
        ]
        return "\n".join(lines)

    def _render_start_agent(self) -> str:
        sa = self.agent.start_agent
        lines = [f"start_agent {sa.name}:"]
        if sa.label:
            lines.append(f'{INDENT}label: "{_escape(sa.label)}"')
        lines.append(f'{INDENT}description: "{_escape(sa.description)}"')
        lines.extend(self._render_reasoning(sa.reasoning, indent_level=1))
        return "\n".join(lines)

    def _render_topic(self, topic: Topic) -> str:
        lines = [f"topic {topic.name}:"]
        if topic.label:
            lines.append(f'{INDENT}label: "{_escape(topic.label)}"')
        lines.append(f'{INDENT}description: "{_escape(topic.description)}"')

        # Separate resolved (has target) from unresolved action definitions
        valid_defs = [ad for ad in topic.action_definitions if ad.target]
        unresolved_defs = [ad for ad in topic.action_definitions if not ad.target]

        if valid_defs:
            lines.append(f"{INDENT}actions:")
            for action_def in valid_defs:
                lines.extend(self._render_action_definition(action_def, indent_level=2))

        # Render unresolved actions as commented-out stubs
        if unresolved_defs:
            lines.append("")
            lines.append(f"{INDENT}# TODO: The following actions need agentforce: target in their SKILL.md")
            lines.append(f"{INDENT}# actions:")
            for ad in unresolved_defs:
                lines.append(f"{INDENT}#    {ad.name}:")
                lines.append(f'{INDENT}#       description: "{_escape(ad.description)}"')
                lines.append(f'{INDENT}#       target: "flow://TODO_{ad.name}"')
                logger.warning(
                    "Action '%s' in topic '%s' rendered as stub (no target)",
                    ad.name, topic.name,
                )

        # Filter reasoning action invocations to only reference valid actions
        valid_names = {ad.name for ad in valid_defs}
        reasoning = topic.reasoning
        if reasoning.action_invocations:
            filtered_invocations = [
                inv for inv in reasoning.action_invocations
                if inv.name in valid_names
                or inv.action_ref.startswith("@utils.")
            ]
            reasoning = ReasoningBlock(
                mode=reasoning.mode,
                instruction_lines=reasoning.instruction_lines,
                conditionals=reasoning.conditionals,
                inline_runs=reasoning.inline_runs,
                action_invocations=filtered_invocations,
            )

        # Reasoning block
        lines.extend(self._render_reasoning(reasoning, indent_level=1))

        return "\n".join(lines)

    def _render_action_definition(self, ad: ActionDefinition, indent_level: int) -> list[str]:
        indent = INDENT * indent_level
        inner = INDENT * (indent_level + 1)
        deeper = INDENT * (indent_level + 2)

        lines = [f"{indent}{ad.name}:"]
        if ad.label:
            lines.append(f'{inner}label: "{_escape(ad.label)}"')
        lines.append(f'{inner}description: "{_escape(ad.description)}"')

        if ad.inputs:
            lines.append(f"{inner}inputs:")
            for inp in ad.inputs:
                lines.append(f"{deeper}{inp.name}: {inp.input_type}")
                if inp.label:
                    lines.append(f"{deeper}{INDENT}label: \"{_escape(inp.label)}\"")
                if inp.description:
                    lines.append(f"{deeper}{INDENT}description: \"{_escape(inp.description)}\"")
                if inp.is_user_input:
                    lines.append(f"{deeper}{INDENT}is_user_input: True")
                if inp.complex_data_type_name:
                    lines.append(f"{deeper}{INDENT}complex_data_type_name: \"{inp.complex_data_type_name}\"")
                if inp.default_value:
                    lines.append(f"{deeper}{INDENT}default_value: {inp.default_value}")

        if ad.outputs:
            lines.append(f"{inner}outputs:")
            for out in ad.outputs:
                lines.append(f"{deeper}{out.name}: {out.output_type}")
                if out.label:
                    lines.append(f"{deeper}{INDENT}label: \"{_escape(out.label)}\"")
                if out.description:
                    lines.append(f"{deeper}{INDENT}description: \"{_escape(out.description)}\"")
                if out.complex_data_type_name:
                    lines.append(f"{deeper}{INDENT}complex_data_type_name: \"{out.complex_data_type_name}\"")
                if out.filter_from_agent:
                    lines.append(f"{deeper}{INDENT}filter_from_agent: True")
                if not out.is_displayable:
                    lines.append(f"{deeper}{INDENT}is_displayable: False")

        lines.append(f'{inner}target: "{ad.target}"')

        if ad.require_user_confirmation:
            lines.append(f"{inner}require_user_confirmation: True")
        if ad.include_in_progress_indicator:
            lines.append(f"{inner}include_in_progress_indicator: True")
        if ad.progress_indicator_message:
            lines.append(f'{inner}progress_indicator_message: "{_escape(ad.progress_indicator_message)}"')
        if ad.source:
            lines.append(f'{inner}source: "{ad.source}"')

        return lines

    def _render_reasoning(self, reasoning: ReasoningBlock, indent_level: int) -> list[str]:
        indent = INDENT * indent_level
        inner = INDENT * (indent_level + 1)

        lines = [f"{indent}reasoning:"]

        # Instructions
        if reasoning.instruction_lines:
            if reasoning.mode == InstructionMode.ARROW:
                lines.append(f"{inner}instructions: ->")
            else:
                lines.append(f"{inner}instructions: |")

            instr_indent = INDENT * (indent_level + 2)
            for instr_line in reasoning.instruction_lines:
                lines.append(f"{instr_indent}| {instr_line}")

        # Conditionals (rendered inline in instructions)
        for cond in reasoning.conditionals:
            cond_indent = INDENT * (indent_level + 2)
            lines.append(f"{cond_indent}if {cond.condition}:")
            for cline in cond.if_lines:
                lines.append(f"{cond_indent}{INDENT}| {cline}")
            if cond.else_lines:
                lines.append(f"{cond_indent}else:")
                for eline in cond.else_lines:
                    lines.append(f"{cond_indent}{INDENT}| {eline}")

        # Level 2: Action invocations
        if reasoning.action_invocations:
            lines.append(f"{inner}actions:")
            for inv in reasoning.action_invocations:
                lines.extend(self._render_action_invocation(inv, indent_level + 2))

        return lines

    def _render_action_invocation(self, inv: ActionInvocation, indent_level: int) -> list[str]:
        indent = INDENT * indent_level
        inner = INDENT * (indent_level + 1)
        deeper = INDENT * (indent_level + 2)
        lines = []

        lines.append(f"{indent}{inv.name}: {inv.action_ref}")

        if inv.description:
            lines.append(f'{inner}description: "{_escape(inv.description)}"')

        if inv.available_when:
            lines.append(f"{inner}available when {inv.available_when}")

        for param, value in inv.with_bindings.items():
            lines.append(f"{inner}with {param} = {value}")

        for var_ref, output_ref in inv.set_bindings.items():
            lines.append(f"{inner}set {var_ref} = {output_ref}")

        for branch in inv.post_branches:
            lines.append(f"{inner}if {branch.condition}:")
            lines.append(f"{deeper}transition to @topic.{branch.transition_to}")

        return lines


def _escape(text: str) -> str:
    """Escape quotes in a string for Agent Script output."""
    return text.replace('"', '\\"')


def _bool(value: bool) -> str:
    """Format a boolean for Agent Script (True/False, capitalized)."""
    return "True" if value else "False"


def _format_default(var_type: str, default: str | None) -> str:
    """Format a default value for a mutable variable."""
    if default is not None:
        return default

    # Provide sensible defaults based on type
    type_defaults = {
        "string": '""',
        "number": "0",
        "boolean": "False",
        "object": "{}",
    }

    # Handle list types
    if var_type.startswith("list["):
        return "[]"

    return type_defaults.get(var_type, '""')
