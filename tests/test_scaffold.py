"""Tests for the scaffold module."""

from __future__ import annotations

from pathlib import Path

from scripts.discover import DiscoveryReport, TargetStatus
from scripts.scaffold import scaffold, scaffold_all, _load_skill_actions


def _make_report(missing_targets: list[tuple[str, str, str]]) -> DiscoveryReport:
    """Create a DiscoveryReport with specified missing targets.

    Each tuple is (skill_name, target_uri, target_type).
    """
    targets = []
    for skill_name, target_uri, target_type in missing_targets:
        _, target_name = target_uri.split("://", 1)
        targets.append(TargetStatus(
            skill_name=skill_name,
            target=target_uri,
            target_type=target_type,
            target_name=target_name,
            found=False,
            details="Not found",
        ))
    return DiscoveryReport(targets=targets)


def _create_skill(project_root: Path, skill_name: str, target: str) -> None:
    """Create a SKILL.md with a target and input/output."""
    skill_dir = project_root / ".claude" / "skills" / skill_name
    skill_dir.mkdir(parents=True, exist_ok=True)
    (skill_dir / "SKILL.md").write_text(f"""---
name: {skill_name}
description: Test skill
agentforce:
  target: "{target}"
  inputs:
    test_input:
      type: string
      description: "Test input"
  outputs:
    test_output:
      type: string
      description: "Test output"
---
Test body.
""")


# --- scaffold() tests ---


def test_scaffold_flow(tmp_project: Path):
    """Scaffold generates a Flow XML file."""
    _create_skill(tmp_project, "my-skill", "flow://My_Flow")
    report = _make_report([("my-skill", "flow://My_Flow", "flow")])
    output_dir = tmp_project / "force-app" / "main" / "default"

    result = scaffold(report, tmp_project, output_dir)

    assert len(result.files_created) == 1
    flow_path = output_dir / "flows" / "My_Flow.flow-meta.xml"
    assert flow_path.exists()
    assert flow_path in result.files_created

    content = flow_path.read_text()
    assert "<label>My_Flow</label>" in content
    assert "<name>test_input</name>" in content
    assert "<name>test_output</name>" in content


def test_scaffold_apex(tmp_project: Path):
    """Scaffold generates Apex class + meta + test class + test meta + permission set."""
    _create_skill(tmp_project, "my-apex-skill", "apex://MyAction")
    report = _make_report([("my-apex-skill", "apex://MyAction", "apex")])
    output_dir = tmp_project / "force-app" / "main" / "default"

    result = scaffold(report, tmp_project, output_dir)

    # 4 apex files + 1 permission set
    assert len(result.files_created) == 5
    cls_path = output_dir / "classes" / "MyAction.cls"
    meta_path = output_dir / "classes" / "MyAction.cls-meta.xml"
    test_cls_path = output_dir / "classes" / "MyActionTest.cls"
    test_meta_path = output_dir / "classes" / "MyActionTest.cls-meta.xml"
    assert cls_path.exists()
    assert meta_path.exists()
    assert test_cls_path.exists()
    assert test_meta_path.exists()

    cls_content = cls_path.read_text()
    assert "public with sharing class MyAction" in cls_content
    assert "@InvocableMethod" in cls_content

    test_content = test_cls_path.read_text()
    assert "@isTest" in test_content
    assert "MyActionTest" in test_content


def test_scaffold_unsupported_type(tmp_project: Path):
    """Unsupported target types produce warnings."""
    _create_skill(tmp_project, "my-ret", "retriever://KB")
    report = _make_report([("my-ret", "retriever://KB", "retriever")])
    output_dir = tmp_project / "force-app" / "main" / "default"

    result = scaffold(report, tmp_project, output_dir)

    assert len(result.files_created) == 0
    assert len(result.warnings) == 1
    assert "retriever" in result.warnings[0]


