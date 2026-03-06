---
name: agentforce-optimize
description: Analyze Agentforce session traces from Data Cloud, reproduce issues with live preview, and improve the Agent Script
allowed-tools: Bash Read Write Edit Glob
argument-hint: "<org-alias> [--project-root <path>] [--session-id <id>] [--days <n>]"
---

# Agentforce Optimize

Improve Agentforce agents using real conversation data from the Session Trace Data Model (STDM) in Data Cloud.

**Three-phase workflow:**
- **Observe** — Deploy helper class, query STDM sessions, reconstruct conversations, identify issues
- **Reproduce** — Use `sf agent preview` to simulate problematic conversations live
- **Improve** — Edit agent markdown files, re-convert, deploy, verify

---

## Routing

Gather these inputs before starting:

- **Org alias** (required)
- **Agent API name** (required for preview and deploy; ask if not provided)
- **Project root** (optional, default `.`) — directory containing CLAUDE.md and `.claude/agents/`
- **Session IDs** (optional) — analyze specific sessions; if absent, query last 7 days
- **Days to look back** (optional, default 7)

Determine intent from user input:

- **No specific action** → run all three phases: Observe → surface issues → ask if user wants to Reproduce and/or Improve
- **"analyze" / "sessions" / "what's wrong"** → Phase 1 only, then suggest next steps
- **"reproduce" / "test" / "preview"** → Phase 2 (run Phase 1 first if no issues in hand)
- **"fix" / "improve" / "update"** → Phase 3 (run Phase 1 first if no issues in hand)

---

## Phase 0: Discover Data Space

Before running any STDM query, determine the correct Data Cloud Data Space API name.

```bash
sf api request rest "/services/data/v66.0/ssot/data-spaces" -o <org>
```

Note: `sf api request rest` is a beta command — do not add `--json` (that flag is unsupported and causes an error).

The response shape is:
```json
{
  "dataSpaces": [
    {
      "id": "0vhKh000000g3DjIAI",
      "label": "default",
      "name": "default",
      "status": "Active",
      "description": "Your org's default data space."
    }
  ],
  "totalSize": 1
}
```

The `name` field is the API name to pass to `AgentforceOptimizeService`.

**Decision logic:**
- If the command fails (e.g. 404 or permission error), fall back to `'default'` and note it as an assumption.
- Filter to only `status: "Active"` entries.
- If exactly one active Data Space exists, use it automatically and confirm to the user: "Using Data Space: `<name>`".
- If multiple active Data Spaces exist, show the list (label + name) and ask the user which to use.

Store the selected `name` value as `DATA_SPACE` for all subsequent steps.

---

## Phase 1: Observe — Query STDM

### 1.0 Deploy helper class (once per org)

`AgentforceOptimizeService` is a bundled Apex class that queries all five STDM DMOs and returns clean JSON. Deploy it once; subsequent runs reuse the deployed class.

**Step 1 — copy the class into the project:**

```bash
# Ensure the classes directory exists
mkdir -p <project-root>/force-app/main/default/classes

# Copy from the installed skill location
cp ~/.claude/skills/agentforce-optimize/apex/AgentforceOptimizeService.cls \
   <project-root>/force-app/main/default/classes/
cp ~/.claude/skills/agentforce-optimize/apex/AgentforceOptimizeService.cls-meta.xml \
   <project-root>/force-app/main/default/classes/
```

If the skill was installed from a local clone rather than GitHub, use the clone path instead:
```bash
cp <agentforce-md-repo>/.claude/skills/agentforce-optimize/apex/AgentforceOptimizeService.cls \
   <project-root>/force-app/main/default/classes/
cp <agentforce-md-repo>/.claude/skills/agentforce-optimize/apex/AgentforceOptimizeService.cls-meta.xml \
   <project-root>/force-app/main/default/classes/
```

**Step 2 — ensure `sfdx-project.json` exists** (the `agentforce-convert` skill creates this automatically; if absent, create a minimal one):

```json
{
  "packageDirectories": [{ "path": "force-app", "default": true }],
  "sourceApiVersion": "66.0"
}
```

