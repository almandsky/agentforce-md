# Project Overview: Agentforce + Markdown Conventions POC

## Vision

Enable developers using Claude Code to:
1. Prompt Claude Code to create an Agentforce Agent
2. Claude generates `agent.md`, `skills.md`, hooks, etc. (markdown conventions)
3. A converter translates markdown files into Agent Script (Salesforce metadata)
4. Developer previews and tests the agent locally in Claude Code
5. If satisfied, deploy the agent to a Salesforce Org

## Source Document

From the TDX planning doc, the key deliverables are:

### Milestone 1
- **Integrate Skills.md**: Support markdown-based skills within the authoring bundle. Agent Script remains canonical but references .md files.
- **Import/Export for Agents.md <-> Global Instructions**: Bidirectional translation between Agents.md and Agent Script
- **Support markdown in global instructions**
- **Import/Export for subagent.md <-> Topic**: Map sub-agents to Agentforce topics
- **Expose hooks**: PreToolUse, PostToolUse, SessionStart, StopHook
- **Import/Export for tools.yml**: Convert tools.yml to action definitions and vice versa
- **Import/Export Markdown Bundle**: Full zip with agents.md, sub-agents.md, tools.yml, skills.md

### Key Constraints
- No expectation of editing in NGA (Next-Gen Agent builder)
- API-first approach
- Imports are allowed to be lossy (Agent Script is more restrictive than markdown)
- Target Script first, then graph

## Personas
- **Primary**: CIO/CTO devs building outside Salesforce (AFDX / VS Code / Claude Code / Cursor)
- **Secondary**: FDE & SI devs (CRM-friendly developers)

## Comparison: Agent.md vs Agent Script vs Agent JSON

| Feature | Agent.md | Agent Script | Agent JSON |
|---------|----------|-------------|------------|
| Determinism | Yes | Yes | Yes |
| Sub Agents | Yes | Yes | Yes |
| Tool Filtering | No | Yes | Yes |
| Agent Deploy | No | Yes | Yes |
| Client Connection | No | Yes | Yes |
| Structured Sub-Agent Transition | No | Yes | Yes |
| Handoff | No | Yes (resets to main) | Yes |
| Supervision | No | No (planned) | Yes |
| skill.md support | Yes | Yes | Yes |
| MCP support | Yes | Yes | Yes |
