---
name: agent-foundry-debug
description: Debug failing GECX agent evals, improve pass rates, and fix agent behavior. Use this skill when the user wants to improve eval scores, debug why an eval is failing, hillclimb to a target pass rate, fix agent instructions, inspect agent traces, or says things like "get evals to 90%", "why is this eval failing", "fix the failing evals", "debug the agent", "look at the trace", or "run evals and fix what's broken".
user_invocable: false
---

# Eval Debugger

This skill provides the methodology for systematically debugging eval failures and improving agent behavior. It uses the `agent-foundry/skills/run/SKILL.md` for script documentation.

## References

For detailed guidance on specific debugging tasks, read these reference files:
- `references/debugging-agent.md` — How to test sessions, inspect conversations, execute tools, view traces and changelogs
- `references/improving-agent.md` — How to analyze eval failures, optimize agent instructions, and iterate on agent behavior

When fixing agent instructions, also read the GECX design guide at `skills/build/references/gecx-design-guide.md` — it has best practices for XML formatting, unambiguous instructions, tool design, and callback patterns that prevent common issues.

## Before Starting

### Check prerequisites

Check memory first for project-specific context (app ID, variable handling rules, past pass rates). If available, use it instead of re-asking the user.

Then verify these exist. If any are missing, bootstrap them first.

| Prerequisite | Check | If missing |
|-------------|-------|------------|
| **App name** | Check memory or `evals/scenarios/scenarios.yaml` meta | Ask the user for the full resource path |
| **TDD** | Check for `tdd.md` in project root | Generate one — see "Bootstrap from existing agent" below |
| **Goldens** | Check `evals/goldens/*.yaml` for conversations | Generate from TDD — see `skills/build/SKILL.md` |
| **Sims** | Check `evals/simulations/simulations.yaml` for evals | Generate from TDD — see `skills/build/SKILL.md` |
| **Tool tests** | Check `evals/tool_tests/*.yaml` | Generate using `ToolEvals.generate_tool_tests()` |
| **Callback tests** | Check `evals/callback_tests/agents/` for python_code.py + test.py | Sync from platform and write tests |
| **Target pass rate** | Ask the user | e.g., 90%, 100% |
| **Channel** | Ask the user | text or audio |

### Bootstrap from existing agent

When the user has an agent but no TDD or evals, run this before the iteration loop:

1. **Inspect the agent** — use SCRAPI to pull the agent architecture, tools, variables, callbacks, and instructions. See `skills/build/SKILL.md` → "Inspect App" for the API calls.

2. **Pull existing evals** — check the platform for evals already on the agent:
   ```python
   evals = Evaluations(app_name=app_name)
   evals_map = evals.get_evaluations_map(reverse=True)
   ```
   For each existing eval (goldens and scenarios), present them to the user:
   - Show the eval name, type, and what it tests
   - Ask the user to assign priority (P0/P1/P2) and severity (NO-GO/HIGH/MEDIUM/LOW)
   - Ask if they want to keep, modify, or remove each one
   - Download and save to the local eval files (goldens → `evals/goldens/`, scenarios → `evals/scenarios/`)
   
   Existing evals represent institutional knowledge — don't discard them. They may cover edge cases or regressions that aren't obvious from the agent inspection alone.

3. **Generate the TDD** — from the inspection AND existing evals, write `tdd.md` covering:
   - Agent hierarchy (root + sub-agents) with routing logic
   - Tools (name, type, purpose)
   - Variables (callback-derived vs override-safe)
   - Test data profiles (from session parameters or CSV)
   - Eval coverage map — map existing evals to requirements first, then identify gaps
   - Known issues
   Ask the user to review and approve before proceeding.

4. **Fill eval gaps** — from the TDD coverage map, create evals for uncovered requirements:
   - Goldens for deterministic flows (routing, escalation, auth)
   - Sims for non-deterministic flows (KB-dependent troubleshooting)
   - Tool tests for each tool
   - Callback tests for each callback (sync code from platform, write tests)
   See `skills/build/SKILL.md` → "Generate Evals" for formats and guidelines.

5. **Run baseline** — push all evals (existing + new), run goldens + sims, generate combined report. This establishes the starting pass rate before any fixes.

6. **Start the iteration loop** — proceed to the loop below with the baseline results.

## The Iteration Loop