def test_scaffold_multiple_targets(tmp_project: Path):
    """Scaffold handles multiple missing targets."""
    _create_skill(tmp_project, "skill-a", "flow://Flow_A")
    _create_skill(tmp_project, "skill-b", "apex://ClassB")
    report = _make_report([
        ("skill-a", "flow://Flow_A", "flow"),
        ("skill-b", "apex://ClassB", "apex"),
    ])
    output_dir = tmp_project / "force-app" / "main" / "default"

    result = scaffold(report, tmp_project, output_dir)

    # 1 flow + 4 apex files (cls + meta + test cls + test meta) + 1 permission set
    assert len(result.files_created) == 6


def test_scaffold_empty_report(tmp_project: Path):
    """Empty report produces no files."""
    report = DiscoveryReport()
    output_dir = tmp_project / "force-app" / "main" / "default"

    result = scaffold(report, tmp_project, output_dir)

    assert len(result.files_created) == 0
    assert len(result.warnings) == 0


def test_scaffold_no_matching_skill(tmp_project: Path):
    """Missing skill uses empty inputs/outputs."""
    # Don't create a matching SKILL.md
    report = _make_report([("nonexistent", "flow://My_Flow", "flow")])
    output_dir = tmp_project / "force-app" / "main" / "default"

    result = scaffold(report, tmp_project, output_dir)

    assert len(result.files_created) == 1
    content = (output_dir / "flows" / "My_Flow.flow-meta.xml").read_text()
    assert "<label>My_Flow</label>" in content


# --- scaffold_all() tests ---


def test_scaffold_all(tmp_project: Path):
    """scaffold_all creates stubs for all targets without org check."""
    _create_skill(tmp_project, "skill-x", "flow://Flow_X")
    _create_skill(tmp_project, "skill-y", "apex://ClassY")
    output_dir = tmp_project / "force-app" / "main" / "default"

    result = scaffold_all(tmp_project, output_dir)

    # 1 flow + 4 apex files + 1 permission set
    assert len(result.files_created) == 6


def test_scaffold_all_no_skills(tmp_project: Path):
    """scaffold_all with no SKILL.md files produces nothing."""
    output_dir = tmp_project / "force-app" / "main" / "default"

    result = scaffold_all(tmp_project, output_dir)

    assert len(result.files_created) == 0


# --- _load_skill_actions() tests ---


def test_load_skill_actions(tmp_project: Path):
    _create_skill(tmp_project, "skill-a", "flow://A")
    _create_skill(tmp_project, "skill-b", "apex://B")

    actions = _load_skill_actions(tmp_project)
    assert "skill-a" in actions
    assert "skill-b" in actions
    assert actions["skill-a"].target == "flow://A"


# --- permission set and number warning tests ---


def test_scaffold_generates_permission_set(tmp_project: Path):
    """Scaffold generates a permission set with correct class names."""
    _create_skill(tmp_project, "my-apex-skill", "apex://MyAction")
    report = _make_report([("my-apex-skill", "apex://MyAction", "apex")])
    output_dir = tmp_project / "force-app" / "main" / "default"

    result = scaffold(report, tmp_project, output_dir)

    perm_path = output_dir / "permissionsets" / "Agent_Action_Access.permissionset-meta.xml"
    assert perm_path.exists()
    assert perm_path in result.files_created

    content = perm_path.read_text()
    assert "<apexClass>MyAction</apexClass>" in content
    assert "<apexClass>MyActionTest</apexClass>" in content
    assert "<label>Agent_Action_Access</label>" in content


def test_scaffold_number_type_warning(tmp_project: Path):
    """Warning emitted when a SKILL.md input has type: number."""
    skill_dir = tmp_project / ".claude" / "skills" / "num-skill"
    skill_dir.mkdir(parents=True, exist_ok=True)
    (skill_dir / "SKILL.md").write_text("""---
name: num-skill
description: Skill with number input
agentforce:
  target: "apex://NumAction"
  inputs:
    quantity:
      type: number
      description: "Item count"
  outputs:
    result:
      type: string
      description: "Result"
---
Body.
""")
    report = _make_report([("num-skill", "apex://NumAction", "apex")])
    output_dir = tmp_project / "force-app" / "main" / "default"

    result = scaffold(report, tmp_project, output_dir)

    number_warnings = [w for w in result.warnings if "number" in w.lower()]
    assert len(number_warnings) == 1
    assert "quantity" in number_warnings[0]
    assert "Decimal" in number_warnings[0]
