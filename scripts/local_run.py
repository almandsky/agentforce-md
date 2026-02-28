"""Execute SKILL.md actions against a live Salesforce org."""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from pathlib import Path

from .deploy.sf_cli import SfAgentCli
from .discover import _parse_target
from .parser.skill_md import parse_skill_md

logger = logging.getLogger(__name__)


@dataclass
class RunResult:
    """Result of executing an action."""
    success: bool
    outputs: dict         # key-value outputs from the action
    raw_response: str     # full API response
    error: str | None = None


def run_action(
    skill_path: Path,
    target_org: str,
    inputs: dict[str, str],
    dry_run: bool = False,
) -> RunResult:
    """Execute a SKILL.md action against a live org.

    Args:
        skill_path: Path to the SKILL.md file.
        target_org: Target org username or alias.
        inputs: Input values to pass to the action.
        dry_run: If True, show what would be called without executing.

    Returns:
        RunResult with success status and outputs.
    """
    # 1. Parse the SKILL.md
    action_def = parse_skill_md(skill_path)
    if action_def is None:
        return RunResult(
            success=False,
            outputs={},
            raw_response="",
            error=f"Could not parse SKILL.md at {skill_path}",
        )

    if not action_def.target:
        return RunResult(
            success=False,
            outputs={},
            raw_response="",
            error=f"SKILL.md at {skill_path} has no agentforce target",
        )

    # 2. Validate inputs
    validation_error = _validate_inputs(action_def, inputs)
    if validation_error:
        return RunResult(
            success=False,
            outputs={},
            raw_response="",
            error=validation_error,
        )

    # 3. Route based on target type
    target_type, target_name = _parse_target(action_def.target)

    if dry_run:
        return RunResult(
            success=True,
            outputs={},
            raw_response=json.dumps({
                "dry_run": True,
                "target_type": target_type,
                "target_name": target_name,
                "inputs": inputs,
                "org": target_org,
            }, indent=2),
        )

    cli = SfAgentCli()

    if target_type == "flow":
        return _invoke_flow(target_name, inputs, cli, target_org)
    elif target_type == "apex":
        return _invoke_apex(target_name, inputs, cli, target_org)
    else:
        return RunResult(
            success=False,
            outputs={},
            raw_response="",
            error=f"Unsupported target type: {target_type}",
        )


def _validate_inputs(action_def, provided_inputs: dict) -> str | None:
    """Validate provided inputs against the action definition.

    Returns an error message string, or None if valid.
    """
    if not action_def.inputs:
        return None

    expected_names = {inp.name for inp in action_def.inputs}
    required_names = {inp.name for inp in action_def.inputs if inp.is_required}
    provided_names = set(provided_inputs.keys())

    # Check for missing required inputs
    missing = required_names - provided_names
    if missing:
        return f"Missing required input(s): {', '.join(sorted(missing))}"

    # Check for unknown inputs
    unknown = provided_names - expected_names
    if unknown:
        return f"Unknown input(s): {', '.join(sorted(unknown))}"

    return None


def _invoke_flow(
    flow_name: str,
    inputs: dict,
    cli: SfAgentCli,
    org: str,
) -> RunResult:
    """Invoke a flow and parse the response."""
    result = cli.run_flow(flow_name, inputs, org)

    if result.returncode != 0:
        return RunResult(
            success=False,
            outputs={},
            raw_response=result.stdout or result.stderr,
            error=f"Flow invocation failed: {result.stderr}",
        )

    return _parse_action_response(result.stdout)


def _invoke_apex(
    class_name: str,
    inputs: dict,
    cli: SfAgentCli,
    org: str,
) -> RunResult:
    """Invoke an @InvocableMethod and parse the response."""
    result = cli.run_apex_action(class_name, inputs, org)

    if result.returncode != 0:
        return RunResult(
            success=False,
            outputs={},
            raw_response=result.stdout or result.stderr,
            error=f"Apex action invocation failed: {result.stderr}",
        )

    return _parse_action_response(result.stdout)


def _parse_action_response(raw: str) -> RunResult:
    """Parse the REST API response from a flow or apex action."""
    try:
        data = json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return RunResult(
            success=False,
            outputs={},
            raw_response=raw or "",
            error="Could not parse API response as JSON",
        )

    # The REST API wraps results in a list
    if isinstance(data, list) and len(data) > 0:
        first = data[0]
        is_success = first.get("isSuccess", True)
        output_values = first.get("outputValues", {})
        errors = first.get("errors", [])

        if not is_success and errors:
            error_msg = "; ".join(str(e) for e in errors)
            return RunResult(
                success=False,
                outputs=output_values or {},
                raw_response=raw,
                error=error_msg,
            )

        return RunResult(
            success=True,
            outputs=output_values or {},
            raw_response=raw,
        )

    # Fallback: treat the whole response as outputs
    return RunResult(
        success=True,
        outputs=data if isinstance(data, dict) else {},
        raw_response=raw,
    )