```
1. LOCAL SIM    → Fast pre-flight with scrapi-sim-runner (parallel, ~1 min)
2. PLATFORM     → Run goldens for official scoring
3. TRIAGE       → For each failure: read the transcript, identify what the agent did wrong
4. FIX          → Fix the agent (instruction or callback)
5. UPDATE EVALS → Sync callback code, add/update tests for any changed callbacks
6. COMBINED RPT → Run all 4 eval types, generate combined report (goldens + sims + tools + callbacks)
7. ITER REPORT  → Generate iteration debug report (changes + diffs + results)
8. TDD UPDATE   → Update tdd.md with any changes to agent behavior, evals, or coverage
9. RE-RUN       → Back to step 1
```

### Combined report (MANDATORY)

After every run, generate a combined report with ALL eval types — not just goldens/sims. Run tool tests and callback tests, save results, then:

```bash
python .agents/skills/agent-foundry/scripts/generate-combined-report.py \
  --golden-run <RUN_ID> --sim-results <SIM_JSON> \
  --tool-results eval-reports/tool_test_results.json \
  --callback-results eval-reports/callback_test_results.json \
  --golden-modality audio --sim-modality audio
```

This is in ADDITION to the iteration debug report. The combined report is the stakeholder-facing artifact; the iteration report documents what changed and why.

### Why this order matters
Local sims catch obvious issues in seconds. Platform golden runs take a few minutes — you don't want to waste that time on failures you could have caught locally.

### Recommended fix order
1. **Fix the agent first** — always assume the agent is wrong. Read the actual transcript, identify what the agent did wrong, and fix the instruction or callback.
2. **Move deterministic logic to callbacks** — if the behavior is a flag/variable check followed by a fixed response and tool calls (no LLM judgment needed), move the ENTIRE flow to a callback. Callbacks can call tools directly via the `tools` global (see gecx-design-guide.md "Calling tools from callbacks"). This eliminates LLM flakiness where the agent says the right text but forgets to call the tools.
3. **Make flaky behavior deterministic** — if the agent sometimes does the right thing and sometimes doesn't, use callbacks to enforce consistency. Instructions are suggestions; callbacks are guarantees.
4. **Only modify evals as a last resort** — after confirming the agent behavior is correct and the eval expectation is genuinely wrong (e.g., golden expects "remove cases" but the KB returns "restart phone" — both valid steps).

### Keeping Evals in Sync (MANDATORY)

Every agent change must be accompanied by eval updates. Evals that aren't kept in sync become stale and produce false results.

**After every callback change:**
1. **Sync the code** — download the callback from the platform and save to `evals/callback_tests/agents/{agent}/{callback_type}/{name}/python_code.py`
2. **Add or update tests** — write tests in `evals/callback_tests/tests/{agent}/{callback_type}/{name}/test.py` covering the new/changed behavior
3. **Symlink** — ensure the test is symlinked into the agents directory: `ln -sf $(pwd)/evals/callback_tests/tests/.../test.py agents/.../test.py`
4. **Run callback tests** — verify all pass before proceeding

**What to test for each callback type:**
- `before_agent_callback`: Test each early-return path (flag checks, auth status), verify tool calls made from the callback, verify correct Content/text returned, verify no side effects on unrelated paths
- `before_model_callback`: Test LLM interception conditions, verify the LlmResponse structure (text + tool calls), test the no-op path (returns None)
- `after_model_callback`: Test text injection when tools called without text, test no-op when text already present, test edge cases (whitespace-only text, multiple tool calls)

**After every instruction change:**
1. Check if any goldens reference the changed behavior — update expected agent text if needed
2. Check if any sims test the changed behavior — update task descriptions or expectations
3. Run the affected goldens + sims to verify

**After every golden/sim change:**
1. Push updated evals to the platform
2. Run to verify the change doesn't break other evals
3. Update the TDD coverage map

### Iteration Report (MANDATORY)

After **every** iteration, generate an HTML report to `eval-reports/debug_iteration_N_<timestamp>.html`. Do not skip this step — the report is how stakeholders track progress and how you avoid repeating mistakes.

Each iteration is a standalone file — not appended to a shared doc. This makes it easy to compare iterations side by side and share individual reports.

The iteration report should include these sections in order:

