# Agent Script / Agentforce Metadata Reference

## What is Agent Script?

Agent Script is Salesforce's language for building agents in Agentforce Builder. It combines:
- **Natural language instructions** for conversational tasks
- **Programmatic expressions** for business rules and determinism

Key capabilities:
- Conditional expressions (if/else)
- Variable management for state tracking
- Topic transitions (deterministic or LLM-controlled)
- Action sequencing and chaining
- Reasoning boundaries (LLM freedom vs deterministic execution)

## Writing Methods
1. **Conversational**: Chat with Agentforce to describe behavior
2. **Canvas View**: Visual blocks with `/` for expressions and `@` for resources
3. **Script View**: Direct editing with syntax highlighting and validation

## Syntax Elements
- `->` for conditional logic
- `|` for LLM prompts
- `/` shortcuts for common patterns
- `@` for referencing topics, actions, variables

---

## Agentforce Metadata Types

There is **no single `.ascript` file**. Agents are defined through multiple interrelated XML metadata types:

| Metadata Type | File Suffix | Directory | Purpose |
|---|---|---|---|
| **Bot** | `.bot-meta.xml` | `bots/` | Top-level agent definition |
| **BotVersion** | `.botVersion-meta.xml` | `bots/<name>/` | Version: role, dialogs, planner ref, variables |
| **GenAiPlannerBundle** | `.genAiPlannerBundle` | `genAiPlannerBundles/` | Orchestrator: topics, functions, routing, conditions |
| **GenAiPlugin** | `.genAiPlugin-meta.xml` | `genAiPlugins/` | Topic: scope, instructions, assigned actions |
| **GenAiFunction** | `.genAiFunction-meta.xml` | `genAiFunctions/` | Action: wraps Flow, Apex, or Prompt Template |
| **GenAiPromptTemplate** | `.genAiPromptTemplate-meta.xml` | `genAiPromptTemplates/` | Prompt template with LLM model and data providers |
| **AiEvaluationDefinition** | `.aiEvaluationDefinition-meta.xml` | `aiEvaluationDefinitions/` | Agent test cases |

---

## Directory Structure

```
force-app/main/default/
  bots/
    <AgentName>/
      <AgentName>.bot-meta.xml
      v1.botVersion-meta.xml
  genAiPlannerBundles/
    <PlannerName>/
      <PlannerName>.genAiPlannerBundle
  genAiPlugins/
    <PluginName>.genAiPlugin-meta.xml
  genAiFunctions/
    <FunctionName>/
      <FunctionName>.genAiFunction-meta.xml
      input/schema.json
      output/schema.json
  genAiPromptTemplates/
    <TemplateName>.genAiPromptTemplate-meta.xml
  aiEvaluationDefinitions/
    <TestName>.aiEvaluationDefinition-meta.xml
  lightningTypes/
    <TypeName>/
      schema.json
      lightningDesktopGenAi/renderer.json
```

---

## Relationship Diagram

```
Bot (.bot-meta.xml)
  |-- agentType, contextVariables, type
  |
  +-- BotVersion (.botVersion-meta.xml)
        |-- role (system prompt), company, toneType
        |-- entryDialog, botDialogs (welcome, error)
        |-- conversationVariables
        |
        +-- conversationDefinitionPlanners --> GenAiPlannerBundle
              |-- plannerType: AiCopilot__ReAct
              |-- attributeMappings (variable flow)
              |-- ruleExpressions (conditions)
              |-- ruleExpressionAssignments (condition -> topic)
              |
              +-- genAiPlugins --> GenAiPlugin (Topics)
              |     |-- scope (topic system prompt)
              |     |-- description (for routing)
              |     |-- genAiPluginInstructions
              |     +-- genAiFunctions --> GenAiFunction (Actions)
              |
              +-- genAiFunctions --> GenAiFunction (standalone)
                    |-- invocationTargetType: apex | flow | generatePromptResponse
                    |-- invocationTarget
                    |-- isConfirmationRequired
                    +-- input/schema.json, output/schema.json
```

