# Hooks → Agent Script: Analysis and Conversion Design

## Overview

Claude Code supports a hooks system that fires shell commands, HTTP calls, or prompt
injections on developer-workflow events. Agentforce Agent Script has `reasoning` and
`after_reasoning` blocks that run deterministic logic at runtime inside a deployed agent.
These two systems look superficially similar but solve fundamentally different problems.

This document maps the overlap, identifies what cannot be converted, and documents the
patterns used by the converter.

### The key structural parallel

A **Claude Code sub-agent** maps to an **Agentforce topic** — same concept, same scope.
Because of this, the correct analog for Agent Script's per-topic lifecycle blocks is at
the **sub-agent level**, not the agent level:

| Claude Code | Agentforce Agent Script | Scope |
|---|---|---|
| Sub-agent body (tools, reasoning) | `topic … reasoning:` block | per sub-agent / topic |
| `SubagentStop` — sub-agent finishes | `topic … after_reasoning:` block | per sub-agent / topic |
| `Stop` — full agent session ends | *(no equivalent)* | agent level |

`SubagentStop` is therefore the correct hook analog for `after_reasoning`, not `Stop`.
`Stop` fires at session end; `after_reasoning` fires after each topic turn — a finer grain
that matches the sub-agent lifecycle, not the session lifecycle.

---

## Agent Script Lifecycle Blocks: Supported vs Not

| Block | Supported in Agent Builder | Purpose |
|---|---|---|
| `reasoning` | Yes | LLM reasoning + named action invocations |
| `after_reasoning` | Yes | Deterministic directives run after LLM responds |
| `before_reasoning` | **No** | Defined in grammar, not supported in Agent Builder |

### `reasoning` block

The `reasoning` block handles the LLM turn. It has two sub-elements:

1. `instructions:` — the instruction body for the LLM (and optionally, inline directives)
2. `actions:` — named action invocations using name-binding syntax

#### `instructions: |` vs `instructions: ->`

There are two instruction modes:

**Pipe mode (`instructions: |`)** — pure LLM instruction lines, each prefixed with `|`:

```
reasoning:
    instructions: |
        | Help the customer with their order.
        | Always look up the order before processing a return.
```

**Arrow mode (`instructions: ->`)** — a fully procedural mixed-mode block that interleaves
deterministic directives with `|` LLM instruction lines. This is the more powerful form:

```
reasoning:
    instructions: ->
        set @variables.num_turns = @variables.num_turns + 1

        run @actions.get_delivery_date
            with order_ID=@variables.order_ID
            set @variables.updated_delivery_date=@outputs.delivery_date

        | Tell the user that the expected delivery date for order number {!@variables.order_ID} is {!@variables.updated_delivery_date}

        run @actions.check_if_late
            with order_ID=@variables.order_ID
            with delivery_date=@variables.updated_delivery_date
            set @variables.is_late = @outputs.is_late

        if @variables.is_late == True:
            | Apologize to the customer for the delay in receiving their order.
```

**Directives available inside `instructions: ->`:**

| Directive | Example | Purpose |
|---|---|---|
| `set` | `set @variables.num_turns = @variables.num_turns + 1` | Variable assignment (supports arithmetic) |
| `run @actions.X` | `run @actions.get_delivery_date` | Inline action call (directive syntax) |
| `\| text` | `\| Tell the user... {!@variables.X}` | LLM instruction line with variable interpolation |
| `if condition:` block | `if @variables.is_late == True:` | Conditional block containing `\|` lines |

**Key differences from `reasoning.actions:` (name-binding syntax):**

- `run @actions.X` inside `instructions: ->` uses **directive syntax** (no spaces around `=` in `with`)
- `name: @actions.X` inside `actions:` uses **name-binding syntax** (spaces around `=` in `with`)
- Variable interpolation in `|` lines uses `{!@variables.X}` syntax
- Arithmetic is supported: `@variables.num_turns + 1`

#### Full topic example with arrow mode and `after_reasoning`

```
topic Order_Management:
    description: "Handles order inquiries."
    reasoning:
        instructions: ->
            set @variables.num_turns = @variables.num_turns + 1

            run @actions.get_delivery_date
                with order_ID=@variables.order_ID
                set @variables.updated_delivery_date=@outputs.delivery_date

            | Tell the user that the expected delivery date for order number {!@variables.order_ID} is {!@variables.updated_delivery_date}

            run @actions.check_if_late
                with order_ID=@variables.order_ID
                with delivery_date=@variables.updated_delivery_date
                set @variables.is_late = @outputs.is_late

            if @variables.is_late == True:
                | Apologize to the customer for the delay in receiving their order.
    after_reasoning:
        if @variables.num_turns > 5:
            transition to @topic.escalate_order
```

#### `reasoning.actions:` name-binding syntax (for reference)

```
reasoning:
    actions:
        check_order: @actions.CheckOrderStatus
            with orderId = @variables.OrderId
            set @variables.orderStatus = @outputs.status
            available when @variables.isVerified == True
```

### `after_reasoning` block

