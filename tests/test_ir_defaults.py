"""Tests for IR default enrichment."""

from scripts.ir.defaults import (
    add_connection_block,
    add_linked_variables,
    apply_defaults,
    generate_start_agent,
)
from scripts.ir.models import (
    ActionInvocation,
    AgentDefinition,
    AgentType,
    ConfigBlock,
    ConnectionBlock,
    ReasoningBlock,
    Topic,
    Variable,
    VariableModifier,
)


def _make_agent(agent_type=AgentType.SERVICE.value, topics=None, connection=None):
    return AgentDefinition(
        config=ConfigBlock(
            developer_name="TestAgent",
            description="Test",
            agent_type=agent_type,
        ),
        topics=topics or [],
        connection=connection,
    )


class TestAddLinkedVariables:
    def test_adds_three_linked_vars_for_service_agent(self):
        agent = _make_agent()
        add_linked_variables(agent)
        names = [v.name for v in agent.variables]
        assert "EndUserId" in names
        assert "RoutableId" in names
        assert "ContactId" in names
        assert len(agent.variables) == 3

    def test_skips_for_employee_agent(self):
        agent = _make_agent(agent_type=AgentType.EMPLOYEE.value)
        add_linked_variables(agent)
        assert agent.variables == []

    def test_does_not_duplicate_existing(self):
        agent = _make_agent()
        agent.variables.append(
            Variable(name="EndUserId", var_type="string", modifier=VariableModifier.LINKED)
        )
        add_linked_variables(agent)
        end_user_vars = [v for v in agent.variables if v.name == "EndUserId"]
        assert len(end_user_vars) == 1
        assert len(agent.variables) == 3  # EndUserId + RoutableId + ContactId

    def test_linked_vars_have_correct_sources(self):
        agent = _make_agent()
        add_linked_variables(agent)
        by_name = {v.name: v for v in agent.variables}
        assert by_name["EndUserId"].source == "@MessagingSession.MessagingEndUserId"
        assert by_name["RoutableId"].source == "@MessagingSession.Id"
        assert by_name["ContactId"].source == "@MessagingEndUser.ContactId"

    def test_linked_vars_have_external_visibility(self):
        agent = _make_agent()
        add_linked_variables(agent)
        for var in agent.variables:
            assert var.visibility == "External"


class TestGenerateStartAgent:
    def test_creates_transitions_for_each_topic(self):
        agent = _make_agent(topics=[
            Topic(name="alpha", description="Alpha topic"),
            Topic(name="beta", description="Beta topic"),
        ])
        generate_start_agent(agent)

        inv_names = [i.name for i in agent.start_agent.reasoning.action_invocations]
        assert "go_alpha" in inv_names
        assert "go_beta" in inv_names

    def test_transitions_reference_correct_topics(self):
        agent = _make_agent(topics=[
            Topic(name="orders", description="Order handling"),
        ])
        generate_start_agent(agent)

        inv = agent.start_agent.reasoning.action_invocations[0]
        assert "@utils.transition to @topic.orders" in inv.action_ref
        assert inv.transition_target == "orders"

    def test_no_topics_no_change(self):
        agent = _make_agent(topics=[])
        original_start = agent.start_agent
        generate_start_agent(agent)
        assert agent.start_agent is original_start

    def test_start_agent_has_instruction_lines(self):
        agent = _make_agent(topics=[Topic(name="main", description="Main")])
        generate_start_agent(agent)
        assert len(agent.start_agent.reasoning.instruction_lines) == 2

    def test_start_agent_name_and_description(self):
        agent = _make_agent(topics=[Topic(name="main", description="Main")])
        generate_start_agent(agent)
        assert agent.start_agent.name == "entry"
        assert "route" in agent.start_agent.description.lower()


class TestAddConnectionBlock:
    def test_adds_connection_when_escalation_exists(self):
        topic = Topic(
            name="support",
            description="Support",
            reasoning=ReasoningBlock(
                action_invocations=[
                    ActionInvocation(
                        name="escalate",
                        action_ref="@utils.escalate",
                        description="Escalate",
                    )
                ]
            ),
        )
        agent = _make_agent(topics=[topic])
        add_connection_block(agent)
        assert agent.connection is not None
        assert agent.connection.channel == "messaging"

    def test_no_connection_without_escalation(self):
        topic = Topic(
            name="faq",
            description="FAQ",
            reasoning=ReasoningBlock(
                action_invocations=[
                    ActionInvocation(name="search", action_ref="@actions.search")
                ]
            ),
        )
        agent = _make_agent(topics=[topic])
        add_connection_block(agent)
        assert agent.connection is None

    def test_does_not_overwrite_existing_connection(self):
        custom_conn = ConnectionBlock(escalation_message="Custom message")
        agent = _make_agent(connection=custom_conn)
        add_connection_block(agent)
        assert agent.connection.escalation_message == "Custom message"


class TestApplyDefaults:
    def test_applies_all_defaults(self):
        agent = _make_agent(topics=[
            Topic(name="main", description="Main topic"),
        ])
        apply_defaults(agent)

        # Linked vars added
        assert len(agent.variables) == 3
        # Start agent generated
        assert len(agent.start_agent.reasoning.action_invocations) == 1
        # No connection (no escalation)
        assert agent.connection is None