---

## Detailed Metadata Examples

### Bot (.bot-meta.xml)

```xml
<?xml version="1.0" encoding="UTF-8" ?>
<Bot xmlns="http://soap.sforce.com/2006/04/metadata">
    <agentType>AgentforceEmployeeAgent</agentType>  <!-- or EinsteinServiceAgent -->
    <botMlDomain>
        <label>My Agent</label>
        <name>My_Agent</name>
    </botMlDomain>
    <botUser>agent-username</botUser>  <!-- service agents only -->
    <contextVariables>
        <contextVariableMappings>
            <SObjectType>MessagingSession</SObjectType>
            <fieldName>MessagingSession.MessagingEndUserId</fieldName>
            <messageType>EmbeddedMessaging</messageType>
        </contextVariableMappings>
        <dataType>Id</dataType>
        <developerName>EndUserId</developerName>
        <includeInPrompt>true</includeInPrompt>
        <label>End User Id</label>
    </contextVariables>
    <description>Agent description</description>
    <label>My Agent</label>
    <logPrivateConversationData>false</logPrivateConversationData>
    <richContentEnabled>true</richContentEnabled>
    <sessionTimeout>480</sessionTimeout>
    <type>InternalCopilot</type>  <!-- or ExternalCopilot -->
</Bot>
```

**Key fields:**
- `agentType`: `AgentforceEmployeeAgent` | `EinsteinServiceAgent`
- `type`: `InternalCopilot` | `ExternalCopilot`
- `botUser`: User the agent runs as (service agents)
- `defaultOutboundFlow`: Escalation/routing flow (service agents)
- `sessionTimeout`: Minutes (0 = none)
- `contextVariables`: Maps channel data to variables
  - `messageType`: `EmbeddedMessaging`, `WhatsApp`, `Facebook`, `Text`, `AppleBusinessChat`, `Line`, `Custom`

### BotVersion (.botVersion-meta.xml)

```xml
<?xml version="1.0" encoding="UTF-8" ?>
<BotVersion xmlns="http://soap.sforce.com/2006/04/metadata">
    <fullName>v1</fullName>
    <botDialogs>
        <botSteps>
            <botMessages>
                <message>Hi! How can I help?</message>
                <messageIdentifier>uuid</messageIdentifier>
            </botMessages>
            <stepIdentifier>uuid</stepIdentifier>
            <type>Message</type>
        </botSteps>
        <botSteps>
            <stepIdentifier>uuid</stepIdentifier>
            <type>Wait</type>
        </botSteps>
        <developerName>Welcome</developerName>
        <label>Welcome</label>
    </botDialogs>
    <company>Company description for LLM context</company>
    <conversationDefinitionPlanners>
        <genAiPlannerName>My_Agent</genAiPlannerName>
    </conversationDefinitionPlanners>
    <conversationVariables>
        <dataType>Text</dataType>
        <developerName>currentRecordId</developerName>
        <includeInPrompt>true</includeInPrompt>
        <label>currentRecordId</label>
        <visibility>External</visibility>
    </conversationVariables>
    <entryDialog>Welcome</entryDialog>
    <role>You are an agent that helps with...</role>
    <toneType>Casual</toneType>
</BotVersion>
```

**Key fields:**
- `role`: System prompt / persona
- `company`: Company context
- `toneType`: `Casual`, `Formal`, etc.
- `conversationDefinitionPlanners.genAiPlannerName`: Links to GenAiPlannerBundle
- `conversationVariables`: Runtime vars with `dataType`, `visibility` (Internal/External), `includeInPrompt`

### GenAiPlannerBundle (.genAiPlannerBundle)

