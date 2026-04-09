---
name: agent-foundry-run
description: Create, manage, run, and report on GECX agent evals across three pipelines — platform goldens, platform scenarios, and local SCRAPI simulations. Use this skill whenever the user wants to create evals, push evals, run evals, check eval results, generate eval reports, or manage the eval suite. Also triggers on "goldens", "scenarios", "sim evals", "pass rate", "eval run", "create an eval", "write a golden", or comparing agent behavior against expected behavior.
user_invocable: false
---

# Eval Manager

This skill manages the full eval lifecycle for GECX conversational agents — creating evals, running them across three pipelines, and generating reports. The scripts live in this skill's `scripts/` directory.

## References

For detailed guidance on specific topics, read these reference files:
- `references/creating-evals.md` — How to create golden and scenario evaluations from scratch, including YAML format, tool expectations, and LLM judge criteria
- `references/generating-reports.md` — How to generate stakeholder-ready eval reports with coverage analysis, gate status, and run history

## Before Starting

Check memory for project-specific context (app ID, variable handling rules, known platform bugs). If not available, ask the user for:
1. **App name** — full resource path (`projects/{project}/locations/{location}/apps/{app_id}`)
2. **Eval file locations** — where goldens, scenarios, and simulations YAML files live
3. **Variable handling** — which variables the agent derives automatically vs needs as overrides (check the agent's `before_agent_callback` if unsure)
4. **Known platform issues** — e.g., audio scoring bugs, tool expectation quirks

## Five Eval Types

The eval suite supports five types of tests, each suited for different testing needs:

- **Conversation-level:** goldens, scenarios, simulations (test end-to-end agent behavior)
- **Component-level:** tool tests, callback tests (test individual pieces in isolation)

Component tests run faster and give more precise failure signals. Use them alongside conversation evals, not instead of them.

### 1. Platform Goldens — deterministic flows
Turn-by-turn **ideal** conversations that define what the agent SHOULD do per the PRD. The platform replays user inputs and scores agent responses via semantic similarity and tool call matching.

**Use for:** auth routing, escalation handoff, outage notification — any flow where user behavior is scripted and the agent path is predictable.

**Design principle:** Goldens represent ideal PRD behavior, not current agent behavior. Capturing agent transcripts and using them as goldens is circular — you'd be testing that the agent does what it already does, missing real gaps.

```bash
python .agents/skills/agent-foundry/scripts/scrapi-eval-runner.py push-goldens [path]
python .agents/skills/agent-foundry/scripts/scrapi-eval-runner.py run-goldens [--channel audio] [--runs 1]
```

### 2. Platform Scenarios — open-ended flows
The platform generates a sim user from a task description and lets it converse with the agent. Scoring uses goal satisfaction + LLM judge expectations.

**Use for:** troubleshooting cadence, multi-step failures, flows where tool responses determine the agent's path. These can't be goldens because the conversation varies each run.

```bash
python .agents/skills/agent-foundry/scripts/scrapi-eval-runner.py push [--priority P0] [--tag <tag>]
python .agents/skills/agent-foundry/scripts/scrapi-eval-runner.py run [--priority P0] [--channel audio] [--runs 5]
python .agents/skills/agent-foundry/scripts/scrapi-eval-runner.py results <RUN_ID> [--audio]
```

### 3. Local Simulations — fast iteration
Runs the same scenario evals locally using SCRAPI's Sessions API with Gemini as the sim user. Bypasses the platform queue entirely.

**Use for:** fast pre-flight checks before committing to a 25-minute platform run. Supports parallel execution so the full suite runs in ~1 minute.

```bash
python .agents/skills/agent-foundry/scripts/scrapi-sim-runner.py run [--priority P0] [--parallel 5] [--channel audio]
python .agents/skills/agent-foundry/scripts/scrapi-sim-runner.py run --eval <name> --verbose
python .agents/skills/agent-foundry/scripts/scrapi-sim-runner.py run --tag <tag> --parallel 3
```

### 4. Tool Tests — isolated tool validation
Tests individual tools with specific inputs and validates outputs. Faster than conversation evals and gives precise failure signals when a tool's API or schema changes.

```python
from cxas_scrapi.evals.tool_evals import ToolEvals

tool_evals = ToolEvals(app_name=app_name)
test_cases = tool_evals.load_tool_tests_from_dir("evals/tool_tests")
results_df = tool_evals.run_tool_tests(test_cases)
print(ToolEvals.generate_report(results_df))
```

### 5. Callback Tests — isolated callback validation
Tests agent callbacks using pytest. Agent code lives in `evals/callback_tests/agents/`, tests in `evals/callback_tests/tests/` (symlinked into agents/ for SCRAPI).

```python
from cxas_scrapi.evals.callback_evals import CallbackEvals

cb = CallbackEvals()

# Run all callback tests
results_df = cb.test_all_callbacks_in_app_dir(app_dir="evals/callback_tests")

# Or filter by agent
results_df = cb.test_all_callbacks_in_app_dir(
    app_dir="evals/callback_tests",
    agent_name="handle_connectivity_issue_agent",
    test_file_path="evals/callback_tests/test_before_agent.py",
)
```

## Choosing Golden vs Scenario

Use goldens for deterministic flows where the agent produces consistent tool calls and responses. Use scenarios/sims for flows with non-determinism (e.g., knowledge base queries that return different results).

| Use Goldens When | Use Scenarios/Sims When |
|-----------------|------------------------|
| Agent behavior is enforced by callbacks (deterministic) | Agent uses a knowledge base that returns varying results |
| Tool calls are consistent and predictable | Troubleshooting steps vary per query |
| Routing/escalation is the primary test | Behavioral goals are the primary test |
| The conversation follows a fixed script | The conversation path depends on tool responses |

**When a golden fails, fix the agent — not the eval.** Evals represent the contract with the user. If the agent's behavior varies, make it deterministic using callbacks. Only modify eval text after confirming the agent behavior is correct and the mismatch is purely phrasing.

## Filtering

All commands support `--priority P0` and `--tag <tag>` for filtering. Tags typically include priority (`P0`), severity (`NO-GO`, `HIGH`), PRD ID (`FR-1.1`), and category (`auth-routing`, `outage`, `troubleshooting`, `escalation`).

## Audio Scoring

**Scenarios:** The platform's audio pipeline has a known issue where `taskCompleted` always returns False, making `evaluation_status` unreliable for scenarios. Use `--audio` to score with `goalScore AND allExpectationsSatisfied` instead.

**Goldens:** Golden evals use `evaluation_status` directly (1=PASS, 2=FAIL) regardless of audio/text mode. The `--audio` flag does NOT apply to goldens — it only changes scenario scoring. Golden `evaluation_status` is computed from turn-level semantic similarity, tool invocation correctness, and hallucination checks. Do NOT use the `_score_result_audio()` method for goldens — it checks `scenario_result` which doesn't exist on golden results.

**Tool expectations in audio:** `expect_tools` causes silent failures in scenarios. Use `expect_criteria` (LLM judges) instead. For goldens, tool expectations work but are affected by LLM tool call ordering — only include core tool expectations in the golden's `tool_calls` list.

## Session Parameters

Evals inject variables into the agent session to set up the test scenario. The critical rule: only override variables the agent's callback **cannot derive** from the profile identifiers. If the callback early-returns when a variable is already set, overriding it short-circuits the entire API flow — the agent skips authentication, subscriber line lookup, and device type derivation.

## Reports

The sim runner generates HTML reports automatically after each run. For combined golden + sim reports:

```bash
python .agents/skills/agent-foundry/scripts/generate-combined-report.py \
  --golden-run <RUN_ID> --sim-results <JSON_PATH> \
  [--golden-modality audio] [--sim-modality audio]
```

Reports include: pass/fail summary with clickable dots that jump to specific runs, session ID deep links to the CES console, collapsible tool call I/O, merged audio text chunks, and for goldens, turn-by-turn expected vs actual comparison with semantic scores.

## Scripts

All scripts live in `.agents/skills/agent-foundry/scripts/` and assume they're run from the project root.

| Script | Purpose |
|--------|---------|
| `scrapi-eval-runner.py` | Platform evals: `status`, `push`, `push-goldens`, `run`, `run-goldens`, `results [--audio]`, `report` |
| `scrapi-sim-runner.py` | Local sim evals: `list`, `run [--parallel N] [--channel audio] [--eval name]`. Generates HTML reports. |
| `generate-combined-report.py` | Unified golden + sim HTML report |
| `run-and-report.sh` | Legacy platform runner (curl/REST) |
| `capture-golden-transcripts.py` | Capture live agent transcripts for reference |

## File Layout

```
evals/
├── scenarios/scenarios.yaml      # Platform scenario evals
├── goldens/*.yaml                # Platform golden evals (ideal conversations)
└── simulations/simulations.yaml  # Local sim eval templates
```
