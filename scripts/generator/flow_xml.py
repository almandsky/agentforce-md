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

    lines = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        '<Flow xmlns="http://soap.sforce.com/2006/04/metadata">',
        f'    <apiVersion>{API_VERSION}</apiVersion>',
        f'    <label>{api_name}</label>',
        f'    <processType>{process_type}</processType>',
        '    <status>Draft</status>',
        '    <interviewLabel>{!$Flow.CurrentDateTime}</interviewLabel>',
    ]

    # Input variables
    for inp in inputs:
        flow_type = _TYPE_MAP.get(inp.input_type, "String")
        lines.extend([
            '    <variables>',
            f'        <name>{inp.name}</name>',
            f'        <dataType>{flow_type}</dataType>',
            '        <isCollection>false</isCollection>',
            '        <isInput>true</isInput>',
            '        <isOutput>false</isOutput>',
        ])
        if inp.description:
            lines.append(f'        <description>{_escape_xml(inp.description)}</description>')
        lines.append('    </variables>')

    # Output variables
    for out in outputs:
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
        default = _default_for_type(out.output_type)
        lines.extend([
            '        <assignmentItems>',
            f'            <assignToReference>{out.name}</assignToReference>',
            '            <operator>Assign</operator>',
            f'            <value><stringValue>{_escape_xml(default)}</stringValue></value>',
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


def _default_for_type(type_name: str) -> str:
    """Return a placeholder default value for an output type."""
    defaults = {
        "string": "TODO",
        "number": "0",
        "boolean": "false",
        "date": "2000-01-01",
        "datetime": "2000-01-01T00:00:00Z",
    }
    return defaults.get(type_name, "TODO")