**Step 3 — deploy to the org:**

```bash
sf project deploy start \
  --metadata ApexClass:AgentforceOptimizeService \
  -o <org>
```

Confirm the deploy succeeds before proceeding. If it fails with a compile error, check that the org has Data Cloud enabled (the `ConnectApi.CdpQuery` namespace requires Data Cloud).

**Skip this step if `AgentforceOptimizeService` is already deployed** — check with:
```bash
sf data query \
  --query "SELECT Id, Name FROM ApexClass WHERE Name = 'AgentforceOptimizeService'" \
  -o <org> --json
```

### 1.1 Find sessions

If the user provided session IDs, skip to 1.2. Otherwise, write `/tmp/stdm_find.apex` and run it (substitute actual ISO 8601 UTC timestamps, DATA_SPACE, and AGENT_API_NAME):

```apex
String result = AgentforceOptimizeService.findSessions(
    'DATA_SPACE',
    'START_ISO',
    'END_ISO',
    20,
    'AGENT_API_NAME'
);
System.debug('STDM_RESULT:' + result);
```

```bash
sf apex run --file /tmp/stdm_find.apex -o <org> --json
```

Parse: find `STDM_RESULT:` in `result.logs`, extract the JSON array that follows on that line.

The result is a JSON array of `SessionSummary` objects:
```json
[
  {
    "session_id": "...", "start_time": "...", "end_time": "...",
    "channel": "...", "duration_ms": 12345,
    "end_type": "USER_ENDED"
  }
]
```

- `end_time` and `duration_ms` may be `null` when the session has no recorded end event — this is a normal STDM data quality gap, not an error.
- `end_type` values: `USER_ENDED`, `AGENT_ENDED`, or `null` (in-progress or not recorded). A `null` `end_type` may indicate an abandoned session.

**How agent filtering works** — `findSessions` tries two strategies in order:

1. **Direct** (preferred): `ssot__AiAgentApiName__c = agentApiName` on `ssot__AiAgentSessionParticipant__dlm` — no SOQL needed, uses a dedicated DMO field. Resolves in a single Data Cloud query.
2. **Planner fallback**: If strategy 1 returns no rows, SOQL: `SELECT Id FROM GenAiPlannerDefinition WHERE MasterLabel = :agentApiName` → `ssot__ParticipantId__c IN (...)`. Both 15-char and 18-char ID formats are included (the DMO stores them inconsistently). If both strategies return empty, the query falls back to all sessions in the date range.

**If the debug log shows `Agent not found: <name>`**, no `GenAiPlannerDefinition` matched — verify the agent name with:
```bash
sf data query --query "SELECT Id, MasterLabel, DeveloperName FROM GenAiPlannerDefinition" -o <org> --json
```
Use the exact `MasterLabel` value (not `DeveloperName`). `MasterLabel` matches the agent's display name; `DeveloperName` has a version suffix (e.g. `TeslaSupportAgent_v1`).

**If the debug log shows a warning about no sessions for the agent**, both strategies returned empty — the agent may have no sessions in this date range, or Data Cloud ingestion may be delayed. The query falls back to all sessions in the date range.

### 1.2 Get conversation details

For up to 5 sessions (most recent first), write `/tmp/stdm_details.apex` and run it (substitute session IDs and DATA_SPACE):

```apex
String result = AgentforceOptimizeService.getMultipleConversationDetails(
    'DATA_SPACE',
    new List<String>{ 'SESSION_ID_1', 'SESSION_ID_2' }
);
System.debug('STDM_RESULT:' + result);
```

```bash
sf apex run --file /tmp/stdm_details.apex -o <org> --json
```

Parse: find `STDM_RESULT:` in `result.logs`, extract the JSON array. Each element is a `ConversationData` object:

```json
{
  "session_id": "...",
  "start_time": "...", "end_time": "...", "channel": "...",
  "duration_ms": 45000,
  "end_type": "USER_ENDED",
  "session_variables": "{...}",
  "turn_count": 3,
  "action_error_count": 1,
  "turns": [
    {
      "interaction_id": "...",
      "topic": "CheckOrderStatus",
      "start_time": "...", "end_time": "...", "duration_ms": 8000,
      "telemetry_trace_id": "...",
      "messages": [
        { "message_type": "Input",  "text": "Where is my order?", "sent_at": "..." },
        { "message_type": "Output", "text": "I found your order...", "sent_at": "..." }
      ],
      "steps": [
        { "step_type": "TOPIC_STEP",  "name": "CheckOrderStatus" },
        { "step_type": "LLM_STEP",    "name": "...", "duration_ms": 3200,
          "generation_id": "abc123", "gateway_request_id": "def456" },
        { "step_type": "ACTION_STEP", "name": "GetOrderDetails",
          "input": "{...}", "output": "{...}", "error": null,
          "pre_vars": "{...}", "post_vars": "{...}", "duration_ms": 1500 }
      ]
    }
  ]
}
```

Key new fields:
- `end_type` — how the session ended (`USER_ENDED`, `AGENT_ENDED`, or null)
- `session_variables` — final variable snapshot for the session (null when absent)
- `telemetry_trace_id` — distributed tracing ID for this turn (null when absent)
- `generation_id` / `gateway_request_id` on `LLM_STEP` — pass these step IDs to `getLlmStepDetails()` to retrieve the actual LLM prompt and response (useful for diagnosing LOW instruction adherence)

Treat any `null` field as absent/unknown. The `"NOT_SET"` sentinel is stripped by the service class before returning.

### 1.2b Get LLM prompt/response (optional, for LOW adherence)

When a session shows `TRUST_GUARDRAILS_STEP` with `'value': 'LOW'`, use `getLlmStepDetails()` to retrieve the actual LLM prompt and response for the associated `LLM_STEP` records. Pass the `step_id` values from steps where `step_type == "LLM_STEP"` and `generation_id != null`.

```apex
String result = AgentforceOptimizeService.getLlmStepDetails(
    'DATA_SPACE',
    new List<String>{ 'STEP_ID_1', 'STEP_ID_2' }
);
System.debug('STDM_RESULT:' + result);
```

```bash
sf apex run --file /tmp/stdm_llm.apex -o <org> --json
```

Returns a JSON array of `LlmStepDetail` objects:
```json
[
  {
    "step_id": "...",
    "interaction_id": "...",
    "step_name": "...",
    "prompt": "System: You are a Tesla support agent...\nUser: I want to schedule a test drive",
    "llm_response": "I'd be happy to help you schedule a test drive...",
    "generation_id": "...",
    "gateway_request_id": "..."
  }
]
```

- `prompt` — full prompt from `GenAIGatewayRequest__dlm.prompt__c` (null if Einstein Audit DMO not enabled)
- `llm_response` — model response from `GenAIGeneration__dlm.responseText__c` (null if not available)

Use these to confirm whether the agent's instructions were included in the prompt and whether the response deviated from them.

### 1.3 Reconstruct conversations

For each session, render the turn-by-turn timeline from the `ConversationData` JSON:

```
Session <session_id>  [<channel>]  <duration_ms>ms total  <turn_count> turns
────────────────────────────────────────────────────────
Turn 1  [Topic: <topic>]  <duration_ms>ms
  User:  <messages[type=Input].text>
  Agent: <messages[type=Output].text>
  Steps:
    TOPIC_STEP:  <name>
    LLM_STEP:    <name>  (<duration_ms>ms)
    ACTION_STEP: <name>  in: <input>  out: <output>  [ERROR: <error>]
```

### 1.4 Identify issues

Check each session for these patterns and classify by root cause category:

| Signal | Issue type | Root cause category |
|---|---|---|
| `step.error` not null AND `step.step_type == ACTION_STEP` | **Action error** — Flow/Apex failed | `Agent Configuration Gap` or `Platform / Runtime Issue` |
| `turn.topic` doesn't match user intent | **Topic misroute** | `Agent Configuration Gap` — topic boundary too broad/narrow |
| No `ACTION_STEP` when action was expected | **Action not called** — instruction gap or TODO stub | `Agent Configuration Gap` — action not wired or not deployed |
| `step.input` has wrong/empty values | **Wrong action input** — `with:` binding incorrect | `Agent Configuration Gap` — binding misconfigured |
| `step.pre_vars` ≠ `step.post_vars` unexpectedly | **Variable not captured** — `set:` binding missing | `Agent Configuration Gap` — `set:` binding missing |
| Same `topic` repeated 3+ turns with no resolution | **No transition** — missing `after` or `after_reasoning` | `Agent Configuration Gap` — post-action transition missing |
| `step.duration_ms` > 10 000 | **Slow action** — Flow/Apex performance | `Platform / Runtime Issue` |
| Only `LLM_STEP`s, no `ACTION_STEP`s at all | **TODO stubs** — actions have no SKILL.md target | `Agent Configuration Gap` — actions not deployed |
| Agent answers knowledge question but gives generic/wrong response | **Knowledge miss** | `Knowledge Gap — Infrastructure` (no space/action) or `Knowledge Gap — Content` (article missing/stale) |
| `TRUST_GUARDRAILS_STEP` present and `output` contains `'value': 'LOW'` | **Low instruction adherence** — agent responses drifting from instructions. Check `explanation` field. Run 1.2b to get the raw LLM prompt. | `Agent Configuration Gap` — topic instructions unclear or conflicting |
| `end_type` is `null` on a short session (< 30s, 1-2 turns) | **Abandoned session** — user may have hit a dead-end | `Agent Configuration Gap` or `Knowledge Gap` |

**Root cause categories:**
- `Knowledge Gap — Infrastructure` — no `DataKnowledgeSpace`, no sources indexed, or knowledge action (`AnswerQuestionsWithKnowledge`) not deployed
- `Knowledge Gap — Content` — knowledge infrastructure set up but specific article/document is missing, stale, or not indexed
- `Agent Configuration Gap` — topic boundary, action wiring, instruction text, binding (`with:`/`set:`/`after:`), or missing transition
- `Platform / Runtime Issue` — timeouts, latency spikes, deploy failures, or transient errors

### 1.5 Present findings

**Sessions analyzed:**

| Session ID | Start | Duration | Turns | Topics seen | Action errors |
|---|---|---|---|---|---|

**Issues grouped by root cause category:**

For each root cause category that has at least one issue, list the evidence:

```
## Agent Configuration Gap
- [P1] <description> — turn <N>, topic: <topic>, evidence: `<field>: "<value>"`

## Knowledge Gap — Infrastructure
- [P1] <description> — evidence: no DataKnowledgeSpace / AnswerQuestionsWithKnowledge not deployed

## Knowledge Gap — Content
- [P2] <description> — evidence: knowledge action called but response generic/incorrect

## Platform / Runtime Issue
- [P3] <description> — action `<name>` took <ms>ms
```

Priority: P1 = action errors, topic misroutes, LOW adherence; P2 = missing actions, variable bugs, knowledge gaps; P3 = performance, abandoned sessions

**Uplift estimate** (if 3+ sessions analyzed):

| Category | Issues found | Affected sessions | Projected improvement if fixed |
|---|---|---|---|
| Agent Configuration Gap | N | N | +N sessions fully resolved |
| Knowledge Gap | N | N | +N sessions partially resolved |

Then ask: "Would you like to (1) query the live agent config to confirm root causes (Phase 1.5b), (2) reproduce any issue (Phase 2), (3) apply fixes (Phase 3), or all of the above?"

### 1.5b Agent Config Evidence

Run these queries when issues are found in 1.4 to cross-reference STDM symptoms against the live agent configuration. This answers *why* the symptoms occur, not just *what* happened.

**Step 1 — Agent identity and planner description:**

```bash
sf data query \
  --query "SELECT Id, DeveloperName, Description FROM GenAiPlannerDefinition WHERE DeveloperName LIKE '%<AgentName>%'" \
  -o <org> --json
```

