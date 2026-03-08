---
name: agentforce-skill-migrate
description: Discover Claude Code skills and migrate them to Salesforce Agentforce as Prompt Templates (simple) or Apex callout actions (complex)
allowed-tools: Bash Read Write Edit Glob
argument-hint: "[skill-name | all | discover]"
---

# Agentforce Skill Migrate

Migrate Claude Code SKILL.md files to Salesforce Agentforce by classifying each skill and generating the appropriate Salesforce metadata artifacts.

**Two migration paths:**
- **Simple skills** (prompt-only, no external deps) → GenAiPromptTemplate + GenAiFunction action + Agent Script topic
- **Complex skills** (3rd-party APIs, CLI, MCP) → Apex `@InvocableMethod` callout class + Remote Site Settings + Agent Script topic

---

## Routing

Determine intent from the argument:

- **`discover` or no args** → Phase 0 only — list and classify all skills from both locations, no files written
- **`<skill-name>`** → Phase 0 + Phase 1 for that skill, then Phase 2A (simple) or Phase 2B (complex)
- **`all`** → Run all phases for every un-migrated skill from both locations, one at a time with user confirmation between each

---

## Phase 0: Discover

Scan **both** skill locations:

**Local** — skills in the current project:
```bash
ls .claude/skills/*/SKILL.md 2>/dev/null
```

**Global** — skills installed system-wide:
```bash
ls ~/.claude/skills/*/SKILL.md 2>/dev/null
```

**Deduplication rule:** If the same skill name exists in both locations, the local one takes precedence — show it as `Local` and omit the global copy from the table.

**Exclusion rule:** Skip any skill whose name starts with `agentforce-` from the global list — these are the agentforce-md tool's own skills and are not candidates for migration.

For each SKILL.md found, record:
- **Source** — `Local` (`.claude/skills/`) or `Global` (`~/.claude/skills/`)
- **Full path** — the absolute path to the SKILL.md file (used in all subsequent phases)
- Read `name:`, `description:`, `allowed-tools:` from frontmatter
- Check if `agentforce: target:` already exists → mark as **Already migrated**, skip in subsequent phases
- Check if `.claude/agents/<skill-name>.md` exists in the **current project** → note in "Has sub-agent?" column (always checked locally regardless of skill source)
- Run quick complexity scan (see Phase 1 signals below) for the estimated complexity column

**Output discovery table:**

```
| Skill | Source | Description | Already migrated? | Has sub-agent? | Estimated complexity |
|---|---|---|---|---|---|
| check-order-status | Local | Look up order status | ✓ (skip) | ✓ | — |
| my-prompt-skill | Local | Guide tone of response | ✗ | ✗ | Simple |
| search-external-api | Global | Search GitHub issues | ✗ | ✗ | Complex (API) |
| jira-lookup | Global | Look up a Jira ticket | ✗ | ✗ | Complex (MCP) |
```

If `discover` was the argument (or no argument was given), stop here and do not write any files.

**When looking up `<skill-name>` by name:** search local first (`.claude/skills/<skill-name>/SKILL.md`), then global (`~/.claude/skills/<skill-name>/SKILL.md`). Use whichever is found first. If neither exists, report an error.

---

## Phase 1: Classify

Read the full SKILL.md body for the target skill and evaluate the following signals.

### Simple (ALL must be true)

- No `mcp__*` function call patterns in body
- No bash code blocks calling external systems (`curl`, `wget`, `sf`, non-read CLIs)
- No Python/JS blocks with HTTP calls or subprocess invocations (`requests`, `fetch`, `axios`, `subprocess`)
- Body is primarily LLM instruction / prompt text

### Complex (ANY triggers complex)

| Signal | Classification |
|---|---|
| `mcp__` tool reference patterns in body | **Complex (MCP)** |
| Bash code with `curl`, external API calls, or external CLI tools | **Complex (API/CLI)** |
| Python/JS with `requests`, `fetch`, `axios`, or `subprocess` | **Complex (Code)** |
| References to auth tokens, API keys, or OAuth flows | **Complex (API)** |

**Present classification and ask user to confirm before generating any files:**

