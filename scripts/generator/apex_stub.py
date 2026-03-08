"""Generate Apex @InvocableMethod stubs for SKILL.md targets."""

from __future__ import annotations

from ..ir.models import ActionInput, ActionOutput
from ..org_describe import FieldMapping

# Mapping from SKILL.md types to Apex types
_TYPE_MAP = {
    "string": "String",
    "number": "Decimal",
    "boolean": "Boolean",
    "date": "Date",
    "datetime": "Datetime",
    "id": "Id",
    "object": "Map<String, Object>",
}

API_VERSION = "66.0"


def generate_apex_class(
    class_name: str,
    inputs: list[ActionInput] | None = None,
    outputs: list[ActionOutput] | None = None,
) -> str:
    """Generate an Apex class with @InvocableMethod stub.

    Produces a class with:
    - Inner Request class with @InvocableVariable fields for each input
    - Inner Response class with @InvocableVariable fields for each output
    - @InvocableMethod static method that returns a placeholder response

    Args:
        class_name: The Apex class name.
        inputs: Action input definitions from SKILL.md.
        outputs: Action output definitions from SKILL.md.

    Returns:
        Apex class source code string.
    """
    inputs = inputs or []
    outputs = outputs or []

    lines = [
        f'public with sharing class {class_name} {{',
        '',
    ]

    # Request inner class
    lines.append('    public class Request {')
    for inp in inputs:
        apex_type = _TYPE_MAP.get(inp.input_type, "String")
        if inp.description:
            lines.append(f'        @InvocableVariable(label=\'{_escape_apex(inp.description)}\' required={_apex_bool(inp.is_required)})')
        else:
            lines.append(f'        @InvocableVariable(required={_apex_bool(inp.is_required)})')
        lines.append(f'        public {apex_type} {inp.name};')
        lines.append('')
    lines.append('    }')
    lines.append('')

    # Response inner class
    lines.append('    public class Response {')
    for out in outputs:
        apex_type = _TYPE_MAP.get(out.output_type, "String")
        if out.description:
            lines.append(f'        @InvocableVariable(label=\'{_escape_apex(out.description)}\')')
        else:
            lines.append(f'        @InvocableVariable')
        lines.append(f'        public {apex_type} {out.name};')
        lines.append('')
    lines.append('    }')
    lines.append('')

    # @InvocableMethod
    method_label = _class_to_label(class_name)
    lines.extend([
        f'    @InvocableMethod(label=\'{method_label}\' description=\'TODO: Add description\')',
        '    public static List<Response> invoke(List<Request> requests) {',
        '        List<Response> responses = new List<Response>();',
        '        for (Request req : requests) {',
        '            Response res = new Response();',
        '            // TODO: Implement business logic',
    ])

    # Set placeholder values for outputs
    for out in outputs:
        default = _default_for_type(out.output_type)
        lines.append(f'            res.{out.name} = {default};')

    lines.extend([
        '            responses.add(res);',
        '        }',
        '        return responses;',
        '    }',
        '}',
    ])

    return "\n".join(lines) + "\n"


def generate_apex_meta_xml(api_version: str = API_VERSION) -> str:
    """Generate the .cls-meta.xml companion file.

    Args:
        api_version: Salesforce API version.

    Returns:
        XML string for the .cls-meta.xml file.
    """
    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<ApexClass xmlns="http://soap.sforce.com/2006/04/metadata">\n'
        f'    <apiVersion>{api_version}</apiVersion>\n'
        '    <status>Active</status>\n'
        '</ApexClass>\n'
    )


def _escape_apex(text: str) -> str:
    """Escape single quotes for Apex strings."""
    return text.replace("'", "\\'")


def _apex_bool(value: bool) -> str:
    """Format boolean for Apex (lowercase)."""
    return "true" if value else "false"


def _class_to_label(class_name: str) -> str:
    """Convert PascalCase class name to a human-readable label.

    e.g. GetOrderStatus -> Get Order Status
    """
    result = []
    for i, ch in enumerate(class_name):
        if ch.isupper() and i > 0 and not class_name[i - 1].isupper():
            result.append(" ")
        result.append(ch)
    return "".join(result)


def _default_for_type(type_name: str) -> str:
    """Return a placeholder Apex default value literal."""
    defaults = {
        "string": "'TODO'",
        "number": "0",
        "boolean": "false",
        "date": "Date.today()",
        "datetime": "Datetime.now()",
        "id": "null",
    }
    return defaults.get(type_name, "null")


