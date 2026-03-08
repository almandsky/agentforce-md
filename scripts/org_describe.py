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


# Output name patterns that are computed (not direct SObject fields).
# These should be handled by the generator's unmapped-output heuristics.
_COMPUTED_SUFFIXES = ("_json", "_list", "_xml", "_csv")
_COMPUTED_PATTERNS = ("total_count", "result_count", "record_count", "error_message")


def _is_computed_output(name: str) -> bool:
    """Check if an output name looks like a computed value rather than a field."""
    lower = name.lower()
    if any(lower.endswith(s) for s in _COMPUTED_SUFFIXES):
        return True
    if lower in _COMPUTED_PATTERNS:
        return True
    return False


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

    # Build field lists by filterability
    filterable = [f for f in fields if f.filterable]
    all_fields_list = fields

    # Match inputs to filterable fields
    for inp in inputs:
        matched = _find_best_match(inp.name, filterable)
        if matched:
            mapping.input_mappings[inp.name] = matched.name
            mapping.where_fields.append(matched.name)

    # Match outputs to any fields (skip computed-output patterns)
    for out in outputs:
        if _is_computed_output(out.name):
            continue
        matched = _find_best_match(out.name, all_fields_list)
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
    fields: list[FieldInfo] | dict[str, FieldInfo],
    threshold: float = 0.6,
) -> FieldInfo | None:
    """Find the best matching field for an input/output name.

    Matches against both API name and label for better accuracy.
    First tries exact normalized match, then falls back to fuzzy matching.

    Accepts either a list of FieldInfo or a dict (normalized_name -> FieldInfo)
    for backward compatibility.
    """
    normalized_input = _normalize(input_name)

    # Support both list and dict inputs
    if isinstance(fields, dict):
        field_list = list(fields.values())
        # Exact match against dict keys
        if normalized_input in fields:
            return fields[normalized_input]
    else:
        field_list = fields

    # Exact normalized match against API name or label
    for fi in field_list:
        if _normalize(fi.name) == normalized_input:
            return fi
        if fi.label and fi.label.lower().replace(" ", " ") == normalized_input:
            return fi

    # Fuzzy match — check API name, label, and word containment
    best_score = 0.0
    best_field: FieldInfo | None = None
    for fi in field_list:
        norm_name = _normalize(fi.name)
        norm_label = fi.label.lower() if fi.label else ""

        # Sequence similarity against API name and label
        name_score = difflib.SequenceMatcher(
            None, normalized_input, norm_name,
        ).ratio()
        label_score = difflib.SequenceMatcher(
            None, normalized_input, norm_label,
        ).ratio() if norm_label else 0.0

        # Word containment bonus: if the input appears as a complete word
        # in the field name or label, boost the score significantly.
        # This makes "state" prefer "BillingState" over "Site".
        name_words = norm_name.split()
        label_words = norm_label.split()
        input_words = normalized_input.split()
        if any(w in name_words for w in input_words):
            name_score = max(name_score, 0.8)
        if any(w in label_words for w in input_words):
            label_score = max(label_score, 0.8)

        score = max(name_score, label_score)
        if score > best_score and score >= threshold:
            best_score = score
            best_field = fi

    return best_field
