---
name: debug-agent
description: Debug GECX agents — test sessions, inspect conversations, execute tools, view traces and changelogs
user_invocable: true
---

# Debug GECX Agent

You are an expert at debugging agents on the Google Customer Engagement Suite (GECX/CES) platform. Help the user diagnose issues by testing sessions, inspecting conversations, executing tools directly, and analyzing traces.

## Contents
- [Authentication](#authentication)
- [Base URL](#base-url)
- [Required Information](#required-information)
- [Diagnostic Toolkit](#diagnostic-toolkit)
  - [1. Inspect Current Agent Configuration](#1-inspect-current-agent-configuration)
  - [2. Test the Agent Interactively](#2-test-the-agent-interactively)
  - [3. Execute Tools Directly](#3-execute-tools-directly)
  - [4. Retrieve Tool Schema](#4-retrieve-tool-schema)
  - [5. List and Inspect Tools](#5-list-and-inspect-tools)
  - [6. Review Conversations](#6-review-conversations)
  - [7. Check Recent Changes (Changelogs)](#7-check-recent-changes-changelogs)
  - [8. Check Guardrails](#8-check-guardrails)
  - [9. List Examples](#9-list-examples)
  - [10. Check Deployments](#10-check-deployments)
  - [11. Stream Session (Server-Side Streaming)](#11-stream-session-server-side-streaming)
  - [12. Generate Chat Token](#12-generate-chat-token)
  - [13. Retrieve Toolset Tools](#13-retrieve-toolset-tools)
  - [14. Test Persona Voice](#14-test-persona-voice)
  - [15. Manage Operations (Long-Running)](#15-manage-operations-long-running)
- [Common Issues and Diagnosis](#common-issues-and-diagnosis)
  - [Agent doesn't call the right tool](#agent-doesnt-call-the-right-tool)
  - [Agent gives wrong responses](#agent-gives-wrong-responses)
  - [Agent transfers to wrong sub-agent](#agent-transfers-to-wrong-sub-agent)
  - [Tool returns errors](#tool-returns-errors)
  - [Agent is slow](#agent-is-slow)
  - [Toolset tools not showing up](#toolset-tools-not-showing-up)
- [Debugging Workflow](#debugging-workflow)

## Authentication
```bash
TOKEN=$(gcloud auth print-access-token)
```

## Base URL
```
https://ces.googleapis.com/v1beta
```

## Required Information

Ask the user for:
1. **Project ID** and **Location** (default: `global`)
2. **App ID** — which app to debug
3. **The problem** — what's going wrong?

---

## Diagnostic Toolkit

### 1. Inspect Current Agent Configuration

**List all agents:**
```bash
curl -s "https://ces.googleapis.com/v1beta/projects/${PROJECT}/locations/${LOCATION}/apps/${APP_ID}/agents" \
  -H "Authorization: Bearer ${TOKEN}" | jq '.agents[] | {name, displayName, instruction: .instruction[:200]}'
```

**Get agent details:**
```bash
curl -s "https://ces.googleapis.com/v1beta/projects/${PROJECT}/locations/${LOCATION}/apps/${APP_ID}/agents/${AGENT_ID}" \
  -H "Authorization: Bearer ${TOKEN}" | jq .
```

**Get app config:**
```bash
curl -s "https://ces.googleapis.com/v1beta/projects/${PROJECT}/locations/${LOCATION}/apps/${APP_ID}" \
  -H "Authorization: Bearer ${TOKEN}" | jq .
```

### 2. Test the Agent Interactively

**Send a single message:**
```bash
curl -s -X POST \
  "https://ces.googleapis.com/v1beta/projects/${PROJECT}/locations/${LOCATION}/apps/${APP_ID}/sessions/${SESSION_ID}:runSession" \
  -H "Authorization: Bearer ${TOKEN}" \
  -H "Content-Type: application/json" \
  -d '{
    "config": {},
    "inputs": [
      {"text": "<test message>"}
    ]
  }'
```

**Send with historical context (simulate mid-conversation):**
```bash
curl -s -X POST \
  "https://ces.googleapis.com/v1beta/projects/${PROJECT}/locations/${LOCATION}/apps/${APP_ID}/sessions/${SESSION_ID}:runSession" \
  -H "Authorization: Bearer ${TOKEN}" \
  -H "Content-Type: application/json" \
  -d '{
    "config": {
      "historicalContexts": [
        {"role": "user", "chunks": [{"text": "previous user message"}]},
        {"role": "agent", "chunks": [{"text": "previous agent response"}]}
      ]
    },
    "inputs": [
      {"text": "<current test message>"}
    ]
  }'
```

**Test with a specific entry agent (not root):**
```bash
curl -s -X POST \
  "https://ces.googleapis.com/v1beta/projects/${PROJECT}/locations/${LOCATION}/apps/${APP_ID}/sessions/${SESSION_ID}:runSession" \
  -H "Authorization: Bearer ${TOKEN}" \
  -H "Content-Type: application/json" \
  -d '{
    "config": {
      "entryAgent": "projects/${PROJECT}/locations/${LOCATION}/apps/${APP_ID}/agents/${AGENT_ID}"
    },
    "inputs": [
      {"text": "<test message>"}
    ]
  }'
```

**Test with fake tools (bypass real API calls):**
```bash
curl -s -X POST \
  "https://ces.googleapis.com/v1beta/projects/${PROJECT}/locations/${LOCATION}/apps/${APP_ID}/sessions/${SESSION_ID}:runSession" \
  -H "Authorization: Bearer ${TOKEN}" \
  -H "Content-Type: application/json" \
  -d '{
    "config": {
      "useToolFakes": true
    },
    "inputs": [
      {"text": "<test message>"}
    ]
  }'
```

### 3. Execute Tools Directly

Test if a tool works independently of the agent:
```bash
curl -s -X POST \
  "https://ces.googleapis.com/v1beta/projects/${PROJECT}/locations/${LOCATION}/apps/${APP_ID}:executeTool" \
  -H "Authorization: Bearer ${TOKEN}" \
  -H "Content-Type: application/json" \
  -d '{
    "tool": "projects/${PROJECT}/locations/${LOCATION}/apps/${APP_ID}/tools/${TOOL_ID}",
    "arguments": {
      "param1": "value1"
    }
  }'
```

### 4. Retrieve Tool Schema

Check what parameters a tool expects:
```bash
curl -s -X POST \
  "https://ces.googleapis.com/v1beta/projects/${PROJECT}/locations/${LOCATION}/apps/${APP_ID}:retrieveToolSchema" \
  -H "Authorization: Bearer ${TOKEN}" \
  -H "Content-Type: application/json" \
  -d '{
    "tool": "projects/${PROJECT}/locations/${LOCATION}/apps/${APP_ID}/tools/${TOOL_ID}"
  }'
```

### 5. List and Inspect Tools

```bash
curl -s "https://ces.googleapis.com/v1beta/projects/${PROJECT}/locations/${LOCATION}/apps/${APP_ID}/tools" \
  -H "Authorization: Bearer ${TOKEN}" | jq '.tools[] | {name, displayName, type: (keys - ["name","displayName","createTime","updateTime","etag","executionType"])[0]}'
```

### 6. Review Conversations

**List recent live conversations:**
```bash
curl -s "https://ces.googleapis.com/v1beta/projects/${PROJECT}/locations/${LOCATION}/apps/${APP_ID}/conversations?sources=LIVE&pageSize=10" \
  -H "Authorization: Bearer ${TOKEN}"
```

**List simulator conversations:**
```bash
curl -s "https://ces.googleapis.com/v1beta/projects/${PROJECT}/locations/${LOCATION}/apps/${APP_ID}/conversations?sources=SIMULATOR&pageSize=10" \
  -H "Authorization: Bearer ${TOKEN}"
```

**Get conversation details (full transcript):**
```bash
curl -s "https://ces.googleapis.com/v1beta/projects/${PROJECT}/locations/${LOCATION}/apps/${APP_ID}/conversations/${CONVERSATION_ID}" \
  -H "Authorization: Bearer ${TOKEN}" | jq '.turns[].messages[] | {role, text: .chunks[]?.text, toolCall: .chunks[]?.toolCall, agentTransfer: .chunks[]?.agentTransfer}'
```

### 7. Check Recent Changes (Changelogs)

```bash
curl -s "https://ces.googleapis.com/v1beta/projects/${PROJECT}/locations/${LOCATION}/apps/${APP_ID}/changelogs?pageSize=20" \
  -H "Authorization: Bearer ${TOKEN}" | jq '.changelogs[] | {createTime, action, resourceType, resourceName, author}'
```

### 8. Check Guardrails

```bash
curl -s "https://ces.googleapis.com/v1beta/projects/${PROJECT}/locations/${LOCATION}/apps/${APP_ID}/guardrails" \
  -H "Authorization: Bearer ${TOKEN}" | jq .
```

### 9. List Examples

```bash
curl -s "https://ces.googleapis.com/v1beta/projects/${PROJECT}/locations/${LOCATION}/apps/${APP_ID}/examples" \
  -H "Authorization: Bearer ${TOKEN}" | jq '.examples[] | {name, displayName, invalid}'
```

### 10. Check Deployments

```bash
curl -s "https://ces.googleapis.com/v1beta/projects/${PROJECT}/locations/${LOCATION}/apps/${APP_ID}/deployments" \
  -H "Authorization: Bearer ${TOKEN}" | jq .
```

### 11. Stream Session (Server-Side Streaming)

Test with streaming responses for real-time debugging:
```bash
curl -s -X POST \
  "https://ces.googleapis.com/v1beta/projects/${PROJECT}/locations/${LOCATION}/apps/${APP_ID}/sessions/${SESSION_ID}:streamRunSession" \
  -H "Authorization: Bearer ${TOKEN}" \
  -H "Content-Type: application/json" \
  -d '{
    "config": {
      "enableTextStreaming": true
    },
    "inputs": [
      {"text": "<test message>"}
    ]
  }'
```

### 12. Generate Chat Token

Generate a token for web-based chat integration:
```bash
curl -s -X POST \
  "https://ces.googleapis.com/v1beta/projects/${PROJECT}/locations/${LOCATION}/apps/${APP_ID}/sessions/${SESSION_ID}:generateChatToken" \
  -H "Authorization: Bearer ${TOKEN}" \
  -H "Content-Type: application/json" \
  -d '{}'
```

### 13. Retrieve Toolset Tools

Debug which tools a toolset resolves to (useful for MCP/OpenAPI toolsets):
```bash
curl -s -X POST \
  "https://ces.googleapis.com/v1beta/projects/${PROJECT}/locations/${LOCATION}/apps/${APP_ID}/toolsets/${TOOLSET_ID}:retrieveTools" \
  -H "Authorization: Bearer ${TOKEN}" \
  -H "Content-Type: application/json" \
  -d '{}'
```

### 14. Test Persona Voice

Test a persona's voice configuration:
```bash
curl -s -X POST \
  "https://ces.googleapis.com/v1beta/projects/${PROJECT}/locations/${LOCATION}/apps/${APP_ID}:testPersonaVoice" \
  -H "Authorization: Bearer ${TOKEN}" \
  -H "Content-Type: application/json" \
  -d '{
    "personaId": "<PERSONA_ID_OR_default>",
    "text": "Hello, how can I help you today?"
  }'
```

### 15. Manage Operations (Long-Running)

**List operations:**
```bash
curl -s "https://ces.googleapis.com/v1beta/projects/${PROJECT}/locations/${LOCATION}/operations" \
  -H "Authorization: Bearer ${TOKEN}"
```

**Get operation status:**
```bash
curl -s "https://ces.googleapis.com/v1beta/${OPERATION_NAME}" \
  -H "Authorization: Bearer ${TOKEN}"
```

**Cancel operation:**
```bash
curl -s -X POST \
  "https://ces.googleapis.com/v1beta/${OPERATION_NAME}:cancel" \
  -H "Authorization: Bearer ${TOKEN}" \
  -H "Content-Type: application/json" \
  -d '{}'
```

**Delete operation:**
```bash
curl -s -X DELETE \
  "https://ces.googleapis.com/v1beta/${OPERATION_NAME}" \
  -H "Authorization: Bearer ${TOKEN}"
```

---

## Common Issues and Diagnosis

### Agent doesn't call the right tool
1. Check the tool is attached to the agent (`tools` array)
2. Check the tool's name and description — the LLM uses these to decide
3. Check the instruction — does it mention when to use the tool?
4. Test the tool directly with `executeTool`
5. Check tool schema with `retrieveToolSchema`

### Agent gives wrong responses
1. Review the instruction text — is it clear and specific?
2. Check examples — are they consistent with desired behavior?
3. Check if globalInstruction on the App conflicts
4. Review recent changelogs for unintended changes
5. Test with specific historical contexts to isolate the issue

### Agent transfers to wrong sub-agent
1. Check `childAgents` on the parent agent
2. Check `transferRules` — deterministic rules take priority
3. Check child agent descriptions — the LLM uses these for routing
4. Check if `disablePlannerTransfer` rules are blocking

### Tool returns errors
1. Execute the tool directly with `executeTool`
2. Check authentication config (API key, OAuth, service account)
3. Check the OpenAPI schema is valid
4. For connector tools, verify the connection resource exists

### Agent is slow
1. Check model — `gemini-2.0-flash` is faster than pro models
2. Check `toolExecutionMode` — `PARALLEL` is faster for independent tools
3. Review tool latency in evaluation results
4. Check if callbacks are adding overhead

### Toolset tools not showing up
1. Check the toolset exists and is attached to the agent (`toolsets` on the agent resource)
2. Use `retrieveTools` to see what tools the toolset resolves to
3. For MCP toolsets, verify the server address is reachable
4. For OpenAPI toolsets, verify the schema is valid
5. Check if `toolIds` filter on the toolset is too restrictive

---

## Debugging Workflow

1. **Understand the problem** — Ask user what's happening vs. what's expected
2. **Inspect configuration** — Check agent, tools, instructions, examples
3. **Reproduce** — Send test messages via `runSession`
4. **Isolate** — Test tools directly, test sub-agents individually, test with fake tools
5. **Check history** — Review conversations and changelogs
6. **Identify root cause** — Configuration, instruction, tool, or model issue
7. **Fix** — Update the relevant resource via PATCH
8. **Verify** — Re-test after the fix
