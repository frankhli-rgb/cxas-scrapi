# GECX Agent Development Workspace

This workspace manages GECX (Google Customer Engagement Suite) conversational agents — building, testing, and iterating on them.

## Skills

- **`cxas-agent-foundry`** — End-to-end agent lifecycle: build from PRD, create evals, run evals, debug failures. This is a composite skill with three sub-skills (build/run/debug) and shared scripts.

## Project Structure

```
<project_name>/                        # Named project folder (app-specific)
├── gecx-config.json            # Project config
├── cxas_app/                   # Agent code from platform
├── tdd.md                      # Technical design document
├── evals/                      # Eval definitions
│   ├── goldens/*.yaml
│   ├── simulations/simulations.yaml
│   ├── tool_tests/*.yaml
│   └── callback_tests/
├── eval-reports/               # Generated reports
│   ├── debug_iteration_*.html
│   ├── combined_report_*.html
│   └── sim_report_*.html
└── gecxlint.yaml               # Lint config

.agents/skills/                 # Skills (shared, reusable)
└── cxas-agent-foundry/              # Composite skill (build + run + debug)
    ├── SKILL.md                # Router
    ├── scripts/                # All eval scripts
    ├── hooks/                  # Workflow automation hooks (sync, reminders)
    └── skills/{build,run,debug}/
cxas-scrapi/                    # SDK (shipped with skill)
.venv/                          # Shared virtualenv
AGENTS.md                       # This file
.active-project                 # Points to active project (e.g., "cymbal")
```

## Setup

Run the setup script to create a virtualenv and install `cxas-scrapi` from the local source:

```bash
.agents/skills/cxas-agent-foundry/scripts/setup.sh          # Full setup (install + configure)
.agents/skills/cxas-agent-foundry/scripts/setup.sh --configure  # Reconfigure only
source .venv/bin/activate
```

Requires Python 3.

## Development Workflow

Agent development uses a **hybrid approach** — local files in git for version control, with SCRAPI for running evals and platform operations.

- **`<project>/gecx-config.json`** — Centralized config (project ID, app ID, location, modality, environments). Located in the active project folder.
- **`<project>/cxas_app/`** — Local agent code (instructions, callbacks, tools, variables) pulled from CXAS. This is the canonical source for agent definitions.
- **Hooks** (configured in `.claude/settings.json` and `.gemini/settings.json`) provide safety guardrails: blocking stale pushes, running lint before push, and auto-syncing after SCRAPI updates.
- **SCRAPI** is used for running evals, testing sessions, inspecting state, and rapid prototyping.

## Developer Quick Reference

The core principle: **create on platform, edit locally**.

```
CREATE (new agent/tool/callback/variable)
  └─ Use SCRAPI create_*() then run sync-callbacks.py to pull to local
  └─ See build skill (references/api-reference.md) for SCRAPI API

EDIT (instruction, callback code, tool config)
  └─ Edit directly in <project>/cxas_app/
  └─ <project>/cxas_app/
     ├── agents/{name}/instruction.txt
     ├── callbacks/{agent}/{type}/python_code.py
     ├── tools/{name}/...
     └── variables/...

TEST
  └─ python run-and-report.py --message "what changed" --auto-revert
  └─ See run skill for eval commands

COMMIT
  └─ git add <project>/cxas_app/ <project>/evals/ <project>/tdd.md && git commit
```

Refresh local files: `.agents/skills/cxas-agent-foundry/scripts/setup.sh --configure` → "Pull app from CXAS"

## Key Conventions

- **TDD is the source of truth.** The Technical Design Document (`<project>/tdd.md`) defines agent architecture and eval coverage. Evals follow the TDD, not the agent's current behavior. Update the TDD first, then update evals to match.
- **Four eval types:** goldens, simulations, tool tests, callback tests.
- **Audio scoring:** For **goldens**, use `evaluation_status` directly. For **sims**, the sim runner handles audio scoring automatically.
- **Session variables:** Only override what the agent's `before_agent_callback` can't derive. Never override `auth_status` or `user_role`.
- **Fix the agent first.** When evals fail, assume the agent is wrong. Only modify evals as a last resort after confirming agent behavior is correct.
- **Every agent change needs eval updates.** Callback changes require syncing code + adding/updating tests. Instruction changes require checking affected goldens/sims.
- **Combined report after every run.** Always generate a combined report with all 4 eval types using `generate-combined-report.py`.
- **YAML formatting:** Hand-write YAML instead of using `yaml.dump()` to avoid reformatting.

## Memory

Project-specific context is stored in memory files — check them for app IDs, variable handling rules, eval architecture details, and report style preferences.