1. **Header** — iteration number, timestamp, target pass rate
2. **Summary** — before/after pass rates with delta, per-eval-type breakdown (goldens, sims, tool tests, callback tests)
3. **What changed** — high-level description of each agent or eval change and the rationale
4. **Exact diffs** — for each changed file, show the before/after with syntax-highlighted diffs. Capture diffs for: agent instructions (via SCRAPI), callback code, eval YAML, golden YAML, simulation YAML, tool test YAML, callback test.py, and TDD updates. Use `git diff` if the project is version-controlled, otherwise inline the before/after.
5. **Per-eval impact** — table showing which evals improved, regressed, or stayed the same, with the change that caused it
6. **Remaining failures** — grouped by root cause (agent instruction issue, callback bug, test data mismatch)
7. **Full eval results** — embed the combined report content (goldens, sims, tool tests, callback tests with transcripts, tool calls, session links)

Use the same light-theme styling as the combined report for consistency. The report is self-contained — someone reviewing it should understand what was done, why, and what the results look like without needing any other files.

### TDD Update (MANDATORY)

After **every** iteration, update `tdd.md` to reflect what changed. The TDD is the source of truth — if it doesn't match reality, it's stale and misleading. Specifically:

- **Agent instruction changes** → update the Agent Design section (routing logic, escalation rules, taskflow changes)
- **Callback changes** → update the callback descriptions and variable flow
- **New/changed evals** → update the Eval Design coverage map
- **Profile/data changes** → update the Test Data section
- **Pass rate changes** → update the Pass Rate History table
- **New known issues** → add to Known Issues section
- **Resolved issues** → remove from Known Issues, add to Pass Rate History with the fix description

Do not defer TDD updates to "later" — they accumulate and the TDD becomes useless. Update it in the same iteration where the change was made.

**Two places to update:**

1. **In-place** — Update the relevant section of the TDD (Agent Design, Eval Design, Test Data, etc.) so it reflects the current state. Someone reading the TDD should see what's true RIGHT NOW, not what was true when it was first written.

2. **Changelog at the bottom** — Append an entry to a `## Changelog` section at the bottom of the TDD. Each entry should include the date, iteration number, what changed, and why. This creates a running log so anyone can trace how the agent evolved over time.

```markdown
## Changelog

### Iteration 3 — 2026-04-05
- **Agent fix:** Added `after_model_callback` to troubleshoot_agent to inject farewell text before end_session. Agent was escalating silently.
- **Callback fix:** Added `return` after setting `authenticate_customer_api_failed_status=True` in before_agent_callback. Was causing KeyError fall-through.
- **Eval change:** Removed `transfer_to_agent` from golden_home_internet_escalation — root agent now handles home internet directly.
- **Pass rates:** Goldens 43/65 (66.2%), sims 7/7 (100%), tools 19/19 (100%), callbacks 46/46 (100%).
```

## Quick Start

```bash
# Fast local pre-flight
python .agents/skills/agent-foundry/scripts/scrapi-sim-runner.py run --priority P0 --parallel 5

# Platform goldens
python .agents/skills/agent-foundry/scripts/scrapi-eval-runner.py push-goldens
python .agents/skills/agent-foundry/scripts/scrapi-eval-runner.py run-goldens

# Platform scenarios (audio)
python .agents/skills/agent-foundry/scripts/scrapi-eval-runner.py run --priority P0 --channel audio --runs 5
python .agents/skills/agent-foundry/scripts/scrapi-eval-runner.py results <RUN_ID> --audio

# Combined report
python .agents/skills/agent-foundry/scripts/generate-combined-report.py \
  --golden-run <ID> --sim-results <JSON> --golden-modality audio --sim-modality audio
```

## Triage Guide

### Read the transcript for EVERY failure

**Never attribute a failure to "LLM flakiness" or "noise" without reading the actual transcript.** What looks like random 4/5 variance is often a specific, diagnosable agent issue:
- **Silent tool calls** — LLM splits text + tools across multiple model calls so text appears in one call and tools in another. Fix: use `after_model_callback` with `text_or_transcript()` and `events` API to detect prior text across model calls (see gecx-design-guide.md).
- **Missing tool calls** — LLM produces the right text but doesn't call the expected tools. Fix: use the trigger pattern — instruction tells LLM to set a state variable, `before_model_callback` intercepts and returns the tool calls deterministically. Add trigger recovery in `after_model_callback` to detect when the agent said the right text but forgot the state variable call.
- **Empty tool args** — LLM calls tools with `{}` args. Fix with defense in depth: (1) improve tool docstrings with `(REQUIRED)` markers and concrete examples so the LLM knows what values to provide, (2) add a state-based fallback in the tool's code to read from state when args are empty, (3) use the trigger pattern so the callback provides tools with correct args as a backup. Avoid using `hide_tool()` — it reduces the LLM's tool awareness and can cause worse overall instruction-following.
- **Wrong tool args** — LLM fills tool args with generic or incorrect values. Fix: derive correct values from conversation context in the callback (`events` API) instead of relying on the LLM to generate them.
- **Unexpected agent transfer** — LLM routes to a sub-agent alongside other tools, causing golden to fail on the unplanned transfer. Fix: handle the action entirely in `before_model_callback` to prevent the LLM from making routing decisions at the same time.
- **Multi-agent callback gap** — Callbacks on the root agent don't fire when the user's message goes to a sub-agent. Fix: add the same callback logic to ALL agents that handle user messages in the relevant flows.

