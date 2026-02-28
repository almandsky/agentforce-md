# Agent Script DSL (.agent file) Reference

Source: `Jaganpro/sf-skills` - `skills/sf-ai-agentscript/`

## Critical Discovery

There are **TWO deployment paths** for Agentforce agents:

### Path 1: Traditional Metadata API (XML)
- Multiple XML files: Bot, BotVersion, GenAiPlannerBundle, GenAiPlugin, GenAiFunction
- Deployed via `sf project deploy start`
- More verbose, granular control

### Path 2: Agent Script / Authoring Bundle (SINGLE .agent FILE)
- Single `.agent` file + `bundle-meta.xml`
- Deployed via `sf agent publish authoring-bundle`
- Simpler, human-readable, version-control friendly
- **THIS IS THE TARGET FOR OUR POC**

## Bundle Structure

```
force-app/main/default/aiAuthoringBundles/
  MyAgent/
    MyAgent.agent           # Agent Script file (REQUIRED)
    MyAgent.bundle-meta.xml # Metadata XML (REQUIRED)
```

### bundle-meta.xml (always the same)
```xml
<?xml version="1.0" encoding="UTF-8"?>
<AiAuthoringBundle xmlns="http://soap.sforce.com/2006/04/metadata">
    <bundleType>AGENT</bundleType>
</AiAuthoringBundle>
```

## .agent File Block Structure

Required order:
```
config:        # 1. Required: Agent metadata
variables:     # 2. Optional: State management
system:        # 3. Required: Global messages and instructions
connection:    # 4. Optional: Escalation routing
knowledge:     # 5. Optional: Knowledge base config
language:      # 6. Optional: Locale settings
start_agent:   # 7. Required: Entry point (exactly one)
topic:         # 8. Required: Conversation topics (1+)
```

## Block Definitions

### config: (Required)
```yaml
config:
  developer_name: "my_agent"
  agent_description: "Agent purpose"
  agent_type: "AgentforceServiceAgent"  # or AgentforceEmployeeAgent
  default_agent_user: "agent_user@00dxx000001234.ext"
```

### system: (Required)
```yaml
system:
  messages:
    welcome: "Hello! How can I help?"
    error: "Sorry, something went wrong."
  instructions: "You are a helpful assistant."
```

### variables: (Optional)
```yaml
variables:
  # Mutable: Read/write state
  counter: mutable number = 0
  verified: mutable boolean = False
  items: mutable list[string] = []
  name: mutable string = ""

  # Linked: Read-only from external source
  session_id: linked string
    source: @session.sessionID
  customer_id: linked string
    source: @context.customerId
```

Variable types: `string`, `number`, `boolean`, `object`, `date`, `id`, `list[T]`
Booleans: `True`/`False` (capitalized!)

### connection: (Optional, Service Agents only)
```yaml
connection messaging:
   outbound_route_type: "OmniChannelFlow"
   outbound_route_name: "flow://Route_from_Agent"
   escalation_message: "Connecting you with a specialist."
   adaptive_response_allowed: False
```

### language: (Optional)
```yaml
language:
  default_locale: "en_US"
  additional_locales: ""
  all_additional_locales: False
```

### start_agent: (Required, exactly one)
```yaml
start_agent entry:
  description: "Entry point"
  reasoning:
    instructions: ->
      | Greet the user and route appropriately.
    actions:
      go_main: @utils.transition to @topic.main
        description: "Go to main topic"
```

### topic: (Required, one or more)
```yaml
topic my_topic:
  description: "Handles X requests"

  # Optional: topic-level action definitions (Level 1)
  actions:
    get_order:
      description: "Retrieves order info"
      inputs:
        order_id: string
          description: "Order number"
      outputs:
        status: string
          description: "Order status"
      target: "flow://Get_Order_Details"

  reasoning:
    instructions: ->
      # Conditional logic (resolves before LLM)
      if @variables.verified == True:
        | Welcome back!
      else:
        | Please verify your identity.

      # Inline action execution
      run @actions.load_data
        with customer_id = @variables.customer_id
        set @variables.data = @outputs.result

      # Variable injection
      | Risk score: {!@variables.risk_score}

      # Deterministic transition
      if @variables.attempts >= 3:
        transition to @topic.escalation

    # Action invocations (Level 2)
    actions:
      lookup: @actions.get_order
        with order_id = ...
        set @variables.status = @outputs.status

      go_back: @utils.transition to @topic.main
        description: "Return to main"

      escalate_now: @utils.escalate
        description: "Transfer to human"
```

## Instruction Syntax

| Pattern | Purpose | Example |
|---------|---------|---------|
| `instructions: \|` | Multi-line text (no logic) | Simple prompts |
| `instructions: ->` | Procedural with logic | Conditionals, actions |
| `\| text` | Literal text for LLM | `\| Hello!` |
| `if @variables.x:` | Conditional | `if @variables.verified == True:` |
| `else:` | Alternative path | |
| `run @actions.x` | Execute action | `run @actions.load_data` |
| `set @var = @outputs.y` | Capture output | |
| `{!@variables.x}` | Variable injection | `Risk: {!@variables.risk}` |
| `transition to @topic.x` | Deterministic jump | |
| `available when` | Action visibility guard | `available when @variables.verified == True` |
| `with param=...` | LLM slot-filling | `with query=...` |
| `with param=@variables.x` | Bound value | `with id=@variables.customer_id` |

