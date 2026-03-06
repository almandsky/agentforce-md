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

Parse: search for `DEBUG|STDM_RESULT:` (not `STDM_RESULT:` — the first occurrence of that string is in the source echo, not the debug output) and extract the JSON that follows on that line:

```bash
python3 -c "
import json, sys
logs = json.load(sys.stdin)['result']['logs']
idx = logs.find('DEBUG|STDM_RESULT:')
print(logs[idx + len('DEBUG|STDM_RESULT:'):].split('\n')[0].strip())
" < /tmp/apex_result.json
```

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

Parse using the same `DEBUG|STDM_RESULT:` pattern (see 1.1). Each element is a `ConversationData` object:

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
| Specialized topic (e.g. `identity_collection`, `schedule_test_drive`) appears for exactly 1 turn then session returns to `entry` permanently | **Handoff topic with no post-collection routing** — topic collects input but has no instruction for what to do after | `Agent Configuration Gap` — topic instructions missing the "after this, route to X" step |
| `schedule_test_drive` / `general_support` topic has zero sessions over the analysis window despite the agent being designed to handle those intents | **Dead topic** — topic exists in config but is never entered | `Agent Configuration Gap` — `entry` topic is handling the intent directly instead of routing |

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

After presenting findings, **automatically proceed to Phase 1.5b** — do not wait for the user to ask. The config evidence is needed to confirm root causes before any fix can be proposed. Ask about Phase 2/3 only after 1.5b is complete.

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

**Critical check — identical instructions across topics:**

After querying Step 3, compare the instruction text across all topics. If 2 or more topics share the same `Description`/`Instruction` text word-for-word, this is a **critical `Agent Configuration Gap`** — the topics have no differentiated guidance and the LLM is falling back to topic `Description` routing alone. Flag this prominently before presenting per-topic analysis:

```
⚠️  CRITICAL: All N topics share identical GenAiPluginInstructionDef text.
    Specialized topics (identity_collection, schedule_test_drive, etc.) have no actionable
    instructions — the agent cannot know what to do differently in each topic.
    Root cause: Agent Configuration Gap (identical instructions across all topics)
```

**Step 4 — Knowledge infrastructure (only if any topic is expected to answer knowledge questions):**

```bash
# Does a knowledge space exist?
sf data query --query "SELECT Id, Name FROM DataKnowledgeSpace" -o <org> --json

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

### 2.1 Build test scenarios from Phase 1 findings

Before opening a preview session, define one test scenario per confirmed issue:

| Issue type (Phase 1) | Test message to send | Expected behavior | Failure indicator |
|---|---|---|---|
| Dead topic — never entered | Utterance that *should* route to that topic | `topic` in response = `<dead_topic>` | Topic stays `entry` |
| Action not called | Ask directly for the action's task | Action fires in the response | Conversational reply with no action invoked |
| Handoff topic — no post-collection routing | Enter the handoff topic, then send a follow-up | Session continues in specialized topic | Falls back to `entry` after 1 turn |
| LOW adherence | Exact utterance from the flagged `TRUST_GUARDRAILS_STEP` | Response follows topic instruction | Generic/off-instruction answer |
| Knowledge miss | Question requiring a specific knowledge article | Agent cites correct information | Hallucinated or generic answer |
| Topic misroute | Utterance that belongs to topic A | `topic` = A in response | `topic` = B or `entry` |

### 2.2 Run a preview session

```bash
# Start a preview session
sf agent preview start --api-name <AgentApiName> -o <org> --json | tee /tmp/preview_start.json

# Extract the session ID
SESSION_ID=$(python3 -c "import json,sys; print(json.load(open('/tmp/preview_start.json'))['result']['sessionId'])")
echo "Session ID: $SESSION_ID"

# Send the test message
sf agent preview send \
  --session-id "$SESSION_ID" \
  --message "your test utterance here" \
  -o <org> --json | tee /tmp/preview_response.json

# Extract the agent's response text
python3 -c "
import json
data = json.load(open('/tmp/preview_response.json'))
result = data.get('result', data)
# Response field varies by API version — try common shapes
for key in ['messages', 'message', 'response']:
    if key in result:
        msgs = result[key] if isinstance(result[key], list) else [result[key]]
        for m in msgs:
            if isinstance(m, dict) and m.get('type','').lower() in ('output','agent','response'):
                print('Agent:', m.get('message', m.get('text', m)))
        break
