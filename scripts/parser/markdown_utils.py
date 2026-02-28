"""Utilities for parsing markdown body content into scope and instructions."""

from __future__ import annotations


def split_scope_and_instructions(body: str) -> tuple[str, list[str]]:
    """Split a markdown body into scope (first paragraph) and instruction lines.

    The first paragraph (up to the first blank line or bullet) becomes the scope.
    Subsequent lines become individual instruction lines.

    >>> scope, instr = split_scope_and_instructions(
    ...     "Help customers with orders.\\n\\nAlways verify identity.\\nBe polite."
    ... )
    >>> scope
    'Help customers with orders.'
    >>> instr
    ['Always verify identity.', 'Be polite.']
    """
    lines = body.strip().splitlines()
    if not lines:
        return "", []

    # Collect the first paragraph (until blank line or bullet)
    scope_lines = []
    rest_start = 0

    for i, line in enumerate(lines):
        stripped = line.strip()
        if stripped == "":
            rest_start = i + 1
            break
        if stripped.startswith("- ") or stripped.startswith("* "):
            # Bullet list starts the instruction section
            rest_start = i
            break
        scope_lines.append(stripped)
        rest_start = i + 1

    scope = " ".join(scope_lines)

    # Collect instruction lines from the rest
    instruction_lines = []
    for line in lines[rest_start:]:
        stripped = line.strip()
        if stripped == "":
            continue
        # Strip bullet prefixes
        if stripped.startswith("- "):
            stripped = stripped[2:].strip()
        elif stripped.startswith("* "):
            stripped = stripped[2:].strip()
        if stripped:
            instruction_lines.append(stripped)

    return scope, instruction_lines
