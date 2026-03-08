"""Tests for Agent Script generator."""

from scripts.generator.agent_script import AgentScriptGenerator, _escape
from scripts.ir.models import (
    ActionDefinition,
    ActionInput,
    ActionInvocation,
    ActionOutput,
    AfterReasoningDirective,
    AgentDefinition,
    ConfigBlock,
    ConnectionBlock,
    InstructionMode,
    KnowledgeBlock,
    LanguageBlock,
    PostActionBranch,
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
            description="A test agent",
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
    assert 'description: "A test agent"' in output
    assert 'welcome: "Hello!"' in output
    assert 'instructions: "Be helpful."' in output
    assert "start_agent entry:" in output
    assert "topic main:" in output


def test_block_ordering():
    """Verify the output follows: system -> config -> language -> variables -> knowledge -> start_agent -> topics."""
    agent = _make_minimal_agent()
    agent.variables = [
        Variable(name="v1", var_type="string", modifier=VariableModifier.MUTABLE),
    ]
    agent.knowledge = KnowledgeBlock()
    gen = AgentScriptGenerator(agent)
    output = gen.generate()
    system_pos = output.index("system:")
    config_pos = output.index("config:")
    lang_pos = output.index("language:")
    vars_pos = output.index("variables:")
    knowledge_pos = output.index("knowledge:")
    start_pos = output.index("start_agent")
    topic_pos = output.index("topic main:")
    assert system_pos < config_pos < lang_pos < vars_pos < knowledge_pos < start_pos < topic_pos


def test_system_instructions_before_messages():
    """Instructions should appear before messages in the system block."""
    agent = _make_minimal_agent()
    gen = AgentScriptGenerator(agent)
    output = gen.generate()
    instr_pos = output.index("instructions:")
    msg_pos = output.index("messages:")
    assert instr_pos < msg_pos


def test_config_block():
    agent = _make_minimal_agent()
    agent.config.default_agent_user = "agent@test.com"
    gen = AgentScriptGenerator(agent)
    output = gen.generate()
    assert 'default_agent_user: "agent@test.com"' in output


def test_config_agent_label():
    agent = _make_minimal_agent()
    agent.config.agent_label = "My Agent"
    gen = AgentScriptGenerator(agent)
    output = gen.generate()
    assert 'agent_label: "My Agent"' in output


def test_config_description_field_name():
    """Config should use 'description' not 'agent_description'."""
    agent = _make_minimal_agent()
    gen = AgentScriptGenerator(agent)
    output = gen.generate()
    config_section = output.split("config:")[1].split("\n\n")[0]
    assert "description:" in config_section
    assert "agent_description:" not in config_section


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
            visibility="External",
        ),
    ]
    gen = AgentScriptGenerator(agent)
    output = gen.generate()
    assert "verified: mutable boolean = False" in output
    assert "EndUserId: linked string" in output
    assert "source: @MessagingSession.MessagingEndUserId" in output
    assert 'visibility: "External"' in output


def test_variable_label():
    agent = _make_minimal_agent()
    agent.variables = [
        Variable(
            name="CustomerName",
            var_type="string",
            modifier=VariableModifier.MUTABLE,
            label="Customer Name",
        ),
    ]
    gen = AgentScriptGenerator(agent)
    output = gen.generate()
    assert 'label: "Customer Name"' in output


def test_knowledge_block():
    agent = _make_minimal_agent()
    agent.knowledge = KnowledgeBlock(citations_enabled=False)
    gen = AgentScriptGenerator(agent)
    output = gen.generate()
    assert "knowledge:" in output
    assert "citations_enabled: False" in output


def test_no_knowledge_block_by_default():
    agent = _make_minimal_agent()
    gen = AgentScriptGenerator(agent)
    output = gen.generate()
    assert "knowledge:" not in output


def test_connection_block():
    agent = _make_minimal_agent()
    agent.connection = ConnectionBlock()
    gen = AgentScriptGenerator(agent)
    output = gen.generate()
    assert "connection messaging:" in output
    assert 'outbound_route_type: "OmniChannelFlow"' in output
    assert "adaptive_response_allowed: False" in output


def test_start_agent_label():
    agent = _make_minimal_agent()
    agent.start_agent.label = "Entry Point"
    gen = AgentScriptGenerator(agent)
    output = gen.generate()
    assert 'label: "Entry Point"' in output