else:
    print(json.dumps(result, indent=2))  # fallback: print full result
"

# End the session when done
sf agent preview end --session-id "$SESSION_ID" -o <org> --json
```

For multi-turn scenarios (e.g. handoff routing), repeat the `send` step for each follow-up utterance before ending the session.

### 2.3 Classify each scenario

Run each test scenario **3 times** (start a new session each run) and classify:

| Verdict | Criteria |
|---|---|
| `[CONFIRMED]` | Same failure in 3/3 runs |
| `[INTERMITTENT]` | Failure in 1–2 of 3 runs |
| `[NOT REPRODUCED]` | Passes in 3/3 runs — re-examine Phase 1 evidence |

### 2.4 Record results

For each scenario, record before proceeding to Phase 3:

```
Scenario: <issue type from Phase 1>
Test message: "<exact utterance sent>"
Expected: <topic name / action name / response behavior>
Actual:   <observed topic / action / verbatim response>
Verdict:  [CONFIRMED] / [INTERMITTENT] / [NOT REPRODUCED]
```

Only `[CONFIRMED]` and `[INTERMITTENT]` issues proceed to Phase 3.

---

## Phase 3: Improve — Fix and Deploy

### 3.1 Understand the markdown file structure

Each topic is a `.claude/agents/<topic-name>.md` file:

```markdown
---
name: topic-name                   # kebab-case; snake_case in .agent output
description: <one-line summary>    # → GenAiPluginDefinition.Description (topic routing)
tools: ActionName1, ActionName2    # → actions available in this topic
agentforce:
  bindings:
    ActionName1:
      with:                        # input mappings: action param ← variable/literal
        inputParam: "{{var}}"
      set:                         # output capture: variable ← action output field
        myVar: "{{output.field}}"
      after: next-topic            # routing after action completes
---

<scope paragraph — first paragraph after closing --->
  ↑ also feeds GenAiPluginDefinition.Description (topic routing signal)

<instruction body — all text after scope paragraph>
  ↑ becomes GenAiPluginInstructionDef.Instruction — injected verbatim into LLM prompt
