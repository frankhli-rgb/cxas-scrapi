---
name: eval-report
description: Generate a comprehensive eval report — coverage analysis of existing evals and structured run results
user_invocable: true
---

# GECX Eval Report

You are an expert at generating comprehensive evaluation reports for agents on the Google Customer Engagement Suite (GECX/CES) platform. Generate two types of reports: **coverage analysis** (what do existing evals test?) and **run results** (how did evals perform?).

## Contents
- [Authentication](#authentication)
- [Base URL](#base-url)
- [Required Information](#required-information)
- [Part 1: Coverage Analysis](#part-1-coverage-analysis)
  - [1a. Fetch All Agent Configuration](#1a-fetch-all-agent-configuration)
  - [1b. Fetch All Evaluations (Full Detail)](#1b-fetch-all-evaluations-full-detail)
  - [1c. Build Coverage Report](#1c-build-coverage-report)
- [Python Code / Callback Coverage](#python-code--callback-coverage)
- [Guardrail Coverage](#guardrail-coverage)
- [Custom LLM Judges (Evaluation Expectations)](#custom-llm-judges-evaluation-expectations)
- [Scheduled Runs](#scheduled-runs)
- [Evaluation Datasets](#evaluation-datasets)
- [Gaps & Recommendations](#gaps--recommendations)
- [Part 2: Run Results Report](#part-2-run-results-report)
  - [2a. Get Latest Evaluation Runs](#2a-get-latest-evaluation-runs)
  - [2b. Get Run Details](#2b-get-run-details)
  - [2c. Get All Results for Each Evaluation in the Run](#2c-get-all-results-for-each-evaluation-in-the-run)
  - [2d. Get Aggregated Metrics](#2d-get-aggregated-metrics)
  - [2e. Build Run Results Report](#2e-build-run-results-report)
- [Execution Workflow](#execution-workflow)
- [Tips](#tips)

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
2. **App ID** — which app to report on
3. **Report type** — Coverage, Run Results, or Both (default: Both)

---

## Part 1: Coverage Analysis

Analyze what the existing evaluations cover across the agent's capabilities.

### 1a. Fetch All Agent Configuration

```bash
# Get app config (root agent, global instruction, model)
curl -s "https://ces.googleapis.com/v1beta/projects/${PROJECT}/locations/${LOCATION}/apps/${APP_ID}" \
  -H "Authorization: Bearer ${TOKEN}" | jq '{displayName, rootAgent, globalInstruction, modelSettings}'

# Get all agents with instructions
curl -s "https://ces.googleapis.com/v1beta/projects/${PROJECT}/locations/${LOCATION}/apps/${APP_ID}/agents" \
  -H "Authorization: Bearer ${TOKEN}" | jq '.agents[] | {name, displayName, instruction, tools, childAgents, toolsets}'

# Get all tools
curl -s "https://ces.googleapis.com/v1beta/projects/${PROJECT}/locations/${LOCATION}/apps/${APP_ID}/tools" \
  -H "Authorization: Bearer ${TOKEN}" | jq '.tools[] | {name, displayName, type: (keys - ["name","displayName","createTime","updateTime","etag","executionType"])[0]}'

# Get all toolsets
curl -s "https://ces.googleapis.com/v1beta/projects/${PROJECT}/locations/${LOCATION}/apps/${APP_ID}/toolsets" \
  -H "Authorization: Bearer ${TOKEN}" | jq '.toolsets[]? | {name, displayName, type: (if .mcpToolset then "MCP" elif .openApiToolset then "OpenAPI" elif .connectorToolset then "Connector" else "unknown" end)}'

# Get examples
curl -s "https://ces.googleapis.com/v1beta/projects/${PROJECT}/locations/${LOCATION}/apps/${APP_ID}/examples" \
  -H "Authorization: Bearer ${TOKEN}" | jq '.examples[]? | {name, displayName}'

# Get guardrails
curl -s "https://ces.googleapis.com/v1beta/projects/${PROJECT}/locations/${LOCATION}/apps/${APP_ID}/guardrails" \
  -H "Authorization: Bearer ${TOKEN}" | jq '.guardrails[]? | {name, displayName, enabled, type: (if .contentFilter then "contentFilter" elif .llmPromptSecurity then "llmPromptSecurity" elif .llmPolicy then "llmPolicy" elif .modelSafety then "modelSafety" elif .codeCallback then "codeCallback" else "unknown" end)}'
```

### 1b. Fetch All Evaluations (Full Detail)

```bash
# List all evaluations
curl -s "https://ces.googleapis.com/v1beta/projects/${PROJECT}/locations/${LOCATION}/apps/${APP_ID}/evaluations" \
  -H "Authorization: Bearer ${TOKEN}" | jq '.evaluations[]'

# List evaluation datasets
curl -s "https://ces.googleapis.com/v1beta/projects/${PROJECT}/locations/${LOCATION}/apps/${APP_ID}/evaluationDatasets" \
  -H "Authorization: Bearer ${TOKEN}"

# List evaluation expectations (custom LLM judges)
curl -s "https://ces.googleapis.com/v1beta/projects/${PROJECT}/locations/${LOCATION}/apps/${APP_ID}/evaluationExpectations" \
  -H "Authorization: Bearer ${TOKEN}"

# List scheduled evaluation runs
curl -s "https://ces.googleapis.com/v1beta/projects/${PROJECT}/locations/${LOCATION}/apps/${APP_ID}/scheduledEvaluationRuns" \
  -H "Authorization: Bearer ${TOKEN}"
```

### 1c. Build Coverage Report

Analyze the data and produce a structured coverage report:

#### Coverage Report Template

```
# Eval Coverage Report — <APP_NAME>
Generated: <DATE>

## Agent Architecture
- Root Agent: <name>
- Sub-agents: <list with descriptions>
- Total agents: <N>

## Coverage Summary

| Dimension           | Total | Covered by Evals | Coverage % | Gaps |
|---------------------|-------|-------------------|------------|------|
| Agents              |       |                   |            |      |
| Tools               |       |                   |            |      |
| Agent Transfers     |       |                   |            |      |
| Guardrails          |       |                   |            |      |
| Instruction Intents |       |                   |            |      |

## Evaluation Inventory

| # | Name | Type | Tags | Turns/Rubrics | Tools Tested | Agents Tested | Status |
|---|------|------|------|---------------|-------------|---------------|--------|
|   |      |      |      |               |             |               |        |

## Tool Coverage

| Tool Name | Type | Used in N Evals | Eval Names | Params Tested |
|-----------|------|-----------------|------------|---------------|
|           |      |                 |            |               |

## Agent Transfer Coverage

| From Agent | To Agent | Tested? | Eval Names |
|------------|----------|---------|------------|
|            |          |         |            |

## Instruction Coverage Analysis (Deep Prompt Audit)

This is the most critical section. For EACH agent, you must:

1. **Read the full instruction text** from the agent config (fetched in step 1a)
2. **Decompose the instruction into discrete, testable directives** using the categories below
3. **Cross-reference each directive against all evaluations** to determine if any eval exercises that behavior
4. **Flag uncovered directives** as gaps

### How to Decompose Agent Instructions

Parse the instruction text and extract every distinct directive into one of these categories:

| Category | What to look for | Examples |
|----------|-----------------|---------|
| **Persona / Identity** | Role definitions, tone, communication style | "You are a virtual assistant for [the brand]", "Be professional and factual" |
| **Conversation Flow Rules** | Ordered steps, required sequences, state transitions | "First ask X, then do Y", "After authentication, proceed to..." |
| **Tool Usage Rules** | When to call which tool, required parameters, how to use results | "Use the FAQ/knowledge tool when...", "Call the diagnostic tool after identifying the issue" |
| **Conditional Behaviors** | If/then/else logic, branching based on user input or state | "If user has multiple lines, ask which one", "If API fails, escalate" |
| **Guardrails / Constraints** | Things the agent must never do, boundaries, restrictions | "NEVER ask the user to call or contact...", "Only use information from tool responses" |
| **Escalation Rules** | When to transfer to human or another agent, escalation triggers | "Escalate if user uses profanity", "Transfer to sub_agent_a when..." |
| **Response Format Rules** | How to format responses, pronunciation, acknowledgements | "Pronounce numbers as individual digits", "Use brief acknowledgements" |
| **Edge Case Handling** | Specific scenarios with special handling | "If user asks about competitor...", "Handle inappropriate questions by..." |
| **Variable / State Management** | Session variables to set, state transitions | "Set auth_status to...", "Update device_type when..." |
| **Transfer Rules** | When to route to child agents | "Transfer to sub_agent_b when user reports a specific issue type" |

### Instruction Directive Table

For each agent, produce a table like this:

| # | Agent | Category | Directive (from instruction) | Instruction Quote | Covered? | Covering Eval(s) | Notes |
|---|-------|----------|------------------------------|-------------------|----------|-------------------|-------|
| 1 | root_agent | Persona | Be professional, factual, positive | "Be professional, factual, and positive" | Partial | scenario evals check tone | No golden eval verifies exact tone |
| 2 | root_agent | Guardrail | Express empathy ONLY ONCE per conversation | "Express empathy ONLY ONCE per conversation when a problem is first identified" | No | — | Need eval with multi-turn empathy check |
| 3 | root_agent | Escalation | Escalate after 2 failed attempts or profanity | "Escalate to a human agent if the customer is unable to provide the correct responses in two attempts or uses profanity" | No | — | Need golden eval with 2 wrong attempts |
| 4 | root_agent | Response Format | Pronounce numbers as individual digits | "Always pronounce numbers as individual digits" | No | — | Voice-specific, hard to test in text evals |
| ... | ... | ... | ... | ... | ... | ... | ... |

### How to Determine if a Directive is Covered

A directive is **covered** if there exists at least one evaluation (golden or scenario) that would exercise that specific behavior:

- **Golden eval covers a directive** if:
  - A turn's `userInput` would trigger the directive's condition
  - An `expectation` (toolCall, agentResponse, agentTransfer, updatedVariables) verifies the directive's expected outcome
  - Example: Directive "call the diagnostic tool after identifying the issue" is covered if a golden eval has a turn that identifies the issue, followed by a `toolCall` expectation for that diagnostic tool

- **Scenario eval covers a directive** if:
  - The scenario's `task` description describes a situation that would trigger the directive
  - A `rubric` explicitly checks for the directive's behavior
  - A `scenarioExpectation` verifies the expected tool call or outcome
  - Example: Directive "escalate if user uses profanity" is covered if a scenario has task "user is angry and uses profanity" with rubric "agent should escalate to human"

- **NOT covered** if:
  - No eval triggers the directive's condition at all
  - An eval triggers the condition but has no expectation/rubric verifying the correct outcome
  - The eval that would cover it is `invalid: true`

### Coverage Summary Per Agent

After the directive table, summarize per agent:

```
### <AGENT_NAME> Instruction Coverage

- **Total directives extracted**: N
- **Covered**: N (X%)
- **Partially covered**: N (X%)
- **Not covered**: N (X%)

**Most critical uncovered directives:**
1. <directive> — Why it matters: <impact if untested>
2. <directive> — Why it matters: <impact if untested>
```

## Python Code / Callback Coverage

List all python callbacks (agent callbacks, guardrail code callbacks, python tools)
and whether they have eval coverage:

| Location | Callback Type | Description | Tested? | Eval Name |
|----------|---------------|-------------|---------|-----------|
|          |               |             |         |           |

## Guardrail Coverage

| Guardrail | Type | Enabled | Tested? | Eval Name |
|-----------|------|---------|---------|-----------|
|           |      |         |         |           |

## Custom LLM Judges (Evaluation Expectations)

| Name | Prompt Summary | Tags | Used In Evals |
|------|----------------|------|---------------|
|      |                |      |               |

## Scheduled Runs

| Name | Frequency | Active | Next Run | Evals Included |
|------|-----------|--------|----------|----------------|
|      |           |        |          |                |

## Evaluation Datasets

| Name | # Evals | Evals Included |
|------|---------|----------------|
|      |         |                |

## Gaps & Recommendations

1. **Untested tools**: <list>
2. **Untested agent transfers**: <list>
3. **Uncovered instruction intents**: <list>
4. **Missing negative/edge case tests**: <list>
5. **Untested guardrails**: <list>
6. **Untested callbacks/python code**: <list>
7. **No scheduled runs**: <yes/no — recommend if missing>
```

---

## Part 2: Run Results Report

Generate a structured report from the latest (or specified) evaluation run.

### 2a. Get Latest Evaluation Runs

```bash
# List recent eval runs
curl -s "https://ces.googleapis.com/v1beta/projects/${PROJECT}/locations/${LOCATION}/apps/${APP_ID}/evaluationRuns" \
  -H "Authorization: Bearer ${TOKEN}" | jq '.evaluationRuns[] | {name, displayName, state, createTime, evaluationType, evaluationRunSummaries, latencyReport}'
```

### 2b. Get Run Details

```bash
# Get specific run with summaries
curl -s "https://ces.googleapis.com/v1beta/projects/${PROJECT}/locations/${LOCATION}/apps/${APP_ID}/evaluationRuns/${RUN_ID}" \
  -H "Authorization: Bearer ${TOKEN}"
```

### 2c. Get All Results for Each Evaluation in the Run

```bash
# Get results for a specific evaluation
curl -s "https://ces.googleapis.com/v1beta/projects/${PROJECT}/locations/${LOCATION}/apps/${APP_ID}/evaluations/${EVAL_ID}/results" \
  -H "Authorization: Bearer ${TOKEN}"

# Get specific result with full detail
curl -s "https://ces.googleapis.com/v1beta/projects/${PROJECT}/locations/${LOCATION}/apps/${APP_ID}/evaluations/${EVAL_ID}/results/${RESULT_ID}" \
  -H "Authorization: Bearer ${TOKEN}"
```

### 2d. Get Aggregated Metrics

```bash
# Evaluations include aggregatedMetrics and lastCompletedResult
curl -s "https://ces.googleapis.com/v1beta/projects/${PROJECT}/locations/${LOCATION}/apps/${APP_ID}/evaluations" \
  -H "Authorization: Bearer ${TOKEN}" | jq '.evaluations[] | {displayName, evaluationStatus: .lastCompletedResult.evaluationStatus, aggregatedMetrics}'
```

### 2e. Build Run Results Report

#### Run Results Report Template

```
# Eval Run Results — <APP_NAME>
Run: <RUN_DISPLAY_NAME>
Date: <CREATE_TIME>
App Version: <APP_VERSION_DISPLAY_NAME>
Initiated by: <INITIATED_BY>

## Run Summary

| Metric        | Value |
|---------------|-------|
| Total Evals   |       |
| Passed        |       |
| Failed        |       |
| Errors        |       |
| Pass Rate     |       |

## Results by Evaluation

### <EVAL_NAME> — <PASS/FAIL>

**Type:** Golden / Scenario
**Status:** PASS / FAIL

#### Golden Results (per turn)

| Turn | Tool Invocation | Semantic Similarity | Hallucination | Latency | Status |
|------|-----------------|---------------------|---------------|---------|--------|
|      |                 |                     |               |         |        |

**Expectation Details:**

| Turn | Step | Type | Expected | Observed | Outcome | Note |
|------|------|------|----------|----------|---------|------|
|      |      |      |          |          |         |      |

#### Scenario Results

| Metric                  | Value |
|-------------------------|-------|
| Task Completed          |       |
| User Goal Satisfied     |       |
| All Expectations Met    |       |

**Rubric Scores:**

| Rubric | Score (0-1) | Explanation |
|--------|-------------|-------------|
|        |             |             |

**Tool Expectations:**

| Expected Tool | Expected Args | Observed Tool | Observed Args | Match |
|---------------|---------------|---------------|---------------|-------|
|               |               |               |               |       |

**Hallucination Check:**

| Turn | Score (0-1) | Details |
|------|-------------|---------|
|      |             |         |

#### Custom LLM Judge Results (Evaluation Expectations)

| Judge Name | Prompt | Outcome | Score | Explanation |
|------------|--------|---------|-------|-------------|
|            |        |         |       |             |

---

## Latency Report

### Turn Latency

| Metric     | Value |
|------------|-------|
| Sessions   |       |
| P50        |       |
| P90        |       |
| P99        |       |

### Tool Latency

| Tool | P50 | P90 | P99 | Calls |
|------|-----|-----|-----|-------|
|      |     |     |     |       |

### LLM Call Latency

| Model | P50 | P90 | P99 | Calls |
|-------|-----|-----|-----|-------|
|       |     |     |     |       |

### Callback Latency

| Callback | P50 | P90 | P99 |
|----------|-----|-----|-----|
|          |     |     |     |

### Guardrail Latency

| Guardrail | P50 | P90 | P99 |
|-----------|-----|-----|-----|
|           |     |     |     |

---

## Trend (Last 10 Results)

For evaluations with `lastTenResults`:

| Run Date | Status | Tool Score | Semantic Sim | Hallucination | Latency |
|----------|--------|------------|--------------|---------------|---------|
|          |        |            |              |               |         |

---

## Failures & Root Causes

For each failed evaluation:

| Eval | Turn/Rubric | Failure Type | Expected | Actual | Root Cause |
|------|-------------|--------------|----------|--------|------------|
|      |             |              |          |        |            |

**Failure Categories:**
- **Tool Mismatch**: Wrong tool called or wrong parameters
- **Response Mismatch**: Agent response doesn't match expected (low semantic similarity)
- **Hallucination**: Agent fabricated information (hallucination score > 0.3)
- **Transfer Error**: Agent routed to wrong sub-agent
- **Rubric Failure**: Scenario rubric scored below threshold
- **Task Incomplete**: Scenario task was not completed
- **Latency**: Response time exceeded acceptable threshold
- **Error**: Execution error during evaluation

## Recommendations

Based on failures, provide actionable recommendations:
1. **Instruction changes** needed
2. **Tool description** improvements
3. **New examples** to add
4. **New evaluations** to create for uncovered failures
5. **Model/temperature** adjustments
```

---

## Execution Workflow

1. Ask user for project, location, app ID, and report type
2. **For coverage**: Fetch all agent config + all evaluations, cross-reference to build coverage matrix
3. **For run results**: Fetch latest run (or ask user which run), get all results, build structured report
4. Present report in markdown format
5. Highlight critical gaps and failures
6. Provide specific, actionable recommendations

## Tips

- Use `jq` extensively to extract and cross-reference data
- **Instruction analysis is the most important part of coverage** — read every agent's full instruction text, not just summaries
- When decomposing instructions, look for these textual patterns:
  - Numbered lists / bullet points → individual directives
  - `<persona>`, `<guidelines>`, `<constraints>`, `<instructions>` XML-like tags → section boundaries
  - "always", "never", "must", "should", "do not" → hard constraints/guardrails
  - "if...then", "when...do", conditional keywords → conditional behaviors
  - "transfer to", "escalate", "hand off" → transfer/escalation rules
  - "call", "use", "invoke" + tool name → tool usage rules
  - "set", "update", "store" + variable name → state management rules
  - Indented sub-bullets under a step → sub-directives (each testable independently)
- Include the **exact quote** from the instruction for each directive so the user can trace it back
- For golden evals: map each expectation's tool reference back to the tool's displayName for readability
- For scenario evals: pay attention to rubric scores — anything below 0.7 is a concern
- Hallucination scores above 0.3 warrant investigation
- Semantic similarity below 3.0 (on 0-4 scale) indicates response quality issues
- Tool invocation correctness below 1.0 means missed or wrong tool calls
- Compare trends across the last 10 results to spot regressions
- When a golden eval is marked `invalid: true`, it references a deleted/changed tool — flag this prominently