Note the `Id` (e.g. `16jWt000000REZxIAO`). Topics for this agent follow the naming convention `<topicName>_<15-char-planner-id>` in `DeveloperName`.

**Step 2 — Topics deployed for this agent:**

```bash
sf data query \
  --query "SELECT Id, DeveloperName, MasterLabel, Description FROM GenAiPluginDefinition WHERE DeveloperName LIKE '%_<15-char-planner-id>'" \
  -o <org> --json
```

**Step 3 — Verbatim topic instructions:**

The instruction field name varies by org API version — describe the object first:
```bash
sf api request rest "/services/data/v66.0/sobjects/GenAiPluginInstructionDef/describe" -o <org> 2>/dev/null \
  | python3 -c "import sys,json; [print(f['name'],'-',f['type']) for f in json.loads(sys.stdin.read()).get('fields',[])]"
```
Use `Instruction` if present; fall back to `Description` if not.

```bash
sf data query \
  --query "SELECT Id, GenAiPluginDefinitionId, Description FROM GenAiPluginInstructionDef WHERE GenAiPluginDefinitionId IN ('<topic_id_1>', '<topic_id_2>')" \
  -o <org> --json
```

**Step 4 — Knowledge infrastructure (only if any topic is expected to answer knowledge questions):**

```bash
# Does a knowledge space exist?
sf data query --query "SELECT Id, Name, Status FROM DataKnowledgeSpace" -o <org> --json

# Is the knowledge action deployed for this agent?
sf data query \
  --query "SELECT Id, DeveloperName FROM GenAiPluginDefinition WHERE DeveloperName LIKE 'AnswerQuestionsWithKnowledge%'" \
  -o <org> --json

# If a space exists, what sources are indexed?
sf data query \
  --query "SELECT Id, FileName, Status, LastModifiedDate FROM DataKnowledgeSrcFileRef WHERE DataKnowledgeSpaceId = '<space_id>'" \
  -o <org> --json
```

**Mapping STDM symptoms to config evidence:**

| STDM symptom | Config to check | What to look for |
|---|---|---|
| Topic misroute | `GenAiPluginDefinition.Description` on affected topics | Description too broad — overlaps with adjacent topic description |
| Action not called | `GenAiPluginInstructionDef.Instruction` for the topic | Instruction doesn't mention the action, or wrong action name |
| LOW instruction adherence | `GenAiPluginInstructionDef.Instruction` for the topic | Instructions are vague, short, or conflict with other topics |
| Topic stuck, no transition | `GenAiPluginInstructionDef.Instruction` | No guidance on what to do after the main task completes |
| Knowledge miss | `DataKnowledgeSpace` + `DataKnowledgeSrcFileRef` | Space missing = Infrastructure gap; space exists but no relevant sources = Content gap |

**Present config evidence alongside STDM findings:**

```
Agent: <AgentName> (<DeveloperName_v1>)
  Description: "<verbatim GenAiPlannerDefinition.Description>"

Topics configured:
  <topic_DeveloperName>: "<verbatim GenAiPluginDefinition.Description>"
  Instructions: "<verbatim GenAiPluginInstructionDef.Instruction>"
  ...

Knowledge:
  DataKnowledgeSpace: <name(s) if present, else "None configured">
  AnswerQuestionsWithKnowledge action: <deployed / not deployed>
  Indexed sources: <N> files
```

**Confirmed root cause format** (when config evidence supports the STDM symptom):

```
Root cause: Agent Configuration Gap — <topic_DeveloperName>
  Current instruction (GenAiPluginInstructionDef <Id>):
  > <verbatim Instruction field text>

  Proposed fix:
  > <replacement instruction text>
```

---

## Phase 2: Reproduce — Live Preview

Use `sf agent preview` to simulate conversations in an isolated session (no production data affected).

```bash
# Start a preview session — note the session ID in the response
sf agent preview start --api-name <AgentApiName> -o <org> --json

# Send a message that reproduces the issue
sf agent preview send \
  --session-id <preview-session-id> \
  --message "your test message here" \
  -o <org> --json

# Continue the conversation as needed
sf agent preview send \
  --session-id <preview-session-id> \
  --message "follow-up message" \
  -o <org> --json

# End the session
sf agent preview end --session-id <preview-session-id> -o <org> --json
```