`after_reasoning` runs **after the LLM has produced its response** for the current turn.
It uses **directive syntax** — different from `reasoning.actions:`:

```
after_reasoning:
    if @variables.customer_email != "" and @variables.customer_name != "":
        run @actions.Verify_Customer_Identity
            with email=@variables.customer_email
            with name=@variables.customer_name
            set @variables.customer_verified = @outputs.customer_found
            set @variables.customer_id = @outputs.customer_id

    if @variables.customer_verified:
        run @actions.Get_Customer_Case_History
            with customer_id=@variables.customer_id
            set @variables.case_count = @outputs.previous_cases

    if @variables.case_type != "":
        transition to @topic.case_creation
```

**Syntax differences across the three execution contexts:**

| Feature | `reasoning.actions:` block | `instructions: ->` block | `after_reasoning` block |
|---|---|---|---|
| Define action call | `name: @actions.Foo` (name-binding) | `run @actions.Foo` (directive) | `run @actions.Foo` (directive) |
| Input binding | `with param = @variables.X` (spaces around `=`) | `with param=@variables.X` (no spaces) | `with param=@variables.X` (no spaces) |
| Output capture | `set @variables.X = @outputs.Y` | `set @variables.X = @outputs.Y` | `set @variables.X = @outputs.Y` |
| Variable assign | not available | `set @variables.X = expr` (arithmetic ok) | `set @variables.X = expr` |
| LLM instruction line | not applicable | `\| text {!@variables.X}` | not applicable |
| Conditionals | `available when @variables.X` (per invocation) | `if @variables.X condition:` (block) | `if @variables.X condition:` (block) |
| Routing | `if condition: transition to @topic.Y` (post-branch) | not typically used | `transition to @topic.Y` (directive) |
| When it runs | LLM decides when to invoke | Before LLM generates reply | After LLM has already replied |

**Key behaviours of `after_reasoning`:**
- Runs after the LLM's response has already been sent to the user for that turn.
- Can run actions, capture outputs into variables, and trigger transitions.
- Actions inside are conditional — wrap in `if` to control when they fire.
- Transitions here move to the next topic *on the next turn*.
- Cannot affect what the LLM said in the current turn.

---

## System Comparison

### Claude Code Hooks

Hooks are defined in `.claude/settings.json`. They fire on lifecycle events during a
Claude Code **development** session.

**Execution mechanisms:**
- `command` — Shell command; receives event data as JSON on stdin.
- `url` — HTTP POST to an endpoint.
- `prompt` — Inject text into the LLM's context (`UserPromptSubmit` only).

**Relevant event types:**

| Event | When it fires | Scope |
|---|---|---|
| `UserPromptSubmit` | User sends a message | agent |
| `PreToolCall` | Before Claude calls any tool | agent |
| `PostToolCall` | After a tool returns | agent |
| `Stop` | Full agent session ends | agent |
| `SubagentStop` | A sub-agent finishes its turn | **sub-agent** |
| `PreCompact` | Before context compaction | agent |
| `Notification` | When a notification is sent | agent |

**Key properties:**
- Run on the **developer's machine** at development time, not at agent runtime.
- Can read/write files, run git commands, call APIs, etc.
- `PreToolCall` can block tool execution (`{"decision": "block"}`).
- `PostToolCall` can read output but cannot modify it.
- Not deployed to Salesforce — not part of the agent's runtime.

### Agent Script (runtime, in org)

| Block | Scope | Trigger | Mechanism |
|---|---|---|---|
| `reasoning` (pipe mode `\|`) | topic | LLM turn | Pure `\|` instruction lines + named action invocations |
| `reasoning` (arrow mode `->`) | topic | LLM turn | Mixed: `set`, `run`, `if`, and `\|` instruction lines interleaved |
| `after_reasoning` | topic | After LLM responds | Directives: `if`, `run`, `set`, `transition to` |

Both run on the **Salesforce platform** at runtime inside the deployed agent.

**Arrow mode is the more powerful form** — it makes the reasoning block procedural: actions
run in a deterministic sequence, their outputs can be inspected with `if` to vary what the
LLM is told, and variable state is updated before the LLM generates its reply.

---

## Conceptual Mismatch Matrix

| Dimension | Claude Code hooks | Agent Script |
|---|---|---|
| **Execution environment** | Developer's machine | Salesforce org (runtime) |
| **When it runs** | During development sessions | Every conversation turn |
| **Execution mechanism** | Shell / HTTP / prompt injection | Action invocations + directives |
| **Pre-tool hook (any tool)** | `PreToolCall` fires for all tools | `available when` per specific action only |
| **Post-tool hook (any tool)** | `PostToolCall` fires for all tools | `set`/`if`/`transition` per specific action (reasoning); or `after_reasoning` block |
| **Can block execution** | Yes — `{"decision": "block"}` | `available when` on each invocation |
| **Can transform inputs** | Yes — shell can mutate and re-emit | No — bind from declared sources only |
| **Sub-agent finishes** (`SubagentStop`) | `SubagentStop` event | `after_reasoning` block (per-topic) |
| **Full session ends** (`Stop`) | `Stop` event | *(no equivalent — session end has no runtime hook)* |
| **Deployed to org** | No | Yes |