Each of these has a concrete fix. Don't stop investigating at "it works 4/5 times."

### Fix the agent first, not the eval

**Always assume the agent is wrong until proven otherwise.** When a golden or sim fails, the default action is to fix the agent — not to loosen the eval. Evals represent the contract with the user. Changing an eval to make it pass means lowering the bar, not improving the product.

Only modify an eval when ALL of these are true:
1. You have verified the agent behavior is correct by reading the actual transcript
2. The failure is purely a phrasing mismatch where the agent's response meets the spirit of the requirement
3. You can explain exactly WHY the eval text doesn't match and WHY the agent's version is acceptable
4. The tool calls and routing are correct — only the text wording differs

If the agent skips a tool call, escalates without speaking, routes incorrectly, or gives the wrong information — that is ALWAYS an agent issue, never an eval issue.

### When to use goldens vs sims

| Use Goldens When | Use Sims When |
|-----------------|---------------|
| Agent flow is deterministic (routing, escalation, auth checks) | Agent uses a knowledge base that returns varying results |
| Tool calls are consistent and predictable | Troubleshooting steps vary by query |
| The conversation follows a fixed script (greeting → classify → route) | The conversation path depends on tool responses |
| Callbacks enforce the behavior (before_model, after_model) | The agent's phrasing naturally varies |
| You need to verify exact tool parameters | You need to verify behavioral goals (e.g., "agent escalates after 3 failures") |

**Rule of thumb:** If the agent's response comes from a callback (deterministic), use a golden. If it comes from the LLM interpreting a knowledge base response (non-deterministic), use a sim.

### Making agent behavior deterministic

When a golden keeps failing due to agent variance, the fix is to make the agent MORE deterministic — not to loosen the golden. Techniques from the GECX best practices:

1. **Use `after_model_callback` to enforce text before end_session** — the LLM often calls tools without saying anything first. **Important:** The LLM can split a turn across multiple model calls (text in call 1, tools in call 2, end_session in call 3). Use `callback_context.state` to track whether text was already produced — see gecx-design-guide.md "Multi-model-call turns" for the pattern. Without state tracking, the callback injects duplicate text.
2. **Use `before_model_callback` to intercept and return fixed responses** — for greetings, ETR messages, or any response that must be word-for-word consistent
3. **Inline tool calls in callbacks** instead of relying on instructions — callbacks execute deterministically, instructions don't
4. **Handle escalation flows in the root agent** — sub-agent responses cause role mismatches in golden evaluations
5. **Truncate goldens to the last deterministic turn** — don't test KB-dependent text or goodbye/end_session in goldens. End the golden at the last turn where the agent's response is predictable (e.g., after ETR delivery, not after goodbye). Test goodbye behavior with sims instead.

See `build/references/gecx-design-guide.md` → "Callback Patterns for Deterministic Behavior" for code examples.

### Instruction editing pitfalls

These are hard-won lessons from debugging agent instructions. Violating these will cause regressions.

**Never do wholesale instruction rewrites.** The LLM relies on the verbose context, examples, and phrasing in the instruction. A "cleaner" rewrite that looks better to a human often breaks the agent because the LLM loses context it was depending on. Instead, make small, targeted edits and test each one individually.

**Don't use `conditional_logic` for intent classification.** When you put profanity, unintelligible input, live agent requests, and connectivity issues into a single `conditional_logic` block, the LLM gets confused and falls back to generic refusals ("I'm unable to assist"). Keep them as separate `<step>` elements with distinct triggers — the LLM handles sequential steps better than priority-ordered conditionals.

**Don't add negative conditions to triggers.** A trigger like `Customer describes a connectivity issue that is NOT home internet` confuses the LLM — it sometimes treats ALL issues as needing a "home internet check" and gets stuck. Use positive triggers only: `Customer describes a connectivity issue (calls, internet, data, signal)`. Put the home internet check as a separate, earlier step.

