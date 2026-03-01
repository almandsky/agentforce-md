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

    def test_no_skill_renders_stub_comment(self, tmp_path: Path):
        """Tools without SKILL.md (no target) are rendered as commented-out stubs."""
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
        # Action without target should be a commented-out stub
        assert "# TODO: The following actions need agentforce: target" in content
        assert "#    unknown_tool:" in content
        assert '#       target: "flow://TODO_unknown_tool"' in content
        # The topic should still exist
        assert "topic topic:" in content

    def test_strict_mode_fails_on_unresolved(self, tmp_path: Path):
        """In strict mode, unresolved actions should raise ValueError."""
        import pytest

        (tmp_path / ".claude" / "agents").mkdir(parents=True)
        (tmp_path / "CLAUDE.md").write_text("Agent instructions.")

        (tmp_path / ".claude" / "agents" / "topic.md").write_text(
            "---\nname: topic\ndescription: A topic\ntools: UnresolvedTool\n---\nDo things."
        )

        with pytest.raises(ValueError, match="Strict mode"):
            convert(
                project_root=tmp_path,
                agent_name="StrictTest",
                output_dir=tmp_path / "out",
                strict=True,
            )

    def test_strict_mode_passes_when_all_resolved(self, tmp_path: Path):
        """In strict mode, fully resolved actions should succeed."""
        (tmp_path / ".claude" / "agents").mkdir(parents=True)
        (tmp_path / ".claude" / "skills" / "my-tool").mkdir(parents=True)
        (tmp_path / "CLAUDE.md").write_text("Agent instructions.")

        (tmp_path / ".claude" / "agents" / "topic.md").write_text(
            "---\nname: topic\ndescription: A topic\ntools: MyTool\n---\nDo things."
        )
        (tmp_path / ".claude" / "skills" / "my-tool" / "SKILL.md").write_text(
            "---\nname: MyTool\ndescription: A tool\n"
            "agentforce:\n  target: \"flow://My_Flow\"\n---\nUse this."
        )

        bundle_dir = convert(
            project_root=tmp_path,
            agent_name="StrictPass",
            output_dir=tmp_path / "out",
            strict=True,
        )
        content = (bundle_dir / "StrictPass.agent").read_text()
        assert 'target: "flow://My_Flow"' in content

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

    def test_default_output_dir(self, tmp_path: Path, monkeypatch):
        """When output_dir is None, output goes to cwd/force-app/main/default."""
        (tmp_path / "CLAUDE.md").write_text("Agent.")
        monkeypatch.chdir(tmp_path)

        bundle_dir = convert(
            project_root=tmp_path,
            agent_name="DefaultDir",
        )

        expected = tmp_path / "force-app" / "main" / "default" / "aiAuthoringBundles" / "DefaultDir"
        assert bundle_dir == expected
        assert bundle_dir.is_dir()


