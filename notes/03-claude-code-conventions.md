# Claude Code Conventions Reference

## Overview

Claude Code uses markdown-based conventions for agent memory, skills, sub-agents, and hooks. These are the "source" formats that our POC will convert FROM to produce Agent Script metadata.

---

## 1. CLAUDE.md (Agent Memory / Instructions)

Plain markdown files that provide instructions and rules for Claude across sessions.

### File Locations (Hierarchy, highest to lowest priority)

| Location | Purpose | Shared |
|----------|---------|--------|
| `/Library/Application Support/ClaudeCode/CLAUDE.md` | Managed org policy | All org users |
| `./CLAUDE.md` or `./.claude/CLAUDE.md` | Project instructions | Team (via git) |
| `./.claude/rules/*.md` | Modular topic rules | Team (via git) |
| `~/.claude/CLAUDE.md` | Personal prefs (all projects) | Just you |
| `./CLAUDE.local.md` | Local project prefs (gitignored) | Just you |

### Features
- **Import syntax**: `@path/to/import` to pull in other files
- **Recursive loading**: Reads CLAUDE.md up the directory tree
- **Path-specific rules** via YAML frontmatter in `.claude/rules/*.md`:

```yaml
---
paths:
  - "src/api/**/*.ts"
---
# API Rules
- All endpoints must include input validation
```

---

## 2. SKILL.md (Agent Skills - Open Standard)

