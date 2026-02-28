"""Tests for YAML frontmatter parsing."""

from scripts.parser.frontmatter import parse_frontmatter


def test_basic_frontmatter():
    text = "---\nname: test\ndescription: A test\n---\nHello world"
    fm, body = parse_frontmatter(text)
    assert fm == {"name": "test", "description": "A test"}
    assert body == "Hello world"


def test_no_frontmatter():
    text = "Just some text without frontmatter"
    fm, body = parse_frontmatter(text)
    assert fm == {}
    assert body == text


def test_empty_frontmatter():
    text = "---\n---\nBody here"
    fm, body = parse_frontmatter(text)
    # yaml.safe_load of empty string returns None, which isn't a dict
    assert fm == {}


def test_multiline_body():
    text = "---\nname: agent\n---\nLine 1\nLine 2\nLine 3"
    fm, body = parse_frontmatter(text)
    assert fm == {"name": "agent"}
    assert body == "Line 1\nLine 2\nLine 3"


def test_complex_frontmatter():
    text = """---
name: order-support
description: Handles orders
tools: CheckOrder, ProcessReturn
agentforce:
  target: "flow://Get_Order"
---
Help with orders."""
    fm, body = parse_frontmatter(text)
    assert fm["name"] == "order-support"
    assert fm["tools"] == "CheckOrder, ProcessReturn"
    assert fm["agentforce"]["target"] == "flow://Get_Order"
    assert body == "Help with orders."


def test_invalid_yaml(caplog):
    text = "---\n: invalid: yaml:\n---\nBody"
    fm, body = parse_frontmatter(text)
    # Should fall back gracefully
    assert isinstance(fm, dict)
    # Should log a warning about the malformed YAML
    assert any("Malformed YAML frontmatter" in r.message for r in caplog.records)


def test_no_closing_delimiter():
    text = "---\nname: test\nNo closing delimiter"
    fm, body = parse_frontmatter(text)
    assert fm == {}
    assert body == text
