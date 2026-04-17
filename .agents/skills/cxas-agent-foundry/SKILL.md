---
name: cxas-agent-foundry
description: End-to-end GECX agent lifecycle — build agents from requirements, create and run evals, debug failures, and update evals when requirements change. TRIGGER this skill whenever the user mentions GECX, CXAS, conversational agents, voice agents, IVR replacement, or agent evals. Also trigger on "build me an agent", "create evals", "run evals", "run tool tests", "test callbacks", "debug failing evals", "get to 90%", "update evals", "generate a report", "push goldens", "run sims", "check pass rate", "fix the agent", "lint the agent", "inspect the app", PRD-to-agent workflows, or anything related to creating, testing, debugging, or improving a GECX conversational agent. Even if the user doesn't explicitly say "agent" — if they're working with CXAS apps, SCRAPI, agent instructions, callbacks, or eval YAML files, this skill applies.
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
| "Build me an agent from this PRD" | Build | `references/build.md` |
| "Create evals for my agent" | Build | `references/build.md` |
| "Generate tool tests", "create callback tests" | Build | `references/build.md` |
| "Update evals — requirements changed" | Build | `references/build.md` |
| "Update the TDD" | Build | `references/build.md` |
| "Run evals", "push evals", "check results" | Run | `references/run.md` |
| "Run tool tests", "test the callbacks" | Run | `references/run.md` |
| "Generate a report" | Run | `references/run.md` |
| "Why is this eval failing", "get to 90%" | Debug | `references/debug.md` |
| "Fix the failing evals", "debug the agent" | Debug | `references/debug.md` |
| "Tool test is failing", "callback test broke" | Debug | `references/debug.md` |

If the intent is unclear, ask: "Are you looking to **build/create** evals, **run** them, or **debug** failures?"



## Development Workflow

Agent development uses a **hybrid approach** — local files in git for version control, with SCRAPI for running evals and platform operations.

Each agent is managed within a dedicated `<project>` workspace folder containing:
- **`gecx-config.json`** — Centralized config (project ID, app ID, location, modality).
- **`cxas_app/`** — Local agent code (instructions, callbacks, tools). The canonical source for agent definitions.
- **`tdd.md`** — Technical Design Document (the source of truth for architecture).
- **`evals/`** — Test definitions (goldens, simulations, tool tests, callback tests).
- **`eval-reports/`** — HTML reports generated after running evals, including historical snapshots in `iterations/`.
- **`experiment_log.md`** — Tracks iterations, what was tried, and pass rate progression over time.

- **SCRAPI** is used for running evals, testing sessions, inspecting state, and rapid prototyping.

The core principle: **create and edit locally, push to platform**.

## Key Conventions

- **TDD is the source of truth.** The Technical Design Document (`<project>/tdd.md`) defines agent architecture and eval coverage. Evals follow the TDD, not the agent's current behavior. Update the TDD first, then update evals to match.
- **Four eval types:** goldens, simulations, tool tests, callback tests.
- **Audio scoring:** For **goldens**, use `evaluation_status` directly. For **sims**, the sim runner handles audio scoring automatically.
- **Session variables:** Only override what the agent's `before_agent_callback` can't derive. Never override `auth_status` or `user_role`.
- **Fix the agent first.** When evals fail, assume the agent is wrong. Only modify evals as a last resort after confirming agent behavior is correct.
- **Every agent change needs eval updates.** Callback changes require syncing code + adding/updating tests. Instruction changes require checking affected goldens/sims.
- **Combined report after every run.** Always generate a combined report with all 4 eval types using `generate-combined-report.py`.
- **YAML formatting:** Hand-write YAML instead of using `yaml.dump()` to avoid reformatting.

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
| `cxas lint` | Lint agent instructions, callbacks, tools, evals, and configs (installed via cxas-scrapi) |
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

