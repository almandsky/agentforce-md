"""Tests for the local_run module."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

from scripts.deploy.sf_cli import CliResult
from scripts.local_run import (
    RunResult,
    _invoke_apex,
    _invoke_flow,
    _parse_action_response,
    _validate_inputs,
    run_action,
)
from scripts.ir.models import ActionDefinition, ActionInput, ActionOutput


def _create_skill_md(path: Path, target: str, inputs: str = "", outputs: str = "") -> Path:
    """Create a SKILL.md file and return its path."""
    path.parent.mkdir(parents=True, exist_ok=True)
    input_section = ""
    if inputs:
        input_section = f"""  inputs:
{inputs}"""
    output_section = ""
    if outputs:
        output_section = f"""  outputs:
{outputs}"""

    path.write_text(f"""---
name: test-skill
description: Test skill
agentforce:
  target: "{target}"
{input_section}
{output_section}
---
Test body.
""")
    return path


# --- _validate_inputs tests ---


def test_validate_inputs_all_present():
    action = ActionDefinition(
        name="test", description="test",
        inputs=[
            ActionInput(name="a", input_type="string", is_required=True),
            ActionInput(name="b", input_type="string", is_required=False),
        ],
    )
    assert _validate_inputs(action, {"a": "val", "b": "val"}) is None


def test_validate_inputs_optional_missing():
    action = ActionDefinition(
        name="test", description="test",
        inputs=[
            ActionInput(name="a", input_type="string", is_required=True),
            ActionInput(name="b", input_type="string", is_required=False),
        ],
    )
    assert _validate_inputs(action, {"a": "val"}) is None


def test_validate_inputs_required_missing():
    action = ActionDefinition(
        name="test", description="test",
        inputs=[
            ActionInput(name="a", input_type="string", is_required=True),
        ],
    )
    error = _validate_inputs(action, {})
    assert error is not None
    assert "a" in error


def test_validate_inputs_unknown():
    action = ActionDefinition(
        name="test", description="test",
        inputs=[
            ActionInput(name="a", input_type="string"),
        ],
    )
    error = _validate_inputs(action, {"a": "val", "z": "extra"})
    assert error is not None
    assert "z" in error


def test_validate_inputs_no_definition():
    action = ActionDefinition(name="test", description="test")
    assert _validate_inputs(action, {"anything": "goes"}) is None


# --- _invoke_flow tests ---


def test_invoke_flow_success():
    from unittest.mock import MagicMock
    cli = MagicMock()
    response = json.dumps([{"isSuccess": True, "outputValues": {"status": "shipped"}}])
    cli.run_flow.return_value = CliResult(returncode=0, stdout=response, stderr="")

    result = _invoke_flow("My_Flow", {"order_id": "123"}, cli, "TestOrg")
    assert result.success is True
    assert result.outputs == {"status": "shipped"}


def test_invoke_flow_cli_error():
    from unittest.mock import MagicMock
    cli = MagicMock()
    cli.run_flow.return_value = CliResult(returncode=1, stdout="", stderr="Connection failed")

    result = _invoke_flow("My_Flow", {}, cli, "TestOrg")
    assert result.success is False
    assert "Connection failed" in result.error


def test_invoke_flow_api_error():
    from unittest.mock import MagicMock
    cli = MagicMock()
    response = json.dumps([{"isSuccess": False, "errors": ["Invalid input"], "outputValues": {}}])
    cli.run_flow.return_value = CliResult(returncode=0, stdout=response, stderr="")

    result = _invoke_flow("My_Flow", {}, cli, "TestOrg")
    assert result.success is False
    assert "Invalid input" in result.error


# --- _invoke_apex tests ---


def test_invoke_apex_success():
    from unittest.mock import MagicMock
    cli = MagicMock()
    response = json.dumps([{"isSuccess": True, "outputValues": {"result": "done"}}])
    cli.run_apex_action.return_value = CliResult(returncode=0, stdout=response, stderr="")

    result = _invoke_apex("MyClass", {"x": "1"}, cli, "TestOrg")
    assert result.success is True
    assert result.outputs == {"result": "done"}


def test_invoke_apex_cli_error():
    from unittest.mock import MagicMock
    cli = MagicMock()
    cli.run_apex_action.return_value = CliResult(returncode=1, stdout="", stderr="Timeout")

    result = _invoke_apex("MyClass", {}, cli, "TestOrg")
    assert result.success is False


# --- _parse_action_response tests ---


def test_parse_response_success():
    raw = json.dumps([{"isSuccess": True, "outputValues": {"key": "val"}}])
    result = _parse_action_response(raw)
    assert result.success is True
    assert result.outputs == {"key": "val"}


def test_parse_response_error():
    raw = json.dumps([{"isSuccess": False, "errors": ["bad input"], "outputValues": {}}])
    result = _parse_action_response(raw)
    assert result.success is False
    assert "bad input" in result.error


def test_parse_response_dict_fallback():
    raw = json.dumps({"some": "data"})
    result = _parse_action_response(raw)
    assert result.success is True
    assert result.outputs == {"some": "data"}


def test_parse_response_bad_json():
    result = _parse_action_response("not json")
    assert result.success is False
    assert "JSON" in result.error


# --- run_action integration tests ---


def test_run_action_no_target(tmp_path: Path):
    """SKILL.md without target returns error."""
    md = tmp_path / "SKILL.md"
    md.write_text("""---