## Two-Level Action System

```
Level 1: ACTION DEFINITION (in topic's `actions:` block)
   → Has target:, inputs:, outputs:, description:
   → Defines WHAT to call

Level 2: ACTION INVOCATION (in reasoning.actions: block)
   → References Level 1 via @actions.name
   → Uses with/set (NOT inputs:/outputs:)
   → Defines HOW to call it
```

## Action Target Protocols

| Protocol | Use |
|----------|-----|
| `flow://FlowName` | Invoke a Flow |
| `apex://ClassName` | Invoke @InvocableMethod |
| `prompt://TemplateName` | Invoke Prompt Template |
| `api://` | REST API callout |
| `retriever://` | RAG knowledge search |
| `externalService://` | Third-party API via Named Credential |

## Utility Actions
- `@utils.transition to @topic.x` - Navigate to topic
- `@utils.escalate` - Hand off to human
- `@utils.setVariables` - Set multiple variables

## Transition vs Delegation

| Syntax | Behavior | Returns? |
|--------|----------|----------|
| `@utils.transition to @topic.X` | Permanent handoff | No |
| `@topic.X` (in reasoning.actions) | Delegation | Yes |
| `transition to @topic.X` (inline) | Deterministic jump | No |

## Expression Operators

- Comparison: `==`, `!=`, `<`, `<=`, `>`, `>=`, `is`, `is not`
- Logical: `and`, `or`, `not`
- Arithmetic: `+`, `-` (NO *, /, %)
- Access: `.` (property), `[]` (index)

## Lifecycle Hooks

```yaml
topic main:
  before_reasoning:
    set @variables.turn_count = @variables.turn_count + 1
    if @variables.needs_redirect == True:
      transition to @topic.redirect

  reasoning:
    instructions: ->
      | Turn {!@variables.turn_count}: How can I help?

  after_reasoning:
    set @variables.interaction_logged = True
```

## Naming Rules
- Only letters, numbers, underscores
- Must begin with a letter
- Max 80 characters
- developer_name must match folder name (case-sensitive)

## Key Constraints
- No `else if` keyword (use compound `if A and B:`)
- No nested `if` inside `else:`
- Booleans: `True`/`False` (capitalized)
- Never mix tabs and spaces
- Exactly one `start_agent` block
- `...` is for LLM slot-filling only, not defaults
- Always use `@actions.` prefix for action references
- Reserved field names: description, label, is_required, is_displayable, is_used_by_planner

## CLI Commands

```bash
# Validate
sf agent validate authoring-bundle --api-name MyAgent -o TARGET_ORG --json

# Publish (does NOT activate)
sf agent publish authoring-bundle --api-name MyAgent -o TARGET_ORG --json

# Activate (make live)
sf agent activate --api-name MyAgent -o TARGET_ORG

# Deactivate (take offline)
sf agent deactivate --api-name MyAgent -o TARGET_ORG

# Preview (simulated)
sf agent preview start --api-name MyAgent -o TARGET_ORG --json

# Preview (live)
sf agent preview start --api-name MyAgent --use-live-actions -o TARGET_ORG --json

# Retrieve from org
sf project retrieve start --metadata Agent:MyAgent -o TARGET_ORG
```

## Full Deployment Lifecycle
```
Validate -> Publish -> Activate
(Update: Deactivate -> Re-publish -> Re-activate)
```

## Complete Example: Verification Gate Agent

```yaml
system:
   messages:
      welcome: "Welcome! I'll need to verify your identity."
      error: "Something went wrong. Let me try again."
   instructions: "You are a secure customer service agent."

config:
   developer_name: "SecureAgent"
   agent_description: "Agent with verification gate"
   agent_type: "AgentforceServiceAgent"
   default_agent_user: "agent@yourorg.com"

variables:
   customer_verified: mutable boolean = False
   failed_attempts: mutable number = 0
   customer_id: linked string
      source: @session.customerId

start_agent entry:
   description: "Entry point - routes through verification"
   reasoning:
      instructions: |
         Welcome the customer and route to verification.
      actions:
         start: @utils.transition to @topic.identity_verification

topic identity_verification:
   description: "Verify customer identity"
   reasoning:
      instructions: ->
         if @variables.failed_attempts >= 3:
            | Too many failed attempts. Transferring to human.
            transition to @topic.escalation
         if @variables.customer_verified == True:
            | Identity verified! How can I help?
         if @variables.customer_verified == False:
            | Please verify your identity.
      actions:
         verify: @actions.verify_email
            set @variables.customer_verified = @outputs.verified
         go_to_account: @utils.transition to @topic.account
            available when @variables.customer_verified == True

topic account:
   description: "Account management (requires verification)"
   reasoning:
      instructions: ->
         if @variables.customer_verified == False:
            transition to @topic.identity_verification
         | What would you like to do with your account?

topic escalation:
   description: "Escalate to human agent"
   reasoning:
      instructions: |
         Transferring you to a human agent.
      actions:
         handoff: @utils.escalate
```
