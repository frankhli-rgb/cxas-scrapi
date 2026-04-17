---
name: improve-agent
description: Automatically improve GECX agents — analyze eval failures, optimize instructions, and iterate
user_invocable: true
---

# Improve GECX Agent

You are an expert at improving agents on the Google Customer Engagement Suite (GECX/CES) platform. Analyze evaluation results, identify failures, generate improved instructions/tools/examples, and iterate until quality improves.

## Contents
- [Authentication](#authentication)
- [Base URL](#base-url)
- [Required Information](#required-information)
- [Improvement Workflow](#improvement-workflow)
  - [Phase 1: Assessment -- Understand Current State](#phase-1-assessment--understand-current-state)
  - [Phase 2: Diagnosis -- Separate Agent Issues from Eval Issues](#phase-2-diagnosis--separate-agent-issues-from-eval-issues)
  - [Phase 3: Fix -- Apply Improvements](#phase-3-fix--apply-improvements)
  - [Phase 4: Validate -- Re-evaluate](#phase-4-validate--re-evaluate)
- [Improvement Strategies by Issue Type](#improvement-strategies-by-issue-type)
- [Common Pitfalls](#common-pitfalls)
- [Execution](#execution)

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
2. **App ID** — which app to improve
3. **Goal** — what should improve? (accuracy, tool usage, response quality, latency, etc.)

---

## Improvement Workflow

### Phase 1: Assessment — Understand Current State

#### 1a. Get App & Agent Configuration
```bash
# Get app
curl -s "https://ces.googleapis.com/v1beta/projects/${PROJECT}/locations/${LOCATION}/apps/${APP_ID}" \
  -H "Authorization: Bearer ${TOKEN}" | jq '{displayName, rootAgent, globalInstruction, modelSettings}'

# Get all agents
curl -s "https://ces.googleapis.com/v1beta/projects/${PROJECT}/locations/${LOCATION}/apps/${APP_ID}/agents" \
  -H "Authorization: Bearer ${TOKEN}" | jq '.agents[] | {name, displayName, instruction, tools, childAgents}'

# Get all tools
curl -s "https://ces.googleapis.com/v1beta/projects/${PROJECT}/locations/${LOCATION}/apps/${APP_ID}/tools" \
  -H "Authorization: Bearer ${TOKEN}" | jq '.tools[] | {name, displayName}'

# Get examples
curl -s "https://ces.googleapis.com/v1beta/projects/${PROJECT}/locations/${LOCATION}/apps/${APP_ID}/examples" \
  -H "Authorization: Bearer ${TOKEN}" | jq '.examples[] | {name, displayName, invalid}'
```

#### 1b. Get Latest Evaluation Results
```bash
# List evaluation runs
curl -s "https://ces.googleapis.com/v1beta/projects/${PROJECT}/locations/${LOCATION}/apps/${APP_ID}/evaluationRuns" \
  -H "Authorization: Bearer ${TOKEN}"
```

#### 1c. Review Recent Conversations for Failure Patterns
```bash
curl -s "https://ces.googleapis.com/v1beta/projects/${PROJECT}/locations/${LOCATION}/apps/${APP_ID}/conversations?sources=LIVE&pageSize=20" \
  -H "Authorization: Bearer ${TOKEN}"
```

---

### Phase 2: Diagnosis — Separate Agent Issues from Eval Issues

**CRITICAL**: Before fixing the agent, check if the failures are actually eval config problems. In practice, **most eval failures are caused by bad eval configs, not bad agent behavior.** Check these first:

#### Eval Config Issues (fix the eval, not the agent):
1. **Missing `taskCompletionBehavior: "TASK_SATISFIED"`** — Default requires task completion, which fails for behavioral tests
2. **Tool arg matching** — Any `args` in `scenarioExpectations` with `$matchValue: ""`, `rewrittenQueries: []`, or exact values
3. **Vague sim user task** — Sim user doesn't follow instructions, refuses steps, or goes off-script
4. **Wrong tool expectations** — Expecting a tool that isn't called in the actual flow
5. **Task doesn't define success** — Missing "X counts as a successful outcome" ending

#### Actual Agent Issues (fix the agent):
1. **Hallucination** — Agent suggests steps not in tool output
2. **Instruction contradictions** — Sub-agent instructions conflict with root agent
3. **Missing handling** — Agent doesn't know what to do for certain inputs
4. **Wrong routing** — Agent transfers to wrong sub-agent
5. **Tone/format** — Too verbose, too many emojis, repeated empathy

---

### Phase 3: Fix — Apply Improvements

#### 3a. Fix Eval Configs First
See the `eval-agent` skill for detailed guidance. Key fixes:
- Add `taskCompletionBehavior: "TASK_SATISFIED"` with proper task wording
- Remove all tool arg matching from `scenarioExpectations`
- Rewrite sim user tasks to be extremely directive
- Delete and recreate evals (PATCH doesn't work for scenario structure)

#### 3b. Fix Agent Instructions

```bash
curl -s -X PATCH \
  "https://ces.googleapis.com/v1beta/projects/${PROJECT}/locations/${LOCATION}/apps/${APP_ID}/agents/${AGENT_ID}?updateMask=instruction" \
  -H "Authorization: Bearer ${TOKEN}" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "projects/${PROJECT}/locations/${LOCATION}/apps/${APP_ID}/agents/${AGENT_ID}",
    "instruction": "<IMPROVED_INSTRUCTION>"
  }'
```

**Instruction Best Practices:**
- Be specific about when to use each tool
- Use structured format (numbered steps, bullet points)
- Specify tone, format, and length expectations
- Include edge case handling
- Add guardrails in instructions ("never reveal X", "always verify Y")
- **NEVER put example phrases for the agent to say** — the agent will use them verbatim even when inappropriate, and the hallucination grader will flag them if they're not in tool output

#### 3c. Fix Hallucination Issues

Hallucination is when the agent says things not grounded in tool output. Common causes and fixes:

| Cause | Fix |
|-------|-----|
| Example phrases in instructions ("try turning off Wi-Fi") | Remove all example troubleshooting steps from instructions |
| Agent paraphrases/embellishes tool output | Add: "CRITICAL: Only suggest steps that appear in the tool response. Do NOT invent, paraphrase, or add steps not explicitly in the tool output." |
| Agent adds context from training data | Add: "Only use information from tool responses to guide the customer" |

#### 3d. Fix Instruction Contradictions Between Agents

Root agent and sub-agents MUST be consistent. Common contradiction:
- Root agent: "Express empathy ONLY ONCE"
- Sub-agent: "Show Empathy Throughout"

Fix: Align all agents to the same guidelines. Search for contradictions in tone, empathy, verbosity, and escalation rules.

#### 3e. Improve Global Instruction (App-level)

```bash
curl -s -X PATCH \
  "https://ces.googleapis.com/v1beta/projects/${PROJECT}/locations/${LOCATION}/apps/${APP_ID}?updateMask=globalInstruction" \
  -H "Authorization: Bearer ${TOKEN}" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "projects/${PROJECT}/locations/${LOCATION}/apps/${APP_ID}",
    "globalInstruction": "<IMPROVED_GLOBAL_INSTRUCTION>"
  }'
```

#### 3f. Add/Improve Examples

```bash
curl -s -X POST \
  "https://ces.googleapis.com/v1beta/projects/${PROJECT}/locations/${LOCATION}/apps/${APP_ID}/examples" \
  -H "Authorization: Bearer ${TOKEN}" \
  -H "Content-Type: application/json" \
  -d '{
    "displayName": "<EXAMPLE_NAME>",
    "messages": [
      {"role": "user", "chunks": [{"text": "<user message>"}]},
      {"role": "agent", "chunks": [
        {"toolCall": {"tool": "projects/${PROJECT}/locations/${LOCATION}/apps/${APP_ID}/tools/${TOOL_ID}", "arguments": {"key": "value"}}},
        {"text": "<agent response after tool call>"}
      ]}
    ]
  }'
```

#### 3g. Adjust Guardrails

If guardrails are blocking legitimate agent behavior (e.g., blocking profanity before the agent can escalate):
```bash
# Get current guardrails
curl -s "${BASE}/guardrails" -H "Authorization: Bearer ${TOKEN}"

# Lower safety threshold to allow agent to handle hostile input
curl -s -X PATCH "${BASE}/guardrails/${GUARDRAIL_ID}?updateMask=modelSafety" \
  -H "Authorization: Bearer ${TOKEN}" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "...",
    "modelSafety": {
      "safetySettings": [
        {"category": "HARM_CATEGORY_HARASSMENT", "threshold": "BLOCK_ONLY_HIGH"}
      ]
    }
  }'
```

#### 3h. Change Model

```bash
curl -s -X PATCH \
  "https://ces.googleapis.com/v1beta/projects/${PROJECT}/locations/${LOCATION}/apps/${APP_ID}/agents/${AGENT_ID}?updateMask=modelSettings" \
  -H "Authorization: Bearer ${TOKEN}" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "projects/${PROJECT}/locations/${LOCATION}/apps/${APP_ID}/agents/${AGENT_ID}",
    "modelSettings": {
      "model": "gemini-2.5-pro",
      "temperature": 0.2
    }
  }'
```

---

### Phase 4: Validate — Re-evaluate

#### 4a. Create a Version Snapshot (for rollback)
```bash
curl -s -X POST \
  "https://ces.googleapis.com/v1beta/projects/${PROJECT}/locations/${LOCATION}/apps/${APP_ID}/versions" \
  -H "Authorization: Bearer ${TOKEN}" \
  -H "Content-Type: application/json" \
  -d '{
    "displayName": "Pre-improvement snapshot - '$(date +%Y%m%d_%H%M%S)'"
  }'
```

#### 4b. Run All Evaluations
```bash
EVAL_IDS=$(curl -s "${BASE}/evaluations" -H "Authorization: Bearer ${TOKEN}" | \
  jq -r '.evaluations[].name' | while read name; do echo "\"${name}\""; done | paste -sd, -)

curl -s -X POST "${BASE}:runEvaluation" \
  -H "Authorization: Bearer ${TOKEN}" \
  -H "Content-Type: application/json" \
  -d "{
    \"evaluations\": [${EVAL_IDS}],
    \"displayName\": \"Post-improvement run - $(date +%Y-%m-%d_%H:%M)\",
    \"runsPerEvaluation\": 5,
    \"optimizationConfig\": {\"generateLossReport\": true}
  }"
```

#### 4c. Compare Before/After
After the run completes, get per-eval pass rates and compare with previous run.

#### 4d. Rollback if Needed
```bash
curl -s -X POST \
  "https://ces.googleapis.com/v1beta/projects/${PROJECT}/locations/${LOCATION}/apps/${APP_ID}/versions/${VERSION_ID}:restore" \
  -H "Authorization: Bearer ${TOKEN}" \
  -H "Content-Type: application/json" \
  -d '{}'
```

---

## Improvement Strategies by Issue Type

| Issue | Strategy |
|-------|----------|
| Wrong tool called | Improve tool descriptions, add examples showing correct tool choice |
| Missing tool call | Add explicit instruction: "When user asks X, always use tool Y" |
| Wrong parameters | Add parameter guidance in instructions |
| Bad response tone | Update globalInstruction with persona/tone guidance |
| Hallucination | Add grounding constraint: "Only use information from tool responses" + remove example phrases from instructions |
| Repeated empathy | Add: "Express empathy ONLY ONCE" with explicit prohibition |
| Too verbose | Add: "Keep responses to 2-3 short sentences maximum" |
| Wrong agent routing | Add deterministic transfer rules, improve child agent descriptions |
| Inconsistent behavior | Align sub-agent instructions with root agent, lower temperature |
| Guardrail blocking valid input | Lower safety threshold or add safe categories to prompt guardrail |

---

## Common Pitfalls

### 1. Most Eval Failures Are Eval Config Issues, Not Agent Issues (~70%)
Before modifying agent instructions, check if the eval config is causing false failures. In practice, approximately **70% of pass rate improvements come from fixing eval configs**, not agent behavior. The most common patterns:
- Missing `taskCompletionBehavior: "TASK_SATISFIED"` — the #1 cause of false failures
- Tool arg matching with `$matchValue: ""` or `rewrittenQueries: []`
- Vague sim user task descriptions causing the sim user to go off-script
- Task descriptions that require "resolution" when escalation is the correct outcome

Fix the eval configs first, then re-run. You may find the agent is already behaving correctly. Use the `iterate-evals` skill for the full iteration loop.

### 1b. Don't Over-Fix 4/5 Evals
If an eval scores 4/5, the one failure is likely sim user randomness, not a real issue. Focus effort on evals at 3/5 or below. A 4/5 eval that drops to 3/5 after a "fix" is a regression — investigate immediately.

### 2. Guardrails vs Instructions Conflict
Guardrails run **before** agent instructions. If a guardrail blocks profanity/adversarial input, the agent's instruction to "escalate on profanity" never executes. Check guardrail configuration first when escalation behaviors don't work.

### 3. Instruction Examples Cause Hallucination
If you put example phrases in agent instructions like "Please try turning off your Wi-Fi", the agent will suggest these steps even when they're not in the tool output. The hallucination grader only checks against tool output, not instruction text. **Never put specific troubleshooting steps as examples in instructions.**

### 4. Sub-Agent Instruction Contradictions
Sub-agents may have instructions that contradict the root agent. Common examples:
- Root says "empathy once" but sub-agent says "show empathy throughout"
- Root says "brief responses" but sub-agent has long templates
- Root says "escalate billing" but sub-agent says "decline billing"

Always audit all agent instructions together when making changes.

### 5. Fixing Invalid Evaluations
If evals become `invalid: true` after deleting agents/tools, the `invalid` flag is read-only. **Delete and recreate** each invalid eval.

---

## Execution

1. Run Phase 1 to understand current state
2. **Run Phase 2 to separate eval issues from agent issues** (most important step!)
3. Fix eval configs first, re-run to establish true baseline
4. Then fix actual agent issues
5. Re-evaluate and report improvement metrics
6. Iterate if needed