def test_topic_label():
    agent = _make_minimal_agent()
    agent.topics[0].label = "Main Topic"
    gen = AgentScriptGenerator(agent)
    output = gen.generate()
    assert 'label: "Main Topic"' in output


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


def test_action_definition_new_fields():
    agent = _make_minimal_agent()
    agent.topics[0].action_definitions = [
        ActionDefinition(
            name="get_order",
            description="Get order details",
            target="flow://Get_Order_Details",
            label="Get Order",
            require_user_confirmation=True,
            include_in_progress_indicator=True,
            progress_indicator_message="Looking up order...",
            source="Get_Order_Details",
        )
    ]
    gen = AgentScriptGenerator(agent)
    output = gen.generate()
    assert 'label: "Get Order"' in output
    assert "require_user_confirmation: True" in output
    assert "include_in_progress_indicator: True" in output
    assert 'progress_indicator_message: "Looking up order..."' in output
    assert 'source: "Get_Order_Details"' in output


def test_action_input_new_fields():
    agent = _make_minimal_agent()
    agent.topics[0].action_definitions = [
        ActionDefinition(
            name="search",
            description="Search",
            target="flow://Search",
            inputs=[ActionInput(
                name="query",
                input_type="string",
                label="Search Query",
                is_user_input=True,
                complex_data_type_name="QueryType",
                default_value="@knowledge.citations_url",
            )],
        )
    ]
    gen = AgentScriptGenerator(agent)
    output = gen.generate()
    assert 'label: "Search Query"' in output
    assert "is_user_input: True" in output
    assert 'complex_data_type_name: "QueryType"' in output
    assert "default_value: @knowledge.citations_url" in output


def test_action_output_new_fields():
    agent = _make_minimal_agent()
    agent.topics[0].action_definitions = [
        ActionDefinition(
            name="search",
            description="Search",
            target="flow://Search",
            outputs=[ActionOutput(
                name="result",
                output_type="string",
                label="Search Result",
                complex_data_type_name="ResultType",
                filter_from_agent=True,
                is_displayable=False,
            )],
        )
    ]
    gen = AgentScriptGenerator(agent)
    output = gen.generate()
    assert 'label: "Search Result"' in output
    assert 'complex_data_type_name: "ResultType"' in output
    assert "filter_from_agent: True" in output
    assert "is_displayable: False" in output


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
    assert "\n    actions:\n" not in topic_section.split("# TODO")[0]


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


def test_default_valued_fields_omitted():
    """Fields at their default values should not appear in the output."""
    agent = _make_minimal_agent()
    agent.topics[0].action_definitions = [
        ActionDefinition(
            name="basic",
            description="Basic action",
            target="flow://Basic",
            inputs=[ActionInput(name="x", input_type="string")],
            outputs=[ActionOutput(name="y", output_type="string")],
            # All other fields at defaults
        )
    ]
    gen = AgentScriptGenerator(agent)
    output = gen.generate()
    # These default-valued fields should NOT appear
    assert "require_user_confirmation:" not in output
    assert "include_in_progress_indicator:" not in output
    assert "progress_indicator_message:" not in output
    assert "is_user_input:" not in output
    assert "filter_from_agent:" not in output
    assert "is_displayable:" not in output
    assert "complex_data_type_name:" not in output
    assert "default_value:" not in output
    # label/source should not appear either
    assert "source:" not in output.split("basic:")[1].split("target:")[0]


def test_post_action_branch():
    """Post-action if/transition renders correctly."""
    agent = _make_minimal_agent()
    agent.topics[0].action_definitions = [
        ActionDefinition(
            name="identify",
            description="Identify customer",
            target="flow://Identify_Record",
        ),
    ]
    agent.topics[0].reasoning.action_invocations = [
        ActionInvocation(
            name="identify",
            action_ref="@actions.identify",
            set_bindings={"@variables.isVerified": "@outputs.isVerified"},
            post_branches=[
                PostActionBranch(
                    condition="@variables.isVerified",
                    transition_to="case_management",
                ),
            ],
        ),
    ]
    gen = AgentScriptGenerator(agent)
    output = gen.generate()
    assert "set @variables.isVerified = @outputs.isVerified" in output
    assert "if @variables.isVerified:" in output
    assert "transition to @topic.case_management" in output


