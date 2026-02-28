"""Naming utilities for converting between Claude Code and Agent Script conventions."""

import re


def kebab_to_snake(name: str) -> str:
    """Convert kebab-case to snake_case.

    >>> kebab_to_snake("order-support")
    'order_support'
    >>> kebab_to_snake("general-faq")
    'general_faq'
    """
    return name.replace("-", "_")


def kebab_to_title(name: str) -> str:
    """Convert kebab-case to Title Case.

    >>> kebab_to_title("order-support")
    'Order Support'
    >>> kebab_to_title("general-faq")
    'General Faq'
    """
    return name.replace("-", " ").title()


def sanitize_developer_name(name: str) -> str:
    """Sanitize a string to be a valid Agent Script developer name.

    Rules:
    - Only letters, numbers, underscores
    - Must begin with a letter
    - Max 80 characters

    >>> sanitize_developer_name("My Agent! v2.0")
    'My_Agent_v2_0'
    >>> sanitize_developer_name("123-start")
    'A_123_start'
    """
    # Replace dots, hyphens, and spaces with underscores
    result = re.sub(r"[-.\s]+", "_", name)
    # Remove any characters that aren't letters, numbers, or underscores
    result = re.sub(r"[^a-zA-Z0-9_]", "", result)
    # Must begin with a letter
    if result and not result[0].isalpha():
        result = "A_" + result
    # Max 80 characters
    result = result[:80]
    return result


def tool_name_to_snake(name: str) -> str:
    """Convert a tool/action name to snake_case for Agent Script.

    Handles PascalCase, camelCase, kebab-case, and mixed.

    >>> tool_name_to_snake("CheckOrderStatus")
    'check_order_status'
    >>> tool_name_to_snake("processReturn")
    'process_return'
    >>> tool_name_to_snake("search-knowledge")
    'search_knowledge'
    """
    # Handle consecutive uppercase (e.g. XMLParser -> XML_Parser)
    result = re.sub(r"([A-Z]+)([A-Z][a-z])", r"\1_\2", name)
    # Handle camelCase (e.g. processReturn -> process_Return)
    result = re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", result)
    # Handle kebab-case
    result = result.replace("-", "_")
    # Handle spaces
    result = result.replace(" ", "_")
    return result.lower()
