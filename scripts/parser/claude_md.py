"""Parse CLAUDE.md files for system-level instructions."""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

from ..ir.models import Variable, VariableModifier
from .frontmatter import parse_frontmatter

logger = logging.getLogger(__name__)


@dataclass
class ParsedClaudeMd:
    """Structured result from parsing CLAUDE.md."""
    instructions: str = ""
    welcome_message: Optional[str] = None
    error_message: Optional[str] = None
    agent_type: Optional[str] = None
    company: Optional[str] = None
    variables: list[Variable] = field(default_factory=list)
    knowledge_citations_enabled: Optional[bool] = None


def parse_claude_md(path: Path) -> str:
    """Parse a CLAUDE.md file and return the body as system instructions.

    Backwards-compatible wrapper that returns just the instructions string.
    Use parse_claude_md_structured() for the full result.
    """
    result = parse_claude_md_structured(path)
    return result.instructions


def parse_claude_md_structured(path: Path) -> ParsedClaudeMd:
    """Parse a CLAUDE.md file into structured fields.

    Supports two modes:

    1. Plain markdown (backwards compatible): entire body = instructions
    2. Frontmatter + sections: YAML frontmatter overrides defaults,
       and ``## Section`` headers extract specific fields.

    Supported frontmatter fields::

        ---
        welcome: "Hello! How can I help?"
        error: "Sorry, something went wrong."
        agent_type: AgentforceServiceAgent
        company: Acme Corp
        ---

    Supported markdown sections (extracted and removed from instructions)::

        ## Welcome Message
        Hello! How can I help?

        ## Error Message
        Sorry, something went wrong.

        ## Company
        Acme Corp
    """
    if not path.exists():
        return ParsedClaudeMd()

    text = path.read_text(encoding="utf-8").strip()
    if not text:
        return ParsedClaudeMd()

    # Try frontmatter extraction
    frontmatter, body = parse_frontmatter(text)

    result = ParsedClaudeMd()

    # Extract structured fields from frontmatter
    if frontmatter:
        result.welcome_message = frontmatter.get("welcome")
        result.error_message = frontmatter.get("error")
        result.agent_type = frontmatter.get("agent_type")
        result.company = frontmatter.get("company")
        result.variables = _parse_variables(frontmatter.get("variables", {}))
        knowledge = frontmatter.get("knowledge", {})
        if isinstance(knowledge, dict) and "citations_enabled" in knowledge:
            result.knowledge_citations_enabled = bool(knowledge["citations_enabled"])
    else:
        body = text

    # Extract structured sections from the markdown body
    body, section_values = _extract_sections(body)

    if "welcome" in section_values and not result.welcome_message:
        result.welcome_message = section_values["welcome"]
    if "error" in section_values and not result.error_message:
        result.error_message = section_values["error"]
    if "company" in section_values and not result.company:
        result.company = section_values["company"]

    # Remaining body becomes instructions
    result.instructions = _clean_body(body)

    return result


# Section header patterns we recognize and extract
_SECTION_PATTERNS: dict[str, re.Pattern] = {
    "welcome": re.compile(r"^##\s+welcome\s*(?:message)?$", re.IGNORECASE),
    "error": re.compile(r"^##\s+error\s*(?:message)?$", re.IGNORECASE),
    "company": re.compile(r"^##\s+company$", re.IGNORECASE),
}


def _extract_sections(body: str) -> tuple[str, dict[str, str]]:
    """Extract recognized ## sections from markdown body.

    Returns (remaining_body, extracted_sections_dict).
    """
    lines = body.splitlines()
    sections: dict[str, str] = {}
    remaining: list[str] = []
    current_section: str | None = None
    current_lines: list[str] = []

    for line in lines:
        stripped = line.strip()

        # Check if this line starts a recognized section
        matched_section = None
        for key, pattern in _SECTION_PATTERNS.items():
            if pattern.match(stripped):
                matched_section = key
                break

        # Check if this is any ## header (end of current section)
        is_any_header = stripped.startswith("## ") or stripped.startswith("# ")

        if matched_section:
            # Flush previous section if any
            if current_section:
                sections[current_section] = "\n".join(current_lines).strip()
            current_section = matched_section
            current_lines = []
        elif is_any_header and current_section:
            # A different header ends the current section
            sections[current_section] = "\n".join(current_lines).strip()
            current_section = None
            current_lines = []
            remaining.append(line)
        elif current_section:
            current_lines.append(line)
        else:
            remaining.append(line)

    # Flush last section
    if current_section:
        sections[current_section] = "\n".join(current_lines).strip()

    return "\n".join(remaining), sections


def _clean_body(body: str) -> str:
    """Clean the body text into instructions.

    Strips top-level headers and collapses blank lines.
    """
    lines = body.splitlines()
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


def _parse_variables(vars_dict: Any) -> list[Variable]:
    """Parse variables from CLAUDE.md frontmatter.

    Expected format::

        variables:
          isVerified:
            type: boolean
            modifier: mutable
            default: "False"
            description: "Whether the customer is verified"
            label: "Customer Verified"
            visibility: Internal
          EndUserId:
            type: string
            modifier: linked
            source: "@MessagingSession.MessagingEndUserId"
            description: "Messaging End User ID"
            visibility: External
    """
    if not vars_dict or not isinstance(vars_dict, dict):
        return []

    result = []
    for var_name, spec in vars_dict.items():
        if not isinstance(spec, dict):
            logger.warning("Variable '%s' has invalid spec (expected dict), skipping", var_name)
            continue

        modifier_str = spec.get("modifier", "mutable")
        if modifier_str == "linked":
            modifier = VariableModifier.LINKED
        else:
            modifier = VariableModifier.MUTABLE

        var = Variable(
            name=var_name,
            var_type=spec.get("type", "string"),
            modifier=modifier,
            default=spec.get("default"),
            source=spec.get("source"),
            description=spec.get("description"),
            visibility=spec.get("visibility"),
            label=spec.get("label"),
        )
        result.append(var)

    return result
