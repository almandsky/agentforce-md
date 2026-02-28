"""Parse CLAUDE.md files for system-level instructions."""

from __future__ import annotations

from pathlib import Path


def parse_claude_md(path: Path) -> str:
    """Parse a CLAUDE.md file and return the body as system instructions.

    The entire content is treated as system instructions for the agent.
    Strips markdown headers and normalizes whitespace.

    Returns the instructions text (may be multi-line).
    """
    if not path.exists():
        return ""

    text = path.read_text(encoding="utf-8").strip()
    if not text:
        return ""

    # Strip top-level markdown headers (e.g. "# My Agent") since they're
    # metadata, not instructions. Keep sub-headers as they may be structuring
    # the instructions.
    lines = text.splitlines()
    filtered = []
    for line in lines:
        stripped = line.strip()
        # Skip top-level headers
        if stripped.startswith("# ") and not stripped.startswith("## "):
            continue
        filtered.append(line)

    result = "\n".join(filtered).strip()

    # Collapse multiple blank lines into one
    while "\n\n\n" in result:
        result = result.replace("\n\n\n", "\n\n")

    return result
