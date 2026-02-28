"""Tests for Agent Script generator."""

from scripts.generator.agent_script import AgentScriptGenerator
from scripts.ir.models import (
    ActionDefinition,
    ActionInput,
    ActionInvocation,
    ActionOutput,
    AgentDefinition,
    ConfigBlock,
    ConnectionBlock,
    InstructionMode,
    LanguageBlock,
    ReasoningBlock,
    StartAgent,
    SystemBlock,
    Topic,
    Variable,
    VariableModifier,
)


def _make_minimal_agent() -> AgentDefinition:
    return AgentDefinition(
        config=ConfigBlock(
            developer_name="TestAgent",
            agent_description="A test agent",
            agent_type="AgentforceServiceAgent",
        ),
        system=SystemBlock(
            welcome_message="Hello!",
            error_message="Oops.",
            instructions="Be helpful.",
        ),
        language=LanguageBlock(),
        start_agent=StartAgent(
            reasoning=ReasoningBlock(
                mode=InstructionMode.PIPE,
                instruction_lines=["Greet the user."],
                action_invocations=[
                    ActionInvocation(
                        name="go_main",
                        action_ref="@utils.transition to @topic.main",
                        description="Go to main",
                    )
                ],
            )
        ),
        topics=[
            Topic(
                name="main",
                description="Main topic",
                reasoning=ReasoningBlock(
                    mode=InstructionMode.PIPE,
                    instruction_lines=["Help the user."],
                ),
            )
        ],
    )


def test_minimal_agent_generates():
    agent = _make_minimal_agent()
    gen = AgentScriptGenerator(agent)
    output = gen.generate()
    assert 'developer_name: "TestAgent"' in output
    assert 'agent_description: "A test agent"' in output
    assert 'welcome: "Hello!"' in output
    assert 'instructions: "Be helpful."' in output
    assert "start_agent entry:" in output
    assert "topic main:" in output


def test_config_block():
    agent = _make_minimal_agent()
    agent.config.default_agent_user = "agent@test.com"
    gen = AgentScriptGenerator(agent)
    output = gen.generate()
    assert 'default_agent_user: "agent@test.com"' in output


def test_variables_block():
    agent = _make_minimal_agent()
    agent.variables = [
        Variable(
            name="verified",
            var_type="boolean",
            modifier=VariableModifier.MUTABLE,
            default="False",
        ),
        Variable(
            name="EndUserId",
            var_type="string",
            modifier=VariableModifier.LINKED,
            source="@MessagingSession.MessagingEndUserId",
            description="Messaging End User ID",
        ),
    ]
    gen = AgentScriptGenerator(agent)
    output = gen.generate()
    assert "verified: mutable boolean = False" in output
    assert "EndUserId: linked string" in output
    assert "source: @MessagingSession.MessagingEndUserId" in output


def test_connection_block():
    agent = _make_minimal_agent()
    agent.connection = ConnectionBlock()
    gen = AgentScriptGenerator(agent)
    output = gen.generate()
    assert "connection messaging:" in output
    assert 'outbound_route_type: "OmniChannelFlow"' in output
    assert "adaptive_response_allowed: False" in output


def test_action_definitions():
    agent = _make_minimal_agent()
    agent.topics[0].action_definitions = [
        ActionDefinition(
            name="get_order",
            description="Get order details",
            target="flow://Get_Order_Details",
            inputs=[ActionInput(name="order_id", input_type="string", description="Order number")],
            outputs=[ActionOutput(name="status", output_type="string", description="Order status")],
        )
    ]
    gen = AgentScriptGenerator(agent)
    output = gen.generate()
    assert "get_order:" in output
    assert 'target: "flow://Get_Order_Details"' in output
    assert "order_id: string" in output
    assert "status: string" in output


def test_action_definition_without_target_rendered_as_stub():
    """Actions without a target are rendered as commented-out stubs with TODO."""
    agent = _make_minimal_agent()
    agent.topics[0].action_definitions = [
        ActionDefinition(name="unknown_action", description="No target yet")
    ]
    gen = AgentScriptGenerator(agent)
    output = gen.generate()
    # Should appear as a commented stub, not a real action definition
    assert "# TODO: The following actions need agentforce: target" in output
    assert "#    unknown_action:" in output
    assert '#       target: "flow://TODO_unknown_action"' in output
    # Should NOT appear as a real Level 1 definition
    topic_section = output.split("topic main:")[1]
    assert "\n   actions:\n" not in topic_section.split("# TODO")[0]


def test_action_invocations_with_bindings():
    agent = _make_minimal_agent()
    # Must have a matching action definition with a target for the invocation to render
    agent.topics[0].action_definitions = [
        ActionDefinition(
            name="lookup",
            description="Look up order",
            target="flow://Get_Order",
        ),
    ]
    agent.topics[0].reasoning.action_invocations = [
        ActionInvocation(
            name="lookup",
            action_ref="@actions.get_order",
            with_bindings={"order_id": "..."},
            set_bindings={"@variables.status": "@outputs.status"},
        ),
        ActionInvocation(
            name="escalate_now",
            action_ref="@utils.escalate",
            description="Transfer to human",
        ),
    ]
    gen = AgentScriptGenerator(agent)
    output = gen.generate()
    assert "lookup: @actions.get_order" in output
    assert "with order_id = ..." in output
    assert "set @variables.status = @outputs.status" in output
    assert "escalate_now: @utils.escalate" in output


def test_available_when_guard():
    agent = _make_minimal_agent()
    agent.topics[0].reasoning.action_invocations = [
        ActionInvocation(
            name="go_account",
            action_ref="@utils.transition to @topic.account",
            available_when="@variables.verified == True",
        ),
    ]
    gen = AgentScriptGenerator(agent)
    output = gen.generate()
    assert "available when @variables.verified == True" in output


def test_multiline_system_instructions():
    agent = _make_minimal_agent()
    agent.system.instructions = "Line one.\nLine two.\nLine three."
    gen = AgentScriptGenerator(agent)
    output = gen.generate()
    assert "instructions: |" in output
    assert "Line one." in output
    assert "Line three." in output


def test_three_space_indentation():
    agent = _make_minimal_agent()
    gen = AgentScriptGenerator(agent)
    output = gen.generate()
    # Check that we're using 3-space indentation
    lines = output.splitlines()
    indented = [l for l in lines if l.startswith(" ") and not l.startswith("    ")]
    # All indented lines should use multiples of 3 spaces
    for line in indented:
        spaces = len(line) - len(line.lstrip())
        assert spaces % 3 == 0, f"Line has {spaces} spaces (not multiple of 3): {line!r}"
