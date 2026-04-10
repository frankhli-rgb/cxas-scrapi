# GECX Agent Development Workspace

This workspace manages GECX (Google Customer Engagement Suite) conversational agents — building, testing, and iterating on them.

## Skills

- **`agent-foundry`** — End-to-end agent lifecycle: build from PRD, create evals, run evals, debug failures. This is a composite skill with three sub-skills (build/run/debug) and shared scripts.

## Project Structure

```
setup.sh                        # Environment setup (virtualenv + cxas-scrapi install)
gecx-config.json                # Centralized project config (project, app ID, modality, environments)
tdd.md                          # Technical Design Document (source of truth)
cxas_app/                       # Local agent code pulled from CXAS (canonical source)
eval-reports/                   # Generated reports
  debug_iteration_*.html        #   Per-iteration debug reports (changes + diffs + results)
  combined_report_*.html        #   Combined eval reports (goldens + sims + tools + callbacks)
  sim_report_*.html             #   Sim-only reports
evals/                          # All eval definitions
├── scenarios/scenarios.yaml    # Platform scenario evals (sim-user driven)
├── goldens/*.yaml              # Platform golden evals (turn-by-turn ideal)
├── simulations/simulations.yaml # Local sim eval templates
├── tool_tests/*.yaml           # Isolated tool tests
└── callback_tests/             # Pytest callback tests
    ├── agents/                 # Raw callback code from platform
    └── tests/                  # Test assertions (symlinked into agents/)

.agents/skills/
└── agent-foundry/              # Composite skill (build + run + debug)
    ├── SKILL.md                # Router
    ├── scripts/                # All eval scripts
    ├── hooks/                  # Workflow automation hooks (sync, reminders)
    └── skills/{build,run,debug}/
```

## Setup

Run the setup script to create a virtualenv and install `cxas-scrapi`:

```bash
./setup.sh          # Install latest version
./setup.sh 0.1.5    # Install specific version
source .venv/bin/activate
```

Requires `gsutil` (Google Cloud SDK) and Python 3.

## Development Workflow

Agent development uses a **hybrid approach** — local files in git for version control, with SCRAPI for running evals and platform operations. Hooks automate the sync between local files and the CXAS platform.

- **`gecx-config.json`** — Centralized config (project ID, app ID, location, modality, environments). Hooks and skills read this instead of parsing YAML or asking the user.
- **`cxas_app/`** — Local agent code (instructions, callbacks, tools, variables) pulled from CXAS. This is the canonical source for agent definitions. Edit locally, hooks auto-push before evals.
- **Hooks** handle sync automatically (configured in `.claude/settings.json` and `.gemini/settings.json`):
  - `pre-agent-edit.sh` — Auto-pulls latest from CXAS before editing files in `cxas_app/`
  - `pre-eval-run.sh` — Auto-pushes local code to CXAS before running evals
  - `pre-agent-push.sh` — Blocks push if local files are stale vs platform (drift detection)
  - `post-agent-update.sh` — Auto-pulls after SCRAPI updates to keep local in sync
  - `post-agent-push.sh` — Reminds to commit to git after pushing
- **SCRAPI** is still used for running evals, testing sessions, inspecting state, and rapid prototyping. When prototyping via SCRAPI, the post-hook auto-pulls changes to local files.

## Developer Quick Reference

The core principle: **create on platform, edit locally**.

```
CREATE (new agent/tool/callback/variable)
  └─ Use SCRAPI create_*() → hook auto-pulls to cxas_app/
  └─ See build skill (references/api-reference.md) for SCRAPI API

EDIT (instruction, callback code, tool config)
  └─ Edit directly in cxas_app/ → hook auto-pushes on eval run
  └─ cxas_app/
     ├── agents/{name}/instruction.txt
     ├── callbacks/{agent}/{type}/python_code.py
     ├── tools/{name}/...
     └── variables/...

TEST
  └─ Run evals via scripts → hook auto-pushes first
  └─ See run skill for eval commands

COMMIT
  └─ git add cxas_app/ evals/ tdd.md && git commit
```

Refresh local files: `./setup.sh --configure` → "Pull app from CXAS"

## Key Conventions

- **TDD is the source of truth.** The Technical Design Document (`tdd.md`) defines agent architecture and eval coverage. Evals follow the TDD, not the agent's current behavior. Update the TDD first, then update evals to match.
- **Five eval types:** goldens, scenarios, simulations, tool tests, callback tests.
- **Audio scoring:** For **scenarios**, use `--audio` flag — `taskCompleted` is broken in audio mode. For **goldens**, use `evaluation_status` directly (the `--audio` flag does NOT apply to goldens).
- **Session variables:** Only override what the agent's `before_agent_callback` can't derive. Never override `auth_status` or `user_role`.
- **Fix the agent first.** When evals fail, assume the agent is wrong. Only modify evals as a last resort after confirming agent behavior is correct.
- **Every agent change needs eval updates.** Callback changes require syncing code + adding/updating tests. Instruction changes require checking affected goldens/sims.
- **Combined report after every run.** Always generate a combined report with all 4 eval types using `generate-combined-report.py`.
- **YAML formatting:** Hand-write YAML instead of using `yaml.dump()` to avoid reformatting.

## Memory

Project-specific context is stored in memory files — check them for app IDs, variable handling rules, eval architecture details, and report style preferences.