**Keep the "Post-Answer Follow-up" simple.** A follow-up trigger like `After answering any question` fires too eagerly — including after sub-agent returns, causing the agent to say "Do you have any questions?" instead of resuming the flow. Use `Ask "Is there anything else I can help you with today?"` only when the conversation is clearly at a resolution point.

**Test after every change.** Run at least one golden batch after each instruction edit. Instruction changes can have non-obvious cascading effects — a fix for one golden can break three others. If a change causes regression, revert immediately and try a different approach.

**Simpler instructions are more reliable.** Adding complexity to instructions (state-tracked counting, multi-step conditional logic, explicit keyword requirements) often REDUCES reliability by confusing the LLM. A simple "On the FIRST attempt... On the SECOND attempt..." outperforms a complex "First call set_variables to increment count, then check count and branch." The LLM handles natural language instructions better than programmatic logic.

**Don't overfit the agent to pass evals.** If you find yourself adding hardcoded phrase lists to callbacks, requiring exact keywords in triggers, or bypassing the LLM for intent detection — you're overfitting. The agent might pass goldens but fail on real conversations. Signs of overfitting:
- Callbacks with hardcoded phrase lists (e.g., `["unacceptable", "ridiculous", "terrible"]`) for intent detection
- Dynamic instruction triggers requiring exact words (e.g., "If the customer EXPLICITLY said 'current line'")  
- Callbacks that bypass the LLM entirely for decisions the LLM should make (e.g., detecting frustration, classifying live agent requests)
- Golden pass rate goes up but sim pass rate or real-world behavior degrades

**The right separation: LLM detects, callbacks execute.** The LLM is good at understanding natural language intent — let it handle detection (profanity, frustration, live agent requests, issue classification). Callbacks should handle execution that must be deterministic (tool calls with correct args, session termination). The trigger pattern (`set_variables` → `before_model_callback` returns tools) achieves this separation.

**Callbacks vs instructions for escalation:** Use `after_model_callback` to guarantee text before `end_session`, and `before_model_callback` with the trigger pattern for deterministic tool calls. But keep all intent detection in the instruction — don't reimpliment it in callbacks with phrase matching.

**Don't include auxiliary tool calls in golden expectations.** Tool calls like `update_troubleshooting_slots` that run alongside routing calls (`transfer_to_agent`) should NOT be in the golden's `tool_calls` list. The LLM reorders these calls unpredictably — sometimes slot update runs before transfer, sometimes after. When it runs after, the platform marks the slot expectation as failed (outcome=2). Only include the CORE tool expectations (routing, escalation, outage check) that define the behavior being tested.

**Use `$matchType: "ignore"` for LLM-generated free-text parameters.** Fields like `escalation_reason`, `summary`, and `main_topic` in `update_ccaas_payload` are generated by the LLM and vary each run. The platform's semantic matching is flaky on these (rejects valid semantics like "customer_is_unhappy" vs "Customer unhappy with outage"). Use `ignore` unless you need to verify the exact content.

**Don't have duplicate YAML keys in a turn.** Having two `tool_calls:` blocks at the same level in a turn mapping is invalid YAML — the second overwrites the first. Combine all tool calls into a single `tool_calls:` list.

### Golden failures

Goldens compare expected vs actual turn-by-turn, so failures are specific and actionable.

| Symptom | Likely cause | Fix |
|---------|-------------|-----|
| Semantic similarity score low (1-2/4) | Agent phrasing differs from golden text | **Fix the agent** — make the response deterministic via callback, or tighten the instruction. Only loosen golden text after confirming agent behavior is correct. |
| Tool call mismatch (expected X, got Y) | Agent calls a different tool or different args | **Fix the agent** — this is always an agent issue. Check the instruction and callback logic. |
| Tool parameter mismatch | Agent passes different arg values | Use `$matchType` directives in the golden: `ignore` for varying fields like `summary`, `semantic` for meaning-based matching (value goes in `$originalValue`), `contains`/`regexp` for keyword/pattern checks |
| Agent escalates without text | LLM calls tools without speaking first | **Fix the agent** — add `after_model_callback` to inject text before end_session. This is an agent bug, not a platform limitation. |
| Wrong routing (expected agent A, got B) | Agent instruction routing logic is wrong | **Fix the agent** — check the routing conditional_logic and callback routing code. |
| Turn count mismatch | Agent takes more/fewer turns than golden | Check if agent is skipping steps or adding unnecessary turns. Fix the agent instruction. |
| Agent response comes from wrong sub-agent | Escalation/routing handled in sub-agent instead of root | **Fix the agent** — move the handling to the root agent so the response has the correct role. |

