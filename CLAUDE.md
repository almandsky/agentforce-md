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

## Running

```bash
# Activate venv
source .venv/bin/activate

# Convert a template
python -m scripts.cli convert --project-root templates/multi-topic --agent-name AcmeAgent

# Discover which SKILL.md targets exist in an org
python -m scripts.cli discover --project-root templates/multi-topic -o MyOrg

# Generate metadata stubs for missing targets
python -m scripts.cli scaffold --project-root templates/multi-topic -o MyOrg

# Execute a single action against a live org
python -m scripts.cli run --skill templates/multi-topic/.claude/skills/check-order-status/SKILL.md -o MyOrg --input '{"order_number":"12345"}' --dry-run

# Run tests
python -m pytest tests/ -v
```

## Key conventions

- Agent Script uses 4-space indentation
- Booleans are `True`/`False` (capitalized)
- Sub-agent names are kebab-case in filenames, snake_case in .agent output
- Tools without SKILL.md targets generate action stubs with `# TODO` comments
- Service agents automatically get linked variables (EndUserId, RoutableId, ContactId)