```
Skill: my-prompt-skill  [Local: .claude/skills/my-prompt-skill/SKILL.md]
  Classification: Simple
  Reason: Body is pure LLM instructions with no external calls.
  Proposed path: GenAiPromptTemplate → GenAiFunction action → Agent Script topic

Skill: search-external-api  [Global: ~/.claude/skills/search-external-api/SKILL.md]
  Classification: Complex (API)
  Reason: Bash block calls curl to https://api.github.com/...
  Proposed path: Apex @InvocableMethod + Remote Site Setting → Agent Script topic

Skill: jira-lookup  [Global: ~/.claude/skills/jira-lookup/SKILL.md]
  Classification: Complex (MCP)
  Reason: Uses mcp__jira__search_issues tool call.
  Proposed path: ⚠️ External MCP Server Connection (not yet automated — see MCP section below)

Proceed with migration? (y/n)
```

Wait for user confirmation before proceeding to Phase 2A or 2B.

---

## Phase 2A: Simple Skill → Prompt Template + Topic

### Naming conventions

Derive `<SkillName>` by converting the kebab-case skill name to PascalCase (strip hyphens, capitalize each word). For example: `my-prompt-skill` → `MyPromptSkill`.

### 2A.1 Generate GenAiPromptTemplate XML

Output: `force-app/main/default/genAiPromptTemplates/<SkillName>Prompt.genAiPromptTemplate-meta.xml`

Create the `force-app/main/default/genAiPromptTemplates/` directory if it does not exist.

**Important:** The metadata type is `GenAiPromptTemplate` (not `PromptTemplate`). The `promptTemplates/` directory with `.promptTemplate-meta.xml` suffix is NOT recognized by the sf CLI and will cause `TypeInferenceError` during deployment.

```xml
<?xml version="1.0" encoding="UTF-8"?>
<GenAiPromptTemplate xmlns="http://soap.sforce.com/2006/04/metadata">
    <activeVersionNumber>1</activeVersionNumber>
    <developerName><SkillName>Prompt</developerName>
    <masterLabel><Readable Label from skill name></masterLabel>
    <description><SKILL.md description: value></description>
    <templateType>einstein__agentAction</templateType>
    <relatedEntity>N/A</relatedEntity>
    <versions>
        <content><![CDATA[<full instruction body — everything after frontmatter closing --->]]></content>
        <status>Published</status>
        <versionNumber>1</versionNumber>
    </versions>
</GenAiPromptTemplate>
```

Populate:
- `developerName` ← `<SkillName>Prompt` (PascalCase, hyphens stripped)
- `masterLabel` ← human-readable label derived from the skill name
- `description` ← `description:` frontmatter value from SKILL.md
- `templateType` ← `einstein__agentAction` (for use as an Agentforce action)
- `content` ← full SKILL.md body (all text after the closing `---` of the frontmatter block)

### 2A.2 Generate GenAiFunction action metadata (bundle)

Output: `force-app/main/default/genAiFunctions/<SkillName>PromptAction/<SkillName>PromptAction.genAiFunction-meta.xml`

**Important:** GenAiFunction is a **bundle** metadata type. The file MUST be inside a subdirectory named after the function. A flat file directly in `genAiFunctions/` will cause `ExpectedSourceFilesError` during deployment.

Create the bundle directory structure:
```bash
mkdir -p force-app/main/default/genAiFunctions/<SkillName>PromptAction
```

```xml
<?xml version="1.0" encoding="UTF-8"?>
<GenAiFunction xmlns="http://soap.sforce.com/2006/04/metadata">
    <masterLabel><SkillName> Prompt Action</masterLabel>
    <type>PromptTemplateGenerateText</type>
    <promptTemplateRef><SkillName>Prompt</promptTemplateRef>
</GenAiFunction>
```

`promptTemplateRef` must match the `developerName` of the template created in 2A.1.

### 2A.3 Create or update the topic file

The topic file always lives in the **current project's** `.claude/agents/` directory, regardless of whether the skill came from local or global.

**Check for an existing sub-agent:**

```bash
ls .claude/agents/<skill-name>.md 2>/dev/null
```

**Path A — Sub-agent already exists:**

Read the file, then:
- Append `<SkillName>PromptAction` to the `tools:` list in frontmatter
- Add an `agentforce: bindings:` entry for `<SkillName>PromptAction` with `after: end`

**Path B — No sub-agent exists:**

Create `.claude/agents/<skill-name>.md`:

```markdown
---
name: <skill-name>
description: <description from SKILL.md>
tools: <SkillName>PromptAction
agentforce:
  bindings:
    <SkillName>PromptAction:
      after: end
---
<scope paragraph derived from SKILL.md description>

Use `<SkillName>PromptAction` to handle this request.
```

### 2A.4 Update source SKILL.md

