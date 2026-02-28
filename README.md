# agentforce-md

Convert Claude Code markdown conventions into Agentforce Agent Script (`.agent`) files for deployment to Salesforce orgs.

## What it does

Developers using Claude Code write agent behavior as plain markdown files — `CLAUDE.md` for global instructions, sub-agent `.md` files for topics, and `SKILL.md` files for actions. This tool converts those markdown files into Salesforce's Agent Script DSL format (a single `.agent` file), ready for deployment via `sf agent publish authoring-bundle`.

```
CLAUDE.md + .claude/agents/*.md + .claude/skills/*/SKILL.md
                        │
                        ▼
              ┌─────────────────┐
              │  agentforce-md  │
              │  convert        │
              └────────┬────────┘
                       │
                       ▼
       force-app/main/default/aiAuthoringBundles/
         AgentName/
           AgentName.agent            ← Agent Script DSL
           AgentName.bundle-meta.xml  ← Required metadata
                       │
                       ▼
              sf agent publish authoring-bundle
```

## How it works

The converter runs a four-stage pipeline:

### 1. Parse

Each input file type has a dedicated parser:

| Input file | Parser | What it extracts |
|---|---|---|
| `CLAUDE.md` | `scripts/parser/claude_md.py` | System-level instructions (the agent's persona) |
| `.claude/agents/*.md` | `scripts/parser/subagent.py` | YAML frontmatter (`name`, `description`, `tools`) + markdown body split into scope and instruction lines |
| `.claude/skills/*/SKILL.md` | `scripts/parser/skill_md.py` | Optional `agentforce:` frontmatter section with `target`, `inputs`, `outputs` |

Parsers handle YAML frontmatter extraction (`scripts/parser/frontmatter.py`) and markdown body splitting (`scripts/parser/markdown_utils.py`). Fields that have no Agent Script equivalent (`model`, `maxTurns`, `permissionMode`, `memory`, `isolation`) are logged and dropped.

### 2. Build IR

Parsed data is assembled into a tree of Python dataclasses defined in `scripts/ir/models.py`:

```
AgentDefinition
├── ConfigBlock        (developer_name, agent_type, default_agent_user, ...)
├── SystemBlock        (welcome/error messages, instructions)
├── Variable[]         (mutable with defaults, linked with sources)
├── LanguageBlock      (locale settings)
├── ConnectionBlock?   (escalation routing, if needed)
├── StartAgent         (entry point with topic transitions)
└── Topic[]
    ├── ActionDefinition[]   (Level 1: target, inputs, outputs)
    └── ReasoningBlock
        ├── instruction_lines
        ├── conditionals
        └── ActionInvocation[]  (Level 2: with/set bindings, guards)
```

Each sub-agent `.md` file becomes a `Topic`. Each tool listed in a sub-agent becomes an `ActionDefinition` and `ActionInvocation`. Skills with an `agentforce:` section supply the real target, inputs, and outputs. Actions without a target (no matching SKILL.md) are omitted from the output since the Agent Script compiler requires every action to have a valid target.

### 3. Apply defaults

`scripts/ir/defaults.py` enriches the IR:

- **Linked variables** — Service agents get `EndUserId`, `RoutableId`, and `ContactId` automatically
- **start_agent** — Auto-generates a hub-and-spoke entry point with `@utils.transition` actions routing to each topic
- **connection block** — Added if any topic contains an `@utils.escalate` action

### 4. Generate

`scripts/generator/agent_script.py` renders the IR into Agent Script DSL text:

- 3-space indentation (matching Salesforce conventions)
- `True`/`False` booleans (capitalized)
- `|` (pipe) for simple multi-line instructions, `->` (arrow) for procedural logic
- Two-level action system: definitions (what to call) and invocations (how to call it)

The bundle writer creates the output directory structure under `aiAuthoringBundles/<AgentName>/`.

## Quick start

### Prerequisites

- Python 3.10+
- `pyyaml` (`pip install pyyaml`)
- Salesforce CLI >= 2.123.1 (for deployment)

### Setup

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install pyyaml pytest
```

### Initialize from a template

```bash
python3 -m scripts.cli init --template multi-topic --output-dir my-agent
```

This creates a starter project with `CLAUDE.md` and sub-agent files you can edit.

Available templates: `hello-world`, `multi-topic`, `verification-gate`

### Find your ASA user

Service agents require an Agent Service Account (ASA) user. Query your org to find available ASA users:

```bash
python3 -m scripts.cli setup -o MyOrg
```

This queries for users with the "Einstein Agent User" profile and displays them:

```
Found 2 ASA user(s):

  #    Username                                                Name
  ──── ─────────────────────────────────────────────────────── ──────────────────────────────
  1    acmeagent@00dwt00000bvllc880056991.ext                  EinsteinServiceAgent User
  2    bot@00dwt00000bvllc156044328.ext                        EinsteinServiceAgent User
```

### Convert markdown to .agent

```bash
python3 -m scripts.cli convert \
  --project-root my-agent \
  --agent-name AcmeAgent \
  --default-agent-user "acmeagent@00dwt00000bvllc880056991.ext"
```

Output lands in `my-agent/force-app/main/default/aiAuthoringBundles/AcmeAgent/`.

The `--default-agent-user` flag is required for service agents. If omitted, a warning is printed with instructions to run `setup` to find available ASA users.

### Deploy to a Salesforce org

```bash
# Validate without deploying
python3 -m scripts.cli deploy --api-name AcmeAgent -o MyOrg --dry-run

# Publish (compile + deploy)
python3 -m scripts.cli deploy --api-name AcmeAgent -o MyOrg

# Publish and activate
python3 -m scripts.cli deploy --api-name AcmeAgent -o MyOrg --activate
```

The `deploy` command calls `sf agent publish authoring-bundle`, which compiles the Agent Script into BotDefinition/BotVersion/GenAiPlannerBundle metadata and deploys everything to the org.

### Preview

```bash
python3 -m scripts.cli preview --api-name AcmeAgent -o MyOrg --client-app my-app
```

## Input file formats

### CLAUDE.md

Plain markdown. The entire content becomes the agent's `system.instructions`.

```markdown
You are a customer support agent for Acme Corp.
Be helpful, professional, and concise.
Always verify the customer before making changes.
```

### Sub-agent files (`.claude/agents/*.md`)

YAML frontmatter + markdown body. Each file becomes one topic.

```yaml
---
name: order-support
description: Handles order inquiries and returns
tools: CheckOrderStatus, ProcessReturn
---
Help customers with their orders.

Always look up the order before processing a return.
If the order is older than 30 days, escalate to a manager.
```

- `name` — Used as the topic name (kebab-case → snake_case)
- `description` — Topic description for routing
- `tools` — Comma-separated or YAML list. Built-in Claude Code tools (Read, Grep, etc.) are filtered out. Custom tools become action definitions — but only if a matching SKILL.md provides a target.
- Body first paragraph → scope; remaining lines → instruction lines

### SKILL.md files (`.claude/skills/*/SKILL.md`)

Standard SKILL.md with an optional `agentforce:` section for Salesforce-specific metadata:

```yaml
---
name: check-order-status
description: Check the status of a customer order
agentforce:
  target: "flow://Get_Order_Details"
  inputs:
    order_id:
      type: string
      description: "The order number"
  outputs:
    status:
      type: string
      description: "Current order status"
---
```

If a skill's name matches a tool listed in a sub-agent, the target/inputs/outputs are merged into the action definition. Without the `agentforce:` section, the tool is omitted from the generated output (the Agent Script compiler requires every action to have a valid target).

## Output format

The generated `.agent` file follows the Agent Script DSL. Example output for the `multi-topic` template:

```yaml
config:
   developer_name: "AcmeAgent"
   agent_description: "You are a customer support agent for Acme Corp."
   agent_type: "AgentforceServiceAgent"
   default_agent_user: "acmeagent@00dwt00000bvllc880056991.ext"

system:
   messages:
      welcome: "Hello! How can I help you today?"
      error: "Sorry, something went wrong. Please try again."
   instructions: |
      You are a customer support agent for Acme Corp.
      Be helpful, professional, and concise.
      Always verify the customer before making changes.

variables:
   EndUserId: linked string
      source: @MessagingSession.MessagingEndUserId
      description: "Messaging End User ID"
   RoutableId: linked string
      source: @MessagingSession.Id
      description: "Messaging Session ID"
   ContactId: linked string
      source: @MessagingEndUser.ContactId
      description: "Contact ID"

language:
   default_locale: "en_US"
   additional_locales: ""
   all_additional_locales: False

start_agent entry:
   description: "Entry point - route to appropriate topic"
   reasoning:
      instructions: ->
         | Determine what the customer needs help with.
         | Route them to the appropriate topic.
      actions:
         go_general_faq: @utils.transition to @topic.general_faq
            description: "Answers general questions about Acme Corp"
         go_order_support: @utils.transition to @topic.order_support
            description: "Handles order inquiries and returns"

topic general_faq:
   description: "Answers general questions about Acme Corp"
   reasoning:
      instructions: |
         | Answer general questions about our company.

topic order_support:
   description: "Handles order inquiries and returns"
   reasoning:
      instructions: |
         | Help customers with their orders.
```

## What gets dropped

These Claude Code features have no Agent Script equivalent and are silently dropped:

| Field | Reason |
|---|---|
| `model` | Agentforce uses its own model selection |
| `permissionMode` | No equivalent concept |
| `maxTurns` | No equivalent concept |
| `memory` | No equivalent concept |
| `isolation` | No equivalent concept |
| `background` | No equivalent concept |

Tools listed in sub-agents that don't have a corresponding SKILL.md with an `agentforce:` target are also omitted — the Agent Script compiler requires every action to have a valid target string.

## CLI reference

```
agentforce-md setup     -o ORG
agentforce-md convert   --project-root DIR --agent-name NAME [--agent-type TYPE] [--default-agent-user USER] [--output-dir DIR]
agentforce-md deploy    --api-name NAME -o ORG [--dry-run] [--activate] [--skip-retrieve]
agentforce-md preview   --api-name NAME -o ORG --client-app APP
agentforce-md init      --template TEMPLATE [--output-dir DIR]
```

| Command | Description |
|---|---|
| `setup` | Query the org for available ASA users (Einstein Agent User profile) |
| `convert` | Parse markdown files and generate `.agent` + `.bundle-meta.xml` |
| `deploy` | Publish the authoring bundle to the org (compile + deploy). Uses `sf agent publish authoring-bundle` |
| `deploy --dry-run` | Validate the bundle without publishing. Uses `sf agent validate authoring-bundle` |
| `deploy --activate` | Also activate the agent after publishing |
| `deploy --skip-retrieve` | Don't retrieve generated metadata back to the DX project |
| `preview` | Start an interactive agent preview session |
| `init` | Scaffold a new project from a template |

## Project structure

```
scripts/
├── cli.py                    # CLI entry point (argparse)
├── convert.py                # Main orchestrator
├── parser/
│   ├── frontmatter.py        # YAML frontmatter extraction
│   ├── markdown_utils.py     # Body → scope + instruction lines
│   ├── claude_md.py          # Parse CLAUDE.md
│   ├── subagent.py           # Parse .claude/agents/*.md
│   └── skill_md.py           # Parse .claude/skills/*/SKILL.md
├── ir/
│   ├── models.py             # Dataclass IR definitions
│   ├── naming.py             # Name conversion utilities
│   └── defaults.py           # Auto-generate linked vars, start_agent, connection
├── generator/
│   ├── agent_script.py       # IR → .agent file text
│   ├── bundle_meta.py        # Constant bundle-meta.xml
│   └── writer.py             # Write files to disk
└── deploy/
    └── sf_cli.py             # Wraps sf agent CLI commands

templates/                    # Starter project templates
tests/                        # pytest test suite
```

## Running tests

```bash
source .venv/bin/activate
python -m pytest tests/ -v
```
