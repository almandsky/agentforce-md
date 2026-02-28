"""Unit tests for the convert orchestrator logic."""

from pathlib import Path

from scripts.convert import convert, _derive_description


class TestDeriveDescription:
    def test_uses_first_line(self):
        instructions = "You are a helpful agent.\nBe concise."
        assert _derive_description(instructions, "Test") == "You are a helpful agent."

    def test_fallback_when_empty(self):
        assert _derive_description("", "MyBot") == "MyBot agent"

    def test_truncates_long_instructions(self):
        long_line = "A" * 300
        result = _derive_description(long_line, "Test")
        assert len(result) == 200
        assert result.endswith("...")


class TestSkillMerging:
    def test_skill_target_merged_into_topic_actions(self, tmp_path: Path):
        """When a SKILL.md has agentforce target, it should fill the action definition."""
        # Create project structure
        (tmp_path / ".claude" / "agents").mkdir(parents=True)
        (tmp_path / ".claude" / "skills" / "check-order-status").mkdir(parents=True)

        (tmp_path / "CLAUDE.md").write_text("You are a support agent.")

        (tmp_path / ".claude" / "agents" / "orders.md").write_text(
            "---\nname: orders\ndescription: Order support\ntools: CheckOrderStatus\n---\n"
            "Handle orders."
        )

        (tmp_path / ".claude" / "skills" / "check-order-status" / "SKILL.md").write_text(
            "---\nname: check-order-status\ndescription: Check order status\n"
            "agentforce:\n  target: \"flow://Get_Order_Details\"\n"
            "  inputs:\n    order_id:\n      type: string\n      description: Order number\n"
            "  outputs:\n    status:\n      type: string\n      description: Order status\n---\n"
            "Check the order."
        )

        bundle_dir = convert(
            project_root=tmp_path,
            agent_name="MergeTest",
            output_dir=tmp_path / "out",
        )

        content = (bundle_dir / "MergeTest.agent").read_text()
        assert 'target: "flow://Get_Order_Details"' in content
        assert "order_id: string" in content
        assert "status: string" in content

    def test_no_skill_omits_targetless_actions(self, tmp_path: Path):
        """Tools without SKILL.md (no target) are omitted from the output."""
        (tmp_path / ".claude" / "agents").mkdir(parents=True)
        (tmp_path / "CLAUDE.md").write_text("Agent instructions.")

        (tmp_path / ".claude" / "agents" / "topic.md").write_text(
            "---\nname: topic\ndescription: A topic\ntools: UnknownTool\n---\nDo things."
        )

        bundle_dir = convert(
            project_root=tmp_path,
            agent_name="StubTest",
            output_dir=tmp_path / "out",
        )

        content = (bundle_dir / "StubTest.agent").read_text()
        # Action without target should be omitted (would cause compile error)
        assert "unknown_tool" not in content
        # But the topic should still exist
        assert "topic topic:" in content

    def test_no_subagents_produces_empty_agent(self, tmp_path: Path):
        """A project with only CLAUDE.md and no sub-agents should still produce output."""
        (tmp_path / "CLAUDE.md").write_text("Minimal agent.")

        bundle_dir = convert(
            project_root=tmp_path,
            agent_name="EmptyAgent",
            output_dir=tmp_path / "out",
        )

        content = (bundle_dir / "EmptyAgent.agent").read_text()
        assert 'developer_name: "EmptyAgent"' in content
        assert "start_agent entry:" in content

    def test_default_output_dir(self, tmp_path: Path):
        """When output_dir is None, output goes to project_root/force-app/main/default."""
        (tmp_path / "CLAUDE.md").write_text("Agent.")

        bundle_dir = convert(
            project_root=tmp_path,
            agent_name="DefaultDir",
        )

        expected = tmp_path / "force-app" / "main" / "default" / "aiAuthoringBundles" / "DefaultDir"
        assert bundle_dir == expected
        assert bundle_dir.is_dir()
