"""Generate stub Flow XML for SKILL.md targets."""

from __future__ import annotations

from ..ir.models import ActionInput, ActionOutput
from ..org_describe import FieldMapping

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

API_VERSION = "66.0"


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
    - Uses API version 66.0

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

    # When no outputs, declare a placeholder variable so the assignment is valid
    if not outputs:
        lines.extend([
            '    <variables>',
            '        <name>placeholder_result</name>',
            '        <dataType>String</dataType>',
            '        <isCollection>false</isCollection>',
            '        <isInput>false</isInput>',
            '        <isOutput>true</isOutput>',
            '    </variables>',
        ])

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

    if not outputs:
        # Must have at least one assignmentItem — use a placeholder variable
        lines.extend([
            '        <assignmentItems>',
            '            <assignToReference>placeholder_result</assignToReference>',
            '            <operator>Assign</operator>',
            '            <value><stringValue>TODO</stringValue></value>',
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


def generate_smart_flow_xml(
    api_name: str,
    sobject: str,
    field_mapping: FieldMapping,
    inputs: list[ActionInput] | None = None,
    outputs: list[ActionOutput] | None = None,
    process_type: str = "AutoLaunchedFlow",
) -> str:
    """Generate a Flow XML with a GetRecords element using SObject field mappings.

    Produces a flow that:
    - Declares input/output variables matching SKILL.md
    - Uses a recordLookups element to query the SObject
    - Filters by input field mappings
    - Assigns record fields to output variables

    Falls back to generate_flow_xml() if no field mappings are available.
    """
    inputs = inputs or []
    outputs = outputs or []

    if not field_mapping.select_fields and not field_mapping.where_fields:
        return generate_flow_xml(api_name, inputs, outputs, process_type)

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

    # Input variables
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

    # Output-only variables
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

    # Record variable for query results
    lines.extend([
        '    <variables>',
        f'        <name>{sobject.replace("__c", "").replace("__", "_")}Records</name>',
        '        <dataType>SObject</dataType>',
        '        <isCollection>true</isCollection>',
        '        <isInput>false</isInput>',
        '        <isOutput>false</isOutput>',
        f'        <objectType>{sobject}</objectType>',
        '    </variables>',
    ])

    # GetRecords element (recordLookups)
    record_var = f'{sobject.replace("__c", "").replace("__", "_")}Records'
    lines.extend([
        '    <recordLookups>',
        '        <name>Get_Records</name>',
        '        <label>Get Records</label>',
        '        <locationX>176</locationX>',
        '        <locationY>158</locationY>',
        '        <connector>',
        '            <targetReference>Assign_Outputs</targetReference>',
        '        </connector>',
        f'        <object>{sobject}</object>',
        '        <getFirstRecordOnly>false</getFirstRecordOnly>',
        '        <storeOutputAutomatically>false</storeOutputAutomatically>',
        f'        <outputReference>{record_var}</outputReference>',
    ])

    # Filter conditions from input mappings
    for inp_name, field_name in field_mapping.input_mappings.items():
        lines.extend([
            '        <filterLogic>and</filterLogic>',
            '        <filters>',
            f'            <field>{field_name}</field>',
            '            <operator>EqualTo</operator>',
            '            <value>',
            f'                <elementReference>{inp_name}</elementReference>',
            '            </value>',
            '        </filters>',
        ])

    lines.append('    </recordLookups>')

    # Assignment element — map record fields to output variables
    lines.extend([
        '    <assignments>',
        '        <name>Assign_Outputs</name>',
        '        <label>Assign Outputs</label>',
        '        <locationX>176</locationX>',
        '        <locationY>308</locationY>',
    ])

    for out_name, field_name in field_mapping.output_mappings.items():
        lines.extend([
            '        <assignmentItems>',
            f'            <assignToReference>{out_name}</assignToReference>',
            '            <operator>Assign</operator>',
            '            <value>',
            f'                <elementReference>{record_var}.{field_name}</elementReference>',
            '            </value>',
            '        </assignmentItems>',
        ])

    # Handle unmapped outputs with placeholder
    for out in outputs:
        if out.name not in field_mapping.output_mappings:
            lines.extend([
                '        <assignmentItems>',
                f'            <assignToReference>{out.name}</assignToReference>',
                '            <operator>Assign</operator>',
                f'            <value>{_default_value_element(out.output_type)}</value>',
                '        </assignmentItems>',
            ])

    # Ensure at least one assignment item
    if not field_mapping.output_mappings and not outputs:
        lines.extend([
            '        <assignmentItems>',
            f'            <assignToReference>{record_var}</assignToReference>',
            '            <operator>Assign</operator>',
            '            <value><stringValue>TODO</stringValue></value>',
            '        </assignmentItems>',
        ])

    lines.extend([
        '    </assignments>',
        '    <start>',
        '        <locationX>50</locationX>',
        '        <locationY>0</locationY>',
        '        <connector>',
        '            <targetReference>Get_Records</targetReference>',
        '        </connector>',
        '    </start>',
        '</Flow>',
    ])

    return "\n".join(lines) + "\n"