```xml
<?xml version="1.0" encoding="UTF-8"?>
<GenAiPlannerBundle xmlns="http://soap.sforce.com/2006/04/metadata">
    <description>Agent description</description>
    <masterLabel>My Agent</masterLabel>
    <plannerType>AiCopilot__ReAct</plannerType>

    <!-- Standalone functions -->
    <genAiFunctions>
        <genAiFunctionName>EmployeeCopilot__AnswerQuestionsWithKnowledge</genAiFunctionName>
    </genAiFunctions>

    <!-- Topics -->
    <genAiPlugins>
        <genAiPluginName>Customer_Support</genAiPluginName>
    </genAiPlugins>

    <!-- Variable flow between actions -->
    <attributeMappings>
        <attributeName>Topic.Action.parameterName</attributeName>
        <attributeType>StandardPluginFunctionOutput</attributeType>
        <mappingTargetName>variableName</mappingTargetName>
        <mappingType>Variable</mappingType>
    </attributeMappings>

    <!-- Conditional rules -->
    <ruleExpressions>
        <conditions>
            <leftOperand>isVerified</leftOperand>
            <leftOperandType>Variable</leftOperandType>
            <operator>equal</operator>
            <rightOperandValue>true</rightOperandValue>
        </conditions>
        <expressionLabel>Is Verified</expressionLabel>
        <expressionName>Is_Verified</expressionName>
        <expressionType>sel</expressionType>
    </ruleExpressions>

    <!-- Assign rules to topics -->
    <ruleExpressionAssignments>
        <ruleExpressionName>Is_Verified</ruleExpressionName>
        <targetName>Verified_Support</targetName>
        <targetType>Plugin</targetType>
    </ruleExpressionAssignments>
</GenAiPlannerBundle>
```

**Key fields:**
- `plannerType`: Always `AiCopilot__ReAct`
- `attributeMappings`: Data flow, dot-notation `Plugin.Function.parameter`
  - `attributeType`: `StandardPluginFunctionOutput`, `StandardPluginFunctionInput`, `CustomPluginFunctionAttribute`
- `ruleExpressions.conditions.operator`: `isEmpty`, `isNotEmpty`, `equal`
- `ruleExpressionAssignments`: Maps conditions to topics

### GenAiPlugin (.genAiPlugin-meta.xml) - Topics

```xml
<?xml version="1.0" encoding="UTF-8"?>
<GenAiPlugin xmlns="http://soap.sforce.com/2006/04/metadata">
    <canEscalate>false</canEscalate>
    <description>Handles booking inquiries</description>
    <developerName>Customer_Support</developerName>
    <genAiFunctions>
        <functionName>Create_Booking</functionName>
    </genAiFunctions>
    <genAiFunctions>
        <functionName>Check_Weather</functionName>
    </genAiFunctions>
    <genAiPluginInstructions>
        <description>Always verify the customer before creating a booking.</description>
        <developerName>instruction_alwaysver0</developerName>
        <language>en_US</language>
        <masterLabel>instruction_alwaysver0</masterLabel>
    </genAiPluginInstructions>
    <language>en_US</language>
    <masterLabel>Customer Support</masterLabel>
    <pluginType>Topic</pluginType>
    <scope>Your job is to help customers with bookings and inquiries.</scope>
</GenAiPlugin>
```

### GenAiFunction (.genAiFunction-meta.xml) - Actions

Three invocation types:

**Apex:**
```xml
<GenAiFunction xmlns="http://soap.sforce.com/2006/04/metadata">
    <description>Check weather at a specific date</description>
    <invocationTarget>CheckWeather</invocationTarget>
    <invocationTargetType>apex</invocationTargetType>
    <isConfirmationRequired>false</isConfirmationRequired>
    <masterLabel>Check Weather</masterLabel>
</GenAiFunction>
```

**Flow (with confirmation):**
```xml
<GenAiFunction xmlns="http://soap.sforce.com/2006/04/metadata">
    <description>Create a booking record</description>
    <invocationTarget>Create_Booking</invocationTarget>
    <invocationTargetType>flow</invocationTargetType>
    <isConfirmationRequired>true</isConfirmationRequired>
    <mappingAttributes>
        <label>contactId</label>
        <name>input_contactId</name>
        <parameterName>contactId</parameterName>
        <parameterType>input</parameterType>
    </mappingAttributes>
    <masterLabel>Create Booking</masterLabel>
</GenAiFunction>
```

