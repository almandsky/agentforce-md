This is the agentforce-md project: a converter from Claude Code markdown conventions to Agentforce Agent Script (.agent) files.

## Project structure

- `scripts/` — Python package with the converter
  - `scripts/ir/` — Intermediate representation (dataclasses)
  - `scripts/parser/` — Parsers for CLAUDE.md, sub-agent .md, SKILL.md
  - `scripts/generator/` — Agent Script file generator
  - `scripts/deploy/` — Salesforce CLI wrapper
  - `scripts/convert.py` — Main orchestrator
  - `scripts/cli.py` — CLI entry point
- `templates/` — Starter templates (hello-world, multi-topic, verification-gate)
- `tests/` — pytest test suite
- `notes/` — Research and reference docs

## Global installation

Skills can be installed globally so they're available in any project:

```bash
# From a local clone
python3 tools/install.py

# Or from GitHub
curl -sSL https://raw.githubusercontent.com/almandsky/agentforce-md/main/tools/install.sh | bash
```

This installs to `~/.claude/agentforce-md/` with a bundled venv. Skills are copied to `~/.claude/skills/agentforce-*/`. Installs side-by-side with sf-skills (no collisions).

## Running (after installation)

```bash
# Convert a template
~/.claude/agentforce-md/bin/agentforce-md convert --project-root templates/multi-topic --agent-name AcmeAgent

# Discover which SKILL.md targets exist in an org
~/.claude/agentforce-md/bin/agentforce-md discover --project-root templates/multi-topic -o MyOrg

# Generate metadata stubs for missing targets
~/.claude/agentforce-md/bin/agentforce-md scaffold --project-root templates/multi-topic -o MyOrg

# Execute a single action against a live org
~/.claude/agentforce-md/bin/agentforce-md run --skill templates/multi-topic/.claude/skills/check-order-status/SKILL.md -o MyOrg --input '{"order_number":"12345"}' --dry-run
```

## Development (contributing)

```bash
# Set up local venv for running tests
python3 -m venv .venv && source .venv/bin/activate && pip install pyyaml pytest

# Run tests
python -m pytest tests/ -v

# Install from local clone (reflects your changes)
python3 tools/install.py --force
```

## Key conventions

- Agent Script uses 4-space indentation
- Booleans are `True`/`False` (capitalized)
- Sub-agent names are kebab-case in filenames, snake_case in .agent output
- Tools without SKILL.md targets generate action stubs with `# TODO` comments
- Service agents automatically get linked variables (EndUserId, RoutableId, ContactId)
