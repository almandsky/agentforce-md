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
    assert "<status>Active</status>" in xml
    assert "Placeholder_Assignment" in xml
    assert "<apiVersion>66.0</apiVersion>" in xml


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


def test_flow_active_status():
    """Generated flows use Active status so they are callable as invocable actions."""
    xml = generate_flow_xml("My_Flow")
    assert "<status>Active</status>" in xml
    assert "<status>Draft</status>" not in xml


def test_flow_bidirectional_variable_no_duplicate():
    """When input and output share the same name, only one <variables> block is emitted."""
    inputs = [ActionInput(name="appointmentId", input_type="string", description="Appointment ID")]
    outputs = [
        ActionOutput(name="appointmentId", output_type="string"),
        ActionOutput(name="confirmationNumber", output_type="string"),
    ]
    xml = generate_flow_xml("RescheduleAppointment", inputs=inputs, outputs=outputs)

    # Only one <name>appointmentId</name> block — no duplicate
    assert xml.count("<name>appointmentId</name>") == 1

    # That single block is bidirectional
    # Find the variables block for appointmentId and verify both flags
    idx = xml.index("<name>appointmentId</name>")
    block = xml[xml.rindex("<variables>", 0, idx):xml.index("</variables>", idx) + len("</variables>")]
    assert "<isInput>true</isInput>" in block
    assert "<isOutput>true</isOutput>" in block

    # Output-only variable is still generated
    assert "<name>confirmationNumber</name>" in xml


def test_flow_boolean_placeholder_uses_boolean_value():
    """Boolean output placeholder uses <booleanValue>, not <stringValue>."""
    outputs = [ActionOutput(name="success", output_type="boolean")]
    xml = generate_flow_xml("Test", outputs=outputs)
    assert "<booleanValue>false</booleanValue>" in xml
    # Must NOT use stringValue for boolean — that causes deploy-time errors
    assert "<stringValue>false</stringValue>" not in xml


def test_flow_number_placeholder_uses_number_value():
    """Number output placeholder uses <numberValue>, not <stringValue>."""
    outputs = [ActionOutput(name="count", output_type="number")]
    xml = generate_flow_xml("Test", outputs=outputs)
    assert "<numberValue>0</numberValue>" in xml
    assert "<stringValue>0</stringValue>" not in xml


def test_flow_no_outputs_has_valid_assignment_items():
    """When no outputs exist, a placeholder assignmentItem and variable are generated."""
    xml = generate_flow_xml("No_Outputs_Flow", inputs=[
        ActionInput(name="order_id", input_type="string"),
    ])
    # Must have at least one assignmentItem so the Flow XML is valid
    assert "<assignmentItems>" in xml
    assert "<assignToReference>placeholder_result</assignToReference>" in xml
    # Placeholder variable must be declared
    assert "<name>placeholder_result</name>" in xml
    assert "<isOutput>true</isOutput>" in xml
