"""Generate stub Flow XML for SKILL.md targets."""

from __future__ import annotations

from ..ir.models import ActionInput, ActionOutput

# Mapping from SKILL.md types to Flow variable dataTypes
_TYPE_MAP = {
    "string": "String",
    "number": "Number",
    "boolean": "Boolean",
    "date": "Date",
    "datetime": "DateTime",
    "id": "String",
    "object": "Apex",
}

API_VERSION = "63.0"


def generate_flow_xml(
    api_name: str,
    inputs: list[ActionInput] | None = None,
    outputs: list[ActionOutput] | None = None,
    process_type: str = "AutoLaunchedFlow",
) -> str:
    """Generate a stub Flow XML with matching input/output variables.

    Produces a minimal .flow-meta.xml that:
    - Declares input variables matching SKILL.md inputs
    - Declares output variables matching SKILL.md outputs
    - Merges variables that appear in both inputs and outputs into one
      bidirectional variable (isInput=true, isOutput=true) to avoid
      "Duplicate developer name" deploy errors
    - Uses Active status so flows are immediately callable as invocable actions
    - Uses type-appropriate XML value elements in the placeholder assignment
      (booleanValue for boolean, numberValue for number, stringValue otherwise)
    - Has a single Assignment element as placeholder logic
    - Uses API version 63.0

    Args:
        api_name: The flow API name.
        inputs: Action input definitions from SKILL.md.
        outputs: Action output definitions from SKILL.md.
        process_type: Flow process type (default: AutoLaunchedFlow).

    Returns:
        Flow XML string.
    """
    inputs = inputs or []
    outputs = outputs or []

    # Variables that appear in both inputs and outputs — merged into one
    # bidirectional variable to avoid "Duplicate developer name" deploy errors.
    input_names = {inp.name for inp in inputs}
    bidirectional_names = input_names & {out.name for out in outputs}

    lines = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        '<Flow xmlns="http://soap.sforce.com/2006/04/metadata">',
        f'    <apiVersion>{API_VERSION}</apiVersion>',
        f'    <label>{api_name}</label>',
        f'    <processType>{process_type}</processType>',
        '    <status>Active</status>',
        '    <interviewLabel>{!$Flow.CurrentDateTime}</interviewLabel>',
    ]

    # Input variables — bidirectional ones get isOutput=true too
    for inp in inputs:
        flow_type = _TYPE_MAP.get(inp.input_type, "String")
        is_output = inp.name in bidirectional_names
        lines.extend([
            '    <variables>',
            f'        <name>{inp.name}</name>',
            f'        <dataType>{flow_type}</dataType>',
            '        <isCollection>false</isCollection>',
            '        <isInput>true</isInput>',
            f'        <isOutput>{"true" if is_output else "false"}</isOutput>',
        ])
        if inp.description:
            lines.append(f'        <description>{_escape_xml(inp.description)}</description>')
        lines.append('    </variables>')

    # Output-only variables (skip bidirectional — already declared above)
    for out in outputs:
        if out.name in bidirectional_names:
            continue
        flow_type = _TYPE_MAP.get(out.output_type, "String")
        lines.extend([
            '    <variables>',
            f'        <name>{out.name}</name>',
            f'        <dataType>{flow_type}</dataType>',
            '        <isCollection>false</isCollection>',
            '        <isInput>false</isInput>',
            '        <isOutput>true</isOutput>',
        ])
        if out.description:
            lines.append(f'        <description>{_escape_xml(out.description)}</description>')
        lines.append('    </variables>')

    # Placeholder assignment element
    lines.extend([
        '    <assignments>',
        '        <name>Placeholder_Assignment</name>',
        '        <label>Placeholder Assignment</label>',
        '        <locationX>176</locationX>',
        '        <locationY>158</locationY>',
    ])

    # Assign default values to output variables
    for out in outputs:
        lines.extend([
            '        <assignmentItems>',
            f'            <assignToReference>{out.name}</assignToReference>',
            '            <operator>Assign</operator>',
            f'            <value>{_default_value_element(out.output_type)}</value>',
            '        </assignmentItems>',
        ])

    lines.extend([
        '    </assignments>',
        '    <start>',
        '        <locationX>50</locationX>',
        '        <locationY>0</locationY>',
        '        <connector>',
        '            <targetReference>Placeholder_Assignment</targetReference>',
        '        </connector>',
        '    </start>',
        '</Flow>',
    ])

    return "\n".join(lines) + "\n"


def _escape_xml(text: str) -> str:
    """Escape XML special characters."""
    return (
        text
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
        .replace("'", "&apos;")
    )


def _default_value_element(type_name: str) -> str:
    """Return a type-appropriate XML value element for a placeholder assignment.

    Flow XML requires typed value elements — using <stringValue> for a Boolean
    variable causes a deploy-time "field integrity exception".
    """
    if type_name == "boolean":
        return "<booleanValue>false</booleanValue>"
    if type_name == "number":
        return "<numberValue>0</numberValue>"
    if type_name == "date":
        return "<stringValue>2000-01-01</stringValue>"
    if type_name == "datetime":
        return "<stringValue>2000-01-01T00:00:00Z</stringValue>"
    return "<stringValue>TODO</stringValue>"