---

## What CAN Be Converted

### 1. Per-action bindings — `reasoning` block (implemented)

| Claude Code hook pattern | Agent Script equivalent | agentforce-md input |
|---|---|---|
| `PreToolCall` — bind variable to specific tool input | `with param = @variables.X` | `bindings.ToolName.with` |
| `PreToolCall` — LLM slot-fills input from conversation | `with param = ...` | `bindings.ToolName.with` (value `"..."`) |
| `PreToolCall` — block tool if condition false | `available when @variables.X==True` | `agentforce.available_when` |
| `PostToolCall` — capture output from specific tool | `set @variables.X = @outputs.Y` | `bindings.ToolName.set` |
| `PostToolCall` — route based on specific tool output | `if @variables.X: transition to @topic.Y` | `bindings.ToolName.after` |

### 2. `SubagentStop` → `after_reasoning` (implemented)

`SubagentStop` fires when a sub-agent finishes its turn. Because a **sub-agent = topic**,
the direct Agent Script equivalent is `after_reasoning` — it runs after the topic's LLM
has responded, at exactly the point where the sub-agent "stops" for that turn.

Typical patterns: audit logging, deferred action execution, conditional routing to the
next topic after the LLM has responded.

```
after_reasoning:
    if @variables.caseDescriptionCollected:
        run @actions.create_case
            with subject=@variables.caseSubject
            with description=@variables.caseDescription
            set @variables.caseId = @outputs.caseId

    if @variables.caseId != "":
        transition to @topic.case_confirmation
```

**agentforce-md input** (sub-agent `.md` frontmatter):

```yaml
agentforce:
  after_reasoning:
    - if: "@variables.caseDescriptionCollected"
      run: CreateCase
      with:
        subject: "@variables.caseSubject"
        description: "@variables.caseDescription"
      set:
        "@variables.caseId": "@outputs.caseId"
    - if: "@variables.caseId != \"\""
      transition_to: "case-confirmation"
```

---

## What CANNOT Be Converted

### Shell command hooks
Agent Script has no code execution. Developer-workflow only. **Drop with a warning.**

### HTTP endpoint hooks
Agent Script cannot make arbitrary HTTP calls. **Not convertible.**

### Tool input mutation in `PreToolCall`
Claude Code can intercept and rewrite a tool's input JSON. Agent Script binds from
declared variable sources only — no transformation. **Not convertible.**

### Blocking ALL tools with a single `PreToolCall`
A single `PreToolCall` in Claude Code covers every tool. Agent Script has no global action
guard — `available when` is per-action-invocation only.

**Workaround:** Use `agentforce.available_when` to block topic entry entirely, and add
`available when @variables.isReady==True` to each action invocation inside the topic.

### `Stop` — full session end
`Stop` fires when the entire agent session ends. `after_reasoning` fires per topic turn,
not at session end — the granularities don't match. **Not convertible.**

### `UserPromptSubmit`, `PreCompact`, `Notification`
Development-session events with no runtime equivalent. **Not convertible.**

---

## Conversion Decision Table

| Intent | Approach |
|---|---|
| Bind a variable to an action's input | `agentforce.bindings.ToolName.with` |
| Let LLM slot-fill an action's input | `agentforce.bindings.ToolName.with` (value `"..."`) |
| Capture an action's output into a variable | `agentforce.bindings.ToolName.set` |
| Route to another topic based on action output | `agentforce.bindings.ToolName.after` |
| Block routing to topic until condition is true | `agentforce.available_when` |
| Run action / route conditionally after sub-agent turn (`SubagentStop`) | `agentforce.after_reasoning` (implemented) |
| Run shell command / HTTP call as hook | **Not convertible** |
| Mutate tool inputs | **Not convertible** |
| Block ALL actions with one guard | **Partial** — `available_when` on each invocation |
| React to `Stop` (session end) / `UserPromptSubmit` / `PreCompact` | **Not convertible** — dev-session events or wrong granularity |

---

## Implementation Notes for `after_reasoning`

Implemented across three layers:

1. **IR** (`scripts/ir/models.py`) — `AfterReasoningDirective` dataclass holds:
   `condition`, `run` (action ref), `with_bindings`, `set_bindings`, `transition_to`.
   `Topic` has `after_reasoning_directives: list[AfterReasoningDirective]`.

2. **Parser** (`scripts/parser/subagent.py`) — `_parse_after_reasoning()` reads
   `agentforce.after_reasoning` list from sub-agent frontmatter. Converts `run:` tool
   names via `tool_name_to_snake`, `transition_to:` via `kebab_to_snake`.

3. **Generator** (`scripts/generator/agent_script.py`) — `_render_after_reasoning()`
   emits the block after `reasoning:` using **directive syntax**:
   - `run @actions.foo` (not `name: @actions.foo`)
   - `with param=value` (no spaces around `=`)
   - `set @variables.x = @outputs.y` (spaces around `=`)
   - blank lines between directives