def test_post_action_multiple_branches():
    """Multiple post-action branches render in order."""
    agent = _make_minimal_agent()
    agent.topics[0].action_definitions = [
        ActionDefinition(name="check", description="Check", target="flow://Check"),
    ]
    agent.topics[0].reasoning.action_invocations = [
        ActionInvocation(
            name="check",
            action_ref="@actions.check",
            post_branches=[
                PostActionBranch(condition="@variables.urgent", transition_to="escalation"),
                PostActionBranch(condition="@variables.resolved", transition_to="done"),
            ],
        ),
    ]
    gen = AgentScriptGenerator(agent)
    output = gen.generate()
    assert "if @variables.urgent:" in output
    assert "transition to @topic.escalation" in output
    assert "if @variables.resolved:" in output
    assert "transition to @topic.done" in output


def test_full_action_invocation_with_all_features():
    """An invocation with with, set, and post-branch renders in correct order."""
    agent = _make_minimal_agent()
    agent.topics[0].action_definitions = [
        ActionDefinition(name="verify", description="Verify", target="flow://Verify"),
    ]
    agent.topics[0].reasoning.action_invocations = [
        ActionInvocation(
            name="verify",
            action_ref="@actions.verify",
            description="Verify customer identity",
            available_when="@variables.hasId==True",
            with_bindings={"customerId": "@variables.CustomerId"},
            set_bindings={"@variables.isVerified": "@outputs.verified"},
            post_branches=[
                PostActionBranch(condition="@variables.isVerified", transition_to="account_mgmt"),
            ],
        ),
    ]
    gen = AgentScriptGenerator(agent)
    output = gen.generate()
    # Verify ordering within the invocation
    topic_section = output.split("topic main:")[1]
    desc_pos = topic_section.index("description:")
    avail_pos = topic_section.index("available when")
    with_pos = topic_section.index("with customerId")
    set_pos = topic_section.index("set @variables")
    if_pos = topic_section.index("if @variables.isVerified:")
    trans_pos = topic_section.index("transition to @topic.account_mgmt")
    assert desc_pos < avail_pos < with_pos < set_pos < if_pos < trans_pos


def test_after_reasoning_conditional_run():
    """after_reasoning with a conditional run renders directive syntax correctly."""
    agent = _make_minimal_agent()
    agent.topics[0].after_reasoning_directives = [
        AfterReasoningDirective(
            condition="@variables.caseDescriptionCollected",
            run="@actions.create_case",
            with_bindings={
                "subject": "@variables.caseSubject",
                "description": "@variables.caseDescription",
            },
            set_bindings={"@variables.caseId": "@outputs.caseId"},
        ),
    ]
    gen = AgentScriptGenerator(agent)
    output = gen.generate()

    assert "after_reasoning:" in output
    assert "if @variables.caseDescriptionCollected:" in output
    assert "run @actions.create_case" in output
    # Directive syntax: no spaces around = in with
    assert "with subject=@variables.caseSubject" in output
    assert "with description=@variables.caseDescription" in output
    # set uses spaces around =
    assert "set @variables.caseId = @outputs.caseId" in output


def test_after_reasoning_bare_transition():
    """after_reasoning with a conditional bare transition renders correctly."""
    agent = _make_minimal_agent()
    agent.topics[0].after_reasoning_directives = [
        AfterReasoningDirective(
            condition='@variables.caseId != ""',
            transition_to="case_confirmation",
        ),
    ]
    gen = AgentScriptGenerator(agent)
    output = gen.generate()

    assert "after_reasoning:" in output
    assert 'if @variables.caseId != "":' in output
    assert "transition to @topic.case_confirmation" in output
    # Should NOT appear as a reasoning-block invocation
    assert "available when" not in output.split("after_reasoning:")[1]