An **open standard** (https://agentskills.io) adopted by 30+ tools including Claude Code, Cursor, Gemini CLI, VS Code, etc.

### Directory Structure

```
skill-name/
  SKILL.md           # Required: instructions + metadata
  scripts/           # Optional: executable code
  references/        # Optional: documentation
  assets/            # Optional: templates, data
```

### SKILL.md Format

YAML frontmatter + Markdown body:

```yaml
---
name: pdf-processing
description: Extract text and tables from PDF files
license: Apache-2.0
compatibility: Requires git, docker, jq
metadata:
  author: example-org
  version: "1.0"
allowed-tools: Bash(git:*) Bash(jq:*) Read
---

# PDF Processing

## When to use this skill
Use when the user needs to work with PDF files...

## Steps
1. Use pdfplumber for text extraction...
```

### Frontmatter Fields

| Field | Required | Description |
|-------|----------|-------------|
| `name` | Yes | Max 64 chars, lowercase + hyphens |
| `description` | Yes | Max 1024 chars |
| `license` | No | License name |
| `compatibility` | No | Environment requirements |
| `metadata` | No | Key-value pairs |
| `allowed-tools` | No | Pre-approved tools |

### Claude Code Extensions

| Field | Description |
|-------|-------------|
| `argument-hint` | Autocomplete hint |
| `disable-model-invocation` | Only user can invoke via `/name` |
| `user-invocable` | `false` = hidden from `/` menu |
| `model` | Model to use when active |
| `context` | `fork` = run in subagent |
| `agent` | Subagent type for `context: fork` |
| `hooks` | Hooks scoped to skill lifecycle |

### Storage Locations

| Location | Scope |
|----------|-------|
| `~/.claude/skills/<name>/SKILL.md` | All your projects |
| `.claude/skills/<name>/SKILL.md` | Current project |

### Progressive Disclosure
1. **Discovery** (~100 tokens): Only name + description loaded at startup
2. **Activation** (< 5000 tokens): Full body loaded when activated
3. **Execution** (as needed): Referenced files loaded on demand

---

## 3. Sub-Agents

Specialized AI assistants with their own context, tools, and permissions.

### File Format

Markdown with YAML frontmatter:

```yaml
---
name: code-reviewer
description: Reviews code for quality and best practices
tools: Read, Glob, Grep
model: sonnet
permissionMode: default
maxTurns: 50
memory: user
background: false
isolation: worktree
skills:
  - api-conventions
hooks:
  PreToolUse:
    - matcher: "Bash"
      hooks:
        - type: command
          command: "./scripts/validate-command.sh"
---

You are a code reviewer. Analyze code and provide
specific, actionable feedback on quality, security, and best practices.
```

### Frontmatter Fields

| Field | Required | Description |
|-------|----------|-------------|
| `name` | Yes | Unique identifier |
| `description` | Yes | When to delegate to this subagent |
| `tools` | No | Available tools (inherits all if omitted) |
| `disallowedTools` | No | Tools to deny |
| `model` | No | `sonnet`, `opus`, `haiku`, `inherit` |
| `permissionMode` | No | `default`, `acceptEdits`, `dontAsk`, `bypassPermissions`, `plan` |
| `maxTurns` | No | Max agentic turns |
| `skills` | No | Skills to preload |
| `mcpServers` | No | MCP servers available |
| `hooks` | No | Lifecycle hooks |
| `memory` | No | `user`, `project`, `local` |
| `background` | No | Run as background task |
| `isolation` | No | `worktree` = isolated git copy |

### Storage Locations
- `.claude/agents/` - Current project
- `~/.claude/agents/` - All projects

### Built-in Sub-Agents
- **Explore**: Haiku, read-only, file discovery
- **Plan**: Inherits model, read-only, planning
- **General-purpose**: All tools, complex tasks
- **Bash**: Terminal commands

---

## 4. Hooks

Shell commands, HTTP endpoints, or LLM prompts that execute at lifecycle points.

### All Hook Events

| Event | When | Can Block? |
|-------|------|-----------|
| `SessionStart` | Session begins/resumes | No |
| `UserPromptSubmit` | Before Claude processes prompt | Yes |
| `PreToolUse` | Before tool call | Yes |
| `PermissionRequest` | Permission dialog appears | Yes |
| `PostToolUse` | After tool call succeeds | No |
| `PostToolUseFailure` | After tool call fails | No |
| `Notification` | Notification sent | No |
| `SubagentStart` | Subagent spawned | No |
| `SubagentStop` | Subagent finishes | Yes |
| `Stop` | Claude finishes responding | Yes |
| `TeammateIdle` | Teammate about to idle | Yes |
| `TaskCompleted` | Task marked completed | Yes |
| `ConfigChange` | Config file changes | Yes |
| `PreCompact` | Before context compaction | No |
| `SessionEnd` | Session terminates | No |

### Hook Configuration

```json
{
  "hooks": {
    "PreToolUse": [
      {
        "matcher": "Bash",
        "hooks": [
          {
            "type": "command",
            "command": ".claude/hooks/validate.sh"
          }
        ]
      }
    ]
  }
}
```

### Handler Types
- `command`: Shell command (stdin/stdout)
- `http`: HTTP POST with JSON
- `prompt`: LLM evaluation returning `{"ok": true/false}`
- `agent`: Subagent with tool access

### Exit Codes
- **0**: Success
- **2**: Blocking error (blocks action for blocking events)
- **Other**: Non-blocking error

### PreToolUse Decision Control

```json
{
  "hookSpecificOutput": {
    "permissionDecision": "allow|deny|ask",
    "permissionDecisionReason": "...",
    "updatedInput": {},
    "additionalContext": "..."
  }
}
```

---

## 5. Settings Files

All configuration is JSON-based (no tools.yaml/tools.yml):

| File | Purpose |
|------|---------|
| `~/.claude/settings.json` | User-level settings |
| `.claude/settings.json` | Project settings (committable) |
| `.claude/settings.local.json` | Local overrides (gitignored) |
| `.mcp.json` | MCP server configurations |

```json
{
  "$schema": "https://json.schemastore.org/claude-code-settings.json",
  "permissions": {
    "allow": ["Bash(npm run lint)"],
    "deny": ["Bash(curl *)", "Read(./.env)"]
  },
  "env": { "KEY": "value" },
  "hooks": { }
}
```
