---
name: agentforce-discover
description: Check which SKILL.md targets (flows, apex classes, retrievers) exist in a Salesforce org
allowed-tools: Bash Read Glob
argument-hint: "<org-alias> [--project-root <path>]"
---

# Agentforce Discover

Validate that SKILL.md targets actually exist in a Salesforce org.

## Usage

Run the discover command against a target org:

```bash
python3 -m scripts.cli discover --project-root <path> -o <org-alias>
```

## What it does

1. Finds all SKILL.md files in the project's `.claude/skills/` directory
2. Extracts `agentforce: target:` values (e.g. `flow://Get_Order_Status`, `apex://MyClass`)
3. Queries the Salesforce org to check if each target exists
4. Outputs a table showing found/missing status for each target

## Output

A table with columns: Skill | Target | Status (found/MISSING)

Exit code 0 if all targets found, 1 if any are missing.

## Next steps

If targets are missing, suggest running `scaffold` to generate stub metadata:

```bash
python3 -m scripts.cli scaffold --project-root <path> -o <org-alias>
```