Report after reproduction:
- Whether the issue is confirmed or cannot be reproduced
- Exact topic routing and action sequence observed
- Agent's verbatim response
- Whether the issue is consistent or intermittent

---

## Phase 3: Improve — Fix and Deploy

### 3.1 Map issue to fix location

| Root cause category | STDM signal | Fix target | What to change |
|---|---|---|---|
| `Agent Configuration Gap` | Topic misroute | `.claude/agents/<topic>.md` | Scope paragraph (first para after `---`) — use config evidence from 1.5b to see current `GenAiPluginDefinition.Description` and tighten it |
| `Agent Configuration Gap` | Action not called | `.claude/agents/<topic>.md` | Add to `tools:` frontmatter; update topic instructions to explicitly invoke the action |
| `Agent Configuration Gap` | Wrong action input / error | `.claude/skills/<action>/SKILL.md` | Correct `inputs:` types; fix `with:` bindings |
| `Agent Configuration Gap` | Variable not captured | `.claude/agents/<topic>.md` | Fix `bindings.<Action>.set:` |
| `Agent Configuration Gap` | No post-action transition | `.claude/agents/<topic>.md` | Add `bindings.<Action>.after:` or `after_reasoning:` entry |
| `Agent Configuration Gap` | LOW adherence / vague instructions | `.claude/agents/<topic>.md` instruction lines | Use verbatim `GenAiPluginInstructionDef.Instruction` (from 1.5b) to identify the exact gap; rewrite the relevant instruction lines |
| `Agent Configuration Gap` | Action is a TODO stub | Create the Flow/Apex target, update `SKILL.md` `agentforce: target:` | — |
| `Knowledge Gap — Infrastructure` | Knowledge question answered generically | Add `.claude/skills/answer-questions-with-knowledge/SKILL.md`; create `DataKnowledgeSpace` and index sources | — |
| `Knowledge Gap — Content` | Knowledge question — wrong/missing answer | Add missing articles to knowledge space; verify `DataKnowledgeSrcFileRef` has a record linking the article | — |
| `Platform / Runtime Issue` | Action timeout / latency > 10s | Flow or Apex class | Optimize query/processing logic; add timeout handling |

**When fixing topic instructions (Agent Configuration Gap — LOW adherence or action not called)**, always quote the current live instruction verbatim before proposing a replacement:

```
Current instruction (GenAiPluginInstructionDef <Id>):
> <verbatim Instruction field value from 1.5b query>

Proposed replacement:
> <new instruction text>
```

This ensures the fix addresses the exact deployed text, not a stale local copy.

### 3.2 Apply fixes

Read the relevant files, make targeted edits, then re-convert:

```bash
~/.claude/agentforce-md/bin/agentforce-md convert \
  --project-root <path> \
  --agent-name <AgentName> \
  --default-agent-user "<ASA_USER>"
```

Show a summary of what changed in the generated `.agent` file (diff the key sections).

### 3.3 Deploy

```bash
# Validate first
~/.claude/agentforce-md/bin/agentforce-md deploy --api-name <AgentName> -o <org> --dry-run

# Deploy and activate
~/.claude/agentforce-md/bin/agentforce-md deploy --api-name <AgentName> -o <org> --activate
```

### 3.4 Verify

Use Phase 2 (preview) to confirm the fix resolves the issue with the same inputs that triggered it. If the fix is good, run Phase 1 again on new session data to validate behavior at scale.

---

## STDM Reference

### Data hierarchy

```
AiAgentSession (1)
├── AiAgentSessionParticipant (N)       — agent planner IDs and user IDs linked to this session
└── AiAgentInteraction (N)              — one per conversational turn
    ├── AiAgentInteractionMessage (N)   — user and agent messages
    └── AiAgentInteractionStep (N)      — internal steps (LLM, actions)
```

### Key fields