Add `agentforce:` section to the **source** SKILL.md frontmatter (insert before the closing `---`). Use the full path recorded in Phase 0 — this will be either the local or global file:

```yaml
agentforce:
  target: "promptTemplate://<SkillName>Prompt"
```

**Global skill note:** Writing to `~/.claude/skills/<skill-name>/SKILL.md` marks the skill as migrated globally — it will appear as "Already migrated" when this project or any other project runs discover. This is the intended behavior.

### 2A.5 Next steps output

After all files are written, display:

```
Migration complete for: <skill-name>  [<Local|Global> skill]

Files created/updated:
  force-app/main/default/genAiPromptTemplates/<SkillName>Prompt.genAiPromptTemplate-meta.xml
  force-app/main/default/genAiFunctions/<SkillName>PromptAction/<SkillName>PromptAction.genAiFunction-meta.xml
  .claude/agents/<skill-name>.md  (created / updated)
  <source SKILL.md path>  (agentforce: target: added)

Next steps:
  1. Deploy metadata: sf project deploy start --source-dir force-app/main/default -o <org>
  2. Run agentforce-convert to wire the topic into the Agent Script (GenAiPlannerBundle)
  3. Deploy the updated agent bundle to the org
  4. Verify template in Setup → Einstein → Prompt Builder
```

---

## Phase 2B: Complex Skill → Apex + Remote Site Settings

### Naming conventions

Same as Phase 2A: derive `<SkillName>` by converting kebab-case to PascalCase.

### 2B.1 Extract API surface

From the SKILL.md body, identify:
- External URLs (from `curl`/`fetch`/`requests` patterns)
- HTTP methods used (GET, POST, PATCH, etc.)
- Auth patterns (Bearer token, API key header, OAuth)
- Input parameters (what data the skill receives before calling the API)
- Output fields (what the skill extracts from the API response)

Present the extracted surface for user confirmation before generating any code:

```
Extracted API surface for: <skill-name>  [<Local|Global> skill]

  URL:         https://api.example.com/v1/...
  Method:      GET
  Auth:        Bearer token (Authorization header)
  Inputs:      query (string), limit (number)
  Outputs:     items (list), total_count (number)

Does this look correct? (y/n / corrections)
```

Wait for user confirmation or corrections before proceeding.

### 2B.2 Generate Apex action class

Output: `force-app/main/default/classes/<SkillName>Action.cls`

Create the `force-app/main/default/classes/` directory if it does not exist.

```apex
public with sharing class <SkillName>Action {

    public class Input {
        @InvocableVariable(label='<param label>' required=true)
        public String <param>;
    }

    public class Output {
        @InvocableVariable(label='<result label>')
        public String <result>;
    }

    @InvocableMethod(label='<Readable Skill Label>' description='<description from SKILL.md>')
    public static List<Output> execute(List<Input> inputs) {
        Http http = new Http();
        HttpRequest req = new HttpRequest();
        req.setEndpoint('<extracted base URL>');
        req.setMethod('<HTTP_METHOD>');
        // TODO: set headers (auth, Content-Type) based on extracted auth pattern
        req.setBody(/* build request body from inputs */);
        HttpResponse res = http.send(req);
        List<Output> results = new List<Output>();
        // TODO: parse res.getBody() and populate Output fields
        return results;
    }
}
```

Populate all fields from the extracted API surface confirmed in 2B.1. Use a separate `Input` inner class field for each identified input parameter, and a separate `Output` inner class field for each identified output field. Use the most appropriate Apex type for each field.

### 2B.3 Generate Apex metadata

Output: `force-app/main/default/classes/<SkillName>Action.cls-meta.xml`

```xml
<?xml version="1.0" encoding="UTF-8"?>
<ApexClass xmlns="http://soap.sforce.com/2006/04/metadata">
    <apiVersion>66.0</apiVersion>
    <status>Active</status>
</ApexClass>
```

### 2B.4 Generate Remote Site Settings

For each unique base domain extracted from the skill URLs, output:
`force-app/main/default/remoteSiteSettings/<SafeDomainName>.remoteSite-meta.xml`

Derive `<SafeDomainName>` by replacing dots and hyphens in the domain name with underscores and removing any other non-alphanumeric characters (e.g., `api.github.com` → `api_github_com`).

Create the `force-app/main/default/remoteSiteSettings/` directory if it does not exist.

```xml
<?xml version="1.0" encoding="UTF-8"?>
<RemoteSiteSetting xmlns="http://soap.sforce.com/2006/04/metadata">
    <isActive>true</isActive>
    <url>https://<domain></url>
    <description>Remote site for <skill-name> Apex callout</description>
</RemoteSiteSetting>
```

