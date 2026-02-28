"""Tests for sub-agent parsing."""

from pathlib import Path

from scripts.parser.subagent import discover_subagents, parse_subagent


def test_basic_subagent(tmp_path: Path):
    md = tmp_path / "order-support.md"
    md.write_text("""---
name: order-support
description: Handles order inquiries and returns
tools: CheckOrderStatus, ProcessReturn
---
Help customers with their orders.

Always look up the order before processing a return.
If the order is older than 30 days, escalate to a manager.
""")
    topic = parse_subagent(md)
    assert topic.name == "order_support"
    assert topic.description == "Handles order inquiries and returns"
    assert len(topic.action_definitions) == 2
    assert topic.action_definitions[0].name == "check_order_status"
    assert topic.action_definitions[1].name == "process_return"
    assert len(topic.reasoning.instruction_lines) == 3
    assert "Help customers" in topic.reasoning.instruction_lines[0]


def test_subagent_no_tools(tmp_path: Path):
    md = tmp_path / "faq.md"
    md.write_text("""---
name: general-faq
description: Answers general questions
---
Answer general questions.
Be honest if you don't know.
""")
    topic = parse_subagent(md)
    assert topic.name == "general_faq"
    assert len(topic.action_definitions) == 0


def test_subagent_builtin_tools_filtered(tmp_path: Path):
    md = tmp_path / "reviewer.md"
    md.write_text("""---
name: code-reviewer
description: Reviews code
tools: Read, Grep, CustomAnalyzer
---
Review the code.
""")
    topic = parse_subagent(md)
    # Read and Grep are builtin, only CustomAnalyzer should remain
    assert len(topic.action_definitions) == 1
    assert topic.action_definitions[0].name == "custom_analyzer"


def test_subagent_tools_as_list(tmp_path: Path):
    md = tmp_path / "agent.md"
    md.write_text("""---
name: my-agent
description: Test
tools:
  - ToolA
  - ToolB
---
Do things.
""")
    topic = parse_subagent(md)
    assert len(topic.action_definitions) == 2


def test_discover_subagents(tmp_project: Path):
    agents_dir = tmp_project / ".claude" / "agents"
    (agents_dir / "alpha.md").write_text("---\nname: alpha\n---\nAlpha agent.")
    (agents_dir / "beta.md").write_text("---\nname: beta\n---\nBeta agent.")
    (agents_dir / "not-md.txt").write_text("ignored")

    paths = discover_subagents(tmp_project)
    assert len(paths) == 2
    names = [p.stem for p in paths]
    assert "alpha" in names
    assert "beta" in names


def test_subagent_lossy_fields_ignored(tmp_path: Path):
    """Lossy fields like model, maxTurns should not cause errors."""
    md = tmp_path / "agent.md"
    md.write_text("""---
name: test
description: Test agent
model: sonnet
maxTurns: 50
permissionMode: default
---
Do things.
""")
    topic = parse_subagent(md)
    assert topic.name == "test"