**AiAgentSession** (`ssot__AiAgentSession__dlm`)
- `ssot__Id__c` — Session ID
- `ssot__StartTimestamp__c` / `ssot__EndTimestamp__c` — Session timing → `session.duration_ms`
- `ssot__AiAgentChannelType__c` — Channel → `session.channel`
- `ssot__AiAgentSessionEndType__c` — How the session ended: `USER_ENDED`, `AGENT_ENDED`, or null → `session.end_type`
- `ssot__VariableText__c` — Final variable snapshot for the session → `session.session_variables`

**AiAgentSessionParticipant** (`ssot__AiAgentSessionParticipant__dlm`)
- `ssot__AiAgentSessionId__c` — Session this participant belongs to
- `ssot__AiAgentApiName__c` — API name of the agent (primary filter field — no SOQL needed)
- `ssot__ParticipantId__c` — GenAiPlannerDefinition ID (key prefix `16j`) for agents, `005...` for users. May be 15-char or 18-char — `AgentforceOptimizeService` automatically queries both formats as a fallback.

**AiAgentInteraction** (`ssot__AiAgentInteraction__dlm`)
- `ssot__TopicApiName__c` — Topic/skill that handled this turn → `turn.topic`
- `ssot__StartTimestamp__c` / `ssot__EndTimestamp__c` — Turn timing → `turn.duration_ms`
- `ssot__TelemetryTraceId__c` — Distributed tracing ID → `turn.telemetry_trace_id`

**AiAgentInteractionMessage** (`ssot__AiAgentInteractionMessage__dlm`)
- `ssot__AiAgentInteractionMessageType__c` — `Input` (user) or `Output` (agent) → `message.message_type`
- `ssot__ContentText__c` — Message text → `message.text`

**AiAgentInteractionStep** (`ssot__AiAgentInteractionStep__dlm`)
- `ssot__AiAgentInteractionStepType__c` — `TOPIC_STEP`, `LLM_STEP`, `ACTION_STEP`, `SESSION_END`, `TRUST_GUARDRAILS_STEP` → `step.step_type`
- `ssot__Name__c` — Step or action name → `step.name`
- `ssot__ErrorMessageText__c` — Error text (null if none) → `step.error`
- `ssot__InputValueText__c` / `ssot__OutputValueText__c` — Input/output data → `step.input` / `step.output`
- `ssot__PreStepVariableText__c` / `ssot__PostStepVariableText__c` — Variable snapshots → `step.pre_vars` / `step.post_vars`
- `ssot__GenerationId__c` — Links to `GenAIGeneration__dlm` → `step.generation_id` (non-null on LLM_STEP)
- `ssot__GenAiGatewayRequestId__c` — Links to `GenAIGatewayRequest__dlm` → `step.gateway_request_id` (non-null on LLM_STEP)

**Einstein Audit & Feedback DMOs** (joined via `getLlmStepDetails()`)

`GenAIGeneration__dlm` — LLM generation records:
- `generationId__c` — Join key to `ssot__GenerationId__c` on the step DMO
- `responseText__c` — The full LLM response text → `LlmStepDetail.llm_response`

`GenAIGatewayRequest__dlm` — Raw gateway requests sent to the LLM:
- `gatewayRequestId__c` — Join key to `ssot__GenAiGatewayRequestId__c` on the step DMO
- `prompt__c` — Full prompt text including system instructions → `LlmStepDetail.prompt`

These two DMOs are only populated when Einstein Audit & Feedback is enabled in the org's Data Cloud setup.

**`TRUST_GUARDRAILS_STEP`** — A safety/compliance step that measures whether the agent's response followed its instructions:
- `step.name` is typically `InstructionAdherence`
- `step.output` is a Python-style dict string (not JSON). Actual format:
  ```
  {'name': 'InstructionAdherence', 'value': 'HIGH', 'explanation': 'This response adheres to the assigned instructions.'}
  ```
  Check for adherence by searching for `'value': 'LOW'` (or just `LOW`) in the output string.
- `step.input` contains the raw `input_text` and `output_text` that were evaluated, e.g.:
  ```
  input_text: <user message>, output_text: <agent response>
  ```
