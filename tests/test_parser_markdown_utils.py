"""Tests for markdown body splitting utilities."""

from scripts.parser.markdown_utils import split_scope_and_instructions


def test_scope_and_instructions_with_blank_line():
    body = "Help customers with orders.\n\nAlways verify identity.\nBe polite."
    scope, instr = split_scope_and_instructions(body)
    assert scope == "Help customers with orders."
    assert instr == ["Always verify identity.", "Be polite."]


def test_scope_only_no_instructions():
    body = "Just one paragraph with no break."
    scope, instr = split_scope_and_instructions(body)
    assert scope == "Just one paragraph with no break."
    assert instr == []


def test_multi_line_scope():
    body = "Line one of scope\nline two of scope\n\nInstruction here."
    scope, instr = split_scope_and_instructions(body)
    assert scope == "Line one of scope line two of scope"
    assert instr == ["Instruction here."]


def test_bullets_start_instructions():
    body = "Scope paragraph.\n- First bullet\n- Second bullet"
    scope, instr = split_scope_and_instructions(body)
    assert scope == "Scope paragraph."
    assert instr == ["First bullet", "Second bullet"]


def test_bullets_with_asterisks():
    body = "Scope.\n* Item A\n* Item B"
    scope, instr = split_scope_and_instructions(body)
    assert scope == "Scope."
    assert instr == ["Item A", "Item B"]


def test_bullets_at_start():
    """Bullets at the very start mean no scope, all instructions."""
    body = "- Do this\n- Do that"
    scope, instr = split_scope_and_instructions(body)
    assert scope == ""
    assert instr == ["Do this", "Do that"]


def test_empty_body():
    scope, instr = split_scope_and_instructions("")
    assert scope == ""
    assert instr == []


def test_whitespace_only():
    scope, instr = split_scope_and_instructions("   \n  \n  ")
    assert scope == ""
    assert instr == []


def test_blank_lines_between_instructions_are_skipped():
    body = "Scope here.\n\nLine A.\n\nLine B.\n\nLine C."
    scope, instr = split_scope_and_instructions(body)
    assert scope == "Scope here."
    assert instr == ["Line A.", "Line B.", "Line C."]


def test_mixed_bullets_and_plain_lines():
    body = "Scope.\n\n- Bullet one\nPlain line\n- Bullet two"
    scope, instr = split_scope_and_instructions(body)
    assert scope == "Scope."
    assert instr == ["Bullet one", "Plain line", "Bullet two"]
