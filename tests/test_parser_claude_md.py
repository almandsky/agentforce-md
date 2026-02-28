"""Tests for CLAUDE.md parsing."""

from pathlib import Path

from scripts.parser.claude_md import parse_claude_md


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