def generate_smart_apex_class(
    class_name: str,
    sobject: str,
    field_mapping: FieldMapping,
    inputs: list[ActionInput] | None = None,
    outputs: list[ActionOutput] | None = None,
) -> str:
    """Generate an Apex class with a SOQL query based on SObject field mappings.

    Produces a class with:
    - Inner Request class with @InvocableVariable fields for each input
    - Inner Response class with @InvocableVariable fields for each output
    - @InvocableMethod that queries the SObject with WHERE from input mappings
      and maps results to output fields

    Falls back to generate_apex_class() if no field mappings are available.
    """
    inputs = inputs or []
    outputs = outputs or []

    # Fall back to regular stub if no useful mappings
    if not field_mapping.select_fields and not field_mapping.where_fields:
        return generate_apex_class(class_name, inputs, outputs)

    lines = [
        f'public with sharing class {class_name} {{',
        '',
    ]

    # Request inner class
    lines.append('    public class Request {')
    for inp in inputs:
        apex_type = _TYPE_MAP.get(inp.input_type, "String")
        if inp.description:
            lines.append(f'        @InvocableVariable(label=\'{_escape_apex(inp.description)}\' required={_apex_bool(inp.is_required)})')
        else:
            lines.append(f'        @InvocableVariable(required={_apex_bool(inp.is_required)})')
        lines.append(f'        public {apex_type} {inp.name};')
        lines.append('')
    lines.append('    }')
    lines.append('')

    # Response inner class
    lines.append('    public class Response {')
    for out in outputs:
        apex_type = _TYPE_MAP.get(out.output_type, "String")
        if out.description:
            lines.append(f'        @InvocableVariable(label=\'{_escape_apex(out.description)}\')')
        else:
            lines.append(f'        @InvocableVariable')
        lines.append(f'        public {apex_type} {out.name};')
        lines.append('')
    lines.append('    }')
    lines.append('')

    # Build SOQL query
    select_cols = ", ".join(field_mapping.select_fields) if field_mapping.select_fields else "Id, Name"

    where_parts: list[str] = []
    for inp_name, field_name in field_mapping.input_mappings.items():
        where_parts.append(f"{field_name} = :req.{inp_name}")

    # @InvocableMethod
    method_label = _class_to_label(class_name)
    lines.extend([
        f'    @InvocableMethod(label=\'{method_label}\' description=\'Query {sobject} records\')',
        '    public static List<Response> invoke(List<Request> requests) {',
        '        Request req = requests[0];',
    ])

    # SOQL query
    soql = f'SELECT {select_cols} FROM {sobject}'
    if where_parts:
        soql += ' WHERE ' + ' AND '.join(where_parts)
    soql += ' LIMIT 100'

    lines.append(f'        List<{sobject}> records = [')
    lines.append(f'            {soql}')
    lines.append('        ];')
    lines.append('')

    # Map results to response
    lines.append('        Response res = new Response();')
    for out_name, field_name in field_mapping.output_mappings.items():
        out_def = next((o for o in outputs if o.name == out_name), None)
        out_type = out_def.output_type if out_def else "string"
        if out_type == "string" and out_name.endswith("_json"):
            # JSON serialization for list-like outputs
            lines.append(f'        res.{out_name} = JSON.serialize(records);')
        elif out_type == "string":
            lines.append(f'        res.{out_name} = records.isEmpty() ? \'\' : String.valueOf(records[0].{field_name});')
        elif out_type == "number":
            lines.append(f'        res.{out_name} = records.isEmpty() ? 0 : (Decimal) records[0].{field_name};')
        elif out_type == "boolean":
            lines.append(f'        res.{out_name} = records.isEmpty() ? false : (Boolean) records[0].{field_name};')
        else:
            lines.append(f'        res.{out_name} = records.isEmpty() ? null : String.valueOf(records[0].{field_name});')

    # Handle unmapped outputs — add total_count style patterns
    for out in outputs:
        if out.name not in field_mapping.output_mappings:
            if "count" in out.name.lower() or "total" in out.name.lower():
                lines.append(f'        res.{out.name} = String.valueOf(records.size());')
            elif out.name.endswith("_json") or out.name.endswith("_list"):
                lines.append(f'        res.{out.name} = JSON.serialize(records);')
            else:
                lines.append(f'        res.{out.name} = {_default_for_type(out.output_type)}; // TODO: map to field')

    lines.extend([
        '        return new List<Response>{res};',
        '    }',
        '}',
    ])

    return "\n".join(lines) + "\n"
