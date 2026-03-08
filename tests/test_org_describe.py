"""Tests for the org_describe module."""

from __future__ import annotations

import json
from unittest.mock import MagicMock

from scripts.deploy.sf_cli import CliResult
from scripts.ir.models import ActionInput, ActionOutput
from scripts.org_describe import (
    FieldInfo,
    FieldMapping,
    _find_best_match,
    _normalize,
    describe_sobject,
    match_fields,
)


# --- _normalize tests ---


def test_normalize_removes_custom_suffix():
    assert _normalize("State__c") == "state"


def test_normalize_splits_camelcase():
    assert _normalize("OrderNumber") == "order number"


def test_normalize_replaces_underscores():
    assert _normalize("Order_Number") == "order number"


def test_normalize_combined():
    assert _normalize("Order_Number__c") == "order number"


# --- describe_sobject tests ---


def _mock_describe_response(fields: list[dict]) -> CliResult:
    response = json.dumps({"result": {"records": fields}})
    return CliResult(returncode=0, stdout=response, stderr="")


def test_describe_sobject_parses_fields():
    cli = MagicMock()
    cli.query_soql.return_value = _mock_describe_response([
        {
            "QualifiedApiName": "State__c",
            "Label": "State",
            "DataType": "Text",
            "IsApiFilterable": True,
        },
        {
            "QualifiedApiName": "Price__c",
            "Label": "Price",
            "DataType": "Currency",
            "IsApiFilterable": True,
        },
        {
            "QualifiedApiName": "Description__c",
            "Label": "Description",
            "DataType": "LongTextArea",
            "IsApiFilterable": False,
        },
    ])

    fields = describe_sobject("Property__c", "TestOrg", cli=cli)
    assert len(fields) == 3
    assert fields[0].name == "State__c"
    assert fields[0].filterable is True
    assert fields[2].filterable is False


def test_describe_sobject_handles_error():
    cli = MagicMock()
    cli.query_soql.return_value = CliResult(returncode=1, stdout="", stderr="error")

    fields = describe_sobject("Nonexistent__c", "TestOrg", cli=cli)
    assert fields == []


def test_describe_sobject_handles_bad_json():
    cli = MagicMock()
    cli.query_soql.return_value = CliResult(returncode=0, stdout="not json", stderr="")

    fields = describe_sobject("Obj__c", "TestOrg", cli=cli)
    assert fields == []


# --- match_fields tests ---


def _sample_fields() -> list[FieldInfo]:
    return [
        FieldInfo(name="Name", label="Name", data_type="Text", filterable=True),
        FieldInfo(name="State__c", label="State", data_type="Text", filterable=True),
        FieldInfo(name="Price__c", label="Price", data_type="Currency", filterable=True),
        FieldInfo(name="Bedrooms__c", label="Bedrooms", data_type="Number", filterable=True),
        FieldInfo(name="Description__c", label="Description", data_type="LongTextArea", filterable=False),
    ]


def test_match_fields_exact_normalized():
    """Inputs/outputs with matching normalized names are mapped."""
    inputs = [ActionInput(name="state", input_type="string")]
    outputs = [ActionOutput(name="price", output_type="number")]
    fields = _sample_fields()

    mapping = match_fields(inputs, outputs, fields)

    assert "state" in mapping.input_mappings
    assert mapping.input_mappings["state"] == "State__c"
    assert "State__c" in mapping.where_fields

    assert "price" in mapping.output_mappings
    assert mapping.output_mappings["price"] == "Price__c"
    assert "Price__c" in mapping.select_fields


def test_match_fields_includes_name():
    """Name field is auto-included in select if available."""
    inputs = [ActionInput(name="state", input_type="string")]
    outputs = [ActionOutput(name="price", output_type="number")]
    fields = _sample_fields()

    mapping = match_fields(inputs, outputs, fields)

    assert "Name" in mapping.select_fields


def test_match_fields_inputs_only_filterable():
    """Inputs are only matched to filterable fields."""
    inputs = [ActionInput(name="description", input_type="string")]
    outputs = []
    fields = _sample_fields()

    mapping = match_fields(inputs, outputs, fields)

    # Description__c is not filterable, so no input mapping
    assert "description" not in mapping.input_mappings


def test_match_fields_outputs_any_field():
    """Outputs can match any field including non-filterable."""
    inputs = []
    outputs = [ActionOutput(name="description", output_type="string")]
    fields = _sample_fields()

    mapping = match_fields(inputs, outputs, fields)

    assert "description" in mapping.output_mappings
    assert mapping.output_mappings["description"] == "Description__c"


def test_match_fields_no_matches():
    """No mappings when names are too different."""
    inputs = [ActionInput(name="zzz_unrelated", input_type="string")]
    outputs = [ActionOutput(name="xyz_other", output_type="string")]
    fields = _sample_fields()

    mapping = match_fields(inputs, outputs, fields)

    assert len(mapping.input_mappings) == 0
    assert len(mapping.output_mappings) == 0


def test_match_fields_fuzzy_matching():
    """Fuzzy matching finds close-but-not-exact matches."""
    inputs = [ActionInput(name="order_number", input_type="string")]
    fields = [
        FieldInfo(name="OrderNumber__c", label="Order Number", data_type="Text", filterable=True),
    ]

    mapping = match_fields(inputs, [], fields)

    assert "order_number" in mapping.input_mappings
    assert mapping.input_mappings["order_number"] == "OrderNumber__c"


# --- _find_best_match tests ---


def test_find_best_match_exact():
    lookup = {_normalize("State__c"): FieldInfo("State__c", "State", "Text", True)}
    result = _find_best_match("state", lookup)
    assert result is not None
    assert result.name == "State__c"


def test_find_best_match_no_match():
    lookup = {_normalize("State__c"): FieldInfo("State__c", "State", "Text", True)}
    result = _find_best_match("completely_unrelated_xyz", lookup)
    assert result is None