### 2B.5 Generate Custom Metadata Type for API keys (optional)

If the skill uses API keys (detected via `API_Key`, `API-Key`, or `X-Api-Key` patterns in the body), generate a Custom Metadata Type to securely store the key instead of hardcoding it. Ask the user if they want to use Custom Metadata or Named Credentials.

**Custom Metadata Type definition:**

Output: `force-app/main/default/objects/<servicename>__mdt/<servicename>__mdt.object-meta.xml`

```xml
<?xml version="1.0" encoding="UTF-8"?>
<CustomObject xmlns="http://soap.sforce.com/2006/04/metadata">
    <label><ServiceName></label>
    <pluralLabel><ServiceName></pluralLabel>
    <visibility>Protected</visibility>
    <fields>
        <fullName>apikey__c</fullName>
        <label>API Key</label>
        <type>Text</type>
        <length>255</length>
        <externalId>false</externalId>
    </fields>
</CustomObject>
```

**Custom Metadata record (placeholder):**

Output: `force-app/main/default/customMetadata/<servicename>.key.md-meta.xml`

```xml
<?xml version="1.0" encoding="UTF-8"?>
<CustomMetadata xmlns="http://soap.sforce.com/2006/04/metadata">
    <label>key</label>
    <protected>false</protected>
    <values>
        <field>apikey__c</field>
        <value xsi:type="xsd:string" xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" xmlns:xsd="http://www.w3.org/2001/XMLSchema">REPLACE_WITH_ACTUAL_KEY</value>
    </values>
</CustomMetadata>
```

Then reference the key in the Apex class via:
```apex
String apiKey = <servicename>__mdt.getInstance('key').apikey__c;
```

Derive `<servicename>` from the API domain or service name (lowercase, underscores, no dots). For example: `api.ydc-index.io` → `youdotcom`.

### 2B.6 Update source SKILL.md

Add `agentforce:` section to the **source** SKILL.md frontmatter. Use the full path recorded in Phase 0 — this will be either the local or global file:

```yaml
agentforce:
  target: "apex://<SkillName>Action"
  inputs:
    <param>:
      type: string
      required: true
  outputs:
    <result>:
      type: string
```

Add one entry under `inputs:` for each identified input parameter, and one entry under `outputs:` for each identified output field. Use the appropriate type (`string`, `number`, `boolean`, `object`).

**Global skill note:** Writing to `~/.claude/skills/<skill-name>/SKILL.md` marks the skill as migrated globally. It will appear as "Already migrated" in discover across all projects.

### 2B.7 Create or update the topic file

The topic file always lives in the **current project's** `.claude/agents/` directory, regardless of whether the skill came from local or global.

Same logic as Phase 2A.3, except `tools:` references `<SkillName>Action` (the Apex action, not a prompt action):

**Path A — Sub-agent already exists:** append `<SkillName>Action` to `tools:` and add a binding entry with `after: end`.

**Path B — No sub-agent exists:** create `.claude/agents/<skill-name>.md`:

```markdown
---
name: <skill-name>
description: <description from SKILL.md>
tools: <SkillName>Action
agentforce:
  bindings:
    <SkillName>Action:
      after: end
---
<scope paragraph derived from SKILL.md description>

Use `<SkillName>Action` to handle this request.
```

### 2B.8 Next steps output

After all files are written, display:

```
Migration complete for: <skill-name>  [<Local|Global> skill]

Files created/updated:
  force-app/main/default/classes/<SkillName>Action.cls
  force-app/main/default/classes/<SkillName>Action.cls-meta.xml
  force-app/main/default/remoteSiteSettings/<SafeDomainName>.remoteSite-meta.xml
  force-app/main/default/objects/<servicename>__mdt/  (if API key detected)
  force-app/main/default/customMetadata/<servicename>.key.md-meta.xml  (if API key detected)
  .claude/agents/<skill-name>.md  (created / updated)
  <source SKILL.md path>  (agentforce: target: added)

Required manual steps:
  1. Fill in the TODO sections in <SkillName>Action.cls:
     - Parse res.getBody() and populate Output fields
     - Add auth headers (Authorization, Content-Type)
  2. If using Custom Metadata for API key:
     Update the placeholder value in <servicename>.key.md-meta.xml with the actual key
  3. If the API uses OAuth or secret credentials:
     Create a Named Credential in Setup → Security → Named Credentials
     Then replace the hardcoded endpoint with: callout:<CredentialName>/path
  4. Deploy metadata: sf project deploy start --source-dir force-app/main/default -o <org>
  5. Run agentforce-convert to wire the topic into the Agent Script (GenAiPlannerBundle)
  6. Deploy the updated agent bundle to the org
```

