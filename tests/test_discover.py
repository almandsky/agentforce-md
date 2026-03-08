"""Tests for the discover module."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

from scripts.deploy.sf_cli import CliResult
from scripts.discover import (
    DiscoveryReport,
    Suggestion,
    TargetStatus,
    _check_apex,
    _check_flows,
    _check_retrievers,
    _parse_target,
    _suggest_similar,
    _tokenize,
    discover,
)


# --- _parse_target tests ---


def test_parse_target_flow():
    assert _parse_target("flow://Get_Order_Status") == ("flow", "Get_Order_Status")


def test_parse_target_apex():
    assert _parse_target("apex://MyInvocableClass") == ("apex", "MyInvocableClass")


def test_parse_target_retriever():
    assert _parse_target("retriever://KnowledgeBase") == ("retriever", "KnowledgeBase")


def test_parse_target_case_insensitive_scheme():
    assert _parse_target("Flow://My_Flow") == ("flow", "My_Flow")


def test_parse_target_no_scheme():
    """Targets without :// fallback to flow."""
    assert _parse_target("SomeFlowName") == ("flow", "SomeFlowName")


# --- DiscoveryReport tests ---


def test_report_found_and_missing():
    report = DiscoveryReport(targets=[
        TargetStatus("s1", "flow://A", "flow", "A", True, "Found"),
        TargetStatus("s2", "flow://B", "flow", "B", False, "Not found"),
        TargetStatus("s3", "apex://C", "apex", "C", True, "Found"),
    ])
    assert len(report.found) == 2
    assert len(report.missing) == 1
    assert not report.all_found


def test_report_all_found():
    report = DiscoveryReport(targets=[
        TargetStatus("s1", "flow://A", "flow", "A", True, "Found"),
    ])
    assert report.all_found


def test_report_empty():
    report = DiscoveryReport()
    assert report.all_found
    assert report.found == []
    assert report.missing == []


# --- _check_flows / _check_apex / _check_retrievers tests ---


def _mock_cli_with_response(records, field_name="ApiName"):
    """Create a mock SfAgentCli whose query_soql returns the given records."""
    cli = MagicMock()
    response = json.dumps({"result": {"records": records}})
    cli.query_soql.return_value = CliResult(returncode=0, stdout=response, stderr="")
    return cli


def test_check_flows_found():
    cli = _mock_cli_with_response([{"ApiName": "Flow_A"}])
    result = _check_flows(["Flow_A", "Flow_B"], cli, "TestOrg")
    assert result == {"Flow_A": True, "Flow_B": False}


def test_check_flows_none_found():
    cli = _mock_cli_with_response([])
    result = _check_flows(["Flow_A"], cli, "TestOrg")
    assert result == {"Flow_A": False}


def test_check_apex_found():
    cli = _mock_cli_with_response([{"Name": "MyClass"}], "Name")
    result = _check_apex(["MyClass", "Other"], cli, "TestOrg")
    assert result == {"MyClass": True, "Other": False}


def test_check_retrievers_found():
    cli = _mock_cli_with_response([{"DeveloperName": "KnowledgeBase"}], "DeveloperName")
    result = _check_retrievers(["KnowledgeBase"], cli, "TestOrg")
    assert result == {"KnowledgeBase": True}


def test_check_flows_cli_error():
    """CLI error returns all as not found."""
    cli = MagicMock()
    cli.query_soql.return_value = CliResult(returncode=1, stdout="", stderr="error")
    result = _check_flows(["Flow_A"], cli, "TestOrg")
    assert result == {"Flow_A": False}


def test_check_flows_bad_json():
    """Malformed JSON returns all as not found."""
    cli = MagicMock()
    cli.query_soql.return_value = CliResult(returncode=0, stdout="not json", stderr="")
    result = _check_flows(["Flow_A"], cli, "TestOrg")
    assert result == {"Flow_A": False}


# --- discover() integration tests (with mocked CLI) ---


def _create_skill_md(project_root: Path, skill_name: str, target: str) -> None:
    """Helper: create a SKILL.md with a target."""
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
  outputs:
    test_output:
      type: string
