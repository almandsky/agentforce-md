"""Tests for Flow XML generation."""

from __future__ import annotations

from scripts.generator.flow_xml import generate_flow_xml
from scripts.ir.models import ActionInput, ActionOutput


def test_minimal_flow():
    """Flow with no inputs or outputs."""
    xml = generate_flow_xml("My_Flow")
    assert '<?xml version="1.0"' in xml
    assert "<label>My_Flow</label>" in xml
    assert "<processType>AutoLaunchedFlow</processType>" in xml
    assert "<status>Draft</status>" in xml
    assert "Placeholder_Assignment" in xml
    assert "<apiVersion>63.0</apiVersion>" in xml


def test_flow_with_inputs():
    """Flow with input variables."""
    inputs = [
        ActionInput(name="order_id", input_type="string", description="The order ID"),
        ActionInput(name="amount", input_type="number"),
    ]
    xml = generate_flow_xml("Get_Order", inputs=inputs)

    assert "<name>order_id</name>" in xml
    assert "<dataType>String</dataType>" in xml
    assert "<isInput>true</isInput>" in xml
    assert "<isOutput>false</isOutput>" in xml
    assert "<description>The order ID</description>" in xml

    assert "<name>amount</name>" in xml
    assert "<dataType>Number</dataType>" in xml


def test_flow_with_outputs():
    """Flow with output variables."""
    outputs = [
        ActionOutput(name="status", output_type="string", description="Order status"),
        ActionOutput(name="is_active", output_type="boolean"),
    ]
    xml = generate_flow_xml("Get_Status", outputs=outputs)

    assert "<name>status</name>" in xml
    assert "<isInput>false</isInput>" in xml
    assert "<isOutput>true</isOutput>" in xml
    assert "<description>Order status</description>" in xml

    assert "<name>is_active</name>" in xml
    assert "<dataType>Boolean</dataType>" in xml


def test_flow_with_inputs_and_outputs():
    """Flow with both inputs and outputs."""
    inputs = [ActionInput(name="query", input_type="string")]
    outputs = [ActionOutput(name="result", output_type="string")]
    xml = generate_flow_xml("Search", inputs=inputs, outputs=outputs)

    assert "<name>query</name>" in xml
    assert "<isInput>true</isInput>" in xml
    assert "<name>result</name>" in xml
    assert "<isOutput>true</isOutput>" in xml


def test_flow_custom_process_type():
    xml = generate_flow_xml("My_Flow", process_type="Flow")
    assert "<processType>Flow</processType>" in xml


def test_flow_xml_escaping():
    """Special characters in descriptions are XML-escaped."""
    inputs = [ActionInput(name="x", input_type="string", description='Has "quotes" & <brackets>')]
    xml = generate_flow_xml("Test", inputs=inputs)
    assert "&amp;" in xml
    assert "&lt;" in xml
    assert "&gt;" in xml
    assert "&quot;" in xml


def test_flow_has_start_element():
    xml = generate_flow_xml("My_Flow")
    assert "<start>" in xml
    assert "<targetReference>Placeholder_Assignment</targetReference>" in xml


def test_flow_assignment_sets_output_defaults():
    """Placeholder assignment sets default values for outputs."""
    outputs = [ActionOutput(name="result", output_type="string")]
    xml = generate_flow_xml("Test", outputs=outputs)
    assert "<assignToReference>result</assignToReference>" in xml
    assert "<operator>Assign</operator>" in xml


def test_flow_type_mapping():
    """Various SKILL.md types map to correct Flow dataTypes."""
    type_pairs = [
        ("string", "String"),
        ("number", "Number"),
        ("boolean", "Boolean"),
        ("date", "Date"),
        ("datetime", "DateTime"),
    ]
    for skill_type, flow_type in type_pairs:
        inputs = [ActionInput(name="x", input_type=skill_type)]
        xml = generate_flow_xml("Test", inputs=inputs)
        assert f"<dataType>{flow_type}</dataType>" in xml
