"""Tests for SKILL.md parsing."""

from pathlib import Path

from scripts.parser.skill_md import discover_skills, parse_skill_md


def test_skill_with_agentforce_section(tmp_path: Path):
    md = tmp_path / "SKILL.md"
    md.write_text("""---
name: check-order-status
description: Check the status of a customer order
agentforce:
  target: "flow://Get_Order_Details"
  inputs:
    order_id:
      type: string
      description: "The order number"
  outputs:
    status:
      type: string
      description: "Current order status"
---
# Check Order Status
Use this when customer asks about order status.
""")
    action = parse_skill_md(md)
    assert action is not None
    assert action.name == "check_order_status"
    assert action.target == "flow://Get_Order_Details"
    assert len(action.inputs) == 1
    assert action.inputs[0].name == "order_id"
    assert action.inputs[0].input_type == "string"
    assert len(action.outputs) == 1
    assert action.outputs[0].name == "status"


def test_skill_without_agentforce(tmp_path: Path):
    md = tmp_path / "SKILL.md"
    md.write_text("""---
name: pdf-processing
description: Extract text from PDFs
---
# PDF Processing
Extract text from PDF files.
""")
    action = parse_skill_md(md)
    assert action is not None
    assert action.name == "pdf_processing"
    assert action.target is None  # Stub


def test_skill_no_frontmatter(tmp_path: Path):
    md = tmp_path / "SKILL.md"
    md.write_text("Just some instructions, no frontmatter.")
    action = parse_skill_md(md)
    assert action is None


def test_discover_skills(tmp_project: Path):
    skills_dir = tmp_project / ".claude" / "skills"
    (skills_dir / "skill-a").mkdir()
    (skills_dir / "skill-a" / "SKILL.md").write_text("---\nname: skill-a\n---\nA")
    (skills_dir / "skill-b").mkdir()
    (skills_dir / "skill-b" / "SKILL.md").write_text("---\nname: skill-b\n---\nB")

    paths = discover_skills(tmp_project)
    assert len(paths) == 2