---

## Complex (MCP) Skills — Manual Guidance

When a skill is classified as `Complex (MCP)` (contains `mcp__*` tool reference patterns), automated file generation is not supported in v1. Instead:

1. **Explain External MCP Server Connection**: This is the Salesforce-native feature for connecting MCP servers directly to Agentforce at runtime — no Apex needed. The agent can invoke MCP tools from your registered server without any custom code.

2. **Extract MCP server names**: From `mcp__<server>__<tool>` patterns in the skill body, identify the server names (e.g., `mcp__jira__search_issues` → server: `jira`).

3. **Provide manual setup guidance**:
   ```
   To migrate this MCP skill to Agentforce:

   MCP server detected: <server-name>
   Source: <Local|Global> — <full SKILL.md path>

   Manual setup in Salesforce:
     1. Go to Setup → Agents → External MCP Server Connections
     2. Click "New" and register your MCP server endpoint
     3. Provide the server URL and any required auth credentials
     4. Once registered, the MCP tools become available as agent actions
        without needing Apex code

   After registration, re-run agentforce-skill-migrate to wire
   the topic file and update the SKILL.md target.
   ```

4. **Note future automation**: Automated migration of MCP skills is planned for a future version of this tool.

---

## Files Generated per Path

| Path | Files created / updated |
|---|---|
| Simple | `force-app/main/default/genAiPromptTemplates/<SkillName>Prompt.genAiPromptTemplate-meta.xml` |
| Simple | `force-app/main/default/genAiFunctions/<SkillName>PromptAction/<SkillName>PromptAction.genAiFunction-meta.xml` (bundle) |
| Simple or Complex | `.claude/agents/<skill-name>.md` (created or updated — always in current project) |
| Simple or Complex | `<source SKILL.md path>` — local `.claude/skills/…` or global `~/.claude/skills/…` |
| Complex | `force-app/main/default/classes/<SkillName>Action.cls` (`with sharing`) |
| Complex | `force-app/main/default/classes/<SkillName>Action.cls-meta.xml` |
| Complex | `force-app/main/default/remoteSiteSettings/<SafeDomainName>.remoteSite-meta.xml` |
| Complex (optional) | `force-app/main/default/objects/<servicename>__mdt/<servicename>__mdt.object-meta.xml` |
| Complex (optional) | `force-app/main/default/customMetadata/<servicename>.key.md-meta.xml` |

All Salesforce metadata output goes under `force-app/main/default/` in the current project. Create the `force-app/` directory structure if it does not already exist.

The agent topic file (`.claude/agents/`) is always written to the **current project**, regardless of whether the skill source was local or global.

---

## Deployment Notes

**Deploy in two steps:**

1. **Platform metadata first** — deploy Apex classes, Remote Site Settings, Custom Metadata, and GenAiPromptTemplates:
   ```bash
   sf project deploy start --source-dir force-app/main/default -o <org>
   ```

2. **Agent wiring second** — run `agentforce-convert` to regenerate the Agent Script (GenAiPlannerBundle), then deploy the bundle:
   ```bash
   sf project deploy start --source-dir force-app/main/default/genAiPlannerBundles -o <org>
   ```

**Bot vs Bundle naming:** The Bot API name (e.g., `MyAgent`) is different from the GenAiPlannerBundle name (e.g., `MyAgent_v1`). Use the Bot name for `sf agent activate/deactivate` and the Bundle name for deployment and retrieval.

---

## Verification

After running `agentforce-skill-migrate <skill-name>`:

1. All files listed above exist with correct content
2. GenAiFunction files use **bundle** directory structure (subdirectory per function)
3. GenAiPromptTemplate files use `genAiPromptTemplates/` directory (NOT `promptTemplates/`)
4. Apex classes include `with sharing` declaration
5. Source SKILL.md (local or global) has `agentforce: target:` added — confirmed by re-running discover
6. `sf project deploy start --source-dir force-app/main/default -o <org>` succeeds
7. `agentforce-convert` includes the new topic and action in the generated `.agent` file
8. **Simple path**: Prompt Template visible in Setup → Einstein → Prompt Builder
9. **Complex path**: Apex class passes compilation check in the org after deploy
