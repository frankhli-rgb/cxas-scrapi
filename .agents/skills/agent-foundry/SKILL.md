---
name: agent-foundry
description: End-to-end GECX agent lifecycle — build agents from requirements, create and run evals, debug failures, and update evals when requirements change. Use this skill when the user says "build me an agent", "create evals", "run evals", "run tool tests", "test callbacks", "debug failing evals", "get to 90%", "update evals", "generate a report", or anything related to creating, testing, or improving a conversational agent.
user_invocable: true
---

# Agent Foundry

End-to-end lifecycle for GECX conversational agents: build, test, debug, iterate.

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
Push, run, score, and report across five eval types:
- **Platform goldens** — deterministic turn-by-turn tests
- **Platform scenarios** — sim-user-driven open-ended tests
- **Local simulations** — fast parallel testing via SCRAPI Sessions API
- **Tool tests** — isolated tool input/output validation via `ToolEvals`
- **Callback tests** — pytest against agent callbacks via `CallbackEvals`

### Debug (`skills/debug/SKILL.md`)
Triage failures, fix eval configs or agent instructions, iterate to target pass rate. Includes triage guides for all five eval types.

## Shared Resources

**Scripts** — all in `.agents/skills/agent-foundry/scripts/`:

| Script | Purpose |
|--------|---------|
| `scrapi-eval-runner.py` | Platform evals: `status`, `push`, `push-goldens`, `run`, `run-goldens`, `results [--audio]`, `report` |
| `scrapi-sim-runner.py` | Local sim evals: `run [--parallel N] [--channel audio]`. Generates HTML reports. |
| `generate-combined-report.py` | Unified golden + sim HTML report |
| `run-and-report.sh` | Legacy platform runner (curl/REST) |
| `capture-golden-transcripts.py` | Capture live agent transcripts for reference |

**Eval files** — all in `evals/`:

```
evals/
├── scenarios/scenarios.yaml      # Platform scenario evals (sim-user driven)
├── goldens/*.yaml                # Platform golden evals (ideal conversations)
├── simulations/simulations.yaml  # Local sim eval templates
├── tool_tests/*.yaml             # Isolated tool tests (input/output validation)
└── callback_tests/
    ├── agents/                   # Raw callback code from platform (python_code.py)
    │   └── <agent>/<callback_type>/<name>/python_code.py
    └── tests/                    # Pytest assertions (test.py, symlinked into agents/)
        └── <agent>/<callback_type>/<name>/test.py
```

## Quick Reference

```bash
# Conversation evals
python .agents/skills/agent-foundry/scripts/scrapi-eval-runner.py push-goldens
python .agents/skills/agent-foundry/scripts/scrapi-eval-runner.py run-goldens --channel audio
python .agents/skills/agent-foundry/scripts/scrapi-eval-runner.py run --priority P0 --channel audio --runs 5
python .agents/skills/agent-foundry/scripts/scrapi-eval-runner.py results <RUN_ID> --audio
python .agents/skills/agent-foundry/scripts/scrapi-sim-runner.py run --priority P0 --parallel 5 --channel audio

# Combined report
python .agents/skills/agent-foundry/scripts/generate-combined-report.py \
  --golden-run <ID> --sim-results <JSON> --golden-modality audio --sim-modality audio

# Tool tests
from cxas_scrapi.evals.tool_evals import ToolEvals
tool_evals = ToolEvals(app_name=app_name)
results = tool_evals.run_tool_tests(tool_evals.load_tool_tests_from_dir("evals/tool_tests"))

# Callback tests
from cxas_scrapi.evals.callback_evals import CallbackEvals
CallbackEvals().test_single_callback_for_agent(app_name, agent_name, callback_type, test_path)
```

## Hooks

Workflow reminder hooks live in `hooks/`. They trigger after eval runs, agent updates, and callback code changes. See your agent's settings file for the wiring.

## Before Starting

Check memory for project-specific context (app ID, variable handling rules, audio scoring workarounds). If not available, ask the user.