class TestUserDefinedVariables:
    def test_mutable_variables_from_frontmatter(self, tmp_path: Path):
        """Mutable variables from CLAUDE.md frontmatter appear in output."""
        (tmp_path / ".claude" / "agents").mkdir(parents=True)
        (tmp_path / "CLAUDE.md").write_text("""---
variables:
  isVerified:
    type: boolean
    modifier: mutable
    default: "False"
    description: "Whether customer is verified"
    label: "Verified"
    visibility: Internal
---
Service agent instructions.
""")
        (tmp_path / ".claude" / "agents" / "faq.md").write_text(
            "---\nname: faq\ndescription: FAQ\n---\nAnswer questions."
        )

        bundle_dir = convert(
            project_root=tmp_path,
            agent_name="VarTest",
            output_dir=tmp_path / "out",
        )
        content = (bundle_dir / "VarTest.agent").read_text()
        assert "isVerified: mutable boolean = False" in content
        assert 'description: "Whether customer is verified"' in content
        assert 'label: "Verified"' in content
        assert 'visibility: "Internal"' in content

    def test_user_linked_var_overrides_default(self, tmp_path: Path):
        """User-defined EndUserId replaces the auto-generated one."""
        (tmp_path / ".claude" / "agents").mkdir(parents=True)
        (tmp_path / "CLAUDE.md").write_text("""---
agent_type: AgentforceServiceAgent
variables:
  EndUserId:
    type: string
    modifier: linked
    source: "@session.custom_end_user_id"
    description: "Custom end user"
    visibility: Internal
---
Service agent.
""")
        (tmp_path / ".claude" / "agents" / "faq.md").write_text(
            "---\nname: faq\ndescription: FAQ\n---\nAnswer."
        )

        bundle_dir = convert(
            project_root=tmp_path,
            agent_name="OverrideTest",
            output_dir=tmp_path / "out",
        )
        content = (bundle_dir / "OverrideTest.agent").read_text()
        # User's custom source should appear, not the default
        assert "source: @session.custom_end_user_id" in content
        assert "@MessagingSession.MessagingEndUserId" not in content
        # Other default linked vars should still be added
        assert "RoutableId: linked string" in content
        assert "ContactId: linked string" in content

    def test_knowledge_block_from_frontmatter(self, tmp_path: Path):
        """Knowledge block from CLAUDE.md frontmatter appears in output."""
        (tmp_path / "CLAUDE.md").write_text("""---
knowledge:
  citations_enabled: true
---
Agent.
""")

        bundle_dir = convert(
            project_root=tmp_path,
            agent_name="KnowledgeTest",
            output_dir=tmp_path / "out",
        )
        content = (bundle_dir / "KnowledgeTest.agent").read_text()
        assert "knowledge:" in content
        assert "citations_enabled: True" in content


class TestActionBindings:
    def test_with_and_set_bindings_in_output(self, tmp_path: Path):
        """Action bindings from sub-agent agentforce section render in output."""
        (tmp_path / ".claude" / "agents").mkdir(parents=True)
        (tmp_path / ".claude" / "skills" / "identify-record").mkdir(parents=True)
        (tmp_path / "CLAUDE.md").write_text("Agent.")

        (tmp_path / ".claude" / "agents" / "verify.md").write_text("""---
name: verify
description: Verify identity
tools: IdentifyRecord
agentforce:
  label: "Customer Verification"
  bindings:
    IdentifyRecord:
      with:
        customerId: "@variables.VerifiedCustomerId"
      set:
        "@variables.isVerified": "@outputs.isVerified"
      after:
        if: "@variables.isVerified"
        transition_to: "account-management"
---
Verify the customer.
""")

        (tmp_path / ".claude" / "skills" / "identify-record" / "SKILL.md").write_text(
            "---\nname: identify-record\ndescription: Identify record\n"
            "agentforce:\n  target: \"flow://Identify_Record\"\n"
            "  inputs:\n    customerId:\n      type: string\n"
            "  outputs:\n    isVerified:\n      type: boolean\n---\n"
        )

        bundle_dir = convert(
            project_root=tmp_path,
            agent_name="BindTest",
            output_dir=tmp_path / "out",
        )
        content = (bundle_dir / "BindTest.agent").read_text()
        assert 'label: "Customer Verification"' in content
        assert "with customerId = @variables.VerifiedCustomerId" in content
        assert "set @variables.isVerified = @outputs.isVerified" in content
        assert "if @variables.isVerified:" in content
        assert "transition to @topic.account_management" in content

    def test_available_when_on_start_agent_transition(self, tmp_path: Path):
        """Topic available_when propagates to start_agent transition."""
        (tmp_path / ".claude" / "agents").mkdir(parents=True)
        (tmp_path / "CLAUDE.md").write_text("Agent.")

        (tmp_path / ".claude" / "agents" / "account.md").write_text("""---
name: account
description: Account management
agentforce:
  available_when: "@variables.isVerified==True"
---
Manage accounts.
""")

        bundle_dir = convert(
            project_root=tmp_path,
            agent_name="GuardTest",
            output_dir=tmp_path / "out",
        )
        content = (bundle_dir / "GuardTest.agent").read_text()
        # The start_agent transition should have the guard
        start_section = content.split("start_agent entry:")[1].split("topic ")[0]
        assert "available when @variables.isVerified==True" in start_section
