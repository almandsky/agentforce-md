"""Tests for Apex stub generation."""

from __future__ import annotations

from scripts.generator.apex_stub import (
    generate_apex_class,
    generate_apex_meta_xml,
    _class_to_label,
)
from scripts.ir.models import ActionInput, ActionOutput


def test_minimal_apex_class():
    """Apex class with no inputs or outputs."""
    code = generate_apex_class("MyAction")
    assert "public with sharing class MyAction" in code
    assert "public class Request" in code
    assert "public class Response" in code
    assert "@InvocableMethod" in code
    assert "public static List<Response> invoke(List<Request> requests)" in code


def test_apex_with_inputs():
    """Apex class with input variables."""
    inputs = [
        ActionInput(name="order_id", input_type="string", description="The order ID", is_required=True),
        ActionInput(name="amount", input_type="number", is_required=False),
    ]
    code = generate_apex_class("GetOrder", inputs=inputs)

    assert "public String order_id;" in code
    assert "public Decimal amount;" in code
    assert "@InvocableVariable(label='The order ID' required=true)" in code
    assert "required=false" in code


def test_apex_with_outputs():
    """Apex class with output variables."""
    outputs = [
        ActionOutput(name="status", output_type="string", description="Order status"),
        ActionOutput(name="is_active", output_type="boolean"),
    ]
    code = generate_apex_class("GetStatus", outputs=outputs)

    assert "public String status;" in code
    assert "public Boolean is_active;" in code
    assert "@InvocableVariable(label='Order status')" in code


def test_apex_placeholder_values():
    """Outputs have placeholder default values."""
    outputs = [
        ActionOutput(name="text", output_type="string"),
        ActionOutput(name="count", output_type="number"),
        ActionOutput(name="flag", output_type="boolean"),
    ]
    code = generate_apex_class("Test", outputs=outputs)

    assert "res.text = 'TODO';" in code
    assert "res.count = 0;" in code
    assert "res.flag = false;" in code


def test_apex_type_mapping():
    """Various SKILL.md types map to correct Apex types."""
    type_pairs = [
        ("string", "String"),
        ("number", "Decimal"),
        ("boolean", "Boolean"),
        ("date", "Date"),
        ("datetime", "Datetime"),
        ("id", "Id"),
    ]
    for skill_type, apex_type in type_pairs:
        inputs = [ActionInput(name="x", input_type=skill_type)]
        code = generate_apex_class("Test", inputs=inputs)
        assert f"public {apex_type} x;" in code


def test_apex_meta_xml():
    """Meta XML has correct structure."""
    xml = generate_apex_meta_xml()
    assert '<?xml version="1.0"' in xml
    assert "<apiVersion>66.0</apiVersion>" in xml
    assert "<status>Active</status>" in xml
    assert "ApexClass" in xml


def test_apex_meta_xml_custom_version():
    xml = generate_apex_meta_xml(api_version="62.0")
    assert "<apiVersion>62.0</apiVersion>" in xml


def test_class_to_label():
    assert _class_to_label("GetOrderStatus") == "Get Order Status"
    assert _class_to_label("MyClass") == "My Class"
    assert _class_to_label("A") == "A"


def test_apex_escaping():
    """Single quotes in descriptions are escaped."""
    inputs = [ActionInput(name="x", input_type="string", description="It's a test")]
    code = generate_apex_class("Test", inputs=inputs)
    assert "It\\'s a test" in code


def test_apex_todo_comment():
    """Generated class includes TODO comment for business logic."""
    code = generate_apex_class("MyAction")
    assert "// TODO: Implement business logic" in code
