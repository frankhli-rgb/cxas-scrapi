---
name: cxas-agent-foundry
description: End-to-end GECX/CXAS/CES conversational agent lifecycle -- build agents from requirements (PRD-to-agent), create and run evals (goldens, simulations, tool tests, callback tests), debug failures, and iterate to production quality. Use this skill whenever the user mentions GECX, CXAS, CES, SCRAPI, conversational agents, voice agents, audio agents, agent evals, pushing/pulling/linting agents, or agent instructions/callbacks/tools on the Google Customer Engagement Suite platform.
---

# Agent Foundry

End-to-end lifecycle for GECX conversational agents: build, test, debug, iterate.

## Step tracking — MANDATORY (Phase 0, blocking)

**Before doing ANY work — including running setup, asking questions, or scaffolding files — initialize `<project>/todo.md` from the relevant sub-skill's checklist (verbatim).** Note that these checklists are defined as inline templates inside the sub-skill reference files (e.g., `references/build.md` contains the 'Build Steps (todo.md template)' checklist, and `references/run.md` and `references/debug.md` contain their respective checklists). Locate these sections in the appropriate reference doc first to copy the verbatim checklist. The checklist is a contract, not a suggestion. If `todo.md` doesn't exist for the current task, refuse to proceed and create it first.

Long debug/build runs skip verification steps under pressure (e.g., pushing without linting, scaffolding without a TDD, claiming "deployed" without actually pushing). The checklist exists because of this. **The instinct to skip a step is the moment the checklist earns its keep — that's when you must consult it, not the moment to bypass it.**


## Quick Reference

```bash
# Lint: dispatch agents/lint-fixer.md sub-agent — DO NOT run `cxas lint` on the main thread.
# Lint output is verbose; keep it inside the sub-agent context.

# Push local files to platform (only after lint-fixer returns status: clean)
# Note: Use the full cloud resource path projects/<project_id>/locations/<location>/apps/<app_id> for the --to target.
cxas push --app-dir <project>/cxas_app/<AppName> \
  --to projects/<project_id>/locations/<location>/apps/<app_id> \
  --project-id <project_id> --location <location>

# Pull platform state to local
cxas pull projects/<project_id>/locations/<location>/apps/<app_id> \
  --project-id <project_id> --location <location> --target-dir <project>/cxas_app/

# Create a new CXAS Application in the cloud
cxas create "<App Display Name>" \
  --project-id <project_id> \
  --location <location> \
  --description "<App Description>"

# Start a sequential text test session (non-interactive pipe)
echo "<Your query here>" | cxas run-session text "projects/<project_id>/locations/<location>/apps/<app_id>"

# Start an interactive text session (exit with /exit)
cxas run-session text "projects/<project_id>/locations/<location>/apps/<app_id>"

# List all applications deployed under the active project
cxas apps list --project-id <project_id> --location <location>

# Retrieve configuration state of a single deployed application
cxas apps get "projects/<project_id>/locations/<location>/apps/<app_id>" --project-id <project_id> --location <location>

# Run evals + triage + report (single command)
python .agents/skills/cxas-agent-foundry/scripts/run-and-report.py --message "what changed" --runs 5

# Inspect app architecture
python .agents/skills/cxas-agent-foundry/scripts/inspect-app.py

# Triage failures
python .agents/skills/cxas-agent-foundry/scripts/triage-results.py --last 3

# Run all 6 build-verification gates against the deployed app
python .agents/skills/cxas-agent-foundry/scripts/gate-check.py

# Tune scoring thresholds (similarity, hallucination, extra-tools)
python .agents/skills/cxas-agent-foundry/scripts/app-thresholds.py show

# Sync callback Python code into evals/callback_tests/agents/ + create test.py symlinks.
# Required for tests to be discoverable by test_all_callbacks_in_app_dir.
python .agents/skills/cxas-agent-foundry/scripts/sync-callbacks.py                  # post-push: pull from platform
python .agents/skills/cxas-agent-foundry/scripts/sync-callbacks.py --from-local <app_dir>  # pre-push: copy from local app dir

# Cold-start setup (first-time only — venv + project bootstrap)
.agents/skills/cxas-agent-foundry/scripts/setup.sh
python .agents/skills/cxas-agent-foundry/scripts/setup-project.py
```

**Disambiguation:** `gate-check.py` and `inspect-app.py` overlap on "show me the architecture" but `gate-check.py` is the answer whenever the user is about to push, finished building, or wants a verification pass. `inspect-app.py` is for a quick "what's in here" look without the verification gates. When in doubt, use `gate-check.py`.

