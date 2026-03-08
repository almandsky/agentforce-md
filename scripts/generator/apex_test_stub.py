"""Generate @isTest companion classes for Apex @InvocableMethod stubs."""

from __future__ import annotations

from ..ir.models import ActionInput, ActionOutput
from .apex_stub import _TYPE_MAP, generate_apex_meta_xml


def _placeholder_for_type(type_name: str) -> str:
    """Return a placeholder Apex literal suitable for test inputs."""
    placeholders = {
        "string": "'test'",
        "number": "1",
        "boolean": "true",
        "date": "Date.today()",
        "datetime": "Datetime.now()",
        "id": "null",
    }
    return placeholders.get(type_name, "null")


def generate_apex_test_class(
    class_name: str,
    inputs: list[ActionInput] | None = None,
    outputs: list[ActionOutput] | None = None,
) -> str:
    """Generate an @isTest companion class for an Apex @InvocableMethod stub.

    Produces a test class with:
    - An HttpCalloutMock inner class (for skills that make HTTP callouts)
    - A testInvoke() method that constructs a request, calls the method, and asserts

    Args:
        class_name: The Apex class name being tested.
        inputs: Action input definitions from SKILL.md.
        outputs: Action output definitions from SKILL.md.

    Returns:
        Apex test class source code string.
    """
    inputs = inputs or []
    outputs = outputs or []
    test_class_name = f"{class_name}Test"

    lines = [
        f"@isTest",
        f"private class {test_class_name} {{",
        "",
        "    private class MockHttpResponse implements HttpCalloutMock {",
        "        public HttpResponse respond(HttpRequest req) {",
        "            HttpResponse res = new HttpResponse();",
        "            res.setStatusCode(200);",
        "            res.setBody('{}');",
        "            return res;",
        "        }",
        "    }",
        "",
        "    @isTest",
        "    static void testInvoke() {",
        "        Test.setMock(HttpCalloutMock.class, new MockHttpResponse());",
        "",
        f"        {class_name}.Request req = new {class_name}.Request();",
    ]

    # Set placeholder values for each input
    for inp in inputs:
        apex_type = _TYPE_MAP.get(inp.input_type, "String")
        placeholder = _placeholder_for_type(inp.input_type)
        lines.append(f"        req.{inp.name} = {placeholder};")

    lines.extend([
        "",
        f"        List<{class_name}.Request> requests = new List<{class_name}.Request>{{ req }};",
        f"        List<{class_name}.Response> responses = {class_name}.invoke(requests);",
        "",
        "        System.assertNotEquals(null, responses, 'Response list should not be null');",
        "        System.assertEquals(1, responses.size(), 'Should return one response');",
    ])

    # Assert each output field is populated
    for out in outputs:
        lines.append(f"        System.assertNotEquals(null, responses[0].{out.name}, '{out.name} should not be null');")

    lines.extend([
        "    }",
        "}",
    ])

    return "\n".join(lines) + "\n"
