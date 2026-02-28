"""Extract YAML frontmatter from markdown files."""

from __future__ import annotations

import logging
from typing import Any

import yaml

logger = logging.getLogger(__name__)


def parse_frontmatter(text: str) -> tuple[dict[str, Any], str]:
    """Split a markdown file into YAML frontmatter and body.

    Returns (frontmatter_dict, body_text). If no frontmatter is present,
    returns ({}, full_text).

    >>> fm, body = parse_frontmatter("---\\nname: test\\n---\\nHello")
    >>> fm
    {'name': 'test'}
    >>> body
    'Hello'
    """
    text = text.strip()
    if not text.startswith("---"):
        return {}, text

    # Find the closing ---
    end_idx = text.find("---", 3)
    if end_idx == -1:
        return {}, text

    yaml_str = text[3:end_idx].strip()
    body = text[end_idx + 3:].strip()

    try:
        frontmatter = yaml.safe_load(yaml_str)
    except yaml.YAMLError as exc:
        logger.warning("Malformed YAML frontmatter (ignored): %s", exc)
        return {}, text

    if not isinstance(frontmatter, dict):
        return {}, text

    return frontmatter, body