## Sub-agents

For heavy diagnosis/analysis work that would otherwise burn main-thread context, dispatch one of these sub-agents via the `Agent` tool. Pass the contents of the relevant `.md` file as the prompt, then add the inputs the file lists.

| Sub-agent | Reasoning intensity | When to use |
|---|---|---|
| `agents/triage-failure.md` | HIGH | Diagnose ONE failing eval. Fan out for the top 5 failures by category priority in parallel. Iterate on more after the first batch returns. |
| `agents/tdd-writer.md` | HIGH | Reverse-engineer a TDD from an existing agent OR draft from PRD. Returns the TDD + open-questions handoff; main thread runs the show/ask/iterate loop with the user (sub-agents can't ask). |
| `agents/scaffolder.md` | MEDIUM | Bulk-generate all agent code (agent JSONs, instruction.txt, tool python_code, callbacks, app.json) from an APPROVED TDD. One dispatch replaces 30-60 main-thread file writes. |
| `agents/coverage-analyst.md` | MEDIUM | Generate a full eval coverage report against an agent's architecture. |
| `agents/eval-writer.md` | MEDIUM | Generate evals for one entire eval TYPE (all goldens, all sims, etc.) — reads TDD's Coverage Map itself. Max 4 dispatches per build. |
| `agents/lint-fixer.md` | LOW (mechanical) | Run `cxas lint` and mechanically fix all errors + deterministic warnings until clean. Never run lint on main thread. |

For running evals: there is no sub-agent. Use `scripts/run-and-report.py --json-summary <path> > /dev/null 2>&1` and read the summary file — see `references/debug.md` → "Quick Start". The work was deterministic, so it lives in the script.

**Reasoning intensity** is a hint to the runtime: HIGH sub-agents benefit from more thinking budget / a stronger model, LOW sub-agents are recipe-driven and don't. Each sub-agent file repeats this hint at the top with a one-line justification.

## Environment Readiness Check (run BEFORE routing)

Before routing to any sub-skill, check these signals in order:

1. **Virtualenv exists?** -- Check if `.venv/` directory exists
2. **Config exists?** -- Check if `.active-project` file exists and the referenced `<project>/gecx-config.json` exists
3. **Has built before?** -- Check if any `<project>/cxas_app/` directory has content

| Signal | Action |
|--------|--------|
| No `.venv/` or no config | **First-time setup needed.** Load `references/setup.md` before doing anything else. |
| `gecx-config.json` exists but no `cxas_app/` content | Returning user, new project. Route normally. |
| All exist | Returning user. Route normally. |

## Detect Intent and Route

Read what the user wants and load the appropriate sub-skill:

| User says... | Phase | Load |
|-------------|-------|------|
| "Build me an agent from this PRD" | Build | `references/build.md` |
| **"Create a new cxas app", "Make a new agent", "Set up an agent", "I wanna build an agent"** | **Build** | **`references/build.md`** |
| "Create evals for my agent" | Build | `references/build.md` |
| "Generate tool tests", "create callback tests" | Build | `references/build.md` |
| "Update evals -- requirements changed" | Build | `references/build.md` |
| "Update the TDD" | Build | `references/build.md` |
| "Run evals", "push evals", "check results" | Run | `references/run.md` |
| "Run tool tests", "test the callbacks" | Run | `references/run.md` |
| "Generate a report" | Run | `references/run.md` |
| "Why is this eval failing", "get to 90%" | Debug | `references/debug.md` |
| "Fix the failing evals", "debug the agent" | Debug | `references/debug.md` |
| "Tool test is failing", "callback test broke" | Debug | `references/debug.md` |
| **"Edit the agent's instructions", "tweak the auth tool", "fix the greeting", "update this callback"** | **Build** (Edit cycle) | **`references/build.md` → "Editing an Existing Agent"** |

**Any phrasing that implies creating, building, or setting up an agent/app routes to `references/build.md` — even if it sounds like "just create the app shell."** "Create a new cxas app" is NOT a shortcut to scaffolding; it triggers the full build flow (todo.md → interview/PRD → TDD + approval → scaffold → lint → evals → push). Skipping the interview / TDD because the user said "create" instead of "build" is a routing failure.

**Editing an existing agent** (instruction tweak, tool change, callback fix) routes to build.md's "Editing an Existing Agent" section — the standard pull → edit → lint → push → run-evals cycle. Don't skip lint or the eval run after — silent regressions are how 90% rates drop to 70%.

**Hybrid Case (Local-Only Scaffold):** If you discover that a local agent configuration directory (containing `app.json`, `agents/`, etc.) already exists in your CWD workspace, but the app has NEVER been pushed or registered on the GECX cloud server (meaning it has no deployed cloud App ID yet):
- Do **NOT** use the 'Existing App (pull first)' checklist, as you cannot run `cxas pull` without a server resource!
- Instead, treat this as a 'Full Build (Post-Scaffold)' phase:
  1. Initialize the project configuration with a new app using `configure.py --create-app` (or pass the `--create-app` flags in setup tools) to dynamically register a fresh app slot and receive a server UUID.
  2. Map the new server UUID into your local `gecx-config.json` file.
  3. Proceed directly to the subsequent validation and implementation gates (Lint clean → Evals creation/run → Push updates).

If the intent is unclear, ask: "Are you looking to **build/create** evals, **run** them, or **debug** failures?"

## Prompt Design & XML Guidelines
When creating or editing the `instruction.txt` or configuration JSONs for any GECX agent, you MUST always follow these strict structure rules to guarantee zero linter warnings and errors on the first push:
- **XML Tag Hierarchy:** Enclose the agent instructions inside exactly structured tags: `<role>`, `<persona>`, and `<taskflow>`. Never write raw markdown headers (`# Persona` or `# Hard Rules`) outside these tags.
- **Subtask Groupings:** Group all conversational steps inside `<subtask name="Subtask_Name">` elements. Never place bare `<step>` elements directly under `<taskflow>`.
- **Step Casing:** Define steps inside subtasks using the `<step name="Step_Name">` format. Every step must have explicit `<trigger>` and `<action>` child blocks.
- **Valid app.json Schema:** When scaffolding `app.json`, always declare `rootAgent` mapping to the **display name** of the root agent (e.g. `root_agent` or `Main Agent`). Example minimum schema:
  ```json
  {
    "name": "<app-slug>",
    "displayName": "<App Display Name>",
    "description": "<App Description>",
    "rootAgent": "<root_agent_display_name>",
    "timeZoneSettings": { "timeZone": "America/Los_Angeles" }
  }
  ```
- **Valid Agent JSON Schema & Tools:** When scaffolding `<agent_name>.json`, always explicitly include any called system tools (like `end_session` or `set_session_state`) inside the `tools` list. If instructions suggest ending session, `end_session` MUST be listed in tools! Example:
  ```json
  {
    "displayName": "<Agent Display Name>",
    "instruction": "agents/<agent_folder_name>/instruction.txt",
    "tools": ["end_session", "set_session_state"]
  }
  ```
- **Directory naming matches:** In `app.json`'s `rootAgent` and in `<root_agent>.json`'s `childAgents` array, verify naming conventions strictly match the physical directories and sub-agent `.json` resource files (using underscores instead of spaces).

## Before Starting

Check memory for project-specific context (app ID, variable handling rules, audio scoring workarounds). If not available, ask the user.

- **Workspace Path Discovery:** The GECX Developer Skill files (including checklists, sub-agents, and references) are located under the repository root at the relative path `.agents/skills/cxas-agent-foundry/`.
  - To read skill reference guidelines or templates using tools that require absolute paths (like `view_file`), you MUST first discover the absolute path of your active repository root and use it as the base prefix to construct the target path: `<repository_root>/.agents/skills/cxas-agent-foundry/...`.
- **Workspace Root Resolution (CRITICAL):**
  - Your tool execution CWD may default inside a nested subfolder (such as a temporary `scratch/` folder or a pulled project subdirectory).
  - To locate your true **absolute repository root** path, search upwards from your current directory (or use recursive lookups) to identify the parent folder containing `.active-project`, `uv.lock`, or the `.agents/` directory itself.
  - Once identified, treat this path as your **absolute workspace root prefix**. All global path targets (such as `.agents/skills/...` or `.venv/bin/cxas`) MUST be constructed relative to this absolute workspace root prefix to prevent subdirectory path lookup failures!
- **Avoid Hardcoding Python Versions:** When referencing files or paths inside the virtual environment (such as `site-packages/` inside the virtual library), NEVER hardcode a specific python version (like `python3.11`). Instead, use dynamic wildcard globs (e.g., `.venv/lib/python3.*/site-packages/`) or query Python's system path dynamically to retrieve the correct environment string.
- **Global Configurations & Files Locations (CRITICAL CWD Rules):**
  - **Workspace Root Files:** Critical environment files like `.active-project`, `.venv/`, and `uv.lock` ALWAYS reside at the absolute **workspace root** folder level, NOT inside pulled subdirectories.
  - **Subdirectory CWD Navigation:** When you are working inside a pulled GECX agent folder (such as a generic project directory like `untested_billing_agent/`, a standard checkout folder like `cxas_app/Plan_Support_Agent/`, or a dynamic cloud app ID/UUID subdirectory like `73b2d15b-.../`), your execution CWD will be nested under this subfolder.
  - **Accessing Global Resources from Subfolders:** If your active execution Cwd is nested inside any subfolder (including dynamic UUID folders) and you need to execute global python utilities (like `.venv/bin/python ...`), checklists templates, or check configurations like `.active-project`, you MUST reference them using their absolute paths (constructed via your discovered absolute workspace root prefix) or correct parent directory step-backs (e.g., `../.active-project` or `../../.agents/...`). Never assume global paths are accessible relatively from a nested CWD!
- **Platform CLI Reference Mappings:** The active GECX platform CLI command is `cxas` (registered under `.venv/bin/cxas`). You must ONLY use these specific approved subcommands:
  - `cxas init` (scaffolds fresh workspace layout)
  - `cxas create <display_name>` (deploys app slot on server under active project)
  - `cxas push --app-dir <dir>` (deploys configuration templates to cloud)
  - `cxas pull <app_id> --target-dir <dir>` (retrieves active configurations)
  - `cxas lint` (enforces strict schema rules on configurations)
  - `cxas push-eval` (stages and registers Golden YAMLs to platform)
  - `cxas run-session text <app_id>` (starts interactive modality conversation session)
  - *Warning:* Subcommands starting with `cxas app ...`, `cxas agent ...`, or `cxas tool ...` DO NOT EXIST on the platform CLI and will fail. Never use them! Use `cxas create` or edits inside JSONs instead!
- **REST API to CLI Mappings Directives:** If a user prompt or PRD asks you to invoke raw REST HTTP endpoints to manage and run evaluations (e.g., using POST, GET, or JSON bodies targeting Vertex AI APIs), you must **NEVER** try to make raw HTTP requests. Instead, map these REST targets directly to their corresponding `cxas` CLI tool actions:
  1. `POST to /evaluations` (creating/saving evaluations in the cloud) ➡️ Create the golden/simulation YAML files locally under `evals/goldens/` or `evals/simulations/` and then run:
     `cxas push-eval --app-name <app_id> --file <yaml_path> --project-id <project_id> --location <location>`
  2. `POST to :runEvaluation` (running/executing the evaluations suite) ➡️ Run:
     `cxas run --app-name <app_id> --wait --project-id <project_id> --location <location>`
     *(Always use the `--wait` flag to block until execution completes!)*
  3. `GET to /evaluations/...` (querying/confirming final pass/fail metrics) ➡️ Inspect the console output and exit code of `cxas run --wait`. If the command completes with exit code 0, all expectations passed cleanly! Inspect the generated reports under the sandbox folder to confirm detailed metrics.
- **Explicit Project & Location Parameters Mandate:** When running any of the above platform commands, you must ALWAYS pass the explicit project and location options (e.g., `--project-id <project_id> --location <location>`) in your command line parameters string! In sandboxed environments, default environment variable resolution may not be reliable, so being explicit ensures robustness.
- **GECX CLI Directory Nesting Rules (CRITICAL):** When you run `cxas pull <app_id> --target-dir <dir>`, the platform CLI does NOT put the configurations files directly under `<dir>`. Instead, it automatically creates a nested child subdirectory named after the **App Display Name** (using snake_case underscores or spaces: e.g. `<dir>/Your_App_Name/` or `<dir>/Your App Name/`) and puts all files (`app.json`, `agents/`, `tools/`) inside this child folder!
  - Therefore, after running `cxas pull`, you must **ALWAYS** use `list_dir` on the target folder to verify the exact name of this nested child folder.
  - In all subsequent command executions (like lint, push, edits), you must set your execution Cwd (Current Working Directory) parameter targeting this **nested child folder directly** (e.g. `<dir>/Your_App_Name/`), never the parent directory! If you miss this nested folder layer, your edit tools and push commands will fail with 'file not found' errors.
- **Avoid App Creation Conflicts (409 Bypass - CRITICAL):** To prevent `409 App already exists` deployment failures, ALWAYS verify if the target app is already present on the server by running `cxas apps list --project-id <project_id> --location <location>` on Turn 1. If the target app display name exists in the output list, you are strictly FORBIDDEN from running `cxas create`. Proceed directly to `cxas pull` to check out files! Executing an unnecessary create command that triggers a 409 server conflict represents a critical scoring penalty!
- **Strict Template Placeholders Replacement:** When editing configuration templates (`app.json`, `agent.json`, etc.), always verify if there are any active system placeholders (such as `$env_var`, `<placeholder_id>`, or other template parameters). You MUST replace them with literal values (dynamically discovered or context values) before linting or pushing. Never leave system-level placeholders inside active final configurations targets!
- **Preserve Declarative Framework Structures:** When customizing callbacks that implement specific structured frameworks (such as the GECX Slot Filling DAG framework), NEVER delete or replace the declarative class configuration structures (like `_get_config()` hooks or `Slot()` / `Task()` bindings) with basic procedural conditional logic statements (`if/elif` blocks). Always preserve the framework architecture and customize its configuration fields recursively inside the established class hooks!

## Tool Call Safety Guidelines

To prevent tool execution failures and invalid syntax arguments blockages, you MUST strictly adhere to these tool call parameters rules:

- **`replace_file_content` Line Boundaries Mandate:**
  - Always ensure `StartLine <= EndLine` and both numbers are **greater than 0**, cleanly surrounding the precise lines you wish to edit! Never set `EndLine` to `0`.
  - `TargetContent` MUST be a unique, literal, 100% exact copy of the text in the file. You **MUST** capture all leading whitespace (tabs, spaces) and brackets precisely. If there are leading spaces, include them character-for-character!
  - If you hit `target content not found in file` or validation boundary exceptions, do **NOT** guess parameters. Proactively use `view_file` to read the target file's exact line numbers and contents, then reconstruct your replace tool call!
- **`view_file` View Range Limits:**
  - Omit `StartLine` and `EndLine` to read the entire file if it is smaller than 800 lines, or set safe, valid positive integer limits. Do not specify 0.
- **Verification Gates:**
  - Proactively run local Python testing commands (like unit test checks) using the platform CLI before executing git commits or final updates pushes. Ensure that local executions return exit status 0!
- **Banning Chained Interactive Shell Commands:** Never chain multiple testing commands with `&&` inside your terminal shell if they execute interactive user sessions or prompt entries (such as text conversation testing tools `cxas run-session` or raw prompt queries). The first interactive session blocks execution or drops downstream streams, failing to run or capture the second test case in your trajectory logs. Always issue separate, sequential `run_command` tool calls for each independent test session to ensure complete trace capture!
- **Synchronous Process Wait Mandate (WaitMsBeforeAsync Guidelines):** When executing GECX configuration, setup, or evaluation run command lines (like `configure.py`, `gate-check.py`, or `cxas run`), NEVER pass `WaitMsBeforeAsync: 0` unless it is a long-running, interactive Borg deployment that explicitly requires async background loops. Always set `WaitMsBeforeAsync` to a large enough value (e.g. `5000` to `10000` milliseconds) to force the command to execute and complete synchronously on your main thread, preventing background process leaks and infinite status-checking polling loops!

## Proactive PRD Matching Strategy

When building, bootstrapping, or editing GECX conversational agents and evaluations suites from a product requirements document (`prd.md`):

- **PRD Dominance Mandate:**
  - Always read the PRD on Turn 1. The PRD represents the master scope of success!
  - If the PRD demands multiple deliverables (e.g., Goldens, Simulations, and Tool Tests), you MUST proactively scaffold, author, and implement ALL requested deliverables during your initial implementation turn.
  - Do **NOT** restrict your execution to only what the immediate user prompt asks if the PRD specifies additional required components. Proactively implement the complete PRD scope to ensure full compliance and avoid incomplete delivery penalties.
- **Pre-Scaffold Reports Directories:**
  - Before running evaluations using helper scripts (like `run-all-evals.py` or `scrapi-eval-runner`), ensure the target reports directory (e.g., `eval-reports/`) exists. Proactively create it if missing to prevent write path failures.
- **Non-Interactive Project Configuration:**
  - When running setup or configuration scripts (like `configure.py`) in automated environments, always pass all required parameters (such as project ID, location, and modality) as inline command-line arguments (e.g., `--project-id <project_id> --location <location> --modality <modality>`) to force non-interactive execution and prevent the process from hanging on interactive prompts. Discover these values from the active environment or user context dynamically.
