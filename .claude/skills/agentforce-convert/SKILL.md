---
name: agentforce-convert
description: Convert Claude Code markdown conventions to Agentforce Agent Script (.agent) files, or deploy an existing agent bundle
allowed-tools: Bash Read Write Edit Glob
argument-hint: "[prompt describing your agent] | convert | deploy <org> | init <template>"
---

# Agentforce Markdown-to-Agent-Script Converter

You are an orchestration skill that converts Claude Code markdown conventions into Agentforce Agent Script (.agent) files and optionally deploys them.

## Routing

Determine the user's intent from their input:

1. **Full round-trip** (user provides a prompt describing an agent):
   - Generate CLAUDE.md + .claude/agents/*.md files from the prompt
   - Run the Python converter
   - Show the generated .agent file for review
   - Deploy on user approval

2. **Convert only** (input is "convert" or user has existing markdown):
   - Run `python3 -m scripts.cli convert --project-root . --agent-name <AgentName>`
   - Show the output .agent file

3. **Deploy only** (input starts with "deploy"):
   - Run `python3 -m scripts.cli deploy --api-name <Name> -o <Org>`

4. **Init template** (input starts with "init"):
   - Run `python3 -m scripts.cli init --template <template-name>`

## Full Round-Trip Workflow

When the user describes an agent they want to build:

### Step 1: Generate markdown files

Create a CLAUDE.md at the project root with:
- The agent's persona and global instructions
- Company context if provided

For each distinct topic/capability the agent should have, create a sub-agent file at `.claude/agents/<topic-name>.md` with:
```yaml
---
name: <topic-name>
description: <what this topic handles>
tools: <comma-separated tool names if any>
---
<Scope: what this topic does>
<Instruction lines: how to handle requests>
```

### Step 2: Run the converter

```bash
python3 -m scripts.cli convert --project-root . --agent-name <AgentName> --agent-type AgentforceServiceAgent
```

### Step 3: Review

Read the generated .agent file and display it to the user. Ask for feedback.

### Step 4: Deploy (if approved)

```bash
python3 -m scripts.cli deploy --api-name <AgentName> -o <TargetOrg>
```

## Conventions

- Agent names should be PascalCase (e.g., AcmeAgent, OrderBot)
- Topic names should be kebab-case in filenames (e.g., order-support.md)
- Each distinct responsibility should be its own sub-agent/topic
- Keep instruction lines concise and actionable
- Tools without a corresponding SKILL.md will generate stub action definitions
