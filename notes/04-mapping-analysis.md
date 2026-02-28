# Mapping Analysis: Claude Code Conventions -> Agent Script

## Conceptual Mapping

| Claude Code Convention | Agentforce Metadata | Notes |
|------------------------|-------------------|-------|
| `CLAUDE.md` (project instructions) | `BotVersion.role` + `BotVersion.company` | Global agent instructions -> system prompt |
| Sub-agent `.md` file | `GenAiPlugin` (Topic) | Each sub-agent becomes a topic with scope and instructions |
| Sub-agent `description` | `GenAiPlugin.scope` + `GenAiPlugin.description` | Scope = what the topic handles |
| Sub-agent `tools` | `GenAiPlugin.genAiFunctions` | Available tools -> available actions |
| `SKILL.md` | `GenAiFunction` (Action) | Each skill -> an action definition |
| SKILL.md `name` | `GenAiFunction.masterLabel` | |
| SKILL.md `description` | `GenAiFunction.description` | Used by LLM for action selection |
| Hook `PreToolUse` | Agent Script PreToolUse hook | Direct mapping |
| Hook `PostToolUse` | Agent Script PostToolUse hook | Direct mapping |
| Hook `SessionStart` | Agent Script SessionStart hook | Direct mapping |
| Hook `Stop` | Agent Script StopHook | Direct mapping |
| MCP servers (`.mcp.json`) | External service connections | May map to custom actions |
| `settings.json` permissions | N/A | No direct equivalent |

## Detailed Mapping: Sub-Agent -> Topic

### Source (sub-agent .md)
```yaml
---
name: booking-assistant
description: Handles all booking-related requests
tools: Read, CreateBooking, CheckAvailability
model: sonnet
---

You help customers create and manage bookings.
Always verify the customer identity before creating a booking.
When checking availability, ask for the preferred date first.
```

### Target (GenAiPlugin)
```xml
<GenAiPlugin xmlns="http://soap.sforce.com/2006/04/metadata">
    <canEscalate>false</canEscalate>
    <description>Handles all booking-related requests</description>
    <developerName>Booking_Assistant</developerName>
    <genAiFunctions>
        <functionName>CreateBooking</functionName>
    </genAiFunctions>
    <genAiFunctions>
        <functionName>CheckAvailability</functionName>
    </genAiFunctions>
    <genAiPluginInstructions>
        <description>Always verify the customer identity before creating a booking.</description>
        <developerName>instruction_alwaysver0</developerName>
        <language>en_US</language>
        <masterLabel>instruction_alwaysver0</masterLabel>
    </genAiPluginInstructions>
    <genAiPluginInstructions>
        <description>When checking availability, ask for the preferred date first.</description>
        <developerName>instruction_whencheckin1</developerName>
        <language>en_US</language>
        <masterLabel>instruction_whencheckin1</masterLabel>
    </genAiPluginInstructions>
    <language>en_US</language>
    <masterLabel>Booking Assistant</masterLabel>
    <pluginType>Topic</pluginType>
    <scope>You help customers create and manage bookings.</scope>
</GenAiPlugin>
```

## Mapping Rules

### Name Conversion
- `kebab-case` (Claude) -> `Snake_Case` (Salesforce developerName)
- `kebab-case` (Claude) -> `Title Case` (Salesforce masterLabel)

### Instruction Extraction
- The markdown body of a sub-agent is parsed into:
  - First paragraph/sentence -> `scope` (what the topic is about)
  - Subsequent sentences/bullets -> individual `genAiPluginInstructions`
- `developerName` for instructions: `instruction_<first8chars><index>`

### Tool -> Function Mapping
- Each tool listed in the sub-agent -> `genAiFunctions.functionName`
- Built-in tools (Read, Grep, etc.) don't map to Agentforce actions
- Custom tools/MCP tools -> need corresponding GenAiFunction definitions

### What Gets Lost (Lossy Import)

These Claude Code features have NO Agentforce equivalent:
- `model` selection (Agentforce uses its own model config)
- `permissionMode` settings
- `maxTurns` limits
- `isolation: worktree`
- `memory` persistence
- `background` execution mode
- Fine-grained tool permissions (`disallowedTools`)
- Hook types: `prompt`, `agent` (only `command` maps cleanly)
- `PermissionRequest`, `Notification`, `SubagentStart/Stop` hooks
- `TeammateIdle`, `TaskCompleted`, `ConfigChange` hooks
- `PreCompact`, `WorktreeCreate/Remove` hooks

### What Gets Gained (Agentforce-only features)
- Conditional topic routing via `ruleExpressions`
- Variable flow between actions via `attributeMappings`
- Built-in customer verification flow
- Channel-specific context variables (WhatsApp, Embedded, etc.)
- Agent test framework (`AiEvaluationDefinition`)
- Custom output rendering (`lightningTypes`)
- Escalation to human agents (`canEscalate`)
- Structured deterministic transitions

## Conversion Pipeline

```
CLAUDE.md + sub-agents/*.md + .claude/skills/*/SKILL.md + hooks
  |
  v
[Parser] -- Parse markdown + YAML frontmatter
  |
  v
[Intermediate Representation] -- Normalized agent model
  |
  v
[Generator] -- Produce Salesforce XML metadata
  |
  v
Bot + BotVersion + GenAiPlannerBundle + GenAiPlugins + GenAiFunctions + schemas
  |
  v
[Deployer] -- sf project deploy start
```