- `step.error` may contain the literal string `"None"` (not a real error — see Data quality below)
- Does **not** count toward `action_error_count` (the Apex class only counts errors on `ACTION_STEP` type)

### Data quality

**`NOT_SET` sentinel.** Data Cloud uses `"NOT_SET"` for null/absent values. `AgentforceOptimizeService` strips this sentinel — any field returning `null` in the JSON should be treated as absent.

**`TRUST_GUARDRAILS_STEP` error field.** `TRUST_GUARDRAILS_STEP` steps may have the Python string `"None"` in their `error` field (not `"NOT_SET"`). This is **not** a real error — treat it as absent. `action_error_count` is only incremented for `ACTION_STEP` errors so this sentinel does not inflate the count.

**Null `end_time` / `duration_ms`.** Sessions and turns may have `null` for `end_time` and therefore `null` for `duration_ms` when no session-end event was recorded by Data Cloud. This is common and does not indicate a problem — just treat duration as unknown for those sessions.

**`LLM_STEP` input/output format.** The `input` and `output` fields on `LLM_STEP` contain raw Python dict strings (the internal LlamaIndex representation), not valid JSON. They are useful for confirming what was sent to the LLM but are not machine-parseable. Example:
```
{'current_agent_name': 'entry', 'messages': [ChatMessage(role=<MessageRole.SYSTEM: 'system'>, ...)]}
```
Do not attempt to `JSON.parse()` these values. Only `ACTION_STEP` input/output is structured JSON.

**Participant ID format inconsistency.** The `ssot__AiAgentSessionParticipant__dlm` DMO stores `ssot__ParticipantId__c` as either 15-char or 18-char Salesforce IDs, inconsistently across sessions and orgs. `AgentforceOptimizeService.resolvePlannerIds()` automatically adds both the 18-char (from SOQL) and 15-char (substring) versions to the IN clause to handle this.

### Data Space name

Always run Phase 0 first to discover the correct Data Space `name` for the org. Use `sf api request rest "/services/data/v66.0/ssot/data-spaces" -o <org>` (no `--json` flag — unsupported on this beta command). Never assume `'default'` without checking — it is only a fallback if the API call fails. If STDM queries return zero rows after confirming the Data Space, direct the user to Salesforce Setup → Data Cloud → Data Spaces to verify the name.

---

## Agent Config Objects Reference

These standard Salesforce objects are queried in Phase 1.5b to cross-reference STDM symptoms against the live agent configuration.

| Object | Purpose | Key fields |
|---|---|---|
| `GenAiPlannerDefinition` | The agent itself | `DeveloperName` (has `_v1` suffix), `Description` (agent-level system prompt) |
| `GenAiPluginDefinition` | Topics and actions | `DeveloperName` (format: `<topicName>_<15-char-planner-id>`), `MasterLabel`, `Description` (topic routing description) |
| `GenAiPluginInstructionDef` | Topic instructions (verbatim) | `GenAiPluginDefinitionId` (FK to topic), `Instruction` or `Description` (the actual instruction text — field name varies by API version; describe the object to confirm) |
| `DataKnowledgeSpace` | Knowledge base container | `Name`, `Status` |
| `DataKnowledgeSrcFileRef` | Individual knowledge sources | `DataKnowledgeSpaceId`, `FileName`, `Status`, `LastModifiedDate` |
| `KnowledgeArticle` | Salesforce Knowledge articles | `Title`, `ArticleNumber`, `PublishStatus` |

**Topic `DeveloperName` convention:** Agent Builder appends the first 15 characters of the planner's Salesforce ID to each topic's name: `entry_16jWt000000REZx`. Use `WHERE DeveloperName LIKE '%_<15-char-id>'` to find all topics for a given planner.

**`GenAiPluginInstructionDef` is the key object for fix targeting.** It holds the exact text that is injected into the LLM prompt as the topic's operating instructions. When STDM shows LOW adherence, action not called, or topic misroute, this is the first place to look. Always quote its `Instruction` field verbatim before proposing a replacement (see Phase 3.1).
