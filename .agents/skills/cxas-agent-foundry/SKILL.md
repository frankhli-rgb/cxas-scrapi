---
name: cxas-agent-foundry
description: End-to-end GECX agent lifecycle — build agents from requirements, create and run evals, debug failures, and update evals when requirements change. TRIGGER this skill whenever the user mentions GECX, CXAS, conversational agents, voice agents, IVR replacement, or agent evals. Also trigger on "build me an agent", "create evals", "run evals", "run tool tests", "test callbacks", "debug failing evals", "get to 90%", "update evals", "generate a report", "push goldens", "run sims", "check pass rate", "fix the agent", "lint the agent", "inspect the app", PRD-to-agent workflows, or anything related to creating, testing, debugging, or improving a GECX conversational agent. Even if the user doesn't explicitly say "agent" — if they're working with CXAS apps, SCRAPI, agent instructions, callbacks, or eval YAML files, this skill applies.
user_invocable: true
---

# Agent Foundry

End-to-end lifecycle for GECX conversational agents: build, test, debug, iterate.

## Environment Readiness Check (run BEFORE routing)

Before routing to any sub-skill, check these signals in order:

1. **Virtualenv exists?** — Check if `.venv/` directory exists
2. **Config exists?** — Check if `.active-project` file exists and the referenced `<project>/gecx-config.json` exists
3. **Has built before?** — Check if any `<project>/cxas_app/` directory has content

| Signal | Action |
|--------|--------|
| No `.venv/` | **First-time user.** Start the Onboarding Flow below before doing anything else. |
| `.venv/` exists but no `gecx-config.json` | Ask the user for project details (see Configuration below). Then proceed to routing. |
| `gecx-config.json` exists but no `cxas_app/` content | Returning user, new project. Route normally. |
| All exist | Returning user. Route normally. |

## Onboarding Flow (first-time users only)

When the readiness check identifies a first-time user (no `.venv/`):

1. **Create virtualenv and install dependencies:**
   ```bash
   python3 -m venv .venv
   source .venv/bin/activate
   ```
   Then find `cxas-scrapi` source (look for `setup.py` containing `cxas-scrapi` in parent directories or siblings) and install:
   ```bash
   pip install -e <path_to_cxas_scrapi> --quiet
   ```
2. **Collect project details** — see Configuration below.
3. Confirm with the user: "Your environment is set up. You're connected to **[app_name]** on **[project_id]**."
4. If the user's original request was "build me an agent" → proceed to the build sub-skill. If they connected to an existing app → ask: "Do you want to create evals for this existing agent, or build something new?" Otherwise → proceed with their original request.

## Configuration

Only 3 pieces of information are needed. Ask for them **one at a time** — don't batch all questions into a single message. Start with whichever the user hasn't provided yet, wait for the answer, then ask the next. If the user provides multiple details upfront (e.g., "project is foo, voice agent"), skip the questions they already answered.

1. **GCP Project ID** — which GCP project to use
2. **App name** — display name for the agent app (also used as app ID)
3. **Modality** — `audio` (voice agent) or `text` (chat agent)

Everything else is derived:
- **Location**: defaults to `us`
- **Model**: `gemini-3.1-flash-live` for audio, `gemini-3-flash` for text
- **deployed_app_id**: `null` for new apps (set after first push)

Once you have all 3, write `<project_name>/gecx-config.json` inside the project folder (NOT at the repo root):
```json
{
  "gcp_project_id": "<project>",
  "location": "us",
  "app_name": "<app_name>",
  "deployed_app_id": null,
  "app_dir": "cxas_app/",
  "model": "<model_based_on_modality>",
  "modality": "<audio_or_text>",
  "default_channel": "<audio_or_text>"
}
```

If the user provides these details upfront (e.g., "build me an agent, project is foo, app name is bar, voice agent"), skip asking and write the config immediately.

## Detect Intent and Route

Read what the user wants and load the appropriate sub-skill:

| User says... | Phase | Load |
|-------------|-------|------|
| "Build me an agent from this PRD" | Build | `skills/build/SKILL.md` |
| "Create evals for my agent" | Build | `skills/build/SKILL.md` |
| "Generate tool tests", "create callback tests" | Build | `skills/build/SKILL.md` |
| "Update evals — requirements changed" | Build | `skills/build/SKILL.md` |
| "Update the TDD" | Build | `skills/build/SKILL.md` |
| "Run evals", "push evals", "check results" | Run | `skills/run/SKILL.md` |
| "Run tool tests", "test the callbacks" | Run | `skills/run/SKILL.md` |
| "Generate a report" | Run | `skills/run/SKILL.md` |
| "Why is this eval failing", "get to 90%" | Debug | `skills/debug/SKILL.md` |
| "Fix the failing evals", "debug the agent" | Debug | `skills/debug/SKILL.md` |
| "Tool test is failing", "callback test broke" | Debug | `skills/debug/SKILL.md` |

If the intent is unclear, ask: "Are you looking to **build/create** evals, **run** them, or **debug** failures?"

## Sub-Skills

### Build (`skills/build/SKILL.md`)
PRD/requirements → agent + evals. Three entry points:
- **Full build** — write TDD from requirements (user approves), then create app + evals
- **Eval creation** — inspect existing app, write/update TDD, generate evals
- **Eval update** — diff changed requirements against TDD, update TDD, then update evals

### Run (`skills/run/SKILL.md`)
Push, run, score, and report across four eval types:
- **Platform goldens** — deterministic turn-by-turn tests
- **Local simulations** — fast parallel open-ended testing via SCRAPI Sessions API
- **Tool tests** — isolated tool input/output validation via `ToolEvals`
- **Callback tests** — pytest against agent callbacks via `CallbackEvals`

### Debug (`skills/debug/SKILL.md`)
Triage failures, fix eval configs or agent instructions, iterate to target pass rate.

## Shared Resources

**Scripts** — all in `.agents/skills/cxas-agent-foundry/scripts/`:

| Script | Purpose |
|--------|---------|
| `run-all-evals.py` | Runs all 4 eval types + generates combined report |
| `triage-results.py` | Categorizes golden failures for fast debugging |
| `sync-callbacks.py` | Pulls callback code from platform to local test dirs |
| `scrapi-eval-runner.py` | Platform goldens: `push-goldens`, `run-goldens`, `results` |
| `scrapi-sim-runner.py` | Local sims: `run [--parallel N] [--channel audio]` |
| `inspect-app.py` | Dump agent architecture, tools, callbacks, existing evals |
| `app-thresholds.py` | View/update golden scoring thresholds |
| `generate-iteration-report.py` | Snapshot agent state + generate iteration diff report |
| `run-and-report.py` | Single-command iteration step: snapshot + evals + triage + report |
| `generate-combined-report.py` | Combined HTML report |
| `configure.py` | Interactive project configuration (legacy — agent writes `gecx-config.json` directly now) |
| `lint.py` | Lint agent instructions + callbacks for common issues |
| `capture-golden-transcripts.py` | Capture live agent transcripts for reference |

**Eval files** — in `<project>/evals/` (relative to the active project folder, e.g., `tmobile/evals/`):

```
<project>/evals/
├── goldens/*.yaml                # Platform golden evals (ideal conversations)
├── simulations/simulations.yaml  # Local sim eval definitions
├── tool_tests/*.yaml             # Tool test definitions
└── callback_tests/               # Callback code + test assertions
```

**Session parameters** — Only override variables the agent's `before_agent_callback` cannot derive from profile identifiers. If the callback early-returns when a variable is already set, overriding it short-circuits the entire API flow. Check the callback source code when unsure.

## Quick Reference

```bash
# Run everything + generate combined report
python .agents/skills/cxas-agent-foundry/scripts/run-all-evals.py --channel audio --runs 5

# Triage failures
python .agents/skills/cxas-agent-foundry/scripts/triage-results.py

# Sync callbacks from platform
python .agents/skills/cxas-agent-foundry/scripts/sync-callbacks.py

# Individual commands (when you need finer control)
python .agents/skills/cxas-agent-foundry/scripts/scrapi-eval-runner.py push-goldens
python .agents/skills/cxas-agent-foundry/scripts/scrapi-eval-runner.py run-goldens --channel audio --runs 5
python .agents/skills/cxas-agent-foundry/scripts/scrapi-sim-runner.py run --priority P0 --parallel 5 --channel audio
```

## Before Starting

Check memory for project-specific context (app ID, variable handling rules, audio scoring workarounds). If not available, ask the user.

