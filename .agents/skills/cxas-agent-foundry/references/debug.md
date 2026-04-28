# Eval Debugger

Methodology for systematically debugging eval failures and improving agent behavior.

## Core Principle

**Diagnose first, but default to fixing the agent.** Never change eval expectations just to make tests pass -- expectations represent the contract with the user. When in doubt, assume the agent is wrong.

## Table of Contents

- [Core Principle](#core-principle)
- [Quick Start](#quick-start)
- [Prerequisites](#prerequisites)
- [The Iteration Loop](#the-iteration-loop)
- [Prioritizing Failures](#prioritizing-failures)
- [Reading Triage Output](#reading-triage-output)
- [Triage Guide](#triage-guide)
  - [Diagnosis Decision Tree](#diagnosis-decision-tree)
  - [Reading Transcripts](#reading-transcripts)
  - [Diagnosable Failure Patterns](#diagnosable-failure-patterns)
  - [Recommended Fix Approach](#recommended-fix-approach)
  - [Improvement Strategies by Issue Type](#improvement-strategies-by-issue-type)
  - [Simulation Failures](#simulation-failures)
  - [Component Test Failures](#component-test-failures)
  - [Audio-Specific Debugging](#audio-specific-debugging)
  - [Debugging Regressions](#debugging-regressions)
  - [Tuning Scoring Thresholds](#tuning-scoring-thresholds)
- [Common Mistakes](#common-mistakes)
- [Appendix: Bootstrap from Existing Agent](#appendix-bootstrap-from-existing-agent)

### Load additional references as needed:
- **TDD structure and generation**: `references/tdd-guide.md` -- load when generating or updating the TDD
- **Architecture and anti-patterns**: `references/gecx-design-guide.md` -- load when fixing instruction issues or architectural problems
- **Callback API and patterns**: `references/callback-api.md` -- load when fixing callback behavior
- **Eval YAML formats**: `references/eval-templates.md` -- load when fixing eval configuration
- **Report interpretation**: `references/generating-reports.md` -- load when interpreting triage results or understanding triage categories
- **SCRAPI API calls**: `references/api-reference.md`

## Quick Start

```bash
# Single-command iteration step: snapshot + evals + triage + report (recommended)
python .agents/skills/cxas-agent-foundry/scripts/run-and-report.py --runs 5 --auto-revert \
  --message "Change: <what changed>
Reason: <why -- which eval was failing and what the root cause was>
Expected fix: <which evals this should fix>"

# Triage failures from the latest run
python .agents/skills/cxas-agent-foundry/scripts/triage-results.py
python .agents/skills/cxas-agent-foundry/scripts/triage-results.py --last 3  # average across runs

# Sync callback code from platform to local tests
python .agents/skills/cxas-agent-foundry/scripts/sync-callbacks.py

# Bootstrap all eval files for an existing agent (first time only)
python .agents/skills/cxas-agent-foundry/scripts/bootstrap-evals.py
```

The script reads the channel from `gecx-config.json` automatically. Only pass `--channel` to override.

## Prerequisites

Check `<project>/gecx-config.json` first for project configuration (where `<project>` is the active project folder from `.active-project`, e.g., `tmobile/`). If not present, check memory or ask the user.

| Prerequisite | Check | If missing |
|-------------|-------|------------|
| **Environment** | `.venv/` exists, `cxas-scrapi` installed | Follow Onboarding Flow in `references/setup.md` |
| **App name** | `<project>/gecx-config.json` -> `deployed_app_id` | Ask the user |
| **TDD (Mandatory)** | `<project>/tdd.md` | --> *You MUST immediately execute the [Bootstrap from Existing Agent](#appendix-bootstrap-from-existing-agent) flow to reverse-engineer the TDD.* |
| **Goldens** | `<project>/evals/goldens/*.yaml` | Generate from TDD -- see `references/build.md` |
| **Sims** | `<project>/evals/simulations/simulations.yaml` | Generate from TDD -- see `references/build.md` |
| **Tool tests** | `<project>/evals/tool_tests/*.yaml` | Generate using `ToolEvals.generate_tool_tests()` |
| **Callback tests** | `<project>/evals/callback_tests/agents/` | Sync from platform and write tests |
| **Target pass rate** | Ask the user | e.g., 90%, 100% -- this is your exit criteria for the iteration loop |
| **Channel** | Ask the user | text or audio |

## The Iteration Loop

This is the core debug cycle. Initialize your `todo.md` checklist with the following. **All items MUST start unchecked (`[ ]`).** Only check an item (`[x]`) AFTER you have fully completed it -- not when you begin it, and not preemptively.

1. [ ] Check prerequisites (see [Prerequisites](#prerequisites) -- each sub-item must be individually verified)
2. [ ] Check `<project>/experiment_log.md` for prior attempts -- avoid repeating approaches that caused regressions
3. [ ] Lint + push current agent state, then run evals (`cxas lint` + `cxas push` + `run-and-report.py --runs 5 --auto-revert`)
4. [ ] Read triage output (see [Reading Triage Output](#reading-triage-output))
5. [ ] Prioritize failures (see [Prioritizing Failures](#prioritizing-failures))
6. [ ] Read failing transcripts (see [Reading Transcripts](#reading-transcripts))
7. [ ] Diagnose root cause using the [Diagnosis Decision Tree](#diagnosis-decision-tree)
8. [ ] Plan fix (get user approval if structural change -- see [Recommended Fix Approach](#recommended-fix-approach))
9. [ ] Apply fix + lint + push
10. [ ] Re-run evals to verify -- go to step 2 until adjusted pass rate meets target

```
LINT + PUSH  ->  RUN EVALS  ->  TRIAGE  ->  PRIORITIZE  ->  READ TRANSCRIPTS  ->  DIAGNOSE  ->  FIX  ->  (repeat)
```

**Why lint + push before every eval run?** Goldens run on the platform, not locally. If you skip the push, evals run against the old agent version and your fix appears to have no effect. This is the single most common source of "my fix didn't work" confusion.

`run-and-report.py` combines snapshot + eval runs + triage + iteration-report into one command. Use `--auto-revert` to automatically revert `cxas_app/` on real regressions.

**Write detailed `--message` values.** The message goes into the iteration report and experiment log -- someone reviewing the history should be able to understand each iteration without reading the diff.

Good message:
```bash
python .agents/skills/cxas-agent-foundry/scripts/run-and-report.py --auto-revert --runs 5 \
  --message "Change: Added trigger pattern for escalation in root_agent before_model_callback.
Reason: golden_live_agent_request failing with TOOL_MISSING -- LLM says escalation text but forgets to call payload_update_tool.
Expected fix: golden_live_agent_request (TOOL_MISSING), golden_profanity_escalation (TOOL_MISSING)"
```

Bad message:
```bash
--message "Fixed escalation"  # No context on what failed, why, or what should improve
```

### Auto-revert conditions

`--auto-revert` reverts `cxas_app/` when **ALL** of these are true:
1. Golden pass rate dropped from previous iteration
2. Failures are real agent issues (TOOL_MISSING, TEXT_MISMATCH, EXPECTATION_FAIL), not platform issues (timeouts, SCORES_PASS_BUT_FAIL)
3. Sims did NOT improve (if goldens regressed but sims improved, it's a mixed signal -- investigate instead of reverting, the golden expectation may need updating)

### Syncing local and platform

When local `cxas_app/` and the platform diverge (e.g., someone edited on the platform UI while you edited locally):

1. **Pull** platform state into your local `cxas_app/` (or a temp dir to diff first)
2. **Merge** any conflicting changes -- reconcile, don't overwrite
3. **Push** the merged version back to the platform

### Don't trust a single run

A golden that passes 1/1 may fail 2/5. Run goldens at least 5 times (`--runs 5`) and use `triage-results.py --last 3` to see the real pass rate across runs. Only consider a golden stable when it passes consistently across multiple runs.

## Prioritizing Failures

When triage shows multiple failures, fix them in this order. Earlier fixes often resolve later ones -- a missing tool fix frequently eliminates text mismatches downstream.

**Fix order:**

1. **EVAL_ERROR** -- broken eval config blocks you from even measuring progress. Fix these first so your signal is clean.
2. **TOOL_MISSING** -- the most impactful category. When the agent can't find the right tool, it improvises with wrong tools or skips the action entirely, causing cascading text and expectation failures. Fixing tool availability often resolves 2-3 other failures for free.
3. **EXPECTATION_FAIL** -- custom LLM judge failures usually indicate real behavioral gaps. Read the judge explanation to understand what's wrong.
4. **HALLUCINATION** -- agent fabricating information is a trust violation. Fix by removing example phrases from instructions and adding grounding constraints.
5. **TEXT_MISMATCH** -- sometimes these resolve after fixing TOOL_MISSING. If they persist, check whether the instruction changed but the golden still expects old phrasing.
6. **EXTRA_TURNS** -- agent produces output after the golden ends (usually a transfer). Either extend the golden to cover the sub-agent response, or end the golden before the transfer.
7. **TIMEOUT / SCORES_PASS_BUT_FAIL** -- platform issues, not agent bugs. Exclude from adjusted pass rate. Increase `max_turns` for timeouts.

**When multiple evals fail in the same category:** Fix the simplest one first. A quick win gives you a cleaner signal for diagnosing the harder failures.

**When one fix regresses another eval:** Don't ping-pong. Read both transcripts together and look for instruction conflicts -- a constraint needed by eval A that contradicts the fix for eval B. Resolve the conflict rather than choosing sides.

## Reading Triage Output

The triage script produces three sections. Here's how to interpret each:

```
=== Golden Triage (run a1b2c3d4, 2026-04-18 14:30:22) ===

SUMMARY: 18/25 PASS | 3 TOOL_MISSING | 2 TEXT_MISMATCH | 1 EXTRA_TURNS | 1 SCORES_PASS_BUT_FAIL
Adjusted (excl platform/config issues): 18/24 (75.0%)
```

**SUMMARY line**: raw pass count, then failure counts by category. Scan this to see the shape of the problem -- is it mostly tool issues? Mostly text? A mix?

**Adjusted pass rate**: the real metric. It excludes SCORES_PASS_BUT_FAIL, TIMEOUT, and EVAL_ERROR (platform/config issues you can't fix by changing the agent). Track this number across iterations to measure progress.

```
PER-EVAL:
  ~ golden_auth_failure: 3/5
      TOOL_MISSING: expected auth_check_tool, not found. Called: [lookup_faq]
      TOOL_MISSING: expected auth_check_tool, not found. Called: [lookup_faq]
  ~ golden_escalation: 4/5
      TEXT_MISMATCH: sem_score=2.1
  v golden_greeting: 5/5
```

**PER-EVAL section**: shows pass rate per golden and the category + detail for each failure. This tells you which evals to focus on and gives the first clue about root cause. In the example above, `golden_auth_failure` fails 2/5 with TOOL_MISSING -- the agent called `lookup_faq` instead of `auth_check_tool`, which suggests the tool is either missing from the agent's tool list or the instruction doesn't reference it clearly.

```
FAILURES BY CATEGORY:
  TOOL_MISSING (3): golden_auth_failure x2, golden_billing_check
  TEXT_MISMATCH (2): golden_escalation, golden_farewell
```

**FAILURES BY CATEGORY**: groups all failures by type, showing which evals contribute to each. Use this to spot patterns -- if 3 evals all have TOOL_MISSING for the same tool, that's one fix, not three.

## Triage Guide

### Diagnosis Decision Tree

Use this tree to classify each failure before attempting a fix:

```
Failure
+-- TIMEOUT / EVAL_ERROR / SCORES_PASS_BUT_FAIL
|   +-- Platform or config issue, NOT an agent bug
|       +-- TIMEOUT: Increase max_turns, check tool latency
|       +-- EVAL_ERROR: Fix the golden YAML (empty inputs, invalid args)
|       +-- SCORES_PASS_BUT_FAIL: Platform scorer bug. Exclude from adjusted pass rate
|
+-- EXTRA_TURNS
|   +-- Agent transfers after golden ends, NOT an agent bug
|       +-- End golden before transfer, or extend to cover sub-agent
|
+-- TEXT_MISMATCH / TOOL_MISSING / EXPECTATION_FAIL / HALLUCINATION
    +-- Likely an agent issue. Read the transcript, then ask:
        |
        +-- Is the golden expectation stale (instruction changed but golden expects old phrasing)?
        |   +-- Yes: Fix the eval, not the agent
        |
        +-- Is the sim response_guide too vague or success_criteria too narrow?
        |   +-- Yes: Fix the eval config (see Simulation Failures below)
        |
        +-- Is a tool missing from the agent's tool list?
        |   +-- Yes: Add the tool to the agent config. This is the most common and
        |       hardest-to-diagnose issue -- the LLM silently improvises when it
        |       can't find the right tool.
        |
        +-- Are instructions contradictory across agents?
        |   +-- Yes: Audit ALL agent instructions together, resolve conflicts
        |
        +-- Is the behavior inherently non-deterministic (passes 3/5, fails 2/5)?
        |   +-- Yes: Use the trigger pattern for deterministic execution,
        |       or convert to a simulation if the flow is inherently variable
        |
        +-- Is the agent hallucinating (saying things not grounded in tool output)?
            +-- Yes: Remove example phrases from instructions,
                add "Only use information from tool responses"
```

### Reading Transcripts

**Read the transcript before attributing any failure to "LLM flakiness"** -- most failures have a diagnosable root cause. Here's how to access them:

**From triage output:** `triage-results.py` prints failure categories and per-eval breakdowns. For failing goldens, it shows which category each failure falls into (TOOL_MISSING, TEXT_MISMATCH, etc.) with details about what went wrong.

**From eval run results:** Fetch the full results for an eval run using the Evaluations API:

```python
from cxas_scrapi.core.evaluations import Evaluations

evals = Evaluations(app_name=APP_NAME)
# Get results from a specific run
results = evals.list_evaluation_results_by_run(evaluation_run_id="<run_id>")
# Each result contains per-turn scores, tool call comparisons, and agent responses
```

**Replay and capture full transcripts:** Use `capture-golden-transcripts.py` to replay golden user turns against the live agent and capture the full conversation:

```bash
# Capture transcript for a specific golden
python .agents/skills/cxas-agent-foundry/scripts/capture-golden-transcripts.py --eval golden_auth_failure

# Capture all golden transcripts
python .agents/skills/cxas-agent-foundry/scripts/capture-golden-transcripts.py --all
```

Transcripts are saved to `<project>/evals/goldens/transcripts/` as JSON files with full tool calls, agent transfers, and callback responses.

**What to look for in transcripts:**
- Which model call produced the wrong behavior (text, tool call, or transfer)?
- Did the agent have the right information available (check prior tool responses)?
- Did a callback fire when expected? Did it return the right response?
- Was there an unexpected agent transfer mid-turn?
- Did the agent produce text AND tools in separate model calls (silent tool call pattern)?

### Diagnosable Failure Patterns

These are the most common agent issues. For triage category definitions (TEXT_MISMATCH, TOOL_MISSING, etc.), see `references/generating-reports.md` -> Triage Categories.

| Pattern | What you see | Root cause | Fix |
|---------|-------------|------------|-----|
| Silent tool calls | Text in one model call, tools in another | Multi-model-call turn splitting | `after_model_callback` with `text_or_transcript()` + `events` API |
| Missing tool calls | Right text, no tools | LLM forgot tool call | Trigger pattern: instruction sets state variable, callback returns tools |
| Missing tool (variant) | LLM improvises with other tools | Tool not in agent's tool list | Add the tool to the agent -- verify tool availability! |
| Empty tool args | Tool called with `{}` | LLM doesn't know required args | Better docstrings with `(REQUIRED)` + state-based fallback in tool code |
| Unexpected transfer | Extra agent transfer alongside tools | LLM routes + acts simultaneously | Handle action entirely in `before_model_callback` |
| Callback gap | Behavior works on root but not sub-agent | Root callbacks don't fire on sub-agents | Add callback to every agent in the flow |
| Stale golden | Golden expects old phrasing after instruction update | Eval not updated after agent change | Update the golden expected response to match new instructions |
| Flaky pass (3-4/5) | Sometimes passes, sometimes fails | Non-deterministic LLM behavior | Use trigger pattern for deterministic execution, or convert to sim |

### Recommended Fix Approach

The core principle: **LLM detects, callbacks execute.**

The LLM understands natural language intent -- let it handle detection (hostility, frustration, transfer requests, issue classification). Callbacks handle execution that must be deterministic (tool calls with correct args, session termination).

**CRITICAL -- PLAN BEFORE STRUCTURAL CHANGES:** If fixing a failure requires a cross-cutting architectural change (e.g., adding a new agent, modifying `before_agent` state derivation, or changing multi-agent routing), propose the structural fix to the user and get approval before making file changes. Simple prompt tweaks in `instruction.txt` do not require a plan.

When behavior is flaky:
1. **Check tool availability first** -- if the instruction references a tool the agent can't access, the LLM silently improvises. This is the most common and hardest-to-diagnose issue.
2. **Fix the instruction** -- make triggers clearer, remove conflicting constraints, add priority ordering. See `references/gecx-design-guide.md` -> "Instruction Design Anti-Patterns".
3. **Use the trigger pattern** -- for actions that must be deterministic (escalation, session termination), have the instruction tell the LLM to set a state variable, then have the callback intercept and execute. See `references/gecx-design-guide.md` -> "Trigger pattern for deterministic tool calls".
4. **Use `after_model_callback`** -- to guarantee text before `end_session`, or to recover when the LLM forgets the state-setting call.

**Don't overfit.** If you find yourself adding hardcoded phrase lists to callbacks, requiring exact keywords in triggers, or bypassing the LLM for intent detection -- stop. The agent might pass goldens but fail on real conversations. Signs: golden pass rate goes up but sim pass rate degrades.

### Improvement Strategies by Issue Type

| Issue | Strategy |
|-------|----------|
| Wrong tool called | Improve tool descriptions, add examples showing correct tool choice |
| Missing tool call | Add explicit instruction: "When user asks X, always use tool Y" |
| Wrong parameters | Add parameter guidance in instructions |
| Bad response tone | Update globalInstruction with persona/tone guidance |
| Hallucination | Add grounding constraint + remove example phrases from instructions |
| Repeated empathy | Add: "Express empathy ONLY ONCE" with explicit prohibition |
| Too verbose | Add: "Keep responses to 2-3 short sentences maximum" |
| Wrong agent routing | Add deterministic transfer rules, improve child agent descriptions |
| Inconsistent behavior | Align sub-agent instructions with root agent, lower temperature |
| Guardrail blocking valid input | Lower safety threshold or add safe categories to prompt guardrail |

### Simulation Failures

| Symptom | Likely cause | Fix |
|---------|-------------|-----|
| "Task not completed" | `success_criteria` too narrow | Add "X counts as a successful outcome" |
| Sim user goes off-script | `response_guide` too vague | Be extremely directive: "You MUST cooperate fully" |
| Sim user refuses steps | `response_guide` doesn't instruct cooperation | Add "Follow ALL steps without objection" |
| Runs out of turns | Flow exceeds `max_turns` | Increase `max_turns` -- audio needs 4-6 extra |
| Tool not called | Expectation uses function name | Use behavioral description: "must call a tool to check outages" |

**When to convert a golden to a simulation:** If a golden fails >40% of runs despite correct agent behavior (verified by reading transcripts), the flow is inherently variable. Convert to a simulation -- see `references/run.md` -> "Choosing Golden vs Sim" for the decision criteria.

### Component Test Failures

Component tests (tool tests, callback tests) are deterministic -- they should pass 100% of the time. Failures indicate bugs in code, not LLM variance.

**Tool test failures:**
1. Read the failing test's expected output and the actual output from the test results
2. Read the tool's source code: `<project>/cxas_app/<AppName>/tools/<tool_name>/python_function/python_code.py`
3. Common causes:
   - Return dict keys don't match expectations (check exact key names)
   - Tool depends on external API that returned unexpected data
   - Tool uses `context` variables that aren't set in the test's `session_params`
4. Fix the tool code or update the test's `session_params` to provide required context

**Callback test failures:**
1. Sync the latest callback code from the platform:
   ```bash
   python .agents/skills/cxas-agent-foundry/scripts/sync-callbacks.py
   ```
2. Read the failing test in `<project>/evals/callback_tests/agents/<agent>/`
3. Common causes:
   - Callback logic changed on the platform but tests weren't updated
   - Mock objects don't match the real `CallbackContext` shape
   - Callback imports something the test environment doesn't provide (remember: `Part`, `Content`, `LlmResponse`, `LlmRequest`, `CallbackContext` are auto-provided globals on the platform)
4. Fix the test mocks or the callback code, then re-run locally with pytest

### Audio-Specific Debugging

Audio agents have unique failure modes. If `gecx-config.json` specifies `"modality": "audio"`, keep these in mind:

**`expect_tools` silently fails in audio mode.** Tool expectations in sim YAML (`expect_tools`) don't work for audio -- the platform doesn't return tool call data in audio transcripts. Use `expect_criteria` (LLM-judged behavioral expectations) instead: `"The agent must check for outages"` rather than `expect_tools: ["check_outages_tool"]`.

**Audio needs more turns.** Audio conversations include silence handling, filler acknowledgments, and chunked speech that inflate turn count. Add 4-6 extra turns to `max_turns` compared to text equivalents to avoid false TIMEOUT failures.

**Semantic similarity scores differently for spoken language.** The agent's audio output is transcribed before scoring, so minor phrasing differences that wouldn't matter in text (contractions, filler words) can drag down similarity scores. If a golden shows TEXT_MISMATCH with `sem_score` between 2.0-3.0 and the transcript looks correct when you read it, consider lowering the similarity threshold for that eval rather than changing the agent.

**Never run audio agents in text mode for evals.** The runner scripts enforce this (fatal error on `--channel text` for audio apps), but the underlying reason matters: audio agents have voice-specific instructions (pronunciation, cadence, filler handling) that produce unnatural text responses, leading to false failures.

### Debugging Regressions

When a previously-passing eval starts failing after a change:

1. **Identify what changed** -- diff the current agent state against the last passing iteration:
   ```bash
   # Check the experiment log for the last known-good state
   cat <project>/experiment_log.md

   # Diff against the snapshot (run-and-report.py snapshots before each run)
   diff -r <project>/eval-reports/iterations/iteration-<N-1>/snapshot/ <project>/cxas_app/
   ```
2. **Check for instruction conflicts** -- the most common cause of regressions is a fix for eval A that contradicts constraints needed by eval B. Audit all instruction files together, looking for:
   - Conflicting priority between guidelines and taskflow steps
   - New constraints that block previously-working behaviors
   - Changes to routing logic that affect unrelated flows
3. **Check for callback side effects** -- if you modified a callback, verify it doesn't affect other flows:
   - `before_model_callback` changes affect every model call on that agent
   - `before_agent_callback` changes affect session initialization
   - State variable changes propagate to all downstream logic
4. **Decide: fix forward or revert**
   - If the regression is in a lower-priority eval and the fix improved higher-priority evals, fix forward (adjust the regressed eval)
   - If the regression affects core functionality, revert and try a different approach
   - `--auto-revert` handles this automatically for golden pass rate drops

### Tuning Scoring Thresholds

When goldens fail despite correct agent behavior (verified by reading transcripts), the scoring may be too strict. Use `app-thresholds.py` to view and adjust:

```bash
python .agents/skills/cxas-agent-foundry/scripts/app-thresholds.py show
python .agents/skills/cxas-agent-foundry/scripts/app-thresholds.py set --similarity 2      # lower text matching (1-4)
python .agents/skills/cxas-agent-foundry/scripts/app-thresholds.py set --extra-tools allow  # allow extra tool calls
python .agents/skills/cxas-agent-foundry/scripts/app-thresholds.py set --hallucination disabled
```

**When to use each threshold:**
- **`--similarity`**: Lower (1-2) when the agent says the right thing but with different phrasing. Higher (3-4) when exact phrasing matters (compliance, legal disclaimers).
- **`--extra-tools allow`**: When the agent calls the right tools plus additional helpful ones (e.g., logging, state updates) that the golden doesn't expect.
- **`--hallucination disabled`**: When the hallucination scorer flags grounded information as hallucinated (false positives). Verify by reading the transcript first.

Tune thresholds after confirming the agent behavior is correct (read transcripts) -- not as a substitute for fixing the agent.

---

## Common Mistakes

Ordered by severity -- the first few can block progress entirely, the later ones cause subtle issues.

1. **Running evals without pushing first** -- after fixing agent code locally, you must `cxas lint` + `cxas push` before running evals. Goldens run on the platform, not locally. Skipping the push means evals test the old version, and your fix appears to have no effect.
2. **Deleting evals during active runs** -- causes ERROR state on the platform. Wait for the run to reach COMPLETED before modifying evals.
3. **Pushing without resolving drift** -- if the platform has changes not in your local files, pushing will overwrite them. Always pull and merge before pushing when both sides have been edited.
4. **Repeating a failed approach** -- always check `experiment_log.md` before proposing a fix. If a similar approach was already tried and caused a regression, try a fundamentally different strategy.
5. **Overriding derived variables in eval session_params** -- check the `before_agent_callback` source to see which variables are derived automatically. Overriding them skips API calls and breaks downstream logic.
6. **Conflicting constraints in instructions** -- if a guideline says "gently redirect inappropriate questions" and a taskflow step says "escalate hostile language immediately," the LLM may follow the guideline (redirect) instead of the step (escalate). Audit constraints and guidelines for conflicts with escalation/routing steps.
7. **Using agent transcripts as goldens** -- tests that the agent does what it already does. Goldens should represent ideal PRD behavior.
8. **Truncating goldens via `update_evaluation()`** -- the API merges turns, it doesn't replace them. Removing a turn from the YAML and pushing won't delete it on the platform. To shorten a golden, delete the eval and recreate it.
9. **Using `yaml.dump()` on hand-written YAML** -- reformats, mangles strings, loses comments. Use targeted edits.

---

## Appendix: Bootstrap from Existing Agent

This flow is for when the user has an agent but no TDD or evals. Once bootstrapping is complete, return to [The Iteration Loop](#the-iteration-loop).

1. **Read the local agent code** -- the app and evals should already be set up by `setup-project.py` (which pulls the app and bootstraps eval files). If not, run it first (see `references/setup.md`). Read `app.json`, all instruction files, callback Python files, and tool Python files to understand the agent architecture.

2. **Generate the TDD** -- follow `references/tdd-guide.md` -> "Generating from an Existing Agent" to write `<project>/tdd.md` from scratch based on the agent code. Do NOT copy the template file -- it contains example data that will contaminate your output. Ask the user to review before proceeding.

3. **Complete eval files** -- use `bootstrap-evals.py` to generate initial eval stubs:
   ```bash
   python .agents/skills/cxas-agent-foundry/scripts/bootstrap-evals.py
   ```
   The script creates goldens, tool tests, callback stubs, and a sim skeleton. You still need to:
   - Write simulation goals and `success_criteria` (can't be auto-generated)
   - Write callback test assertions
   - Review exported goldens for correctness
   - Fill gaps from the TDD coverage map (see `references/build.md` -> "Generate Evals")

4. **Run baseline**:
   ```bash
   python .agents/skills/cxas-agent-foundry/scripts/run-and-report.py --runs 3 --message "Baseline run"
   ```
