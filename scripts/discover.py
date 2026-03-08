"""Discover org metadata matching SKILL.md targets."""

from __future__ import annotations

import difflib
import json
import logging
from dataclasses import dataclass, field
from pathlib import Path

from .deploy.sf_cli import SfAgentCli
from .ir.models import ActionDefinition
from .parser.skill_md import discover_skills, parse_skill_md

logger = logging.getLogger(__name__)


@dataclass
class Suggestion:
    """A similar resource found in the org."""
    name: str
    similarity: float  # 0.0 to 1.0


@dataclass
class TargetStatus:
    """Status of a single SKILL.md target in the org."""
    skill_name: str       # e.g. "check-order-status"
    target: str           # e.g. "flow://Get_Order_Status"
    target_type: str      # "flow", "apex", "retriever"
    target_name: str      # "Get_Order_Status"
    found: bool
    details: str          # org metadata match info or "not found"
    suggestions: list[Suggestion] = field(default_factory=list)


@dataclass
class DiscoveryReport:
    """Report of all SKILL.md targets and their org status."""
    targets: list[TargetStatus] = field(default_factory=list)

    @property
    def found(self) -> list[TargetStatus]:
        return [t for t in self.targets if t.found]

    @property
    def missing(self) -> list[TargetStatus]:
        return [t for t in self.targets if not t.found]

    @property
    def all_found(self) -> bool:
        return len(self.missing) == 0


def discover(project_root: Path, target_org: str) -> DiscoveryReport:
    """Discover org resources matching SKILL.md targets.

    Args:
        project_root: Root of the Claude Code project.
        target_org: Target org username or alias.

    Returns:
        DiscoveryReport with status of each target.
    """
    cli = SfAgentCli()

    # 1. Find all SKILL.md files and parse them
    skill_paths = discover_skills(project_root)
    actions: list[tuple[str, ActionDefinition]] = []
    for sk_path in skill_paths:
        action_def = parse_skill_md(sk_path)
        if action_def and action_def.target:
            actions.append((sk_path.parent.name, action_def))

    if not actions:
        logger.info("No SKILL.md files with targets found")
        return DiscoveryReport()

    # 2. Group targets by type
    flow_targets: dict[str, str] = {}    # target_name -> skill_name
    apex_targets: dict[str, str] = {}
    retriever_targets: dict[str, str] = {}

    for skill_name, action_def in actions:
        target_type, target_name = _parse_target(action_def.target)
        if target_type == "flow":
            flow_targets[target_name] = skill_name
        elif target_type == "apex":
            apex_targets[target_name] = skill_name
        elif target_type == "retriever":
            retriever_targets[target_name] = skill_name

    # 3. Query org for each type
    flow_results = _check_flows(list(flow_targets.keys()), cli, target_org) if flow_targets else {}
    apex_results = _check_apex(list(apex_targets.keys()), cli, target_org) if apex_targets else {}
    retriever_results = _check_retrievers(list(retriever_targets.keys()), cli, target_org) if retriever_targets else {}

    # 4. Build report
    report = DiscoveryReport()

    # Track which types have missing targets (for lazy broad queries)
    missing_types: set[str] = set()

    for target_name, skill_name in flow_targets.items():
        found = flow_results.get(target_name, False)
        if not found:
            missing_types.add("flow")
        report.targets.append(TargetStatus(
            skill_name=skill_name,
            target=f"flow://{target_name}",
            target_type="flow",
            target_name=target_name,
            found=found,
            details="Found in FlowDefinitionView" if found else "Not found",
        ))

    for target_name, skill_name in apex_targets.items():
        found = apex_results.get(target_name, False)
        if not found:
            missing_types.add("apex")
        report.targets.append(TargetStatus(
            skill_name=skill_name,
            target=f"apex://{target_name}",
            target_type="apex",
            target_name=target_name,
            found=found,
            details="Found in ApexClass" if found else "Not found",
        ))

    for target_name, skill_name in retriever_targets.items():
        found = retriever_results.get(target_name, False)
        if not found:
            missing_types.add("retriever")
        report.targets.append(TargetStatus(
            skill_name=skill_name,
            target=f"retriever://{target_name}",
            target_type="retriever",
            target_name=target_name,
            found=found,
            details="Found in org" if found else "Not found",
        ))

    # 5. For missing targets, fetch all resources and suggest similar ones
    if missing_types:
        all_resources = _fetch_all_resources(missing_types, cli, target_org)
        for ts in report.missing:
            org_names = all_resources.get(ts.target_type, [])
            ts.suggestions = _suggest_similar(ts.target_name, org_names)

    return report


def _parse_target(target: str) -> tuple[str, str]:
    """Parse 'flow://Name' into ('flow', 'Name').

    Supported schemes: flow://, apex://, retriever://
    """
    if "://" in target:
        scheme, name = target.split("://", 1)
        return scheme.lower(), name
    # Fallback: treat as flow
    return "flow", target


