"""Query org for SObject field definitions and match to SKILL.md inputs/outputs."""

from __future__ import annotations

import difflib
import json
import logging
import re
from dataclasses import dataclass, field

from .deploy.sf_cli import SfAgentCli
from .ir.models import ActionInput, ActionOutput

logger = logging.getLogger(__name__)


@dataclass
class FieldInfo:
    """A single field from an SObject describe."""
    name: str           # API name (e.g., "State__c")
    label: str          # Label (e.g., "State")
    data_type: str      # Salesforce type (e.g., "Text", "Currency")
    filterable: bool    # Can be used in WHERE clause


@dataclass
class FieldMapping:
    """Mapping between SKILL.md inputs/outputs and SObject fields."""
    input_mappings: dict[str, str] = field(default_factory=dict)   # input_name -> field_name
    output_mappings: dict[str, str] = field(default_factory=dict)  # output_name -> field_name
    select_fields: list[str] = field(default_factory=list)         # fields for SELECT clause
    where_fields: list[str] = field(default_factory=list)          # fields for WHERE clause


def describe_sobject(
    object_name: str,
    target_org: str,
    cli: SfAgentCli | None = None,
) -> list[FieldInfo]:
    """Query the org for an SObject's field definitions.

    Args:
        object_name: SObject API name (e.g., "Property__c").
        target_org: Target org username or alias.
        cli: Optional SfAgentCli instance (created if not provided).

    Returns:
        List of FieldInfo for the object's fields.
    """
    if cli is None:
        cli = SfAgentCli()

    soql = (
        "SELECT QualifiedApiName, Label, DataType, IsApiFilterable "
        "FROM FieldDefinition "
        f"WHERE EntityDefinition.QualifiedApiName = '{object_name}'"
    )
    result = cli.query_soql(soql, target_org)

    fields: list[FieldInfo] = []
    if result.returncode != 0:
        # Try to extract a useful error message
        error_detail = result.stderr.strip()
        if not error_detail:
            try:
                err_data = json.loads(result.stdout)
                error_detail = err_data.get("message", "").strip()
            except (json.JSONDecodeError, AttributeError):
                pass
        if not error_detail:
            error_detail = f"SObject '{object_name}' may not exist in the org"
        logger.warning("Failed to describe %s: %s", object_name, error_detail)
        return fields

    try:
        data = json.loads(result.stdout)
        records = data.get("result", {}).get("records", [])
        for record in records:
            fields.append(FieldInfo(
                name=record.get("QualifiedApiName", ""),
                label=record.get("Label", ""),
                data_type=record.get("DataType", ""),
                filterable=record.get("IsApiFilterable", False),
            ))
    except (json.JSONDecodeError, KeyError):
        logger.warning("Could not parse describe response for %s", object_name)

    return fields


def _normalize(name: str) -> str:
    """Normalize a name for comparison.

    Removes __c suffix, lowercases, replaces underscores with spaces.
    Also splits camelCase into separate words.
    """
    # Remove __c suffix
    name = re.sub(r'__c$', '', name, flags=re.IGNORECASE)
    # Split camelCase
    name = re.sub(r'([a-z])([A-Z])', r'\1 \2', name)
    # Replace underscores with spaces, lowercase
    return name.replace("_", " ").lower().strip()


def match_fields(
    inputs: list[ActionInput],
    outputs: list[ActionOutput],
    fields: list[FieldInfo],
) -> FieldMapping:
    """Match SKILL.md inputs/outputs to SObject fields by normalized name similarity.

    Inputs are matched only to filterable fields (for WHERE clause).
    Outputs are matched to any fields (for SELECT clause).

    Args:
        inputs: Action input definitions from SKILL.md.
        outputs: Action output definitions from SKILL.md.
        fields: SObject field definitions from the org.

    Returns:
        FieldMapping with input->field and output->field mappings.
    """
    mapping = FieldMapping()

    # Build lookup of normalized field names
    filterable_fields = {_normalize(f.name): f for f in fields if f.filterable}
    all_fields = {_normalize(f.name): f for f in fields}

    # Match inputs to filterable fields
    for inp in inputs:
        matched = _find_best_match(inp.name, filterable_fields)
        if matched:
            mapping.input_mappings[inp.name] = matched.name
            mapping.where_fields.append(matched.name)

    # Match outputs to any fields
    for out in outputs:
        matched = _find_best_match(out.name, all_fields)
        if matched:
            mapping.output_mappings[out.name] = matched.name
            mapping.select_fields.append(matched.name)

    # Always include Name in select if available and not already there
    name_fields = [f for f in fields if f.name == "Name"]
    if name_fields and "Name" not in mapping.select_fields:
        mapping.select_fields.insert(0, "Name")

    return mapping


def _find_best_match(
    input_name: str,
    field_lookup: dict[str, FieldInfo],
    threshold: float = 0.5,
) -> FieldInfo | None:
    """Find the best matching field for an input/output name.

    First tries exact normalized match, then falls back to fuzzy matching.
    """
    normalized_input = _normalize(input_name)

    # Exact normalized match
    if normalized_input in field_lookup:
        return field_lookup[normalized_input]

    # Fuzzy match
    best_score = 0.0
    best_field: FieldInfo | None = None
    for norm_name, field_info in field_lookup.items():
        score = difflib.SequenceMatcher(None, normalized_input, norm_name).ratio()
        if score > best_score and score >= threshold:
            best_score = score
            best_field = field_info

    return best_field
