---
name: eval-agent
description: Evaluate GECX agents — create evaluations (golden/scenario), run them, and analyze results
user_invocable: true
---

# Evaluate GECX Agent

You are an expert at evaluating agents using the Google Customer Engagement Suite (GECX/CES) API. Help the user create evaluations, run them, and analyze the results.

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
3. **Evaluation type** — Golden (replay expected conversation) or Scenario (simulate with rubrics)

## Evaluation Types

### Golden Evaluation
Replays a scripted conversation and checks that the agent's responses match expectations (tool calls, agent responses, transfers). **Expect high failure rates** — golden evals are inherently brittle with LLM agents due to response variation.

### Scenario Evaluation
Uses an AI user simulator with a task description and rubrics to evaluate the agent's behavior dynamically. **Preferred for behavioral testing.**

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
    "tool": "projects/.../tools/update_ccaas_payload",
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
        "$originalValue": "Connectivity"
      }
    }
  }
}
```

**In YAML golden format:**
```yaml
tool_calls:
  - action: update_ccaas_payload
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
- Use `ignore` for `summary`, `escalation_reason`, and `main_topic` — these are LLM-generated free-text fields that vary each run. The platform's semantic matcher is flaky on these (rejects valid semantics like "customer_is_unhappy" vs "Customer unhappy with outage"). The core test is that the tool WAS called with escalation=true, not what the reason text says.
- Only use `semantic` matching when the field value is critical to verify AND the expected value is short and unambiguous
- Keep exact matching for boolean/enum fields like `session_escalated`, `issue_type`
- Don't include auxiliary tool calls like `update_troubleshooting_slots` in golden expectations — the LLM reorders them relative to `transfer_to_agent`, causing flaky failures. Only test core behavior tools (routing, escalation, outage check).

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
- Redirect: "Being redirected to connectivity topics counts as a successful outcome."
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
You are a T-Mobile customer with an iPhone having service issues. You are NOT calling
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
      "user_role": "pah"
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
