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
```markdown
---
welcome: "Welcome to Acme Support!"
error: "Something went wrong. Please try again."
agent_type: AgentforceServiceAgent
---
You are a customer support agent for Acme Corp.
Be helpful, professional, and concise.
```

Alternatively, use `## Welcome Message` and `## Error Message` sections in the body instead of frontmatter. Plain markdown (no frontmatter, no sections) also works — the entire content becomes system instructions.

**Sub-agent files** (`.claude/agents/<topic-name>.md`) — one per topic:
```yaml
---
name: <topic-name>
description: <what this topic handles>
tools: <comma-separated tool names if any>
---
<Scope: what this topic does>

<Instruction lines: how to handle requests>
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