name: no-target
description: No target
---
Body.
""")
    result = run_action(md, "TestOrg", {})
    assert result.success is False
    assert "no agentforce target" in result.error


def test_run_action_no_frontmatter(tmp_path: Path):
    """SKILL.md without frontmatter returns error."""
    md = tmp_path / "SKILL.md"
    md.write_text("Just text, no frontmatter.")
    result = run_action(md, "TestOrg", {})
    assert result.success is False
    assert "Could not parse" in result.error


def test_run_action_dry_run(tmp_path: Path):
    """Dry run returns invocation plan."""
    md = tmp_path / "SKILL.md"
    md.write_text("""---
name: test
description: test
agentforce:
  target: "flow://My_Flow"
  inputs:
    x:
      type: string
---
""")
    result = run_action(md, "TestOrg", {"x": "val"}, dry_run=True)
    assert result.success is True
    plan = json.loads(result.raw_response)
    assert plan["dry_run"] is True
    assert plan["target_name"] == "My_Flow"
    assert plan["inputs"] == {"x": "val"}


def test_run_action_unsupported_type(tmp_path: Path):
    """Unsupported target type returns error."""
    md = tmp_path / "SKILL.md"
    md.write_text("""---
name: test
description: test
agentforce:
  target: "retriever://KB"
---
""")
    result = run_action(md, "TestOrg", {})
    assert result.success is False
    assert "Unsupported" in result.error


def test_run_action_missing_required_input(tmp_path: Path):
    """Missing required input returns validation error."""
    md = tmp_path / "SKILL.md"
    md.write_text("""---
name: test
description: test
agentforce:
  target: "flow://My_Flow"
  inputs:
    required_field:
      type: string
      required: true
---
""")
    result = run_action(md, "TestOrg", {})
    assert result.success is False
    assert "required_field" in result.error


def test_run_action_flow_success(tmp_path: Path):
    """Full run_action with mocked flow call."""
    md = tmp_path / "SKILL.md"
    md.write_text("""---
name: test
description: test
agentforce:
  target: "flow://My_Flow"
  inputs:
    x:
      type: string
---
""")
    response = json.dumps([{"isSuccess": True, "outputValues": {"result": "ok"}}])
    mock_result = CliResult(returncode=0, stdout=response, stderr="")

    with patch("scripts.local_run.SfAgentCli") as MockCli:
        MockCli.return_value.run_flow.return_value = mock_result
        result = run_action(md, "TestOrg", {"x": "val"})

    assert result.success is True
    assert result.outputs == {"result": "ok"}
