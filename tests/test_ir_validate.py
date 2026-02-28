"""Tests for IR validation."""

import pytest

from scripts.ir.models import (
    ActionDefinition,
    AgentDefinition,
    ConfigBlock,
    ReasoningBlock,
    Topic,
)
from scripts.ir.validate import validate_agent


def _make_agent(**overrides):
    config = ConfigBlock(
        developer_name=overrides.get("developer_name", "TestAgent"),
        description=overrides.get("description", "A test agent"),
    )
    return AgentDefinition(
        config=config,
        topics=overrides.get("topics", []),
    )


class TestValidateAgent:
    def test_valid_agent_no_errors(self):
        agent = _make_agent(topics=[
            Topic(name="main", description="Main topic"),
        ])
        errors = validate_agent(agent)
        assert errors == []

    def test_empty_developer_name(self):
        agent = _make_agent(developer_name="")
        errors = validate_agent(agent)
        assert any("developer_name is empty" in e for e in errors)

    def test_long_developer_name(self):
        agent = _make_agent(developer_name="A" * 81)
        errors = validate_agent(agent)
        assert any("exceeds 80-character limit" in e for e in errors)

    def test_developer_name_starts_with_number(self):
        agent = _make_agent(developer_name="123Agent")
        errors = validate_agent(agent)
        assert any("must start with a letter" in e for e in errors)

    def test_empty_description(self):
        agent = _make_agent(description="")
        errors = validate_agent(agent)
        assert any("description is empty" in e for e in errors)

    def test_duplicate_topic_names(self):
        agent = _make_agent(topics=[
            Topic(name="orders", description="Orders"),
            Topic(name="orders", description="More orders"),
        ])
        errors = validate_agent(agent)
        assert any("Duplicate topic name: 'orders'" in e for e in errors)

    def test_empty_topic_description(self):
        agent = _make_agent(topics=[
            Topic(name="blank", description=""),
        ])
        errors = validate_agent(agent)
        assert any("empty description" in e for e in errors)

    def test_duplicate_action_names_in_topic(self):
        agent = _make_agent(topics=[
            Topic(
                name="support",
                description="Support",
                action_definitions=[
                    ActionDefinition(name="get_info", description="Get info", target="flow://A"),
                    ActionDefinition(name="get_info", description="Get info again", target="flow://B"),
                ],
            ),
        ])
        errors = validate_agent(agent)
        assert any("Duplicate action 'get_info'" in e for e in errors)

    def test_multiple_errors_reported(self):
        agent = _make_agent(
            developer_name="",
            description="",
            topics=[
                Topic(name="a", description=""),
                Topic(name="a", description="dup"),
            ],
        )
        errors = validate_agent(agent)
        assert len(errors) >= 3  # empty name, empty desc, duplicate topic, empty topic desc


class TestValidationInConvert:
    def test_convert_rejects_duplicate_topics(self, tmp_path):
        """Validation errors in convert() raise ValueError."""
        from scripts.convert import convert

        # Create a project with duplicate sub-agent names
        project = tmp_path / "project"
        project.mkdir()
        (project / "CLAUDE.md").write_text("Test agent.")
        agents_dir = project / ".claude" / "agents"
        agents_dir.mkdir(parents=True)
        # Two files that produce the same topic name
        (agents_dir / "orders.md").write_text(
            "---\nname: orders\ndescription: Orders\n---\nHandle orders."
        )
        (agents_dir / "orders-v2.md").write_text(
            "---\nname: orders\ndescription: Orders v2\n---\nHandle orders v2."
        )

        with pytest.raises(ValueError, match="Duplicate topic"):
            convert(
                project_root=project,
                agent_name="DupAgent",
                output_dir=tmp_path / "out",
            )
