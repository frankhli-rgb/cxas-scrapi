# Agent Foundry: Eval Runner

This skill manages the full eval lifecycle for GECX conversational agents — creating evals, running them, and generating reports.

## Table of Contents

- [References](#references)
- [Before Starting](#before-starting)
- [Four Eval Types](#four-eval-types)
- [Run Everything](#run-everything)
- [Choosing Golden vs Sim](#choosing-golden-vs-sim)
- [Filtering](#filtering)
- [Audio Scoring](#audio-scoring)
- [Session Parameters](#session-parameters)
- [Reports](#reports)

## References

- `references/creating-evals.md` — How to create golden and simulation evaluations, YAML format, tool expectations, LLM judge criteria
- `references/generating-reports.md` — How to generate stakeholder-ready eval reports with coverage analysis and gate status

## Before Starting

Check memory for project-specific context (app ID, variable handling rules, known platform bugs). If not available, ask the user for:
1. **App name** — full resource path (`projects/{project}/locations/{location}/apps/{app_id}`)
2. **Eval file locations** — where goldens and simulations YAML files live (in `<project>/evals/`, relative to the active project folder)
3. **Variable handling** — which variables the agent derives automatically vs needs as overrides (check the agent's `before_agent_callback` if unsure)

**CRITICAL: Evaluation Channel Enforcement**
If the app's `gecx-config.json` specifies `"modality": "audio"`, you MUST NOT run evaluations in text mode. The runner scripts will now throw a fatal error if you attempt to bypass this. When running eval scripts, either omit the `--channel` flag to rely on the default config, or explicitly pass `--channel audio`. Never pass `--channel text` for an audio agent.

## Four Eval Types

- **Conversation-level:** goldens, simulations (test end-to-end agent behavior)
- **Component-level:** tool tests, callback tests (test individual pieces in isolation)

### 1. Platform Goldens — deterministic flows
Turn-by-turn **ideal** conversations. The platform replays user inputs and scores agent responses via semantic similarity and tool call matching.

**Use for:** routing, escalation, auth checks — any flow where the agent path is predictable and callbacks enforce the behavior.

**Design principle:** Goldens represent ideal PRD behavior, not current agent behavior. Capturing agent transcripts as goldens is circular.

**Run goldens at least 5 times** (`--runs 5`) and use `triage-results.py --last 3` to average across runs.

```bash
python .agents/skills/cxas-agent-foundry/scripts/scrapi-eval-runner.py push-goldens [path]
python .agents/skills/cxas-agent-foundry/scripts/scrapi-eval-runner.py run-goldens [--channel audio] [--runs 5]
```

### 2. Local Simulations — open-ended flows
Uses SCRAPI's Sessions API with Gemini as the sim user to test flows where the conversation varies each run. Runs locally (not on the platform), supports parallel execution (~1 min for the full suite).

**Use for:** troubleshooting cadence, multi-step failures, knowledge base queries, any flow where tool responses determine the agent's path.

**Default filter:** `run-all-evals.py` runs sims with `--priority P0` by default. To run all priorities, pass `--priority P0,P1,P2` or run the sim runner directly without `--priority`.

```bash
python .agents/skills/cxas-agent-foundry/scripts/scrapi-sim-runner.py run [--priority P0] [--parallel 5] [--channel audio]
python .agents/skills/cxas-agent-foundry/scripts/scrapi-sim-runner.py run --eval <name> --verbose
python .agents/skills/cxas-agent-foundry/scripts/scrapi-sim-runner.py run --tag <tag> --parallel 3
```

### 3. Tool Tests — isolated tool validation (runs locally)
Tests individual tools with specific inputs and validates outputs. These run against the deployed app via SCRAPI — not pushed to the platform as eval objects.

```python
from cxas_scrapi.evals.tool_evals import ToolEvals

tool_evals = ToolEvals(app_name=app_name)
test_cases = tool_evals.load_tool_tests_from_dir("<project>/evals/tool_tests")
results_df = tool_evals.run_tool_tests(test_cases)
```

### 4. Callback Tests — isolated callback validation (runs locally)
Tests agent callbacks using pytest against local callback code. These never touch the platform — they import the callback Python directly and test with mock objects.

```python
from cxas_scrapi.evals.callback_evals import CallbackEvals

cb = CallbackEvals()
results_df = cb.test_all_callbacks_in_app_dir(app_dir="<project>/evals/callback_tests")
```

## Run Everything

```bash
# Single command: run evals + triage + generate iteration report
python .agents/skills/cxas-agent-foundry/scripts/run-and-report.py --message "what changed" --auto-revert

# Or run evals only (without reporting)
python .agents/skills/cxas-agent-foundry/scripts/run-all-evals.py --channel audio --runs 5
```

**After every run**, triage failures with the triage script — don't analyze results manually:

```bash
python .agents/skills/cxas-agent-foundry/scripts/triage-results.py           # latest run
python .agents/skills/cxas-agent-foundry/scripts/triage-results.py --last 3  # average across runs
```

This categorizes each failure (timeout, tool missing, text mismatch, scoring inconsistency) so you know what to fix vs what's a platform issue.

## Choosing Golden vs Sim

See `interview-guide.md` → "Golden vs Scenario Decision" for the decision table. Key rule: if a golden keeps failing because responses inherently vary (KB-dependent), convert to a sim.

## Filtering

All commands support `--priority P0` and `--tag <tag>`.

## Audio Scoring

**Goldens:** Use `evaluation_status` directly (1=PASS, 2=FAIL). The `--audio` flag does NOT apply to goldens.

**Sims:** The sim runner handles audio scoring automatically. Tool expectations (`expect_tools`) cause silent failures in audio mode — use `expect_criteria` (LLM judges) instead.

## Session Parameters

See the router skill for session parameter rules. Only override what the callback can't derive.

## Reports

```bash
# Combined report (auto-generated by run-all-evals.py)
python .agents/skills/cxas-agent-foundry/scripts/generate-combined-report.py \
  --golden-run <RUN_ID> --sim-results <JSON_PATH> \
  [--golden-modality audio] [--sim-modality audio]
```

