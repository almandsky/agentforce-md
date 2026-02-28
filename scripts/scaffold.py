"""Generate stub metadata files for missing SKILL.md targets."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path

from .discover import DiscoveryReport, TargetStatus, discover
from .generator.apex_stub import generate_apex_class, generate_apex_meta_xml
from .generator.flow_xml import generate_flow_xml
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
) -> ScaffoldResult:
    """Generate metadata stubs for missing targets.

    Args:
        report: Discovery report (from discover step).
        project_root: Root of the Claude Code project.
        output_dir: Where to write stubs. Defaults to force-app/main/default/.

    Returns:
        ScaffoldResult with list of created files.
    """
    if output_dir is None:
        output_dir = Path.cwd() / "force-app" / "main" / "default"

    result = ScaffoldResult()

    # Build a lookup from target to action definition (for inputs/outputs)
    skill_actions = _load_skill_actions(project_root)

    for target_status in report.missing:
        action_def = skill_actions.get(target_status.skill_name)
        inputs = action_def.inputs if action_def else []
        outputs = action_def.outputs if action_def else []

        if target_status.target_type == "flow":
            _scaffold_flow(
                target_status, inputs, outputs, output_dir, result,
            )
        elif target_status.target_type == "apex":
            _scaffold_apex(
                target_status, inputs, outputs, output_dir, result,
            )
        else:
            result.warnings.append(
                f"Unsupported target type '{target_status.target_type}' "
                f"for {target_status.skill_name} — skipping"
            )

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
    return scaffold(report, project_root, output_dir)


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
    skill_actions = _load_skill_actions(project_root)

    for skill_name, action_def in skill_actions.items():
        if not action_def.target:
            continue

        from .discover import _parse_target
        target_type, target_name = _parse_target(action_def.target)

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
        else:
            result.warnings.append(
                f"Unsupported target type '{target_type}' for {skill_name} — skipping"
            )

    return result


def _scaffold_flow(
    target: TargetStatus,
    inputs: list,
    outputs: list,
    output_dir: Path,
    result: ScaffoldResult,
) -> None:
    """Generate a stub Flow XML."""
    flow_dir = output_dir / "flows"
    flow_dir.mkdir(parents=True, exist_ok=True)

    xml_content = generate_flow_xml(
        api_name=target.target_name,
        inputs=inputs,
        outputs=outputs,
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
) -> None:
    """Generate an Apex class stub + meta XML."""
    classes_dir = output_dir / "classes"
    classes_dir.mkdir(parents=True, exist_ok=True)

    cls_content = generate_apex_class(
        class_name=target.target_name,
        inputs=inputs,
        outputs=outputs,
    )
    meta_content = generate_apex_meta_xml()

    cls_path = classes_dir / f"{target.target_name}.cls"
    cls_path.write_text(cls_content, encoding="utf-8")
    result.files_created.append(cls_path)

    meta_path = classes_dir / f"{target.target_name}.cls-meta.xml"
    meta_path.write_text(meta_content, encoding="utf-8")
    result.files_created.append(meta_path)

    logger.info("Created apex stub: %s + meta", cls_path)


def _load_skill_actions(project_root: Path) -> dict:
    """Load all SKILL.md actions keyed by skill directory name."""
    skill_actions = {}
    for sk_path in discover_skills(project_root):
        action_def = parse_skill_md(sk_path)
        if action_def:
            skill_actions[sk_path.parent.name] = action_def
    return skill_actions
