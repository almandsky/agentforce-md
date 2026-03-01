# agentforce-md

Convert Claude Code markdown conventions into Agentforce Agent Script (`.agent`) files for deployment to Salesforce orgs.

## What it does

Developers using Claude Code write agent behavior as plain markdown files — `CLAUDE.md` for global instructions, sub-agent `.md` files for topics, and `SKILL.md` files for actions. This tool converts those markdown files into Salesforce's Agent Script DSL format (a single `.agent` file), ready for deployment via `sf agent publish authoring-bundle`.

The full round-trip is orchestrated by a Claude Code skill (`/agentforce-convert`) that generates markdown from a user prompt, converts it to Agent Script, and deploys to a Salesforce org:

```
  User
   │  ① Prompt
   ▼
  ┌─────────────────────────────────┐
  │          Claude Code CLI        │
  │                                 │          Markdown Files
  │  ┌───────────────────────────┐  │     ┌──────────────────────────┐
  │  │  Agent Markdown           │──┼─②─►│  CLAUDE.md               │
  │  │  Generation SKILL         │  │     │  .claude/agents/*.md     │
  │  └───────────────────────────┘  │     └────────────┬─────────────┘
  │              │                  │                   │
  │              ▼                  │        ③          │
  │  ┌───────────────────────────┐  │                   │
  │  │  Markdown to Agent        │◄─┼──────────────────┘
  │  │  Script Conversion        │  │          Agent Script
  │  │                           │──┼─④─►┌──────────────────────────┐
  │  └───────────────────────────┘  │     │  aiAuthoringBundles/     │
  │              │                  │     └────────────┬─────────────┘
  │              ▼                  │        ⑤          │
  │  ┌───────────────────────────┐  │                   │
  │  │  Deploy to                │◄─┼──────────────────┘
  │  │  Salesforce Org           │  │          Salesforce Org
  │  │                           │──┼─⑥─►┌──────────────────────────┐
  │  └───────────────────────────┘  │     │  Metadata                │
  │                                 │     └──────────────────────────┘
  └─────────────────────────────────┘
```

| Step | What happens |
|------|-------------|
| ① | User describes the agent they want to build |
| ② | Claude Code SKILL generates markdown files (CLAUDE.md + sub-agent .md files) |
| ③ | Markdown files are fed into the Python converter |
| ④ | Converter produces an Agent Script `.agent` file in `aiAuthoringBundles/` |
| ⑤ | The `.agent` file is passed to the deployment step |
| ⑥ | `sf agent publish authoring-bundle` compiles and deploys metadata to the org |