```

**Critical mapping:**
- `description:` frontmatter + first body paragraph → topic routing description (`GenAiPluginDefinition.Description`)
- Instruction body (everything after the scope paragraph) → verbatim LLM prompt text (`GenAiPluginInstructionDef.Instruction` or `Description`)
- This is exactly what Phase 1.5b queried — the fix closes the gap between what was deployed and what should be there

### 3.2 Map issue to fix location

| Root cause category | STDM signal | Fix target | What to change |
|---|---|---|---|
| `Agent Configuration Gap` | Topic misroute | `.claude/agents/<topic>.md` | Tighten `description:` + scope paragraph to exclude overlapping intents |
| `Agent Configuration Gap` | Action not called | `.claude/agents/<topic>.md` | Add action to `tools:`; add explicit instruction: "Use `<ActionName>` to..." |
| `Agent Configuration Gap` | Wrong action input / error | `.claude/skills/<action>/SKILL.md` | Correct `inputs:` types; fix `with:` bindings |
| `Agent Configuration Gap` | Variable not captured | `.claude/agents/<topic>.md` | Add `agentforce: bindings: <Action>: set:` mapping |
| `Agent Configuration Gap` | No post-action transition | `.claude/agents/<topic>.md` | Add `agentforce: bindings: <Action>: after: <next-topic>` |
| `Agent Configuration Gap` | LOW adherence / vague instructions | `.claude/agents/<topic>.md` instruction body | Rewrite using Phase 1.5b verbatim text as baseline — see instruction principles below |
| `Agent Configuration Gap` | Identical instructions across topics | All `.claude/agents/*.md` instruction bodies | Give each topic distinct, actionable instructions |
| `Knowledge Gap — Infrastructure` | Knowledge question answered generically | Add `.claude/skills/answer-questions-with-knowledge/SKILL.md`; create `DataKnowledgeSpace` and index sources | — |
| `Knowledge Gap — Content` | Knowledge question — wrong/missing answer | Add missing articles to knowledge space; verify `DataKnowledgeSrcFileRef` links the article | — |
| `Platform / Runtime Issue` | Action timeout / latency > 10s | Flow or Apex class | Optimize query/processing logic; add timeout handling |

**When fixing topic instructions**, always quote the current live instruction verbatim (from Phase 1.5b) before proposing a replacement:

```
Current instruction (GenAiPluginInstructionDef <Id>):
> <verbatim Instruction field value from 1.5b query>

Proposed replacement:
> <new instruction text>
```

### 3.3 Principles for effective topic instructions

Good instructions are specific, imperative, and action-named. Poor instructions are persona descriptions or generic guidance reused across topics.

1. **Name the action explicitly** — "Use `ScheduleTestDrive` to book the appointment" not "help the user book"
2. **State the pre-condition** — "Only handle scheduling after the customer's name and email have been collected"
3. **State what to do after** — "After `ScheduleTestDrive` completes, confirm the date/time and ask if they need anything else"
4. **Scope tightly** — "This topic handles test drive scheduling only. For vehicle specs or pricing, do not answer — route back to `general_support`"
5. **Keep persona out of instructions** — persona belongs in the agent-level description (`GenAiPlannerDefinition.Description`), not per-topic instructions
6. **One responsibility per topic** — if the instruction covers 3 distinct tasks, split into 3 topics

**Before / after example** (identical instructions → distinct instructions):

*Before (generic Nova persona text, same across all 4 topics):*
```
You are Nova, a friendly Tesla support assistant. Greet customers warmly,
help them with their needs, and guide them toward scheduling a test drive.
```

*After (for `identity_collection` topic specifically):*
```
Collect the customer's name, email address, and phone number using CollectCustomerInfo.
Do not proceed until all three fields are provided.
After collection, confirm the details back to the customer, then route to schedule_test_drive.
Do not answer questions about vehicles, pricing, or appointments in this topic.
```

### 3.4 Apply fixes

Read the target file, make the targeted edit, then re-convert:

```bash
# Read the current markdown
cat <project-root>/.claude/agents/<topic-name>.md

# After editing with the Edit tool, re-convert to regenerate the .agent file
~/.claude/agentforce-md/bin/agentforce-md convert \
  --project-root <project-root> \
  --agent-name <AgentName> \
  --default-agent-user "<ASA_USER>"

# Spot-check the generated .agent output — confirm new instruction text appears verbatim
grep -A 30 "topicApiName: <topic_name>" \
  <project-root>/force-app/main/default/genAiPlanners/<AgentName>.agent
```

Show the before/after diff of the instruction text in the `.agent` output before deploying.

### 3.5 Deploy

```bash
# Validate first (dry run — no changes to org)
~/.claude/agentforce-md/bin/agentforce-md deploy --api-name <AgentName> -o <org> --dry-run

# Deploy and activate
~/.claude/agentforce-md/bin/agentforce-md deploy --api-name <AgentName> -o <org> --activate
```

### 3.6 Verify

**Immediate** — run the Phase 2 scenarios that returned `[CONFIRMED]` before the fix. All should now return `[NOT REPRODUCED]`.

**At scale** — after 24–48 hours of new live sessions, re-run Phase 1 over the new date range and compare against the pre-fix baseline:

| Metric | What to look for after fix |
|---|---|
| Topics seen in STDM | Dead topics should now appear in session data |
| `TRUST_GUARDRAILS_STEP` value | `LOW` occurrences should drop or disappear |
| Action invocation per turn | Actions should now fire for the intents they cover |
| `action_error_count` | Should not increase (regression check) |
| Avg session duration / turn count | Shorter = less confusion, faster resolution |

If new issues surface in the post-fix Phase 1 run, repeat the cycle from Phase 1.4.

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
| `DataKnowledgeSpace` | Knowledge base container | `Name` (`Status` field does not exist — query with `SELECT Id, Name` only) |
| `DataKnowledgeSrcFileRef` | Individual knowledge sources | `DataKnowledgeSpaceId`, `FileName`, `Status`, `LastModifiedDate` |
| `KnowledgeArticle` | Salesforce Knowledge articles | `Title`, `ArticleNumber`, `PublishStatus` |

**Topic `DeveloperName` convention:** Agent Builder appends the first 15 characters of the planner's Salesforce ID to each topic's name: `entry_16jWt000000REZx`. Use `WHERE DeveloperName LIKE '%_<15-char-id>'` to find all topics for a given planner.

**`GenAiPluginInstructionDef` is the key object for fix targeting.** It holds the exact text that is injected into the LLM prompt as the topic's operating instructions. When STDM shows LOW adherence, action not called, or topic misroute, this is the first place to look. Always quote its `Instruction` field verbatim before proposing a replacement (see Phase 3.1).
