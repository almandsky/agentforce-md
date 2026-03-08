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


def test_skill_parses_new_action_fields(tmp_path: Path):
    """New action-level fields (label, require_user_confirmation, etc.) are parsed."""
    md = tmp_path / "SKILL.md"
    md.write_text("""---
name: get-order
description: Get order details
agentforce:
  target: "flow://Get_Order"
  label: "Get Order"
  require_user_confirmation: true
  include_in_progress_indicator: true
  progress_indicator_message: "Looking up order..."
  source: "Get_Order_Details"
---
""")
    action = parse_skill_md(md)
    assert action.label == "Get Order"
    assert action.require_user_confirmation is True
    assert action.include_in_progress_indicator is True
    assert action.progress_indicator_message == "Looking up order..."
    assert action.source == "Get_Order_Details"


def test_skill_parses_new_input_fields(tmp_path: Path):
    """New input-level fields (label, is_user_input, etc.) are parsed."""
    md = tmp_path / "SKILL.md"
    md.write_text("""---
name: search
description: Search
agentforce:
  target: "flow://Search"
  inputs:
    query:
      type: string
      description: "Search query"
      label: "Query"
      is_user_input: true
      complex_data_type_name: "QueryType"
      default_value: "@knowledge.citations_url"
---
""")
    action = parse_skill_md(md)
    inp = action.inputs[0]
    assert inp.label == "Query"
    assert inp.is_user_input is True
    assert inp.complex_data_type_name == "QueryType"
    assert inp.default_value == "@knowledge.citations_url"


def test_skill_parses_new_output_fields(tmp_path: Path):
    """New output-level fields (label, complex_data_type_name, etc.) are parsed."""
    md = tmp_path / "SKILL.md"
    md.write_text("""---
name: search
description: Search
agentforce:
  target: "flow://Search"
  outputs:
    result:
      type: string
      description: "Result"
      label: "Search Result"
      complex_data_type_name: "ResultType"
      filter_from_agent: true
      is_displayable: false
---
""")
    action = parse_skill_md(md)
    out = action.outputs[0]
    assert out.label == "Search Result"
    assert out.complex_data_type_name == "ResultType"
    assert out.filter_from_agent is True
    assert out.is_displayable is False


def test_skill_defaults_for_new_fields(tmp_path: Path):
    """New fields default correctly when not specified in YAML."""
    md = tmp_path / "SKILL.md"
    md.write_text("""---
name: basic
description: Basic action
agentforce:
  target: "flow://Basic"
  inputs:
    x:
      type: string
  outputs:
    y:
      type: string
---
""")
    action = parse_skill_md(md)
    assert action.label is None
    assert action.require_user_confirmation is False
    assert action.include_in_progress_indicator is False
    assert action.progress_indicator_message is None
    assert action.source is None
    assert action.inputs[0].label is None
    assert action.inputs[0].is_user_input is False
    assert action.inputs[0].complex_data_type_name is None
    assert action.inputs[0].default_value is None
    assert action.outputs[0].label is None
    assert action.outputs[0].complex_data_type_name is None
    assert action.outputs[0].filter_from_agent is False
    assert action.outputs[0].is_displayable is True


def test_skill_parses_sobject(tmp_path: Path):
    """The sobject field is parsed from agentforce frontmatter."""
    md = tmp_path / "SKILL.md"
    md.write_text("""---
name: search-homes
description: Search for homes
agentforce:
  target: "apex://SearchHomesAction"
  sobject: "Property__c"
  inputs:
    state:
      type: string
      description: "US state abbreviation"
  outputs:
    results_json:
      type: string
      description: "JSON array of matching homes"
---
""")
    action = parse_skill_md(md)
    assert action is not None
    assert action.sobject == "Property__c"
    assert action.target == "apex://SearchHomesAction"


def test_skill_sobject_defaults_to_none(tmp_path: Path):
    """sobject defaults to None when not specified."""
    md = tmp_path / "SKILL.md"
    md.write_text("""---
name: basic
description: Basic action
agentforce:
  target: "flow://Basic"
---
""")
    action = parse_skill_md(md)
    assert action.sobject is None


def test_discover_skills(tmp_project: Path):
    skills_dir = tmp_project / ".claude" / "skills"
    (skills_dir / "skill-a").mkdir()
    (skills_dir / "skill-a" / "SKILL.md").write_text("---\nname: skill-a\n---\nA")
    (skills_dir / "skill-b").mkdir()
    (skills_dir / "skill-b" / "SKILL.md").write_text("---\nname: skill-b\n---\nB")

    paths = discover_skills(tmp_project)
    assert len(paths) == 2
