"""Tests for naming utilities."""

from scripts.ir.naming import (
    kebab_to_snake,
    kebab_to_title,
    sanitize_developer_name,
    tool_name_to_snake,
)


def test_kebab_to_snake():
    assert kebab_to_snake("order-support") == "order_support"
    assert kebab_to_snake("general-faq") == "general_faq"
    assert kebab_to_snake("simple") == "simple"
    assert kebab_to_snake("a-b-c") == "a_b_c"


def test_kebab_to_title():
    assert kebab_to_title("order-support") == "Order Support"
    assert kebab_to_title("general-faq") == "General Faq"


def test_sanitize_developer_name():
    assert sanitize_developer_name("MyAgent") == "MyAgent"
    assert sanitize_developer_name("My Agent! v2.0") == "My_Agent_v2_0"
    assert sanitize_developer_name("123-start") == "A_123_start"
    assert sanitize_developer_name("hello world") == "hello_world"
    # Max 80 chars
    long_name = "A" * 100
    assert len(sanitize_developer_name(long_name)) == 80


def test_tool_name_to_snake():
    assert tool_name_to_snake("CheckOrderStatus") == "check_order_status"
    assert tool_name_to_snake("processReturn") == "process_return"
    assert tool_name_to_snake("search-knowledge") == "search_knowledge"
    assert tool_name_to_snake("Simple") == "simple"
    assert tool_name_to_snake("XMLParser") == "xml_parser"
