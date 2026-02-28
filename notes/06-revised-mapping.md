# Revised Mapping: Claude Code Conventions -> Agent Script (.agent file)

## Key Insight

Instead of generating multiple XML metadata files (the old way), we should generate a **single `.agent` file** using the Agent Script DSL. This is:
- Simpler (one file vs 5+ XML files)
- Human-readable
- Version-control friendly
- Deployed via `sf agent publish authoring-bundle`

## Mapping Table

| Claude Code Convention | Agent Script (.agent) Block | Notes |
|------------------------|---------------------------|-------|
| **CLAUDE.md** (project instructions) | `system.instructions` | Global agent persona/instructions |
| CLAUDE.md company context | `system.instructions` (embedded) | Company info goes into system instructions |
| **Sub-agent .md** files | `topic:` blocks | Each sub-agent becomes a topic |
| Sub-agent `name` | `topic <name>:` | kebab-case -> snake_case |
| Sub-agent `description` | `topic.description` | Used for topic routing |
| Sub-agent markdown body (1st para) | `topic.reasoning.instructions` | What the topic does |
| Sub-agent markdown body (bullets) | Individual instruction lines under `reasoning.instructions` | |
| Sub-agent `tools` list | `topic.reasoning.actions` | Each tool -> an action reference |
| **SKILL.md** files | `topic.actions` (Level 1 definitions) | Skills with targets -> action definitions |
| SKILL.md `name` | Action name in `actions:` | |
| SKILL.md `description` | `actions.description` | |
| **Welcome message** | `system.messages.welcome` | |
| **Error message** | `system.messages.error` | |
| **Hook: PreToolUse** | `before_reasoning:` (partial) | Limited mapping |
| **Hook: PostToolUse** | `after_reasoning:` (partial) | Limited mapping |
| **MCP server tools** | Actions with `externalService://` or `api://` targets | |
| Sub-agent conditions/routing | `available when` guards + `if/else` + `transition to` | |

## Conversion Pipeline (Revised)

```
Input Files (Claude Code conventions):
  CLAUDE.md                    -> system.instructions + config
  .claude/agents/topic-a.md   -> topic topic_a: { ... }
  .claude/agents/topic-b.md   -> topic topic_b: { ... }
  .claude/skills/skill-x/     -> actions: { target: "flow://..." }
  .claude/settings.json hooks  -> before_reasoning/after_reasoning (partial)

                    |
                    v

[Parser Module]
  - Parse CLAUDE.md (extract role, company, instructions)
  - Parse each sub-agent .md (YAML frontmatter + markdown body)
  - Parse each SKILL.md (YAML frontmatter + instructions)
  - Parse settings.json (extract hooks)

                    |
                    v

[Intermediate Representation]
  AgentDefinition {
    config: { developer_name, agent_type, default_agent_user }
    system: { instructions, welcome, error }
    variables: [ { name, type, modifier, default, source? } ]
    topics: [
      {
        name, description, scope,
        instructions: [ ... ],
        actions: [ { name, description, target?, inputs?, outputs? } ],
        transitions: [ { target_topic, condition? } ]
      }
    ]
    start_agent: { name, description, default_topic }
  }

                    |
                    v

[Generator Module]
  - Generate .agent file content
  - Generate bundle-meta.xml
  - Generate any supporting Flow/Apex stubs (if needed)
  - Place in aiAuthoringBundles/<AgentName>/

                    |
                    v

Output:
  force-app/main/default/aiAuthoringBundles/
    MyAgent/
      MyAgent.agent
      MyAgent.bundle-meta.xml

                    |
                    v

[Deployment]
  sf agent validate authoring-bundle --api-name MyAgent -o ORG
  sf agent publish authoring-bundle --api-name MyAgent -o ORG
  sf agent activate --api-name MyAgent -o ORG
```

## What Gets Lost (Lossy Conversion)

These Claude Code features have no Agent Script equivalent:
- `model` selection
- `permissionMode`
- `maxTurns`
- `isolation: worktree`
- `memory` persistence
- `background` execution
- Fine-grained tool permissions
- Most hook types (only PreToolUse/PostToolUse partially map)

## What Gets Added (Agentforce-specific)

The converter should add sensible defaults for:
- `default_agent_user` (prompt user or detect from org)
- `agent_type` (default to `AgentforceServiceAgent`)
- Required linked variables (EndUserId, RoutableId, ContactId)
- `language` block (default en_US)
- `connection` block (if escalation topics exist)
- Proper `start_agent` entry point with routing

## Example: End-to-End Conversion

### Input: CLAUDE.md
```markdown
You are a customer support agent for Acme Corp.
Be helpful, professional, and concise.
Always verify the customer before making changes.
```

### Input: .claude/agents/order-support.md
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

### Input: .claude/agents/general-faq.md
```yaml
---
name: general-faq
description: Answers general questions about Acme Corp
tools: SearchKnowledge
---
Answer general questions about our company.
If you don't know the answer, say so honestly.
```

### Output: AcmeAgent.agent
```yaml
system:
   messages:
      welcome: "Hello! Welcome to Acme Corp support. How can I help?"
      error: "Sorry, something went wrong. Please try again."
   instructions: "You are a customer support agent for Acme Corp. Be helpful, professional, and concise. Always verify the customer before making changes."

config:
   developer_name: "AcmeAgent"
   agent_description: "Customer support agent for Acme Corp"
   agent_type: "AgentforceServiceAgent"
   default_agent_user: "agent@acme.com"

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
         go_orders: @utils.transition to @topic.order_support
            description: "Handle order inquiries"
         go_faq: @utils.transition to @topic.general_faq
            description: "Answer general questions"

topic order_support:
   description: "Handles order inquiries and returns"
   reasoning:
      instructions: ->
         | Help customers with their orders.
         | Always look up the order before processing a return.
         | If the order is older than 30 days, escalate to a manager.
      actions:
         check_order: @actions.check_order_status
            description: "Check the status of an order"
         process_return: @actions.process_return
            description: "Process a return request"
         back_to_menu: @utils.transition to @topic.entry
            description: "Return to main menu"

topic general_faq:
   description: "Answers general questions about Acme Corp"
   reasoning:
      instructions: ->
         | Answer general questions about our company.
         | If you don't know the answer, say so honestly.
      actions:
         search: @actions.search_knowledge
            description: "Search knowledge base"
         back_to_menu: @utils.transition to @topic.entry
            description: "Return to main menu"
```
