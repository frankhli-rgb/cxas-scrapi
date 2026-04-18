# Eval Debugger

Methodology for systematically debugging eval failures and improving agent behavior.

## Table of Contents

- [References](#references)
- [Before Starting](#before-starting)
- [The Iteration Loop](#the-iteration-loop)
- [Quick Start](#quick-start)
- [Triage Guide](#triage-guide)
- [Common Mistakes](#common-mistakes)

## Step Tracking Reminder

**CRITICAL:** Remember to initialize your `todo.md` checklist for this debug session with the following steps: Check Prerequisites, Triage Failures, Fix Agent, Re-run Evals, Generate Report.

## References

- `references/debugging-agent.md` — Test sessions, inspect conversations, execute tools, view traces and changelogs
- `references/improving-agent.md` — Analyze eval failures, optimize instructions, iterate on behavior
- `gecx-design-guide.md` — Instruction design, callback patterns, anti-patterns table (consult when fixing agent behavior)
- `api-schemas/evaluations.md` — Eval schemas, threshold field names, scoring enum values (consult when investigating threshold/scoring issues)

## Before Starting

### Check prerequisites

Check `<project>/gecx-config.json` first for project configuration (where `<project>` is the active project folder from `.active-project`, e.g., `tmobile/`). If not present, check memory or ask the user.

| Prerequisite | Check | If missing |
|-------------|-------|------------|
| **Environment** | `.venv/` exists, `cxas-scrapi` installed | Follow Onboarding Flow in top-level SKILL.md |
| **App name** | `<project>/gecx-config.json` → `deployed_app_id` | Ask the user |
| **TDD** | `<project>/tdd.md` | Generate one — see "Bootstrap" below |
| **Goldens** | `<project>/evals/goldens/*.yaml` | Generate from TDD — see `skills/build/SKILL.md` |
| **Sims** | `<project>/evals/simulations/simulations.yaml` | Generate from TDD — see `skills/build/SKILL.md` |
| **Tool tests** | `<project>/evals/tool_tests/*.yaml` | Generate using `ToolEvals.generate_tool_tests()` |
| **Callback tests** | `<project>/evals/callback_tests/agents/` | Sync from platform and write tests |
| **Target pass rate** | Ask the user | e.g., 90%, 100% |
| **Channel** | Ask the user | text or audio |

### Bootstrap from existing agent

When the user has an agent but no TDD or evals:

1. **Inspect the agent** — pull architecture, tools, variables, callbacks, instructions via SCRAPI (see `skills/build/SKILL.md` → "Inspect App")
2. **Pull existing evals** — check the platform for evals already on the agent. Present each to the user for priority/severity assignment. Existing evals represent institutional knowledge — don't discard them.
3. **Generate the TDD** — from the inspection AND existing evals, write `tdd.md`. Ask the user to review before proceeding.
4. **Fill eval gaps** — from the TDD coverage map, create evals for uncovered requirements (see `skills/build/SKILL.md` → "Generate Evals")
5. **Run baseline** — push all evals, run goldens + sims, generate combined report
6. **Start the iteration loop**

## The Iteration Loop

**Note:** All paths below are relative to the active project folder (resolved from `.active-project`).

```
1. FIX          → Fix the agent, then run `cxas lint` to catch issues early
2. RUN-AND-REPORT → python run-and-report.py --message "what changed" --auto-revert
3. RE-RUN       → Back to step 1
```

The `run-and-report.py` script combines snapshot + run-all-evals + triage + iteration-report into one command. Use `--auto-revert` to automatically revert `cxas_app/` on real regressions.

**Auto-revert conditions — ALL must be true to revert:**
1. Golden pass rate dropped from previous iteration
2. Failures are real agent issues (TOOL_MISSING, TEXT_MISMATCH, EXPECTATION_FAIL), not platform issues (timeouts, SCORES_PASS_BUT_FAIL)
3. Sims did NOT improve (if goldens regressed but sims improved, it's a mixed signal — investigate instead of reverting, the golden expectation may need updating)

Before proposing fixes, check `<project>/experiment_log.md` for what was already tried — avoid repeating approaches that caused regressions.


**After instruction changes:** check if goldens/sims reference the changed behavior — update expected text or tasks if needed.

### Syncing local and platform

When local `cxas_app/` and the platform diverge (e.g., someone edited on the platform UI while you edited locally):

1. **Pull** platform state into your local `cxas_app/` (or a temp dir to diff first)
2. **Merge** any conflicting changes — reconcile, don't overwrite
3. **Push** the merged version back to the platform

### Iteration report

Use `generate-iteration-report.py` for iteration reports:

```bash
python .agents/skills/cxas-agent-foundry/scripts/generate-iteration-report.py report --message "Fixed X by doing Y"
```

This snapshots `<project>/cxas_app/`, diffs against the previous iteration's snapshot, fetches eval results, and generates an HTML report to `<project>/eval-reports/iterations/`.


## Quick Start

```bash
# Single-command iteration step: snapshot + evals + triage + report (recommended)
python .agents/skills/cxas-agent-foundry/scripts/run-and-report.py --message "what changed" --channel audio --runs 5 --auto-revert

# Run ALL evals + generate combined report
python .agents/skills/cxas-agent-foundry/scripts/run-all-evals.py --channel audio --runs 5

# Triage failures from the latest run
python .agents/skills/cxas-agent-foundry/scripts/triage-results.py
python .agents/skills/cxas-agent-foundry/scripts/triage-results.py --last 3  # average across runs

# Sync callback code from platform to local tests
python .agents/skills/cxas-agent-foundry/scripts/sync-callbacks.py

# Individual eval commands (when you need finer control)
python .agents/skills/cxas-agent-foundry/scripts/scrapi-sim-runner.py run --priority P0 --parallel 5
python .agents/skills/cxas-agent-foundry/scripts/scrapi-eval-runner.py push-goldens
python .agents/skills/cxas-agent-foundry/scripts/scrapi-eval-runner.py run-goldens --channel audio --runs 5
python .agents/skills/cxas-agent-foundry/scripts/scrapi-eval-runner.py results <RUN_ID> --audio
```

## Triage Guide

### Don't trust a single run

A golden that passes 1/1 may fail 2/5. Run goldens at least 5 times (`--runs 5`) and use `triage-results.py --last 3` to see the real pass rate across runs. Only consider a golden stable when it passes consistently across multiple runs.

### Read the transcript for EVERY failure

**Read the transcript before attributing any failure to "LLM flakiness"** — most failures have a diagnosable root cause. Common diagnosable patterns:

| Pattern | What you see | Root cause | Fix |
|---------|-------------|------------|-----|
| Silent tool calls | Text in one model call, tools in another | Multi-model-call turn splitting | `after_model_callback` with `text_or_transcript()` + `events` API |
| Missing tool calls | Right text, no tools | LLM forgot tool call | Trigger pattern: instruction sets state variable, callback returns tools |
| Missing tool (variant) | LLM improvises with other tools | Tool not in agent's tool list | Add the tool to the agent — verify tool availability! |
| Empty tool args | Tool called with `{}` | LLM doesn't know required args | Better docstrings with `(REQUIRED)` + state-based fallback in tool code |
| Unexpected transfer | Extra agent transfer alongside tools | LLM routes + acts simultaneously | Handle action entirely in `before_model_callback` |
| Callback gap | Behavior works on root but not sub-agent | Root callbacks don't fire on sub-agents | Add callback to every agent in the flow |

### Fixing: agent first, eval last

**CRITICAL PLAN MODE ENFORCEMENT:** If fixing an evaluation failure requires a cross-cutting architectural change (e.g., adding a new agent, modifying `before_agent` state derivation, or changing multi-agent routing), you MUST use Plan mode to propose the structural fix before making file changes. Simple prompt tweaks in `instruction.txt` do not require Plan Mode.

**Start by assuming the agent is wrong** — eval expectations represent the contract with the user. Only modify an eval when:
1. You've read the transcript and verified agent behavior is correct
2. The failure is purely a phrasing mismatch
3. Tool calls and routing are correct — only text wording differs

### Recommended fix approach

The core principle: **LLM detects, callbacks execute.**

The LLM understands natural language intent — let it handle detection (hostility, frustration, transfer requests, issue classification). Callbacks handle execution that must be deterministic (tool calls with correct args, session termination).

When behavior is flaky:
1. **Check tool availability first** — if the instruction references a tool the agent can't access, the LLM silently improvises. This is the most common and hardest-to-diagnose issue.
2. **Fix the instruction** — make triggers clearer, remove conflicting constraints, add priority ordering. See `gecx-design-guide.md` → "Instruction Design Anti-Patterns".
3. **Use the trigger pattern** — for actions that must be deterministic (escalation, session termination), have the instruction tell the LLM to set a state variable, then have the callback intercept and execute. See `gecx-design-guide.md` → "Trigger pattern for deterministic tool calls".
4. **Use `after_model_callback`** — to guarantee text before `end_session`, or to recover when the LLM forgets the state-setting call.

**Don't overfit.** If you find yourself adding hardcoded phrase lists to callbacks, requiring exact keywords in triggers, or bypassing the LLM for intent detection — stop. The agent might pass goldens but fail on real conversations. Signs: golden pass rate goes up but sim pass rate degrades.

### Golden failures

| Symptom | Triage Category | Likely cause | Fix |
|---------|----------------|-------------|-----|
| Low semantic similarity (1-2) | TEXT_MISMATCH | Agent phrasing differs | Fix the agent — make response deterministic via callback, or tighten instruction |
| Tool call mismatch | TOOL_MISSING | Wrong tool or args | Fix the agent — check instruction and callback logic |
| Tool parameter mismatch | TOOL_MISSING | Varying arg values | Use `$matchType` in golden: `ignore` for free-text fields, `semantic` for meaning-based |
| Custom expectation not met | EXPECTATION_FAIL | Expectation ambiguous or agent doesn't meet it | Read the judge's explanation — fix the agent or rephrase the expectation |
| All turns pass but FAIL | EXTRA_TURNS | Agent transfers to sub-agent after golden ends | End golden before transfer, or extend to cover sub-agent. NOT an agent bug. |
| All scores pass but FAIL | SCORES_PASS_BUT_FAIL | Platform hallucination scorer bug | Not fixable — platform issue. Ignore in adjusted pass rate. |
| Wrong routing | — | Routing logic error | Fix instruction conditional_logic or callback routing |
| Turn count mismatch | — | Agent skips/adds steps | Fix instruction taskflow |

### Tuning app-level scoring thresholds

When goldens fail despite correct agent behavior, the scoring may be too strict. Use `app-thresholds.py` to view and adjust:

```bash
python .agents/skills/cxas-agent-foundry/scripts/app-thresholds.py show
python .agents/skills/cxas-agent-foundry/scripts/app-thresholds.py set --similarity 2      # lower text matching (1-4)
python .agents/skills/cxas-agent-foundry/scripts/app-thresholds.py set --extra-tools allow  # allow extra tool calls
python .agents/skills/cxas-agent-foundry/scripts/app-thresholds.py set --hallucination disabled
```

Tune thresholds after confirming the agent behavior is correct (read transcripts) — not as a substitute for fixing the agent.

### Scenario failures

| Symptom | Likely cause | Fix |
|---------|-------------|-----|
| "Task not completed" | Success criteria too narrow | Add "X counts as a successful outcome" to task |
| Sim user goes off-script | Task instructions too vague | Add "You MUST cooperate fully" |
| Tool expectation fails (audio) | Platform audio bug | Use `expect_criteria` (LLM judges) instead of `expect_tools` |
| Runs out of turns | Flow exceeds `max_turns` | Increase `max_turns` — audio needs 4-6 extra |

### Session parameter pitfalls

See the router skill for the full rule. Only override variables the callback can't derive — overriding derived variables skips API calls and breaks downstream logic.

## Common Mistakes

1. **Deleting evals during active runs** — causes ERROR state. Wait for COMPLETED.
2. **Using agent transcripts as goldens** — tests that the agent does what it already does. Goldens should represent ideal PRD behavior.
3. **Using `yaml.dump()` on hand-written YAML** — reformats, mangles strings, loses comments. Use targeted edits.
4. **Forgetting `--audio` flag for scenarios** — audio results show 0% without it. For goldens, use `evaluation_status` directly.
5. **Not checking tool availability** — if the instruction references a tool not in the agent's tool list, the LLM silently improvises. Verify tool availability first — this is the most common and hardest-to-diagnose issue.
6. **Truncating goldens via `update_evaluation()`** — the API merges turns, it doesn't replace them. Removing a turn from the YAML and pushing won't delete it on the platform. To shorten a golden, delete the eval and recreate it.
7. **All scores pass but eval still fails** — the platform's hallucination scorer can non-deterministically mark results as FAIL even when semantic similarity and tool outcomes all pass, and even when hallucination is set to DISABLED. Use `triage-results.py` to identify these (`SCORES_PASS_BUT_FAIL` category). If most failures in an eval are this category, the agent behavior is correct — it's a platform inconsistency.
8. **Extra turns after golden ends** (`EXTRA_TURNS`) — all expected turns pass, but the agent produces additional output (e.g., transfers to a sub-agent, sub-agent responds) that the golden doesn't cover. The agent behavior is correct — the golden is incomplete. Fix by either ending the golden before the transfer or extending it to cover the sub-agent response. Common in multi-agent flows where goldens test auth but the agent continues to route.
9. **Custom expectation fails** (`EXPECTATION_FAIL`) — an LLM-judged expectation from the golden YAML was marked as not met. Read the judge's explanation in the triage output. Common causes: expectation is ambiguous, golden doesn't cover enough turns for the judge to evaluate, or the agent genuinely doesn't meet the expectation.
8. **Conflicting constraints in instructions** — if a guideline says "gently redirect inappropriate questions" and a taskflow step says "escalate hostile language immediately," the LLM may follow the guideline (redirect) instead of the step (escalate). Audit constraints and guidelines for conflicts with escalation/routing steps.
9. **Pushing without resolving drift** — if the platform has changes not in your local files, pushing will overwrite them. Always pull and merge before pushing when both sides have been edited.
