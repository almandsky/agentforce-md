---
name: agentforce-convert
description: Convert Claude Code markdown conventions to Agentforce Agent Script (.agent) files, or deploy an existing agent bundle
allowed-tools: Bash Read Write Edit Glob
argument-hint: "[prompt describing your agent] | convert | deploy <org> | init <template> | setup <org>"
---

# Agentforce Markdown-to-Agent-Script Converter

You are an orchestration skill that converts Claude Code markdown conventions into Agentforce Agent Script (.agent) files and optionally deploys them.

## Routing

Determine the user's intent from their input:

1. **Full round-trip** (user provides a prompt describing an agent):
   - Ask for the target org alias and agent name
   - Run `setup` to find available ASA users
   - Generate CLAUDE.md + .claude/agents/*.md files from the prompt
   - If any topics have custom tools/actions, generate matching SKILL.md files with `agentforce:` targets
   - Run the Python converter with the ASA user
   - Show the generated .agent file for review
   - Deploy on user approval

2. **Convert only** (input is "convert" or user has existing markdown):
   - Check if `--default-agent-user` is needed (service agents)
   - Run `~/.claude/agentforce-md/bin/agentforce-md convert --project-root . --agent-name <AgentName> --default-agent-user <ASA_USER>`
   - Show the output .agent file

3. **Deploy only** (input starts with "deploy"):
   - Run `~/.claude/agentforce-md/bin/agentforce-md deploy --api-name <Name> -o <Org> --activate`

4. **Init template** (input starts with "init"):
   - Run `~/.claude/agentforce-md/bin/agentforce-md init --template <template-name>`

5. **Setup** (input starts with "setup"):
   - Run `~/.claude/agentforce-md/bin/agentforce-md setup -o <Org>`
   - Show available ASA users

## Full Round-Trip Workflow

When the user describes an agent they want to build:

### Step 1: Gather required info

Ask the user for:
- **Target org** alias (e.g., "MyOrg")
- **Agent name** (e.g., "AcmeAgent")

Then run setup to find ASA users:
```bash
~/.claude/agentforce-md/bin/agentforce-md setup -o <TargetOrg>
```

If multiple ASA users exist, ask which one to use. If none exist, tell the user to create one in Setup > Agent Service Accounts.

### Step 2: Generate markdown files

Derive a kebab-case directory name from the agent name (e.g., `CustomerSupportAgent` → `customer-support-agent`).

Create the agent's input files under `agents/<agent-dir>/`:

```
agents/<agent-dir>/
  CLAUDE.md                          # Agent persona and global instructions
  .claude/agents/<topic-name>.md     # One file per topic
  .claude/skills/<tool>/SKILL.md     # Optional: action targets
```

**CLAUDE.md** — the agent's persona and global instructions. Can be plain markdown or use YAML frontmatter for overrides:
```yaml
---
welcome: "Welcome to Acme Support!"
error: "Something went wrong. Please try again."
agent_type: AgentforceServiceAgent
knowledge:
  citations_enabled: true
variables:
  # Mutable variables (agent state, writable, has defaults)
  isVerified:
    type: boolean
    modifier: mutable
    default: "False"
    description: "Whether the customer has been verified"
    label: "Customer Verified"
    visibility: Internal
  VerifiedCustomerId:
    type: string
    modifier: mutable
    description: "The verified customer record ID"
    label: "Verified Customer ID"
    visibility: Internal
  # Linked variables (context, read-only, has source)
  # Note: Service agents auto-add EndUserId, RoutableId, ContactId if not defined here.
  # Define them explicitly to override source or add extra linked vars.
  EndUserLanguage:
    type: string
    modifier: linked
    source: "@MessagingSession.EndUserLanguage"
    description: "End user language"
    visibility: External
---
You are a customer support agent for Acme Corp.
Be helpful, professional, and concise.
```

Supported frontmatter fields:
- `welcome`, `error` — Messages (or use `## Welcome Message` / `## Error Message` sections)
- `agent_type` — `AgentforceServiceAgent` (default) or `AgentforceEmployeeAgent`
- `company` — Company name
- `knowledge` — Knowledge block settings (`citations_enabled: true/false`)
- `variables` — Agent-level variables (see below)

**Variables** are agent-level state shared across all topics. Two modifiers:
- `mutable` (default) — Writable state with defaults. Actions can `set` values into these. Types: string, number, boolean, object, date, id, list[T].
- `linked` — Read-only context variables with a `source`. Types: string, number, boolean, date, timestamp, currency, id only (no list/object). Cannot have defaults.

Service agents auto-add `EndUserId`, `RoutableId`, and `ContactId` as linked variables if not explicitly defined. Define them in frontmatter to override their source.

Plain markdown (no frontmatter, no sections) also works — the entire content becomes system instructions.

**Sub-agent files** (`.claude/agents/<topic-name>.md`) — one per topic:
```yaml
---
name: <topic-name>
description: <what this topic handles>
tools: <comma-separated tool names if any>
agentforce:
  label: "Human-Readable Topic Name"          # optional
  available_when: "@variables.isVerified==True" # optional: guard for start_agent transition
  bindings:                                     # optional: action-variable bindings
    ToolName:
      with:                                     # bind inputs from variables or LLM
        customerId: "@variables.VerifiedCustomerId"
        caseSubject: "..."                      # "..." means LLM slot-fills from conversation
      set:                                      # capture outputs into variables
        "@variables.isVerified": "@outputs.isVerified"
      after:                                    # conditional transition after action
        if: "@variables.isVerified"
        transition_to: "case-management"        # kebab-case topic name
---
<Scope: what this topic does>

<Instruction lines: how to handle requests>
```

The `agentforce:` section is optional. Without it, topics render with no label, no guard, and bare action invocations (LLM decides all inputs).

**Binding details:**
- `with` — Maps action input params. Use `@variables.X` to bind from a variable, or `"..."` for LLM slot-fill.
- `set` — After the action runs, capture outputs into variables: `@variables.X: @outputs.Y`.
- `after` — Conditional transition: if a variable is truthy after the action, route to another topic. Can be a single `{if, transition_to}` or a list of them.
- `available_when` — Prevents the LLM from routing to this topic until the condition is met. Applied to the `start_agent` transition for this topic.
- `label` — Human-readable name shown in the Agentforce UI.

**Multiple after branches** (list form):
```yaml
agentforce:
  bindings:
    CheckStatus:
      after:
        - if: "@variables.urgent"
          transition_to: "escalation"
        - if: "@variables.resolved"
          transition_to: "completion"
```

**SKILL.md files** (optional, `.claude/skills/<tool-name>/SKILL.md`) — for tools that have known Salesforce targets:
```yaml
---
name: <tool-name>
description: <what the tool does>
agentforce:
  target: "flow://FlowApiName"
  label: "Human-Readable Action Name"
  require_user_confirmation: false
  include_in_progress_indicator: true
  progress_indicator_message: "Processing..."
  source: "MetadataComponentApiName"
  inputs:
    param_name:
      type: string
      description: "Parameter description"
      label: "Param Label"
      is_user_input: true
  outputs:
    result_name:
      type: string
      description: "Output description"
      label: "Result Label"
      is_displayable: true
---
```

All fields except `target` are optional. The `label` fields provide human-readable names. `source` links to the metadata component. `is_user_input` marks inputs collected from the end user. `is_displayable` controls whether outputs are shown to the user.

**Important**: Tools listed in sub-agents that don't have a matching SKILL.md with an `agentforce:` target will be rendered as commented-out stubs with `# TODO` markers in the generated .agent file. Use `--strict` to fail the conversion instead.

### Step 3: Run the converter

```bash
~/.claude/agentforce-md/bin/agentforce-md convert \
  --project-root agents/<agent-dir> \
  --agent-name <AgentName> \
  --default-agent-user "<ASA_USERNAME>"
```

Add `--strict` to fail if any tools lack a target instead of generating stubs.

Output goes to `force-app/main/default/aiAuthoringBundles/<AgentName>/` (relative to the current working directory, not the project root). Multiple agents coexist in separate subdirectories.

### Step 4: Discover (optional)

Check that SKILL.md targets exist in the org before deploying:

```bash
~/.claude/agentforce-md/bin/agentforce-md discover --project-root agents/<agent-dir> -o <TargetOrg>
```

If targets are missing, scaffold stubs:

```bash
~/.claude/agentforce-md/bin/agentforce-md scaffold --project-root agents/<agent-dir> -o <TargetOrg>
```

### Step 5: Review

Read the generated .agent file and display it to the user. Highlight:
- The config block (name, type, ASA user)
- How many topics were generated
- Whether any tools were rendered as stubs (no target) — look for `# TODO` comments

### Step 6: Deploy (if approved)

```bash
# Validate first
~/.claude/agentforce-md/bin/agentforce-md deploy --api-name <AgentName> -o <TargetOrg> --dry-run

# If validation passes, publish and activate
~/.claude/agentforce-md/bin/agentforce-md deploy --api-name <AgentName> -o <TargetOrg> --activate
```

## Conventions

- Agent names should be PascalCase (e.g., AcmeAgent, OrderBot)
- Topic names should be kebab-case in filenames (e.g., order-support.md)
- Each distinct responsibility should be its own sub-agent/topic
- Keep instruction lines concise and actionable
- The first paragraph of a sub-agent body is the scope; remaining lines are instructions (separate with a blank line)
- Service agents always need `--default-agent-user` (the ASA user from `setup`)
- Tools need a SKILL.md with `agentforce: target:` to generate action definitions