**Prompt Template:**
```xml
<GenAiFunction xmlns="http://soap.sforce.com/2006/04/metadata">
    <description>Generate a personalized schedule</description>
    <invocationTarget>Generate_Personalized_Schedule</invocationTarget>
    <invocationTargetType>generatePromptResponse</invocationTargetType>
    <isConfirmationRequired>false</isConfirmationRequired>
    <masterLabel>Generate Schedule</masterLabel>
</GenAiFunction>
```

### Input/Output Schemas (schema.json)

**Input:**
```json
{
    "required": ["contactId", "numberOfGuests"],
    "unevaluatedProperties": false,
    "properties": {
        "contactId": {
            "title": "contactId",
            "description": "Contact record ID",
            "lightning:type": "lightning__textType",
            "lightning:isPII": false,
            "copilotAction:isUserInput": false
        },
        "numberOfGuests": {
            "title": "numberOfGuests",
            "description": "Number of guests",
            "lightning:type": "lightning__numberType",
            "copilotAction:isUserInput": true
        }
    },
    "lightning:type": "lightning__objectType"
}
```

**Output:**
```json
{
    "unevaluatedProperties": false,
    "properties": {
        "result": {
            "title": "result",
            "description": "The created booking",
            "lightning:type": "lightning__recordInfoType",
            "lightning:sObjectInfo": { "apiName": "Booking__c" },
            "copilotAction:isDisplayable": true,
            "copilotAction:isUsedByPlanner": true
        }
    },
    "lightning:type": "lightning__objectType"
}
```

**Lightning types:** `lightning__textType`, `lightning__numberType`, `lightning__dateType`, `lightning__booleanType`, `lightning__recordInfoType`, `lightning__objectType`, `c__customType`

### AiEvaluationDefinition - Agent Tests

```xml
<AiEvaluationDefinition xmlns="http://soap.sforce.com/2006/04/metadata">
    <name>Agent Tests</name>
    <subjectName>My_Agent</subjectName>
    <subjectType>AGENT</subjectType>
    <subjectVersion>v1</subjectVersion>
    <testCase>
        <inputs>
            <utterance>What's the weather tomorrow?</utterance>
        </inputs>
        <number>1</number>
        <expectation>
            <expectedValue>['Check_Weather']</expectedValue>
            <name>action_sequence_match</name>
        </expectation>
        <expectation>
            <expectedValue>Customer_Support</expectedValue>
            <name>topic_sequence_match</name>
        </expectation>
        <expectation><name>completeness</name></expectation>
        <expectation><name>coherence</name></expectation>
    </testCase>
</AiEvaluationDefinition>
```

**Expectation types:**
- `action_sequence_match`: `['Action1', 'Action2']`
- `topic_sequence_match`: Topic name
- `bot_response_rating`: Expected response text
- `completeness`, `coherence`, `conciseness`: Auto-evaluated
- `output_latency_milliseconds`: Performance

---

## Built-in Standard Functions

| Function | Purpose |
|----------|---------|
| `EmployeeCopilot__AnswerQuestionsWithKnowledge` | Knowledge-based Q&A |
| `EmployeeCopilot__GetRecordDetails` | Get record details |
| `EmployeeCopilot__QueryRecords` | Query records (SOQL-like) |
| `EmployeeCopilot__SummarizeRecord` | Summarize a record |
| `SvcCopilotTmpl__SendEmailVerificationCode` | Send verification email |
| `SvcCopilotTmpl__VerifyCustomer` | Verify customer identity |

## Deployment

Standard Salesforce metadata deployment:
- `sf project deploy start` / `sf project retrieve start`
- Permission sets required for agent access
- Prerequisites: Einstein, Data Cloud, Agentforce licensing enabled