def _check_flows(names: list[str], cli: SfAgentCli, org: str) -> dict[str, bool]:
    """Query FlowDefinitionView for flow names."""
    quoted = ", ".join(f"'{n}'" for n in names)
    query = f"SELECT ApiName FROM FlowDefinitionView WHERE ApiName IN ({quoted})"
    result = cli.query_soql(query, org)
    return _extract_names(result, "ApiName", names)


def _check_apex(names: list[str], cli: SfAgentCli, org: str) -> dict[str, bool]:
    """Query ApexClass for class names."""
    quoted = ", ".join(f"'{n}'" for n in names)
    query = f"SELECT Name FROM ApexClass WHERE Name IN ({quoted})"
    result = cli.query_soql(query, org)
    return _extract_names(result, "Name", names)


def _check_retrievers(names: list[str], cli: SfAgentCli, org: str) -> dict[str, bool]:
    """Query for knowledge base / prompt template resources."""
    quoted = ", ".join(f"'{n}'" for n in names)
    query = f"SELECT DeveloperName FROM GenAiPromptTemplate WHERE DeveloperName IN ({quoted})"
    result = cli.query_soql(query, org)
    return _extract_names(result, "DeveloperName", names)


def _extract_names(result, field_name: str, expected: list[str]) -> dict[str, bool]:
    """Parse SOQL query results into a found/not-found dict."""
    found_names: set[str] = set()
    if result.returncode == 0 and result.stdout:
        try:
            data = json.loads(result.stdout)
            records = data.get("result", {}).get("records", [])
            for record in records:
                name = record.get(field_name)
                if name:
                    found_names.add(name)
        except (json.JSONDecodeError, KeyError):
            logger.warning("Could not parse SOQL response")

    return {name: name in found_names for name in expected}


def _extract_all_names(result, field_name: str) -> list[str]:
    """Parse SOQL query results into a list of names."""
    names: list[str] = []
    if result.returncode == 0 and result.stdout:
        try:
            data = json.loads(result.stdout)
            records = data.get("result", {}).get("records", [])
            for record in records:
                name = record.get(field_name)
                if name:
                    names.append(name)
        except (json.JSONDecodeError, KeyError):
            logger.warning("Could not parse SOQL response for resource listing")
    return names


def _fetch_all_resources(
    types: set[str],
    cli: SfAgentCli,
    org: str,
) -> dict[str, list[str]]:
    """Fetch all resource names from the org for given types (cached per call)."""
    field_map = {
        "flow": "ApiName",
        "apex": "Name",
        "retriever": "DeveloperName",
    }
    resources: dict[str, list[str]] = {}
    for rtype in types:
        field_name = field_map.get(rtype)
        if not field_name:
            continue
        result = cli.list_resources(rtype, org)
        resources[rtype] = _extract_all_names(result, field_name)
    return resources


def _tokenize(name: str) -> set[str]:
    """Split a name into lowercase tokens on underscores and camelCase boundaries."""
    # First split on underscores
    parts: list[str] = []
    for segment in name.split("_"):
        # Split camelCase: insert boundary before uppercase letters
        current = []
        for ch in segment:
            if ch.isupper() and current:
                parts.append("".join(current).lower())
                current = [ch]
            else:
                current.append(ch)
        if current:
            parts.append("".join(current).lower())
    return set(parts)


def _suggest_similar(
    target_name: str,
    org_names: list[str],
    max_results: int = 3,
    threshold: float = 0.4,
) -> list[Suggestion]:
    """Find similar resource names using sequence matching + keyword overlap.

    Scoring combines:
    - difflib.SequenceMatcher ratio (string similarity)
    - Keyword overlap: shared tokens / total unique tokens (Jaccard index)
    Final score = max(sequence_ratio, keyword_overlap)
    """
    if not org_names:
        return []

    target_tokens = _tokenize(target_name)
    scored: list[tuple[str, float]] = []

    for org_name in org_names:
        # Skip exact match (already found)
        if org_name == target_name:
            continue

        # Sequence similarity
        seq_ratio = difflib.SequenceMatcher(
            None, target_name.lower(), org_name.lower()
        ).ratio()

        # Keyword overlap (Jaccard)
        org_tokens = _tokenize(org_name)
        union = target_tokens | org_tokens
        overlap = len(target_tokens & org_tokens) / len(union) if union else 0.0

        score = max(seq_ratio, overlap)
        if score >= threshold:
            scored.append((org_name, round(score, 2)))

    # Sort by score descending, take top N
    scored.sort(key=lambda x: x[1], reverse=True)
    return [Suggestion(name=name, similarity=sim) for name, sim in scored[:max_results]]