Each step can also be run independently via the CLI (see [CLI reference](#cli-reference)).

## How it works

The converter runs a four-stage pipeline:

### 1. Parse

Each input file type has a dedicated parser:

| Input file | Parser | What it extracts |
|---|---|---|
| `CLAUDE.md` | `scripts/parser/claude_md.py` | System-level instructions (the agent's persona) |
| `.claude/agents/*.md` | `scripts/parser/subagent.py` | YAML frontmatter (`name`, `description`, `tools`) + markdown body split into scope and instruction lines |
| `.claude/skills/*/SKILL.md` | `scripts/parser/skill_md.py` | Optional `agentforce:` frontmatter section with `target`, `inputs`, `outputs`, `label`, `source`, and other action metadata |

Parsers handle YAML frontmatter extraction (`scripts/parser/frontmatter.py`) and markdown body splitting (`scripts/parser/markdown_utils.py`). Fields that have no Agent Script equivalent (`model`, `maxTurns`, `permissionMode`, `memory`, `isolation`) are logged and dropped.

### 2. Build IR

Parsed data is assembled into a tree of Python dataclasses defined in `scripts/ir/models.py`:

```
AgentDefinition
├── ConfigBlock        (developer_name, description, agent_type, agent_label, default_agent_user)
├── SystemBlock        (instructions, welcome/error messages)
├── Variable[]         (mutable with defaults, linked with sources, visibility, label)
├── LanguageBlock      (locale settings)
├── KnowledgeBlock?    (citations_enabled)
├── ConnectionBlock?   (escalation routing, if needed)
├── StartAgent         (entry point with topic transitions, label)
└── Topic[]
    ├── ActionDefinition[]   (Level 1: target, inputs, outputs, label, source, ...)
    └── ReasoningBlock
        ├── instruction_lines
        ├── conditionals
        └── ActionInvocation[]  (Level 2: with/set bindings, guards)
```

Each sub-agent `.md` file becomes a `Topic`. Each tool listed in a sub-agent becomes an `ActionDefinition` and `ActionInvocation`. Skills with an `agentforce:` section supply the real target, inputs, and outputs. Actions without a target (no matching SKILL.md) are rendered as commented-out stubs with `# TODO` markers. Use `--strict` to fail the conversion instead.

### 3. Apply defaults

`scripts/ir/defaults.py` enriches the IR:

- **Linked variables** — Service agents get `EndUserId`, `RoutableId`, and `ContactId` automatically (with `visibility: "External"`)
- **start_agent** — Auto-generates a hub-and-spoke entry point with `@utils.transition` actions routing to each topic
- **connection block** — Added if any topic contains an `@utils.escalate` action
- **Validation** — Developer name length, duplicate topics, empty descriptions, and other constraints are checked before generation

### 4. Generate

`scripts/generator/agent_script.py` renders the IR into Agent Script DSL text:

- 4-space indentation (matching Salesforce conventions)
- `True`/`False` booleans (capitalized)
- `|` (pipe) for simple multi-line instructions, `->` (arrow) for procedural logic
- Two-level action system: definitions (what to call) and invocations (how to call it)

The bundle writer creates the output directory structure under `aiAuthoringBundles/<AgentName>/`.

## Installation

Install agentforce-md as Claude Code skills available in any project:

```bash
# Install (one command)
curl -sSL https://raw.githubusercontent.com/almandsky/agentforce-md/main/tools/install.sh | bash

# Update to latest version
python3 ~/.claude/agentforce-md-install.py --update

# Check installation status
python3 ~/.claude/agentforce-md-install.py --status

# Uninstall
python3 ~/.claude/agentforce-md-install.py --uninstall
```

After installation, restart Claude Code. The `/agentforce-convert`, `/agentforce-discover`, `/agentforce-scaffold`, and `/agentforce-run` skills will be available in any project.

### Recommended: install sf-skills

agentforce-md works best alongside [sf-skills](https://github.com/Jaganpro/sf-skills), which provides Claude Code skills for creating Flows, Apex classes, and other Salesforce metadata that your agents reference. When `/agentforce-discover` finds missing targets, you can use `/sf-flow` or `/sf-apex` to build them directly in Claude Code.

```bash
curl -sSL https://raw.githubusercontent.com/Jaganpro/sf-skills/main/tools/install.sh | bash
```

Both install to `~/.claude/skills/` with no conflicts (`agentforce-*` vs `sf-*` prefixes).

## Quick start

### Prerequisites

- Python 3.10+ (the installer creates a bundled venv automatically)
- Salesforce CLI >= 2.123.1 (for deployment)
- [sf-skills](https://github.com/Jaganpro/sf-skills) (recommended — for creating Flows, Apex, and other metadata)

### Initialize from a template

```bash
~/.claude/agentforce-md/bin/agentforce-md init --template multi-topic --output-dir my-agent
```

This creates a starter project with `CLAUDE.md` and sub-agent files you can edit.

Available templates: `hello-world`, `multi-topic`, `verification-gate`

### Find your ASA user

Service agents require an Agent Service Account (ASA) user. Query your org to find available ASA users:

```bash
~/.claude/agentforce-md/bin/agentforce-md setup -o MyOrg
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
~/.claude/agentforce-md/bin/agentforce-md convert \
  --project-root my-agent \
  --agent-name AcmeAgent \
  --default-agent-user "acmeagent@00dwt00000bvllc880056991.ext"
```

Output lands in `force-app/main/default/aiAuthoringBundles/AcmeAgent/` (relative to the current working directory). Override with `--output-dir`.

The `--default-agent-user` flag is required for service agents. If omitted, a warning is printed with instructions to run `setup` to find available ASA users.

### Deploy to a Salesforce org

```bash
# Validate without deploying
~/.claude/agentforce-md/bin/agentforce-md deploy --api-name AcmeAgent -o MyOrg --dry-run

# Publish (compile + deploy)
~/.claude/agentforce-md/bin/agentforce-md deploy --api-name AcmeAgent -o MyOrg

# Publish and activate
~/.claude/agentforce-md/bin/agentforce-md deploy --api-name AcmeAgent -o MyOrg --activate
```

The `deploy` command calls `sf agent publish authoring-bundle`, which compiles the Agent Script into BotDefinition/BotVersion/GenAiPlannerBundle metadata and deploys everything to the org.

### Preview

```bash
~/.claude/agentforce-md/bin/agentforce-md preview --api-name AcmeAgent -o MyOrg --client-app my-app
```

> **Tip:** Most users interact through Claude Code skills (`/agentforce-convert`, `/agentforce-run`, etc.) rather than calling the CLI directly. The skills handle the full path automatically.

## Input file formats

### CLAUDE.md

Plain markdown or structured with YAML frontmatter. The body becomes the agent's `system.instructions`.

**Plain markdown** (backwards compatible):
```markdown
You are a customer support agent for Acme Corp.
Be helpful, professional, and concise.
Always verify the customer before making changes.
```

**Structured with frontmatter**:
```yaml
---
welcome: "Welcome to Acme Support!"
error: "Something went wrong. Please try again."
agent_type: AgentforceServiceAgent
company: Acme Corp
---
You are a customer support agent for Acme Corp.
Be helpful, professional, and concise.
```

Supported frontmatter fields: `welcome`, `error`, `agent_type`, `company`. Alternatively, use `## Welcome Message`, `## Error Message`, or `## Company` sections in the body (frontmatter takes precedence). Recognized sections are extracted and removed from the instructions.

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
  label: "Check Order Status"
  require_user_confirmation: false
  include_in_progress_indicator: true
  progress_indicator_message: "Looking up order..."
  source: "Get_Order_Details"
  inputs:
    order_id:
      type: string
      description: "The order number"
      label: "Order ID"
      is_user_input: true
  outputs:
    status:
      type: string
      description: "Current order status"
      label: "Status"
---
```

Only `target` is required in the `agentforce:` section. All other fields are optional:
- `label` — Human-readable name for the action, input, or output
- `require_user_confirmation` — Whether user must confirm before execution (default: false)
- `include_in_progress_indicator` / `progress_indicator_message` — Loading indicator settings
- `source` — Metadata component API name
- `is_user_input` — Marks an input as collected from the end user
- `complex_data_type_name` — For complex/custom data types
- `filter_from_agent` / `is_displayable` — Control output visibility

If a skill's name matches a tool listed in a sub-agent, the target/inputs/outputs are merged into the action definition. Without the `agentforce:` section, the tool is rendered as a commented-out stub with a `# TODO` marker. Use `--strict` to fail the conversion instead of generating stubs.

## Output format

The generated `.agent` file follows the Agent Script DSL. Example output for the `multi-topic` template:

```yaml
system:
    instructions: |
        You are a customer support agent for Acme Corp.
        Be helpful, professional, and concise.
        Always verify the customer before making changes.
    messages:
        welcome: "Hello! How can I help you today?"
        error: "Sorry, something went wrong. Please try again."

config:
    developer_name: "AcmeAgent"
    description: "You are a customer support agent for Acme Corp."
    agent_type: "AgentforceServiceAgent"
    default_agent_user: "acmeagent@00dwt00000bvllc880056991.ext"

language:
    default_locale: "en_US"
    additional_locales: ""
    all_additional_locales: False

variables:
    EndUserId: linked string
        source: @MessagingSession.MessagingEndUserId
        description: "Messaging End User ID"
        visibility: "External"
    RoutableId: linked string
        source: @MessagingSession.Id
        description: "Messaging Session ID"
        visibility: "External"
    ContactId: linked string
        source: @MessagingEndUser.ContactId
        description: "Contact ID"
        visibility: "External"

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

Tools listed in sub-agents that don't have a corresponding SKILL.md with an `agentforce:` target are rendered as commented-out stubs with `# TODO` markers. Use `--strict` to fail the conversion instead.

## Bridge layer: discover, scaffold, run

SKILL.md files reference Salesforce org resources (flows, apex classes) that may not exist yet. The bridge layer connects markdown definitions to live orgs:

```
  discover              scaffold              run
  ┌─────────┐          ┌─────────┐          ┌─────────┐
  │ Query   │          │ Generate│          │ Invoke  │
  │ org for │──missing──▶ flow/  │          │ actions │
  │ targets │          │ apex   │          │ via API │
  └────┬────┘          │ stubs  │          └────┬────┘
       │               └────┬────┘               │
       ▼                    ▼                    ▼
  ┌──────────────────────────────────────────────┐
  │           Salesforce org (sf CLI)            │
  └──────────────────────────────────────────────┘
```

### Discover

Check which SKILL.md targets exist in the org:

```bash
~/.claude/agentforce-md/bin/agentforce-md discover --project-root my-agent -o MyOrg
```

Outputs a table of targets with found/missing status. Exit code 1 if any are missing.

### Scaffold

Generate stub metadata for missing targets:

```bash
# Discover + scaffold missing targets
~/.claude/agentforce-md/bin/agentforce-md scaffold --project-root my-agent -o MyOrg

# Scaffold all targets without checking the org
~/.claude/agentforce-md/bin/agentforce-md scaffold --project-root my-agent -o MyOrg --skip-discover
```

Creates Flow XML (`.flow-meta.xml`) and Apex class (`.cls` + `.cls-meta.xml`) stubs with matching input/output variables from SKILL.md definitions. Review the stubs, fill in business logic, and deploy with `sf project deploy start`.

### Run

Execute a single action against a live org:

```bash
~/.claude/agentforce-md/bin/agentforce-md run \
  --skill my-agent/.claude/skills/check-order-status/SKILL.md \
  -o MyOrg \
  --input '{"order_number":"12345"}'

# Dry run — show invocation plan without executing
~/.claude/agentforce-md/bin/agentforce-md run \
  --skill my-agent/.claude/skills/check-order-status/SKILL.md \
  -o MyOrg \
  --input '{"order_number":"12345"}' \
  --dry-run
```

Invokes the flow or apex action via REST API and returns the output values.

## CLI reference

```
~/.claude/agentforce-md/bin/agentforce-md [-v] setup     -o ORG
~/.claude/agentforce-md/bin/agentforce-md [-v] convert   [--project-root DIR] --agent-name NAME [--agent-type TYPE] [--default-agent-user USER] [--output-dir DIR] [--strict]
~/.claude/agentforce-md/bin/agentforce-md [-v] deploy    --api-name NAME -o ORG [--dry-run] [--activate] [--skip-retrieve]
~/.claude/agentforce-md/bin/agentforce-md [-v] preview   --api-name NAME -o ORG --client-app APP
~/.claude/agentforce-md/bin/agentforce-md [-v] init      [--template TEMPLATE] [--output-dir DIR]
~/.claude/agentforce-md/bin/agentforce-md [-v] discover  [--project-root DIR] -o ORG
~/.claude/agentforce-md/bin/agentforce-md [-v] scaffold  [--project-root DIR] -o ORG [--output-dir DIR] [--skip-discover]
~/.claude/agentforce-md/bin/agentforce-md [-v] run       --skill SKILL_PATH -o ORG [--input JSON] [--dry-run]
```

| Command | Description |
|---|---|
| `setup` | Query the org for available ASA users (Einstein Agent User profile) |
| `convert` | Parse markdown files and generate `.agent` + `.bundle-meta.xml` |
| `convert --strict` | Fail if any actions are missing targets (instead of generating stubs) |
| `deploy` | Publish the authoring bundle to the org (compile + deploy). Uses `sf agent publish authoring-bundle` |
| `deploy --dry-run` | Validate the bundle without publishing. Uses `sf agent validate authoring-bundle` |
| `deploy --activate` | Also activate the agent after publishing |
| `deploy --skip-retrieve` | Don't retrieve generated metadata back to the DX project |
| `preview` | Start an interactive agent preview session |
| `init` | Scaffold a new project from a template |
| `discover` | Check which SKILL.md targets (flows, apex classes) exist in the org |
| `scaffold` | Generate stub metadata (Flow XML, Apex classes) for missing SKILL.md targets |
| `scaffold --skip-discover` | Scaffold all targets without checking the org |
| `run` | Execute a SKILL.md action against a live org via REST API |
| `run --dry-run` | Show what would be called without executing |

## Project structure

```
.claude/skills/                   # Claude Code skills (installed globally)
  agentforce-convert/SKILL.md     #   Full round-trip orchestration
  agentforce-discover/SKILL.md    #   Check org for SKILL.md targets
  agentforce-scaffold/SKILL.md    #   Generate stub metadata
  agentforce-run/SKILL.md         #   Execute actions via REST API

bin/
  agentforce-md                   # CLI wrapper script (uses bundled venv)

tools/
  install.py                      # Python installer (install/update/uninstall/status)
  install.sh                      # Bash bootstrap (checks Python, downloads install.py)

scripts/                          # The converter tool (Python package)
├── cli.py                        # CLI entry point (argparse)
├── convert.py                    # Main orchestrator (convert command)
├── discover.py                   # Org metadata discovery (discover command)
├── scaffold.py                   # Stub metadata generation (scaffold command)
├── local_run.py                  # Action execution (run command)
├── parser/
│   ├── frontmatter.py            # YAML frontmatter extraction
│   ├── markdown_utils.py         # Body → scope + instruction lines
│   ├── claude_md.py              # Parse CLAUDE.md
│   ├── subagent.py               # Parse .claude/agents/*.md
│   └── skill_md.py               # Parse .claude/skills/*/SKILL.md
├── ir/
│   ├── models.py                 # Dataclass IR definitions
│   ├── naming.py                 # Name conversion utilities
│   ├── defaults.py               # Auto-generate linked vars, start_agent, connection
│   └── validate.py               # Pre-generation validation (names, duplicates, etc.)
├── generator/
│   ├── agent_script.py           # IR → .agent file text
│   ├── bundle_meta.py            # Constant bundle-meta.xml
│   ├── writer.py                 # Write files to disk
│   ├── flow_xml.py               # Flow XML stub generator
│   └── apex_stub.py              # Apex @InvocableMethod stub generator
└── deploy/
    └── sf_cli.py                 # Wraps sf agent CLI commands

templates/                        # Starter project templates
tests/                            # pytest test suite
VERSION                           # Version string (read by installer)
```

After installation, the layout under `~/.claude/` is:

```
~/.claude/
├── agentforce-md/                # Installed repo copy
│   ├── scripts/                  # Python CLI backend
│   ├── templates/                # For `init` command
│   ├── bin/agentforce-md         # CLI wrapper script
│   └── .venv/                    # Bundled venv with pyyaml
├── skills/
│   ├── agentforce-convert/       # Installed skills
│   ├── agentforce-discover/
│   ├── agentforce-scaffold/
│   ├── agentforce-run/
│   └── sf-*/                     # sf-skills (untouched)
├── .agentforce-md.json           # Version + install metadata
└── agentforce-md-install.py      # Self-updater
```

## Development

For contributing to agentforce-md:

```bash
git clone https://github.com/almandsky/agentforce-md.git
cd agentforce-md
python3 -m venv .venv && source .venv/bin/activate
pip install pyyaml pytest

# Run tests
python -m pytest tests/ -v

# Install from local clone (reflects your changes)
python3 tools/install.py --force
```
