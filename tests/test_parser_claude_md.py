"""Tests for CLAUDE.md parsing."""

from pathlib import Path

from scripts.parser.claude_md import parse_claude_md, parse_claude_md_structured


def test_basic_claude_md(tmp_path: Path):
    md = tmp_path / "CLAUDE.md"
    md.write_text("You are a customer support agent.\nBe helpful and concise.")
    result = parse_claude_md(md)
    assert "customer support agent" in result
    assert "Be helpful" in result


def test_strips_top_level_header(tmp_path: Path):
    md = tmp_path / "CLAUDE.md"
    md.write_text("# My Agent\n\nYou are helpful.\n\n## Section\nMore details.")
    result = parse_claude_md(md)
    assert "# My Agent" not in result
    assert "You are helpful." in result
    assert "## Section" in result


def test_missing_file(tmp_path: Path):
    result = parse_claude_md(tmp_path / "nonexistent.md")
    assert result == ""


def test_empty_file(tmp_path: Path):
    md = tmp_path / "CLAUDE.md"
    md.write_text("")
    result = parse_claude_md(md)
    assert result == ""


def test_collapses_blank_lines(tmp_path: Path):
    md = tmp_path / "CLAUDE.md"
    md.write_text("Line 1\n\n\n\nLine 2")
    result = parse_claude_md(md)
    assert "\n\n\n" not in result
    assert "Line 1" in result
    assert "Line 2" in result


# --- Structured parsing tests ---


def test_structured_frontmatter_overrides(tmp_path: Path):
    md = tmp_path / "CLAUDE.md"
    md.write_text("""---
welcome: "Hi there!"
error: "Oops, something broke."
agent_type: AgentforceEmployeeAgent
company: Acme Corp
---
You are a helpful agent.
Be concise.
""")
    result = parse_claude_md_structured(md)
    assert result.welcome_message == "Hi there!"
    assert result.error_message == "Oops, something broke."
    assert result.agent_type == "AgentforceEmployeeAgent"
    assert result.company == "Acme Corp"
    assert "helpful agent" in result.instructions
    assert "Be concise" in result.instructions


def test_structured_section_extraction(tmp_path: Path):
    md = tmp_path / "CLAUDE.md"
    md.write_text("""You are a support agent.
Be professional.

## Welcome Message
Welcome to Acme support!

## Error Message
We hit a snag. Please try again.

## Company
Acme Corporation
""")
    result = parse_claude_md_structured(md)
    assert result.welcome_message == "Welcome to Acme support!"
    assert result.error_message == "We hit a snag. Please try again."
    assert result.company == "Acme Corporation"
    # Sections should be removed from instructions
    assert "Welcome to Acme support" not in result.instructions
    assert "We hit a snag" not in result.instructions
    assert "support agent" in result.instructions


def test_structured_frontmatter_takes_precedence_over_sections(tmp_path: Path):
    md = tmp_path / "CLAUDE.md"
    md.write_text("""---
welcome: "Frontmatter wins"
---
Instructions here.

## Welcome Message
Section would lose.
""")
    result = parse_claude_md_structured(md)
    assert result.welcome_message == "Frontmatter wins"


def test_structured_plain_text_backwards_compatible(tmp_path: Path):
    md = tmp_path / "CLAUDE.md"
    md.write_text("You are a customer support agent.\nBe helpful and concise.")
    result = parse_claude_md_structured(md)
    assert result.welcome_message is None
    assert result.error_message is None
    assert result.agent_type is None
    assert "customer support agent" in result.instructions


def test_structured_missing_file(tmp_path: Path):
    result = parse_claude_md_structured(tmp_path / "nonexistent.md")
    assert result.instructions == ""
    assert result.welcome_message is None


# --- Variables and knowledge parsing tests ---


def test_variables_mutable_from_frontmatter(tmp_path: Path):
    md = tmp_path / "CLAUDE.md"
    md.write_text("""---
variables:
  isVerified:
    type: boolean
    modifier: mutable
    default: "False"
    description: "Whether customer is verified"
    label: "Verified"
    visibility: Internal
---
Agent instructions.
""")
    result = parse_claude_md_structured(md)
    assert len(result.variables) == 1
    v = result.variables[0]
    assert v.name == "isVerified"
    assert v.var_type == "boolean"
    assert v.modifier.value == "mutable"
    assert v.default == "False"
    assert v.description == "Whether customer is verified"
    assert v.label == "Verified"
    assert v.visibility == "Internal"


def test_variables_linked_from_frontmatter(tmp_path: Path):
    md = tmp_path / "CLAUDE.md"
    md.write_text("""---
variables:
  EndUserId:
    type: string
    modifier: linked
    source: "@MessagingSession.MessagingEndUserId"
    description: "End User ID"
    visibility: External
---
Instructions.
""")
    result = parse_claude_md_structured(md)
    assert len(result.variables) == 1
    v = result.variables[0]
    assert v.name == "EndUserId"
    assert v.modifier.value == "linked"
    assert v.source == "@MessagingSession.MessagingEndUserId"
    assert v.visibility == "External"


def test_variables_mixed_mutable_and_linked(tmp_path: Path):
    md = tmp_path / "CLAUDE.md"
    md.write_text("""---
variables:
  isVerified:
    type: boolean
    modifier: mutable
    default: "False"
  EndUserId:
    type: string
    modifier: linked
    source: "@MessagingSession.MessagingEndUserId"
  CaseTopic:
    type: string
    modifier: mutable
---
Instructions.
""")
    result = parse_claude_md_structured(md)
    assert len(result.variables) == 3
    assert result.variables[0].modifier.value == "mutable"
    assert result.variables[1].modifier.value == "linked"
    assert result.variables[2].modifier.value == "mutable"
    # Default modifier is mutable
    assert result.variables[2].default is None


def test_variables_default_modifier_is_mutable(tmp_path: Path):
    md = tmp_path / "CLAUDE.md"
    md.write_text("""---
variables:
  counter:
    type: number
---
Instructions.
""")
    result = parse_claude_md_structured(md)
    assert result.variables[0].modifier.value == "mutable"


def test_no_variables_returns_empty_list(tmp_path: Path):
    md = tmp_path / "CLAUDE.md"
    md.write_text("No frontmatter, just instructions.")
    result = parse_claude_md_structured(md)
    assert result.variables == []


def test_knowledge_citations_from_frontmatter(tmp_path: Path):
    md = tmp_path / "CLAUDE.md"
    md.write_text("""---
knowledge:
  citations_enabled: true
---
Instructions.
""")
    result = parse_claude_md_structured(md)
    assert result.knowledge_citations_enabled is True


def test_knowledge_citations_false(tmp_path: Path):
    md = tmp_path / "CLAUDE.md"
    md.write_text("""---
knowledge:
  citations_enabled: false
---
Instructions.
""")
    result = parse_claude_md_structured(md)
    assert result.knowledge_citations_enabled is False


def test_no_knowledge_returns_none(tmp_path: Path):
    md = tmp_path / "CLAUDE.md"
    md.write_text("Just instructions.")
    result = parse_claude_md_structured(md)
    assert result.knowledge_citations_enabled is None