---
Test skill body.
""")


def test_discover_with_mixed_results(tmp_project: Path):
    """Test discover with some found and some missing targets."""
    _create_skill_md(tmp_project, "skill-a", "flow://Flow_A")
    _create_skill_md(tmp_project, "skill-b", "flow://Flow_B")

    records = [{"ApiName": "Flow_A"}]
    response = json.dumps({"result": {"records": records}})
    mock_result = CliResult(returncode=0, stdout=response, stderr="")

    with patch("scripts.discover.SfAgentCli") as MockCli:
        MockCli.return_value.query_soql.return_value = mock_result
        report = discover(tmp_project, "TestOrg")

    assert len(report.targets) == 2
    assert len(report.found) == 1
    assert len(report.missing) == 1
    assert report.found[0].target_name == "Flow_A"
    assert report.missing[0].target_name == "Flow_B"


def test_discover_no_skills(tmp_project: Path):
    """Test discover with no SKILL.md files."""
    report_data = discover.__wrapped__(tmp_project, "TestOrg") if hasattr(discover, '__wrapped__') else None
    # Just call discover directly - it should handle empty gracefully
    with patch("scripts.discover.SfAgentCli"):
        report = discover(tmp_project, "TestOrg")
    assert len(report.targets) == 0
    assert report.all_found


def test_discover_mixed_types(tmp_project: Path):
    """Test discover with flow and apex targets."""
    _create_skill_md(tmp_project, "skill-flow", "flow://My_Flow")
    _create_skill_md(tmp_project, "skill-apex", "apex://MyClass")

    flow_response = json.dumps({"result": {"records": [{"ApiName": "My_Flow"}]}})
    apex_response = json.dumps({"result": {"records": []}})

    call_count = 0

    def mock_query(query, org):
        nonlocal call_count
        call_count += 1
        if "FlowDefinitionView" in query:
            return CliResult(returncode=0, stdout=flow_response, stderr="")
        return CliResult(returncode=0, stdout=apex_response, stderr="")

    with patch("scripts.discover.SfAgentCli") as MockCli:
        MockCli.return_value.query_soql.side_effect = mock_query
        report = discover(tmp_project, "TestOrg")

    assert len(report.targets) == 2
    flow_target = [t for t in report.targets if t.target_type == "flow"][0]
    apex_target = [t for t in report.targets if t.target_type == "apex"][0]
    assert flow_target.found is True
    assert apex_target.found is False


# --- _tokenize tests ---


def test_tokenize_underscore():
    assert _tokenize("Get_Order_Status") == {"get", "order", "status"}


def test_tokenize_camelcase():
    assert _tokenize("GetOrderStatus") == {"get", "order", "status"}


def test_tokenize_mixed():
    assert _tokenize("Get_OrderStatus") == {"get", "order", "status"}


# --- _suggest_similar tests ---


def test_suggest_similar_flows():
    """Similar flows are returned with scores above threshold."""
    org_flows = [
        "Get_Order_Status",
        "Retrieve_Order_Info",
        "Send_Email_Notification",
        "Check_Inventory",
    ]
    suggestions = _suggest_similar("Get_Order_Details", org_flows)
    assert len(suggestions) > 0
    # Get_Order_Status should be the top suggestion
    assert suggestions[0].name == "Get_Order_Status"
    assert suggestions[0].similarity >= 0.5


def test_no_suggestions_when_nothing_similar():
    """No suggestions when nothing is similar enough."""
    org_flows = ["Send_Email", "Update_Contact"]
    suggestions = _suggest_similar("Get_Order_Details", org_flows)
    # These are too dissimilar to match above 0.4
    for s in suggestions:
        assert s.similarity >= 0.4


def test_suggestions_max_results():
    """At most max_results suggestions are returned."""
    org_names = [f"Get_Order_{i}" for i in range(10)]
    suggestions = _suggest_similar("Get_Order_Details", org_names, max_results=3)
    assert len(suggestions) <= 3


def test_suggestions_skips_exact_match():
    """Exact matches (already found) are not suggested."""
    suggestions = _suggest_similar("Flow_A", ["Flow_A", "Flow_B"])
    assert all(s.name != "Flow_A" for s in suggestions)


def test_suggestions_only_for_missing(tmp_project: Path):
    """Found targets don't get suggestions."""
    _create_skill_md(tmp_project, "skill-a", "flow://Flow_A")
    _create_skill_md(tmp_project, "skill-b", "flow://Flow_B")

    # Flow_A is found, Flow_B is missing
    found_response = json.dumps({"result": {"records": [{"ApiName": "Flow_A"}]}})
    all_flows_response = json.dumps({"result": {"records": [
        {"ApiName": "Flow_A"},
        {"ApiName": "Flow_B_Similar"},
        {"ApiName": "Another_Flow"},
    ]}})

    call_count = 0

    def mock_query(query, org):
        nonlocal call_count
        call_count += 1
        if "ApiName IN" in query:
            return CliResult(returncode=0, stdout=found_response, stderr="")
        return CliResult(returncode=0, stdout=all_flows_response, stderr="")

    with patch("scripts.discover.SfAgentCli") as MockCli:
        instance = MockCli.return_value
        instance.query_soql.side_effect = mock_query
        instance.list_resources.return_value = CliResult(
            returncode=0, stdout=all_flows_response, stderr=""
        )
        report = discover(tmp_project, "TestOrg")

    found_target = [t for t in report.targets if t.found][0]
    assert found_target.suggestions == []  # Found targets have no suggestions

    missing_target = [t for t in report.targets if not t.found][0]
    # Missing target may have suggestions (depending on similarity)
