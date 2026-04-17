---
name: eval-agent
description: Evaluate GECX agents — create evaluations (golden/scenario), run them, and analyze results
user_invocable: true
---

# Evaluate GECX Agent

You are an expert at evaluating agents using the Google Customer Engagement Suite (GECX/CES) API. Help the user create evaluations, run them, and analyze the results.

## Contents
- [Authentication](#authentication)
- [Base URL](#base-url)
- [Required Information](#required-information)
- [Evaluation Types](#evaluation-types)
  - [Golden Evaluation](#golden-evaluation)
  - [Local Simulations](#local-simulations)
- [Creating Evaluations](#creating-evaluations)
  - [List Existing Evaluations](#list-existing-evaluations)
  - [Create a Golden Evaluation](#create-a-golden-evaluation)
  - [Create a Scenario Evaluation](#create-a-scenario-evaluation)
- [Running Evaluations](#running-evaluations)
  - [Run All Evaluations](#run-all-evaluations)
  - [Run Specific Evaluations](#run-specific-evaluations)
- [Checking Results](#checking-results)
  - [Poll Run Status](#poll-run-status)
  - [Get Per-Result Pass/Fail](#get-per-result-passfail)
  - [List Evaluation Runs](#list-evaluation-runs)
  - [Evaluation Datasets](#evaluation-datasets)
  - [Evaluation Expectations (Custom LLM Judges)](#evaluation-expectations-custom-llm-judges)
  - [Scheduled Evaluation Runs](#scheduled-evaluation-runs)
  - [Managing Evaluations](#managing-evaluations)
- [Generate Evaluation from Conversation](#generate-evaluation-from-conversation)
- [Workflow](#workflow)
- [Critical Gotchas & Lessons Learned](#critical-gotchas--lessons-learned)
  - [1. invalid Flag is Read-Only](#1-invalid-flag-is-read-only)
  - [2. taskCompletionBehavior -- ALWAYS Use TASK_SATISFIED](#2-taskcompletionbehavior--always-use-task_satisfied)
  - [3. Tool Expectation Arg Matching -- NEVER Use It](#3-tool-expectation-arg-matching--never-use-it)
  - [4. Tool Resource Paths -- No Base URL](#4-tool-resource-paths--no-base-url)
  - [5. Simulated User -- Be EXTREMELY Directive](#5-simulated-user--be-extremely-directive)
  - [6. Task Description Formula](#6-task-description-formula)
  - [7. Session Variables via variableOverrides](#7-session-variables-via-variableoverrides)
  - [8. Prompt Guardrails Run Before Agent Instructions](#8-prompt-guardrails-run-before-agent-instructions)
  - [9. Golden Evals -- Expect 0% Pass Rate](#9-golden-evals--expect-0-pass-rate)
  - [10. Hallucination Grading](#10-hallucination-grading)
  - [11. Fixing Evals -- Delete and Recreate](#11-fixing-evals--delete-and-recreate)
  - [12. maxTurns Sizing](#12-maxturns-sizing)
- [Audio Evaluations](#audio-evaluations)
  - [Running Evals with Audio Channel](#running-evals-with-audio-channel)
  - [Running Audio Evals with Personas](#running-audio-evals-with-personas)
  - [Persona Speech Configuration](#persona-speech-configuration)
  - [Test Persona Voice](#test-persona-voice)
  - [Upload Audio for Golden Evals](#upload-audio-for-golden-evals)
  - [Latency Reports](#latency-reports)
  - [Audio Eval Results](#audio-eval-results)
  - [Key Differences from Text Evals](#key-differences-from-text-evals)
  - [Important Notes](#important-notes)
- [YAML Formats for Bundled Scripts](#yaml-formats-for-bundled-scripts)
  - [Scenarios (evals/scenarios/scenarios.yaml)](#scenarios-evalsscenariosscenariosyaml)
  - [Goldens (evals/goldens/*.yaml)](#goldens-evalsgoldensyaml)
  - [Simulations (evals/simulations/simulations.yaml)](#simulations-evalssimulationssimulationsyaml)
  - [Tool Tests (evals/tool_tests/*.yaml)](#tool-tests-evalstool_testsyaml)
  - [Creating Evaluation Expectations](#creating-evaluation-expectations)
- [Conversational Design Principles for Evals](#conversational-design-principles-for-evals)
- [Eval API Gotchas](#eval-api-gotchas)

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
2. **App ID** — which app to evaluate
3. **Evaluation type** — Golden (replay expected conversation) or Simulation (local sim-user-driven)

## Evaluation Types

### Golden Evaluation
Replays a scripted conversation and checks that the agent's responses match expectations (tool calls, agent responses, transfers). Use for deterministic flows enforced by callbacks.

### Local Simulations
Uses SCRAPI's Sessions API with Gemini as a sim user to test open-ended flows. Runs locally in parallel (~1 min). **Preferred for behavioral testing** — faster iteration than platform scenarios.

> **Note:** This reference also documents platform scenario evals (API-based) for completeness, but the primary sim pipeline uses `scrapi-sim-runner.py` with local simulations.

---

## Creating Evaluations

### List Existing Evaluations
```bash
curl -s "https://ces.googleapis.com/v1beta/projects/${PROJECT}/locations/${LOCATION}/apps/${APP_ID}/evaluations" \
  -H "Authorization: Bearer ${TOKEN}"
```

### Create a Golden Evaluation
```bash
curl -s -X POST \
  "https://ces.googleapis.com/v1beta/projects/${PROJECT}/locations/${LOCATION}/apps/${APP_ID}/evaluations" \
  -H "Authorization: Bearer ${TOKEN}" \
  -H "Content-Type: application/json" \
  -d '{
    "displayName": "<EVAL_NAME>",
    "description": "<EVAL_DESCRIPTION>",
    "tags": ["<tag1>", "<tag2>"],
    "golden": {
      "turns": [
        {
          "steps": [
            {
              "userInput": {"text": "<user message>"}
            },
            {
              "expectation": {
                "toolCall": {
                  "tool": "projects/${PROJECT}/locations/${LOCATION}/apps/${APP_ID}/tools/${TOOL_ID}",
                  "arguments": {"key": "value"}
                },
                "note": "Check that the correct tool was called"
              }
            },
            {
              "expectation": {
                "agentResponse": {
                  "chunks": [{"text": "<expected response content>"}]
                },
                "note": "Check agent response quality"
              }
            }
          ]
        }
      ]
    }
  }'
```

#### Golden Expectation Types
- **toolCall** — Check a specific tool was called with specific parameters
- **toolResponse** — Check the tool returned expected response
- **agentResponse** — Check agent's text response (uses semantic similarity)
- **agentTransfer** — Check agent transferred to correct sub-agent
- **updatedVariables** — Check session variables were updated correctly
- **mockToolResponse** — Inject a mock tool response for testing

#### Tool Call Parameter Matching

By default, tool call arguments are matched exactly. For flexible matching, use `$matchType` directives on individual parameters:

| Match Type | Description | Use When |
|------------|-------------|----------|
| `semantic` | Fuzzy semantic similarity matching | Summary fields, free-text descriptions |
| `ignore` | Skip this parameter entirely | Parameters that vary unpredictably |
| `contains` | Check if actual value contains the match value | Keywords that must appear |
| `regexp` | Match against a regular expression | Pattern-based validation |

**Format:** Each parameter value becomes a JSON object with `$matchType`, `$matchValue`, and `$originalValue`. The expected value goes in `$originalValue`:

```json
{
  "toolCall": {
    "tool": "projects/.../tools/payload_update_tool",
    "args": {
      "summary": {
        "$matchType": "ignore",
        "$matchValue": "",
        "$originalValue": ""
      },
      "escalation_reason": {
        "$matchType": "semantic",
        "$matchValue": "",
        "$originalValue": "Customer requested live agent"
      },
      "main_topic": {
        "$matchType": "contains",
        "$matchValue": "",
        "$originalValue": "Customer Issue"
      }
    }
  }
}
```

**In YAML golden format:**
```yaml
tool_calls:
  - action: payload_update_tool
    args:
      summary:
        $matchType: "ignore"
        $matchValue: ""
        $originalValue: ""
      escalation_reason:
        $matchType: "semantic"
        $matchValue: ""
        $originalValue: "Customer requested live agent"
      session_escalated: true  # exact match (no $matchType = exact)
```

**Guidelines:**
- Use `ignore` for `summary`, `escalation_reason`, and `main_topic` — these are LLM-generated free-text fields that vary each run. The platform's semantic matcher is flaky on these (rejects valid semantics like "customer_is_unhappy" vs "Customer unhappy with service issue"). The core test is that the tool WAS called with escalation=true, not what the reason text says.
- Only use `semantic` matching when the field value is critical to verify AND the expected value is short and unambiguous
- Keep exact matching for boolean/enum fields like `session_escalated`, `issue_type`
- Don't include auxiliary/classification tool calls in golden expectations — the LLM reorders them relative to routing calls like `transfer_to_agent`, causing flaky failures. Only test core behavior tools (routing, escalation, diagnostic checks).

### Create a Scenario Evaluation
```bash
curl -s -X POST \
  "https://ces.googleapis.com/v1beta/projects/${PROJECT}/locations/${LOCATION}/apps/${APP_ID}/evaluations" \
  -H "Authorization: Bearer ${TOKEN}" \
  -H "Content-Type: application/json" \
  -d '{
    "displayName": "<EVAL_NAME>",
    "scenario": {
      "task": "<What the simulated user should do — be EXTREMELY specific and directive>",
      "maxTurns": 12,
      "variableOverrides": {
        "auth_status": "unauthenticated"
      },
      "taskCompletionBehavior": "TASK_SATISFIED",
      "scenarioExpectations": [
        {
          "toolExpectation": {
            "expectedToolCall": {
              "tool": "projects/${PROJECT}/locations/${LOCATION}/apps/${APP_ID}/tools/${TOOL_ID}"
            }
          }
        }
      ]
    }
  }'
```

---

## Running Evaluations

### Run All Evaluations
```bash
EVAL_IDS=$(curl -s "${BASE}/evaluations" -H "Authorization: Bearer ${TOKEN}" | \
  jq -r '.evaluations[].name' | while read name; do echo "\"${name}\""; done | paste -sd, -)

curl -s -X POST "${BASE}:runEvaluation" \
  -H "Authorization: Bearer ${TOKEN}" \
  -H "Content-Type: application/json" \
  -d "{
    \"evaluations\": [${EVAL_IDS}],
    \"displayName\": \"Run - $(date +%Y-%m-%d_%H:%M)\",
    \"runsPerEvaluation\": 5,
    \"optimizationConfig\": {\"generateLossReport\": true}
  }"
```

### Run Specific Evaluations
```bash
curl -s -X POST \
  "https://ces.googleapis.com/v1beta/projects/${PROJECT}/locations/${LOCATION}/apps/${APP_ID}:runEvaluation" \
  -H "Authorization: Bearer ${TOKEN}" \
  -H "Content-Type: application/json" \
  -d '{
    "evaluations": [
      "projects/${PROJECT}/locations/${LOCATION}/apps/${APP_ID}/evaluations/${EVAL_ID}"
    ],
    "displayName": "Eval Run - $(date)",
    "runsPerEvaluation": 5
  }'
```

---

## Checking Results

### Poll Run Status
```bash
curl -s "${BASE}/evaluationRuns/${RUN_ID}" \
  -H "Authorization: Bearer ${TOKEN}" | jq '{state, resultCount: (.evaluationResults | length)}'
```
Runs take 20-45 minutes for 50+ evals. State: `RUNNING` → `COMPLETED`. **Note:** Platform can be significantly slower during high load (hours to days). Set up background polling rather than waiting synchronously.

### Get Per-Result Pass/Fail

**IMPORTANT:** Pass/fail is determined by `scenarioResult.userGoalSatisfactionResult.score` (0 = fail, 1 = pass). Do NOT use `.satisfied` (boolean) — it may not exist. Check `.executionState` for completion status (not `.evaluationStatus`).

```bash
# Fetch all result resource names
RESULTS=$(curl -s "${BASE}/evaluationRuns/${RUN_ID}" -H "Authorization: Bearer ${TOKEN}" | jq -r '.evaluationResults[]')

# Fetch each result in parallel
mkdir -p /tmp/eval_results
echo "$RESULTS" | while read name; do
  id=$(echo "$name" | sed 's|.*/results/||')
  curl -s -H "Authorization: Bearer ${TOKEN}" "https://ces.googleapis.com/v1beta/${name}" > "/tmp/eval_results/${id}.json" &
  if (( $(jobs -r | wc -l) >= 20 )); then
    wait -n 2>/dev/null || wait
  fi
done
wait

# Tally pass/fail
for f in /tmp/eval_results/*.json; do
  state=$(jq -r '.executionState' "$f" 2>/dev/null)
  if [ "$state" = "COMPLETED" ]; then
    score=$(jq -r '.scenarioResult.userGoalSatisfactionResult.score // 0' "$f")
    eval_id=$(jq -r '.name' "$f" | sed 's|.*/evaluations/\([^/]*\)/results/.*|\1|')
    echo "${eval_id},${score}"
  fi
done > /tmp/scored.csv

total=$(wc -l < /tmp/scored.csv | tr -d ' ')
passed=$(grep ',1$' /tmp/scored.csv | wc -l | tr -d ' ')
echo "Pass rate: $(echo "scale=1; $passed * 100 / $total" | bc)% ($passed/$total)"
```

### List Evaluation Runs
```bash
curl -s "https://ces.googleapis.com/v1beta/projects/${PROJECT}/locations/${LOCATION}/apps/${APP_ID}/evaluationRuns" \
  -H "Authorization: Bearer ${TOKEN}"
```

---

### Evaluation Datasets

```bash
curl -s -X POST \
  "https://ces.googleapis.com/v1beta/projects/${PROJECT}/locations/${LOCATION}/apps/${APP_ID}/evaluationDatasets" \
  -H "Authorization: Bearer ${TOKEN}" \
  -H "Content-Type: application/json" \
  -d '{
    "displayName": "<DATASET_NAME>",
    "evaluations": [
      "projects/${PROJECT}/locations/${LOCATION}/apps/${APP_ID}/evaluations/${EVAL_ID_1}",
      "projects/${PROJECT}/locations/${LOCATION}/apps/${APP_ID}/evaluations/${EVAL_ID_2}"
    ]
  }'
```

---

### Evaluation Expectations (Custom LLM Judges)

```bash
curl -s -X POST \
  "https://ces.googleapis.com/v1beta/projects/${PROJECT}/locations/${LOCATION}/apps/${APP_ID}/evaluationExpectations" \
  -H "Authorization: Bearer ${TOKEN}" \
  -H "Content-Type: application/json" \
  -d '{
    "displayName": "<EXPECTATION_NAME>",
    "llmCriteria": {
      "prompt": "<JUDGE_PROMPT_DESCRIBING_WHAT_TO_EVALUATE>"
    },
    "tags": ["quality", "safety"]
  }'
```

---

### Scheduled Evaluation Runs

```bash
curl -s -X POST \
  "https://ces.googleapis.com/v1beta/projects/${PROJECT}/locations/${LOCATION}/apps/${APP_ID}/scheduledEvaluationRuns" \
  -H "Authorization: Bearer ${TOKEN}" \
  -H "Content-Type: application/json" \
  -d '{
    "displayName": "<SCHEDULE_NAME>",
    "active": true,
    "request": {
      "evaluations": ["projects/${PROJECT}/locations/${LOCATION}/apps/${APP_ID}/evaluations/${EVAL_ID}"]
    },
    "schedulingConfig": {
      "frequency": "DAILY",
      "startTime": "2025-01-01T08:00:00Z"
    }
  }'
```

---

### Managing Evaluations

**Delete:** `curl -s -X DELETE "${BASE}/evaluations/${EVAL_ID}" -H "Authorization: Bearer ${TOKEN}"`

**Note:** To fix eval configs, DELETE and recreate — PATCH cannot update scenario structure reliably.

---

## Generate Evaluation from Conversation

```bash
curl -s -X POST \
  "https://ces.googleapis.com/v1beta/projects/${PROJECT}/locations/${LOCATION}/apps/${APP_ID}/conversations/${CONVERSATION_ID}:generateEvaluation" \
  -H "Authorization: Bearer ${TOKEN}" \
  -H "Content-Type: application/json" \
  -d '{}'
```

---

## Workflow

1. Ask what the user wants to evaluate and how
2. Check existing evaluations or create new ones
3. Run the evaluation
4. Poll for completion (expect 20-45 min for large suites)
5. Fetch and analyze results
6. Present a clear summary with actionable recommendations
7. If results are poor, **diagnose using the gotchas below first** — most failures are eval config issues, not agent issues

---

## Critical Gotchas & Lessons Learned

### 1. `invalid` Flag is Read-Only
The `invalid` field on evaluations is `readOnly: true`. Auto-set when an eval references a deleted tool/agent. **Delete and recreate** to fix.

### 2. `taskCompletionBehavior` — ALWAYS Use `TASK_SATISFIED`
Use `taskCompletionBehavior: "TASK_SATISFIED"` on virtually ALL scenario evals. The default (omitted) requires `taskCompleted=true`, which fails for any test where the underlying user issue isn't fully resolved.

**The key trick**: Write the task description so the desired agent behavior IS what "satisfies" the task. End every task with: "X counts as a successful outcome."

Examples:
- Escalation: "Being transferred to a specialist counts as a successful outcome."
- Redirect: "Being redirected to the appropriate topic counts as a successful outcome."
- Troubleshooting: "Receiving troubleshooting guidance counts as a successful outcome."
- Decline: "The agent declining and offering alternatives counts as a successful outcome."

### 3. Tool Expectation Arg Matching — NEVER Use It
Tool argument matching in `scenarioExpectations` is the **#1 source of false failures**:

| Pattern | Why It Fails |
|---------|-------------|
| `"$matchType": "semantic", "$matchValue": ""` | Empty string prevents semantic matcher from matching |
| `"rewrittenQueries": []` | Agent always populates this; empty array fails exact match |
| `"connection_type": "5G"` | Agent may format values differently |
| Any exact arg matching | LLM doesn't produce deterministic arg values |

**Best practice**: Only verify the tool was called. Remove ALL `args`/`arguments`:
```json
{
  "toolExpectation": {
    "expectedToolCall": {
      "tool": "projects/.../tools/TOOL_ID"
    }
  }
}
```

### 4. Tool Resource Paths — No Base URL
Use resource paths: `projects/.../tools/...`
NOT full URLs: `https://ces.googleapis.com/v1beta/projects/.../tools/...`
Full URLs cause 400 errors.

### 5. Simulated User — Be EXTREMELY Directive
The AI sim user often ignores vague instructions:

| Problem | Fix |
|---------|-----|
| Won't use profanity | "Say 'This is complete bull****, fix my damn phone'" |
| Won't give nonsensical answers | "You MUST say 'purple elephants dancing' to EVERY question" |
| Refuses troubleshooting steps | "Follow ALL steps without objection or hesitation" |
| Doesn't confirm resolution | "On the third step, say 'yes the issue is now resolved'" |
| Goes off-script | "You MUST cooperate fully. Do NOT bring up other issues" |

### 6. Task Description Formula
```
You are [role]. You [situation]. [Specific behavior instructions].
[What agent should do]. [What counts as success].
```

Example:
```
You are a customer with a device having service issues. You are NOT calling
from the affected device. Follow ALL troubleshooting steps without objection. After each
step, say you completed it. On the third step, confirm the issue is resolved. Receiving
troubleshooting guidance and resolving the issue counts as a successful outcome.
```

### 7. Session Variables via `variableOverrides`
Set session variables inside the `scenario` object:
```json
{
  "scenario": {
    "task": "...",
    "variableOverrides": {
      "auth_status": "authenticated",
      "user_role": "primary_account_holder"
    }
  }
}
```

### 8. Prompt Guardrails Run Before Agent Instructions
Guardrails intercept BEFORE agent logic. If a guardrail blocks profanity, the agent's escalation instruction never executes. You may need to lower guardrail thresholds (e.g., `BLOCK_ONLY_HIGH` for harassment).

### 9. Golden Evals — Expect 0% Pass Rate
Golden evals check exact text/sequences. They fail frequently due to LLM variation. This is normal. **Prefer scenario evals.** Only use goldens for critical exact-match flows where flakiness is acceptable.

### 10. Hallucination Grading
The evaluator checks if agent responses are grounded in tool output. Agent suggesting steps NOT in tool output causes hallucination failures even when goals are met. Fix in agent instruction: "CRITICAL: Only suggest steps that appear in the tool response."

### 11. Fixing Evals — Delete and Recreate
PATCH cannot reliably update scenario structure. Safe workflow:
1. GET the eval config
2. DELETE the eval
3. POST new eval with fixes

### 12. `maxTurns` Sizing
- Quick tests (redirect, decline): 6 turns
- Standard troubleshooting: 12 turns
- Multi-step troubleshooting with resolution: 16-20 turns
- Set higher than needed — eval ends when sim user's task is satisfied

---

## Audio Evaluations

Audio evals run scenario evaluations through the full voice pipeline (TTS → agent → STT), testing how the agent performs with spoken input rather than text. Audio is configured at **run time**, not at eval creation time.

### Running Evals with Audio Channel
```bash
curl -s -X POST "${BASE}:runEvaluation" \
  -H "Authorization: Bearer ${TOKEN}" \
  -H "Content-Type: application/json" \
  -d '{
    "evaluations": ["projects/${PROJECT}/locations/${LOCATION}/apps/${APP_ID}/evaluations/${EVAL_ID}"],
    "displayName": "Audio eval run",
    "runsPerEvaluation": 5,
    "config": {
      "evaluationChannel": "AUDIO"
    }
  }'
```

The platform automatically sets `inputAudioConfig` (LINEAR16, 16kHz) and `outputAudioConfig` (LINEAR16, 24kHz).

### Running Audio Evals with Personas
```bash
curl -s -X POST "${BASE}:runEvaluation" \
  -H "Authorization: Bearer ${TOKEN}" \
  -H "Content-Type: application/json" \
  -d '{
    "evaluations": ["projects/${PROJECT}/locations/${LOCATION}/apps/${APP_ID}/evaluations/${EVAL_ID}"],
    "runsPerEvaluation": 5,
    "config": {
      "evaluationChannel": "AUDIO"
    },
    "personaRunConfigs": [
      {
        "persona": "projects/${PROJECT}/locations/${LOCATION}/apps/${APP_ID}/evaluationPersonas/${PERSONA_ID}",
        "taskCount": 5
      }
    ]
  }'
```

### Persona Speech Configuration

Personas live in `app.evaluationPersonas` and are managed via app PATCH:

```bash
# Get current personas
curl -s "${BASE}" -H "Authorization: Bearer ${TOKEN}" | jq '.evaluationPersonas'

# Update a persona's speechConfig (must PATCH full persona list)
# 1. Get current personas
# 2. Modify the target persona's speechConfig
# 3. PATCH the app with the full updated list
curl -s -X PATCH "${BASE}?updateMask=evaluationPersonas" \
  -H "Authorization: Bearer ${TOKEN}" \
  -H "Content-Type: application/json" \
  -d '{
    "evaluationPersonas": [
      {
        "name": "projects/.../evaluationPersonas/PERSONA_ID",
        "displayName": "Frustrated Caller",
        "personality": "impatient, interrupts frequently",
        "speechConfig": {
          "voiceId": "en-US-Wavenet-D",
          "speakingRate": 1.2,
          "environment": "CALL_CENTER"
        }
      }
    ]
  }'
```

Speech config fields:
- `voiceId`: TTS voice (e.g., `en-US-Wavenet-D`, `en-GB-Standard-A`)
- `speakingRate`: 0.8 (slow) to 1.5 (fast), default 1.0
- `environment`: Background noise — `CALL_CENTER`, `TRAFFIC`, `KIDS_NOISE`, `CAFE`

### Test Persona Voice
```bash
curl -s -X POST "${BASE}:testPersonaVoice" \
  -H "Authorization: Bearer ${TOKEN}" \
  -H "Content-Type: application/json" \
  -d '{
    "personaId": "PERSONA_ID",
    "text": "Hello, I need help with my phone dropping calls."
  }'
# Returns: {"audio": "<base64 audio bytes>"}
```

### Upload Audio for Golden Evals
```bash
curl -s -X POST \
  "https://ces.googleapis.com/v1beta/projects/${PROJECT}/locations/${LOCATION}/apps/${APP_ID}/evaluations/${EVAL_ID}:uploadEvaluationAudio" \
  -H "Authorization: Bearer ${TOKEN}" \
  -H "Content-Type: application/json" \
  -d '{
    "audioContent": "<base64 LINEAR16 16kHz audio bytes>"
  }'
# Returns: {"audioGcsUri": "gs://...", "transcript": "...", "duration": "..."}
```

### Latency Reports
Enable latency reports for audio runs to get p50/p90/p99 breakdowns:
```bash
curl -s -X POST "${BASE}:runEvaluation" \
  -H "Authorization: Bearer ${TOKEN}" \
  -H "Content-Type: application/json" \
  -d '{
    "evaluations": [...],
    "runsPerEvaluation": 5,
    "config": {"evaluationChannel": "AUDIO"},
    "generateLatencyReport": true
  }'
```

After completion, the run includes `latencyReport` with per-resource p50/p90/p99 latencies for tools, guardrails, LLM calls, and callbacks.

### Audio Eval Results

Audio eval results have the same structure as text evals plus:
- **`conversation.channelType: "AUDIO"`** and **`inputTypes: ["INPUT_TYPE_AUDIO"]`**
- Messages use **`transcript`** field instead of `text`
- **`spanLatencies`**: Per-span timing (LLM, TOOL, USER_CALLBACK, GUARDRAIL) showing full audio pipeline latency
- **`toolCallLatencies`**: Per-tool-call timing with `startTime`, `endTime`, `executionLatency`

### Key Differences from Text Evals
| Aspect | Text | Audio |
|--------|------|-------|
| Channel config | Default (omit) | `config.evaluationChannel: "AUDIO"` |
| Message format | `text` field | `transcript` field |
| Latency data | Minimal | Full span latencies (LLM, tool, callback) |
| Persona voice | N/A | `speechConfig` with voiceId, rate, environment |
| Scoring | Same (`userGoalSatisfactionResult.score`) | Same |
| Run time | Faster | Slower (TTS/STT overhead) |

### Important Notes
- Audio evals use the **same scenario definitions** as text evals — no changes needed to the eval itself
- `evaluationChannel` is set at **run time**, not eval creation time — the same eval can run as text or audio
- Personas are app-level, not eval-level — managed via `app.evaluationPersonas` PATCH
- There are no separate CRUD endpoints for personas — only `testPersonaVoice` is persona-specific
- Maximum 30 personas per app

---

## YAML Formats for Bundled Scripts

The eval scripts in `.agents/skills/cxas-agent-foundry/scripts/` expect specific YAML structures. Using the wrong format causes parse errors.

### Scenarios (`evals/scenarios/scenarios.yaml`) — optional
This file is only needed if you use `scrapi-eval-runner.py push` or `scrapi-eval-runner.py run` for platform scenario evals. Golden-only and sim-only workflows do not require it. App config (project, location, app ID) comes from `gecx-config.json`, not from this file.

```yaml
evals:
  - name: "cuj_name"
    display_name: "CUJ Description"
    priority: "P0"
    tags: ["tag"]
    task: "Sim user persona and goal."
    max_turns: 12
    variables: {}
```

### Goldens (`evals/goldens/*.yaml`)
`EvalUtils.load_golden_evals_from_yaml()` parses the `conversations` format:
```yaml
conversations:
  - conversation: "Test Name"
    tags: ["tag"]
    turns:
      - user: "user message"
        agent: "expected response (plain string ONLY — no dicts, no $matchType)"
      - user: "provide auth info"
        agent: "acknowledged"
        tool_calls:
          - action: authenticate_customer
            args:
              account_id: "12345"
              zip_code: "30033"
```
Golden files do NOT need a `meta` block — app_name comes from `gecx-config.json`.

#### Tool Call Args Matching in Goldens (CRITICAL — common failure point)

The platform evaluates tool call args using a **`parameterCorrectnessScore`** — it checks what percentage of your expected params were present in the actual call. It does NOT do exact string matching on arg values.

**For args that vary unpredictably** (e.g., the agent might pass DOB as "1948-07-12" or "July 12, 1948"), use the `$matchType` / `$originalValue` syntax:

```yaml
tool_calls:
  - action: authenticate_customer
    args:
      date_of_birth:
        $matchType: "ignore"         # skip this param — it varies by LLM phrasing
        $originalValue: "1948-07-12"
        $matchValue: ""
      zip_code: "30033"              # exact match (no $matchType = exact)
      ssn_last4: "4532"              # exact match
```

**Valid `$matchType` values:** `ignore`, `semantic`, `contains`, `regexp`
- `ignore` — skip this param entirely (best for dates, free-text the LLM reformats)
- `semantic` — fuzzy semantic similarity (for summary fields)
- `contains` — actual must contain the `$originalValue` substring
- `regexp` — match against regex in `$originalValue` (NOT `regex` — that's wrong)

**Common mistakes:**
- Using `$matchValue` instead of `$originalValue` for the expected text — the expected text goes in `$originalValue`
- Using `regex` instead of `regexp` — causes `KeyError: 'regex'` on the platform
- Putting `$matchType` on the `agent` field — agent response MUST be a plain string, `$matchType` only works inside `tool_calls.args`
- Putting `$matchType` on boolean/enum args — use exact match for `true`/`false` values

**Best practice:** Use `ignore` for date fields the LLM reformats. Use exact match for structured fields (zip codes, IDs, booleans). Only use `semantic`/`contains` when you need to verify the value is directionally correct.

**Extra turns in multi-agent goldens:** In multi-agent flows, the agent may transfer to a sub-agent after completing the golden's expected turns. The sub-agent responds, producing output the golden doesn't cover. The platform marks this as FAIL even though all expected turns passed. The triage script categorizes these as `EXTRA_TURNS`. To avoid this:
- End the golden before the turn that triggers a transfer (e.g., end at the tool call, don't add expected text after it)
- Or accept that the golden only tests the auth/routing portion and rely on sims for the full flow
- Do NOT add agent text on the last turn of a golden that triggers a transfer — the agent's post-auth phrasing varies and the transfer/sub-agent response adds unexpected turns

### Simulations (`evals/simulations/simulations.yaml`)
`scrapi-sim-runner.py` reads this file for sim templates. App config comes from `gecx-config.json`:
```yaml
evals:
- name: "sim_name"
  steps:
    - goal: "What the caller wants to accomplish"
      success_criteria: "How to judge success"
      response_guide: "Caller persona with auth details"
      max_turns: 10
  expectations:
    - "Behavioral check description"
  session_parameters: {}
```

### Tool Tests (`evals/tool_tests/*.yaml`)
```yaml
tests:
  - name: "test_1"
    tool: "tool_display_name"
    args: { key: "value" }
    variables: {auth_status: "authenticated"}
    expectations:
      response:
        - path: "$.result.field"   # MUST include $.result. prefix
          operator: equals
          value: "expected_value"
```

**Critical format notes:**
- Top-level key MUST be `tests:` — using `test_cases:` silently loads 0 tests.
- Each test case needs `tool:` — don't use a top-level `tool_name:` key.
- Use `variables:` to set session state (e.g., `auth_status`). Tool tests run in isolation with no session state — tools that check `context.state` will fail without it.
- Tool responses are nested under `result` — paths MUST start with `$.result.`.

### Creating Evaluation Expectations
Scenarios need `EvaluationExpectation` resources created on the platform:
```python
client = Evaluations(app_name=APP_NAME)
exp = client.create_evaluation_expectation(
    display_name="task_completed",
    llm_criteria={"prompt": "Did the agent complete the task?"}  # "prompt", NOT "instruction"
)
```
Always create a pacing expectation too:
```python
pacing = client.create_evaluation_expectation(
    display_name="one_question_at_a_time",
    llm_criteria={"prompt": "Did the agent collect information one piece at a time, asking only one question per turn and waiting for the response before asking the next?"}
)
```

## Conversational Design Principles for Evals

Evals must test that the agent behaves like a natural human, not a form-fill bot.

**One question at a time (CRITICAL anti-pattern):**
The agent MUST collect information one piece per turn — ask DOB, wait, ask ZIP, wait, ask ID. Never "What is your DOB, ZIP, and ID?" in one turn.

Goldens should model correct pacing:
```yaml
# CORRECT
steps:
  - user: "I need help with my account"
  - agent: "I'd be happy to help. What's your date of birth?"
  - user: "July 12, 1948"
  - agent: "And your ZIP code?"
  - user: "30033"
  - agent: "Do you have your account ID?"
```

Simulation expectations should catch the anti-pattern:
```yaml
expectations:
  - "The agent asked for information one piece at a time, not all at once."
```

**Other principles:**
- Acknowledge before asking ("Thank you. And your ZIP code?")
- Offer alternatives naturally (SSN fallback if no account ID)
- Use verbal nods ("I understand", "Of course")
- Plain language (no jargon)

## Eval API Gotchas

- `Evaluations` has NO `list_evaluation_runs()` — use `get_evaluation_run(run_id)`
- `list_evaluation_results_by_run()` needs full resource path, often returns 400 — use `scrapi-eval-runner.py results` instead
- `ToolEvals.load_tool_tests_from_dir()` — NOT `load_tool_tests_from_file()`
- Start with `--channel text` for debugging, `--channel audio` for final
- Before writing evals: pull to local + lint + push fixes using full resource path `projects/.../apps/APP_ID` — NEVER create a new app
