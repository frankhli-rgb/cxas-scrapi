# GECX Agent Development Workspace

This workspace manages GECX (Google Customer Engagement Suite) conversational agents — building, testing, and iterating on them.

## Skills

Two skills handle the core workflows:

- **`agent-foundry`** — End-to-end agent lifecycle: build from PRD, create evals, run evals, debug failures. This is a composite skill with three sub-skills (build/run/debug) and shared scripts.
- **`skill-creator`** — Meta-skill for creating and improving skills.

## Project Structure

```
tdd.md                          # Technical Design Document (source of truth)
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
├── agent-foundry/              # Composite skill (build + run + debug)
│   ├── SKILL.md                # Router
│   ├── scripts/                # All eval scripts
│   └── skills/{build,run,debug}/
└── skill-creator/              # Meta-skill

cxas-scrapi/                    # SCRAPI Python library (installed locally)
```

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
