---
name: agentforce-run
description: Execute a SKILL.md action against a live Salesforce org via REST API
allowed-tools: Bash Read Glob
argument-hint: "<skill-path> -o <org-alias> --input '{\"key\":\"val\"}' [--dry-run]"
---

# Agentforce Run

Execute individual SKILL.md actions against a live Salesforce org without deploying the full agent.

## Usage

```bash
# Run an action with inputs
python3 -m scripts.cli run \
  --skill .claude/skills/check-order-status/SKILL.md \
  -o <org-alias> \
  --input '{"order_number":"12345"}'

# Dry run — show what would be called
python3 -m scripts.cli run \
  --skill .claude/skills/check-order-status/SKILL.md \
  -o <org-alias> \
  --input '{"order_number":"12345"}' \
  --dry-run

# You can also pass a skill directory (SKILL.md is appended automatically)
python3 -m scripts.cli run \
  --skill .claude/skills/check-order-status \
  -o <org-alias> \
  --input '{"order_number":"12345"}'
```

## What it does

1. Parses the SKILL.md to get the target and input/output definitions
2. Validates provided inputs against expected inputs
3. Routes based on target type:
   - `flow://Name` -> invokes via `/services/data/v63.0/actions/custom/flow/Name`
   - `apex://Name` -> invokes via `/services/data/v63.0/actions/custom/apex/Name`
4. Returns the action result (success/failure + output values)

## Output

- **Success**: prints output key-value pairs
- **Failure**: prints error message and raw API response
- **Dry run**: prints the invocation plan (target, inputs, org) as JSON
