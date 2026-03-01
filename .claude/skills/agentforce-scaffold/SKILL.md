---
name: agentforce-scaffold
description: Generate stub metadata (Flow XML, Apex classes) for SKILL.md targets missing from the org
allowed-tools: Bash Read Write Glob
argument-hint: "<org-alias> [--project-root <path>] [--output-dir <path>] [--skip-discover]"
---

# Agentforce Scaffold

Generate stub metadata files for SKILL.md targets that don't exist in the org.

## Usage

```bash
# Discover missing targets and generate stubs
~/.claude/agentforce-md/bin/agentforce-md scaffold --project-root <path> -o <org-alias>

# Scaffold all targets without checking the org
~/.claude/agentforce-md/bin/agentforce-md scaffold --project-root <path> -o <org-alias> --skip-discover

# Specify output directory
~/.claude/agentforce-md/bin/agentforce-md scaffold --project-root <path> -o <org-alias> --output-dir ./force-app/main/default
```

## What it does

1. Runs `discover` to find targets missing from the org (unless `--skip-discover`)
2. For each missing target:
   - `flow://Name` -> generates `flows/Name.flow-meta.xml` with input/output variables from SKILL.md
   - `apex://Name` -> generates `classes/Name.cls` + `classes/Name.cls-meta.xml` with @InvocableMethod stub
3. Generated stubs include placeholder logic (Assignment elements for flows, TODO comments for Apex)

## Output

List of generated files under `force-app/main/default/` (or `--output-dir`).

## Next steps

1. Review generated stubs and fill in business logic
2. Deploy to org: `sf project deploy start --source-dir force-app/main/default -o <org>`
3. Re-run discover to confirm targets are now found