### Scenario failures

Scenarios are scored by goal satisfaction + LLM judges, so failures are less precise.

| Symptom | Likely cause | Fix |
|---------|-------------|-----|
| Goal judge says "task not completed" | Success criteria too narrow | Add "X counts as a successful outcome" to task description |
| Sim user goes off-script | Task instructions too vague | Add "You MUST cooperate fully. Do NOT bring up other topics." |
| Tool expectation fails silently (audio) | Platform audio bug | Remove `expect_tools`, use `expect_criteria` (LLM judges) instead |
| Runs out of turns | Complex flow exceeds `max_turns` | Increase `max_turns` — audio flows typically need 4-6 extra turns |
| Score flaky (3/5 one run, 5/5 next) | Could be sim user noise OR a real agent issue | Read the actual transcript for every failure. Common patterns: silent escalation (text in one model call, tools in another — fix with state-tracking callback), missing tool calls (instruction too vague — fix with specific args or callback). Don't assume flakiness without reading the transcript. |

### Tool test failures

| Symptom | Likely cause | Fix |
|---------|-------------|-----|
| Response path not found | Tool response schema changed | Update jsonpath in test expectation |
| Response value mismatch | Backend data or tool logic updated | Update expected value or verify change is intentional |
| Tool not found | Tool renamed or deleted | Update tool display name in test YAML |

### Callback test failures

| Symptom | Likely cause | Fix |
|---------|-------------|-----|
| Import error | Callback uses new dependencies | Update test imports |
| Assertion failed | Callback logic changed | Update test assertions to match new behavior |
| Mock mismatch | Real API response format changed | Update mock data in tests |

### Agent issues

Only investigate these after confirming eval configs are correct.

| Symptom | Likely cause | Fix |
|---------|-------------|-----|
| Agent skips expected step | Missing rule in taskflow | Add the step to the agent instruction's taskflow section |
| Agent escalates without saying anything | LLM calls end_session/tools without text | Add `after_model_callback` to inject text before end_session (see gecx-design-guide.md "Callback Patterns") |
| Agent behavior inconsistent despite instructions | LLM doesn't always follow instructions | Move critical behavior to callbacks (deterministic) instead of relying on instructions (non-deterministic) |
| Agent suggests wrong troubleshooting steps | Hallucination — not grounded in tool output | Add grounding constraint or check knowledge base tool config |
| Agent doesn't escalate when it should | Missing escalation trigger | Add escalation rule after N failed attempts |
| Agent reveals internal details | No privacy constraint | Add "Never reveal tool names, API details, or agent names" |

## Session Parameter Pitfalls

This is the most common source of mysterious regressions. The agent's callback typically derives several variables (auth status, user role, device type) from profile identifiers via API calls. If you override these variables directly, the callback sees them as already set, skips the API call, and breaks downstream logic.

**Rule:** Only override what the callback can't derive. Check the callback source code if unsure.

## Updating the TDD

When debugging leads to changes in evals or agent behavior, update `tdd.md` to keep it current:
- **Changed an eval type** (golden → scenario or vice versa) → update the eval design section
- **Added/removed evals** → update the coverage map
- **Fixed agent behavior** (patched instructions, added routing rule) → update the agent design section
- **Discovered a gap** (missing eval for a PRD requirement) → add it to the TDD first, then create the eval

The TDD should always reflect what's currently built and tested. If the TDD says "FR-1.1 is tested by golden_auth_api_failure" but that eval was deleted, the TDD is stale.

## Common Mistakes

1. **Deleting evals during active runs** — Causes the entire run to enter ERROR state. Always wait for COMPLETED.
2. **Using agent transcripts as goldens** — This tests that the agent does what it already does. Goldens should represent ideal PRD behavior.
3. **Dismissing 4/5 failures as noise** — Always read the transcript for every failure. What looks like "noise" is often a specific, diagnosable agent issue (silent escalation, missing tool calls, wrong escalation context). The fix might be a callback, a state variable, or a more specific instruction. Only attribute to sim user randomness after reading the transcript and confirming the agent behavior was actually correct.
4. **Using `yaml.dump()` on hand-written YAML** — Reformats the file, mangles long strings, loses comments. Use targeted edits instead.
5. **Forgetting `--audio` flag** — Audio results look like 0% without it due to the `taskCompleted` bug. Always use `--audio` for audio runs.