def test_after_reasoning_multiple_directives():
    """Multiple directives are separated by blank lines."""
    agent = _make_minimal_agent()
    agent.topics[0].after_reasoning_directives = [
        AfterReasoningDirective(
            condition="@variables.verified",
            run="@actions.get_history",
            with_bindings={"customer_id": "@variables.customerId"},
            set_bindings={"@variables.caseCount": "@outputs.previousCases"},
        ),
        AfterReasoningDirective(
            condition='@variables.caseType != ""',
            transition_to="case_creation",
        ),
    ]
    gen = AgentScriptGenerator(agent)
    output = gen.generate()

    after_section = output.split("after_reasoning:")[1]
    run_pos = after_section.index("run @actions.get_history")
    transition_pos = after_section.index("transition to @topic.case_creation")
    assert run_pos < transition_pos

    # Blank line between directives
    between = after_section[run_pos:transition_pos]
    assert "\n\n" in between


def test_after_reasoning_unconditional_run():
    """An unconditional directive (no if) indents one level inside after_reasoning."""
    agent = _make_minimal_agent()
    agent.topics[0].after_reasoning_directives = [
        AfterReasoningDirective(
            run="@actions.log_audit_event",
            with_bindings={"userId": "@variables.userId"},
        ),
    ]
    gen = AgentScriptGenerator(agent)
    output = gen.generate()

    assert "after_reasoning:" in output
    assert "run @actions.log_audit_event" in output
    # No conditional wrapping
    after_section = output.split("after_reasoning:")[1]
    assert "if " not in after_section.split("run")[0]


def test_after_reasoning_comes_after_reasoning_block():
    """after_reasoning must appear after the reasoning block in the topic."""
    agent = _make_minimal_agent()
    agent.topics[0].after_reasoning_directives = [
        AfterReasoningDirective(
            condition="@variables.done",
            transition_to="done_topic",
        ),
    ]
    gen = AgentScriptGenerator(agent)
    output = gen.generate()

    reasoning_pos = output.index("reasoning:")
    after_pos = output.index("after_reasoning:")
    assert reasoning_pos < after_pos


def test_after_reasoning_uses_directive_not_name_binding_syntax():
    """Verifies directive syntax (run/with=) not name-binding syntax (name: @actions / with =)."""
    agent = _make_minimal_agent()
    agent.topics[0].after_reasoning_directives = [
        AfterReasoningDirective(
            condition="@variables.ready",
            run="@actions.do_thing",
            with_bindings={"param": "@variables.value"},
        ),
    ]
    gen = AgentScriptGenerator(agent)
    output = gen.generate()
    after_section = output.split("after_reasoning:")[1]

    # Directive syntax: "run @actions.X" (not "name: @actions.X")
    assert "run @actions.do_thing" in after_section
    # No spaces around = in with
    assert "with param=@variables.value" in after_section
    # Should NOT use name-binding syntax
    assert "do_thing: @actions" not in after_section
    assert "with param = @variables.value" not in after_section


def test_no_after_reasoning_block_when_empty():
    """Topics with no after_reasoning directives should not emit the block."""
    agent = _make_minimal_agent()
    gen = AgentScriptGenerator(agent)
    output = gen.generate()
    assert "after_reasoning:" not in output


def test_escape_em_dash():
    """Em dash (U+2014) is replaced with spaced double-hyphen."""
    assert _escape("before\u2014after") == "before -- after"


def test_escape_en_dash():
    """En dash (U+2013) is replaced with a plain hyphen."""
    assert _escape("pages 1\u201310") == "pages 1-10"


def test_escape_newlines():
    """Newlines are collapsed to single spaces."""
    assert _escape("line one\nline two\r\nline three") == "line one line two line three"


def test_escape_multiline_description():
    """A multi-line YAML description becomes a single clean line."""
    text = "Help customers with their orders.\nProvide tracking info\nand handle returns."
    result = _escape(text)
    assert "\n" not in result
    assert result == "Help customers with their orders. Provide tracking info and handle returns."


def test_escape_combined():
    """Em dash + newline + quotes all handled together."""
    text = 'She said \u2014 "hello"\nand left.'
    result = _escape(text)
    assert result == 'She said -- \\"hello\\" and left.'


def test_four_space_indentation():
    agent = _make_minimal_agent()
    gen = AgentScriptGenerator(agent)
    output = gen.generate()
    # Check that we're using 4-space indentation
    lines = output.splitlines()
    indented = [l for l in lines if l.startswith(" ")]
    # All indented lines should use multiples of 4 spaces
    for line in indented:
        spaces = len(line) - len(line.lstrip())
        assert spaces % 4 == 0, f"Line has {spaces} spaces (not multiple of 4): {line!r}"
