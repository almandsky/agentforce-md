"""Intermediate Representation dataclasses for Agent Script generation."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class AgentType(Enum):
    SERVICE = "AgentforceServiceAgent"
    EMPLOYEE = "AgentforceEmployeeAgent"


class VariableModifier(Enum):
    MUTABLE = "mutable"
    LINKED = "linked"


class InstructionMode(Enum):
    """Whether the instructions block uses pipe (|) or arrow (->) syntax."""
    PIPE = "|"      # Multi-line text, no logic
    ARROW = "->"    # Procedural with if/else, run, transition


@dataclass
class Variable:
    name: str
    var_type: str  # string, number, boolean, object, date, id, list[T]
    modifier: VariableModifier
    default: Optional[str] = None  # For mutable vars
    source: Optional[str] = None   # For linked vars (e.g. @session.sessionID)
    description: Optional[str] = None


@dataclass
class ActionInput:
    name: str
    input_type: str  # string, number, boolean, etc.
    description: Optional[str] = None
    is_required: bool = True


@dataclass
class ActionOutput:
    name: str
    output_type: str
    description: Optional[str] = None


@dataclass
class ActionDefinition:
    """Level 1: Defines WHAT to call (target, inputs, outputs)."""
    name: str
    description: str
    target: Optional[str] = None  # e.g. flow://Get_Order, apex://MyClass
    inputs: list[ActionInput] = field(default_factory=list)
    outputs: list[ActionOutput] = field(default_factory=list)


@dataclass
class ActionInvocation:
    """Level 2: Defines HOW to call it (with/set bindings, guards)."""
    name: str
    action_ref: str  # e.g. @actions.get_order, @utils.transition, @utils.escalate
    description: Optional[str] = None
    with_bindings: dict[str, str] = field(default_factory=dict)  # param -> value/expression
    set_bindings: dict[str, str] = field(default_factory=dict)   # @variables.x -> @outputs.y
    available_when: Optional[str] = None  # guard condition
    transition_target: Optional[str] = None  # for @utils.transition: topic name


@dataclass
class InstructionLine:
    """A single line of instruction content."""
    text: str
    indent: int = 0  # indentation level (for nested if/else)


@dataclass
class ConditionalBlock:
    """An if/else block in procedural instructions."""
    condition: str  # e.g. "@variables.verified == True"
    if_lines: list[str] = field(default_factory=list)
    else_lines: list[str] = field(default_factory=list)


@dataclass
class ReasoningBlock:
    mode: InstructionMode = InstructionMode.PIPE
    instruction_lines: list[str] = field(default_factory=list)
    conditionals: list[ConditionalBlock] = field(default_factory=list)
    inline_runs: list[dict] = field(default_factory=list)  # run @actions.x with/set
    action_invocations: list[ActionInvocation] = field(default_factory=list)


@dataclass
class Topic:
    name: str  # snake_case developer name
    description: str
    action_definitions: list[ActionDefinition] = field(default_factory=list)
    reasoning: ReasoningBlock = field(default_factory=ReasoningBlock)


@dataclass
class StartAgent:
    name: str = "entry"
    description: str = "Entry point - route to appropriate topic"
    reasoning: ReasoningBlock = field(default_factory=ReasoningBlock)


@dataclass
class ConfigBlock:
    developer_name: str
    agent_description: str
    agent_type: str = AgentType.SERVICE.value
    default_agent_user: str = ""


@dataclass
class SystemBlock:
    welcome_message: str = "Hello! How can I help you today?"
    error_message: str = "Sorry, something went wrong. Please try again."
    instructions: str = ""


@dataclass
class LanguageBlock:
    default_locale: str = "en_US"
    additional_locales: str = ""
    all_additional_locales: bool = False


@dataclass
class ConnectionBlock:
    channel: str = "messaging"
    outbound_route_type: str = "OmniChannelFlow"
    outbound_route_name: str = "flow://Route_from_Agent"
    escalation_message: str = "Connecting you with a specialist."
    adaptive_response_allowed: bool = False


@dataclass
class AgentDefinition:
    """Root IR node representing the entire agent."""
    config: ConfigBlock
    system: SystemBlock = field(default_factory=SystemBlock)
    variables: list[Variable] = field(default_factory=list)
    language: LanguageBlock = field(default_factory=LanguageBlock)
    connection: Optional[ConnectionBlock] = None
    start_agent: StartAgent = field(default_factory=StartAgent)
    topics: list[Topic] = field(default_factory=list)
