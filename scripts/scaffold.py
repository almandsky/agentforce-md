"""Generate stub metadata files for missing SKILL.md targets."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path

from .deploy.sf_cli import SfAgentCli
from .discover import DiscoveryReport, TargetStatus, discover
from .generator.apex_stub import generate_apex_class, generate_apex_meta_xml, generate_smart_apex_class
from .generator.apex_test_stub import generate_apex_test_class
from .generator.flow_xml import generate_flow_xml, generate_smart_flow_xml
from .generator.permission_set_xml import generate_permission_set_xml
from .org_describe import describe_sobject, match_fields
from .parser.skill_md import discover_skills, parse_skill_md

logger = logging.getLogger(__name__)


@dataclass
class ScaffoldResult:
    """Result of scaffold operation."""
    files_created: list[Path] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


def scaffold(
    report: DiscoveryReport,
    project_root: Path,
    output_dir: Path | None = None,
    target_org: str | None = None,
) -> ScaffoldResult:
    """Generate metadata stubs for missing targets.

    When a SKILL.md specifies a `sobject` and `target_org` is provided,
    generates smart stubs with real SOQL queries and field mappings.

    Args:
        report: Discovery report (from discover step).
        project_root: Root of the Claude Code project.
        output_dir: Where to write stubs. Defaults to force-app/main/default/.
        target_org: Target org (enables smart scaffold with SObject describe).

    Returns:
        ScaffoldResult with list of created files.
    """
    if output_dir is None:
        output_dir = Path.cwd() / "force-app" / "main" / "default"

    result = ScaffoldResult()
    apex_class_names: list[str] = []

    # Build a lookup from target to action definition (for inputs/outputs)
    skill_actions = _load_skill_actions(project_root)

    for target_status in report.missing:
        action_def = skill_actions.get(target_status.skill_name)
        inputs = action_def.inputs if action_def else []
        outputs = action_def.outputs if action_def else []

        _warn_number_inputs(target_status.skill_name, inputs, result)

        # Determine SObject for smart scaffold
        sobject = action_def.sobject if action_def else None

        if target_status.target_type == "flow":
            _scaffold_flow(
                target_status, inputs, outputs, output_dir, result,
                target_org=target_org, sobject=sobject,
            )
        elif target_status.target_type == "apex":
            _scaffold_apex(
                target_status, inputs, outputs, output_dir, result,
                target_org=target_org, sobject=sobject,
            )
            apex_class_names.append(target_status.target_name)
        else:
            result.warnings.append(
                f"Unsupported target type '{target_status.target_type}' "
                f"for {target_status.skill_name} — skipping"
            )

    if apex_class_names:
        _scaffold_permission_set(apex_class_names, output_dir, result)

    return result


def scaffold_from_skills(
    project_root: Path,
    target_org: str,
    output_dir: Path | None = None,
) -> ScaffoldResult:
    """Convenience: discover + scaffold in one call.

    Args:
        project_root: Root of the Claude Code project.
        target_org: Target org username or alias.
        output_dir: Where to write stubs.

    Returns:
        ScaffoldResult with list of created files.
    """
    report = discover(project_root, target_org)
    return scaffold(report, project_root, output_dir, target_org=target_org)


def scaffold_all(
    project_root: Path,
    output_dir: Path | None = None,
) -> ScaffoldResult:
    """Scaffold all targets without checking the org.

    Args:
        project_root: Root of the Claude Code project.
        output_dir: Where to write stubs.

    Returns:
        ScaffoldResult with list of created files.
    """
    if output_dir is None:
        output_dir = Path.cwd() / "force-app" / "main" / "default"

    result = ScaffoldResult()
    apex_class_names: list[str] = []
    skill_actions = _load_skill_actions(project_root)

    for skill_name, action_def in skill_actions.items():
        if not action_def.target:
            continue

        from .discover import _parse_target
        target_type, target_name = _parse_target(action_def.target)

        _warn_number_inputs(skill_name, action_def.inputs, result)

        ts = TargetStatus(
            skill_name=skill_name,
            target=action_def.target,
            target_type=target_type,
            target_name=target_name,
            found=False,
            details="Scaffolding without org check",
        )

        if target_type == "flow":
            _scaffold_flow(ts, action_def.inputs, action_def.outputs, output_dir, result)
        elif target_type == "apex":
            _scaffold_apex(ts, action_def.inputs, action_def.outputs, output_dir, result)
            apex_class_names.append(target_name)
        else:
            result.warnings.append(
                f"Unsupported target type '{target_type}' for {skill_name} — skipping"
            )

    if apex_class_names:
        _scaffold_permission_set(apex_class_names, output_dir, result)

    return result


def _scaffold_flow(
    target: TargetStatus,
    inputs: list,
    outputs: list,
    output_dir: Path,
    result: ScaffoldResult,
    target_org: str | None = None,
    sobject: str | None = None,
) -> None:
    """Generate a Flow XML — smart version if SObject is available."""
    flow_dir = output_dir / "flows"
    flow_dir.mkdir(parents=True, exist_ok=True)

    xml_content: str
    if sobject and target_org:
        fields = describe_sobject(sobject, target_org)
        if fields:
            mapping = match_fields(inputs, outputs, fields)
            xml_content = generate_smart_flow_xml(
                api_name=target.target_name,
                sobject=sobject,
                field_mapping=mapping,
                inputs=inputs,
                outputs=outputs,
            )
            logger.info("Smart flow scaffold using %s (%d fields)", sobject, len(fields))
        else:
            xml_content = generate_flow_xml(
                api_name=target.target_name, inputs=inputs, outputs=outputs,
            )
    else:
        xml_content = generate_flow_xml(
            api_name=target.target_name, inputs=inputs, outputs=outputs,
        )

    flow_path = flow_dir / f"{target.target_name}.flow-meta.xml"
    flow_path.write_text(xml_content, encoding="utf-8")
    result.files_created.append(flow_path)
    logger.info("Created flow stub: %s", flow_path)


def _scaffold_apex(
    target: TargetStatus,
    inputs: list,
    outputs: list,
    output_dir: Path,
    result: ScaffoldResult,
    target_org: str | None = None,
    sobject: str | None = None,
) -> None:
    """Generate an Apex class stub + meta XML + test class + test meta.

    Uses smart generation with SOQL when SObject is available.
    """
    classes_dir = output_dir / "classes"
    classes_dir.mkdir(parents=True, exist_ok=True)

    cls_content: str
    if sobject and target_org:
        fields = describe_sobject(sobject, target_org)
        if fields:
            mapping = match_fields(inputs, outputs, fields)
            cls_content = generate_smart_apex_class(
                class_name=target.target_name,
                sobject=sobject,
                field_mapping=mapping,
                inputs=inputs,
                outputs=outputs,
            )
            logger.info("Smart apex scaffold using %s (%d fields)", sobject, len(fields))
        else:
            cls_content = generate_apex_class(
                class_name=target.target_name, inputs=inputs, outputs=outputs,
            )
    else:
        cls_content = generate_apex_class(
            class_name=target.target_name, inputs=inputs, outputs=outputs,
        )
    meta_content = generate_apex_meta_xml()

    cls_path = classes_dir / f"{target.target_name}.cls"
    cls_path.write_text(cls_content, encoding="utf-8")
    result.files_created.append(cls_path)

    meta_path = classes_dir / f"{target.target_name}.cls-meta.xml"
    meta_path.write_text(meta_content, encoding="utf-8")
    result.files_created.append(meta_path)

    # Test class
    test_cls_content = generate_apex_test_class(
        class_name=target.target_name,
        inputs=inputs,
        outputs=outputs,
    )
    test_cls_path = classes_dir / f"{target.target_name}Test.cls"
    test_cls_path.write_text(test_cls_content, encoding="utf-8")
    result.files_created.append(test_cls_path)

    test_meta_path = classes_dir / f"{target.target_name}Test.cls-meta.xml"
    test_meta_path.write_text(meta_content, encoding="utf-8")
    result.files_created.append(test_meta_path)

    logger.info("Created apex stub: %s + test + meta", cls_path)


def _scaffold_permission_set(
    apex_class_names: list[str],
    output_dir: Path,
    result: ScaffoldResult,
) -> None:
    """Generate a Permission Set XML granting classAccesses."""
    perm_sets_dir = output_dir / "permissionsets"
    perm_sets_dir.mkdir(parents=True, exist_ok=True)

    perm_set_name = "Agent_Action_Access"

    # Include both action classes and their test classes
    all_classes = []
    for name in apex_class_names:
        all_classes.append(name)
        all_classes.append(f"{name}Test")

    xml_content = generate_permission_set_xml(perm_set_name, all_classes)

    perm_set_path = perm_sets_dir / f"{perm_set_name}.permissionset-meta.xml"
    perm_set_path.write_text(xml_content, encoding="utf-8")
    result.files_created.append(perm_set_path)

    logger.info("Created permission set: %s", perm_set_path)


def _warn_number_inputs(
    skill_name: str,
    inputs: list,
    result: ScaffoldResult,
) -> None:
    """Emit a warning for inputs with number type."""
    for inp in inputs:
        if getattr(inp, "input_type", None) == "number":
            result.warnings.append(
                f"{skill_name} uses 'number' type for input '{inp.name}'. "
                "Agent Script may reject Decimal — consider using 'string' "
                "type and parsing manually in Apex."
            )


def _load_skill_actions(project_root: Path) -> dict:
    """Load all SKILL.md actions keyed by skill directory name."""
    skill_actions = {}
    for sk_path in discover_skills(project_root):
        action_def = parse_skill_md(sk_path)
        if action_def:
            skill_actions[sk_path.parent.name] = action_def
    return skill_actions
