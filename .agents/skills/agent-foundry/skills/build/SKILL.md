---
name: agent-foundry-build
description: Build a fully tested GECX conversational agent from requirements, or create evals for an existing agent. Use this skill when the user says "build me an agent", "create an agent from this PRD", "create evals for my agent", "generate test cases", "I have requirements and need an agent", or wants to go from a spec/PRD to a working, eval-verified agent.
user_invocable: false
---

# Agent Foundry

Build GECX conversational agents from requirements and verify them with evals. This skill handles two workflows:

1. **Full build** — PRD/requirements → app + agents + tools + evals → initial test run
2. **Eval creation** — existing app → inspect → generate goldens/scenarios/simulations

Both workflows use the `cxas-scrapi` library for API interactions and the `eval-manager` skill's scripts for running evals. **Prerequisite:** Ensure the virtualenv is set up (`./setup.sh`) and activated (`source .venv/bin/activate`).

## References

- `references/gecx-design-guide.md` — GECX Agent Design Guide with best practices for instructions, architecture, tools, callbacks, variables, and error handling. **Read this before building any agent.** Key principles:
  - Use XML formatting for instructions (`<role>`, `<persona>`, `<step>`)
  - Write unambiguous instructions — treat prompts as software, not vibes
  - Start single-agent, decompose into multi-agent when instruction following degrades
  - Use tool wrappers to consolidate sequential API calls
  - Offload deterministic logic from instructions to callbacks — use trigger pattern (LLM sets variable, callback returns tools) for 100% reliable tool calling
  - Use JSON schemas for complex state instead of many individual variables
  - Embed instructions in tool responses for progressive disclosure
  - Return `agent_action` in error responses for deterministic recovery
- `references/api-reference.md` — SCRAPI API reference for creating apps, agents, tools, variables, callbacks. **Read the Build Order and Common Mistakes sections before making any API calls.**
- `references/build-verification.md` — 7 verification gates to run after building. **ALL gates must pass before writing evals.**
- `references/creating-evals.md` — How to create golden and scenario evaluations

## Entry Point Detection

Determine which workflow based on what the user provides:

- **Has requirements but no app** → Full build (start at Interview)
- **Has an existing app** → Eval creation (start at Inspect App)
- **Unclear** → Ask: "Do you already have an agent app, or are we building from scratch?"

---

## Interview

Gather the information needed to build the agent and/or create evals. Don't ask everything at once — start broad and drill into details as the design takes shape.

### Round 1: The Big Picture

1. **What does this agent do?** — "customer support for billing issues", "booking assistant", etc.
2. **Requirements source** — Ask for the PRD, spec doc, or requirements. Can be a file path, URL, or pasted text. If they don't have a formal doc, interview them to build one.
3. **Existing resources** — Do they have sample conversations, mock data, customer profiles, or an existing agent to reference?

### Round 2: Write the Technical Design Document (TDD)

After gathering requirements, write a TDD to `tdd.md` in the project root. This is a **living document** — it persists as the source of truth for the agent architecture and eval coverage. When requirements change later, the TDD is updated first, then evals are updated to match.

Ask the user to review and approve the TDD before building anything.

#### Agent Design
1. **Agent architecture** — root agent + sub-agents, what each one handles
2. **Tools needed** — knowledge base, API connectors, session tools (with tool names and types)
3. **Routing logic** — how customers get routed (auth status, issue type, etc.)
4. **Variables** — what session variables are needed and where they come from
5. **Callbacks** — before/after agent callbacks for setup logic (auth, profile lookup)

#### Eval Design
For each requirement in the PRD:
1. **Eval type** — golden or scenario (with rationale)
2. **What it tests** — the specific behavior being verified
3. **Priority and severity** — P0/P1/P2, NO-GO/HIGH/MEDIUM/LOW
4. **Session parameters** — which customer profile, what variables
5. **For goldens** — summary of the ideal conversation flow
6. **For scenarios** — task description, max turns, LLM expectations
7. **Tool tests** — which tools need isolated tests and what to assert
8. **Callback tests** — which callbacks need tests and what logic paths to cover
9. **Tags** — for filtering (category, PRD ID, priority)

#### Build Steps
Numbered list of exactly what will be created, in order:
1. App + agents with instructions
2. Tools + tool configurations
3. Variables
4. Callbacks
5. Golden YAML files
6. Scenario YAML entries
7. Simulation YAML entries
8. Tool test YAML files
9. Callback test files (python_code.py + test.py)
10. Initial eval run

**Wait for user approval before proceeding.** The user may want to adjust the architecture, add/remove evals, change priorities, or modify the routing logic. Don't build anything until the TDD is approved.

#### Keeping the TDD Current

The TDD must stay in sync with reality. Three things can trigger an update:

**1. Requirements change** (PRD update, new feature request):
- Read the updated requirements
- Diff against the current TDD
- Update the TDD with new/changed sections
- Present the diff to the user for approval
- After approval, update the affected evals to match

**2. Agent changes** (new tools, changed routing, updated instructions):
- Inspect the agent to identify what changed (use SCRAPI to pull current config)
- Update the Agent Design section of the TDD
- Check if existing evals need updating (e.g., golden expected text, tool expectations)
- Present changes to user for approval

**3. Eval changes** (new eval added, type changed, eval removed during debugging):
- Update the Eval Design section of the TDD to reflect current coverage
- This keeps the TDD accurate as a coverage map

The TDD is the single source of truth — evals follow the TDD, not the agent's current behavior. When in doubt about what an eval should test, check the TDD.

### Golden vs Scenario Decision

The key question: **is the agent's behavior deterministic for this flow?**

| Use Goldens When | Use Scenarios/Sims When |
|-----------------|------------------------|
| Agent flow is deterministic — same input always produces same output | Agent uses a knowledge base that returns varying results per query |
| Tool calls are consistent and predictable | Troubleshooting steps vary (KB returns different steps each time) |
| Callbacks enforce the behavior (before_model, after_model) | Agent phrasing naturally varies due to LLM generation |
| Routing is the primary thing being tested | Behavioral goals are being tested (e.g., "escalates after 3 failures") |
| The conversation follows a fixed script | The conversation path depends on tool responses |

**Examples:**
- Auth API failure → immediate escalation: **Golden** (callback-enforced, deterministic)
- Profanity → escalation with message: **Golden** (instruction-driven but consistent trigger)
- Auth routing → diagnostic check → status response: **Golden** (callback generates response from template)
- Troubleshooting step-by-step with resolution checks: **Sim** (KB returns different steps)
- "Contact customer service" in tool response → escalate: **Sim** (depends on KB returning specific phrase)

**Rule of thumb:** If you need to make a golden pass by making the agent MORE deterministic (via callbacks), that's the right approach. If the golden keeps failing because the agent's response inherently varies (KB-dependent), convert it to a sim.

### Golden Design Principles

- Goldens represent what the agent SHOULD do per the PRD — ideal behavior
- Never capture agent transcripts and use them as goldens — that's circular testing
- Include tool calls with expected args — use `$matchType` for flexible parameter matching
- Goldens are the contract with the user — **do not weaken goldens to make them pass.** Fix the agent instead.
- If a golden keeps failing due to agent variance, make the agent deterministic (use callbacks for execution), but don't overfit by adding hardcoded phrase matching or keyword detection in callbacks — keep intent detection in the LLM's instructions
- For escalation flows, handle them in the root agent (not sub-agents) so the response role matches
- Use `after_model_callback` with state tracking to ensure the agent says a message before `end_session` — the LLM splits turns across multiple model calls, so use `callback_context.state` to track text across calls (see gecx-design-guide.md "Multi-model-call turns")
- **Truncate goldens at the last deterministic turn.** Don't test KB-dependent troubleshooting text or goodbye/end_session in goldens — the LLM varies on these. Test deterministic parts (routing, outage detection, escalation triggers) in goldens, and non-deterministic parts (KB content, farewell text) in sims.
- **Only include core tool expectations.** Don't put auxiliary/classification tool calls in golden `tool_calls` — the LLM reorders them relative to routing calls like `transfer_to_agent`. Only test the tool call that defines the behavior (routing, escalation, diagnostic check).
- **Use `$matchType: "ignore"` for LLM-generated free-text args** (`summary`, `escalation_reason`, `main_topic`). The semantic matcher is flaky on these.
- **Never have duplicate YAML keys in a turn.** Two `tool_calls:` blocks at the same level is invalid — the second overwrites the first. Combine into a single list.

---

## Inspect App

When working with an existing app, first check `gecx-config.json` for project configuration (project ID, app ID, location). If available, use it to construct the app_name instead of asking the user. Then pull context from the API before creating evals:

```python
import json

# Read config if available
with open("gecx-config.json") as f:
    config = json.load(f)
app_name = f"projects/{config['gcp_project_id']}/locations/{config['location']}/apps/{config['deployed_app_id']}"

from cxas_scrapi.core.apps import Apps
from cxas_scrapi.core.agents import Agents
from cxas_scrapi.core.tools import Tools
from cxas_scrapi.core.variables import Variables
from cxas_scrapi.core.evaluations import Evaluations

# Get agent architecture
agents = Agents(app_name=app_name)
agents_map = agents.get_agents_map()

# Get available tools
tools = Tools(app_name=app_name)
tools_map = tools.get_tools_map()

# Get variable declarations
variables = Variables(app_name=app_name)

# Get existing evals (avoid duplicates)
evals = Evaluations(app_name=app_name)
evals_map = evals.get_evaluations_map()
```

Also read the agent instructions and callbacks to understand:
- Routing logic (which variables trigger which paths)
- Which variables the callback derives vs needs as overrides
- Tool names and what they do

Share this context with the user: "Here's what I found in your app..." and confirm before creating evals.

---

## Build App

When building from scratch, use SCRAPI to create the full agent stack. After building, the post-agent-update hook will auto-pull the agent state to local files in `cxas_app/` (configured via `gecx-config.json`).

```python
from cxas_scrapi.core.apps import Apps
from cxas_scrapi.core.agents import Agents
from cxas_scrapi.core.tools import Tools

# Create app
apps = Apps(project_id=project, location=location)
app = apps.create_app(display_name=name, ...)

# Create agents with instructions
agents = Agents(app_name=app.name)
root = agents.create_agent(display_name="root_agent", instruction=instruction)

# Create tools
tools = Tools(app_name=app.name)
tool = tools.create_tool(...)
```

After building:
1. The post-agent-update hook auto-pulls the created agent to local files
2. Update `gecx-config.json` with the new app ID if this is a new app
3. Run the Inspect App step to confirm everything was created correctly
4. Subsequent edits should be made to local files in `cxas_app/` — hooks handle pushing to CXAS before eval runs

---

## Generate Evals

Create three types of eval files:

### 1. Golden YAML (`evals/goldens/*.yaml`)

**Prerequisite variables:** Goldens and sims MUST include all session variables that the agent's callbacks read at startup. Read the `before_agent_callback` source code to identify which variables it accesses from `callback_context.state` — every one of those must be provided in session parameters, or the callback will crash with a KeyError and the agent will fall through to default behavior.

**Watch for case sensitivity** — if the callback reads `callback_context.state["AccountID"]` (specific casing), the session parameter must match exactly (e.g., `AccountID`, not `accountid`).

Put shared prerequisites in `common_session_parameters` and profile-specific values in per-conversation `session_parameters`.

```yaml
common_session_parameters:
  # Include ALL variables the before_agent_callback reads from state
  # Check the callback source code to find these

conversations:
  - conversation: golden_eval_name
    session_parameters:
      account_id: "9820598207"
      customer_id: "4444444"
    turns:
      - user: "Hi"
        agent: "Opening greeting..."
      - user: "Customer's first message"
        agent: "Agent's response"
        tool_calls:
          - action: tool_display_name
            args: {key: value}
          - action: payload_update_tool
            args:
              summary:
                $matchType: "ignore"
                $matchValue: ""
                $originalValue: ""
              escalation_reason:
                $matchType: "semantic"
                $matchValue: "Expected reason"
                $originalValue: ""
      - user: "Goodbye"
        agent: "Thank you for calling. Have a great day!"
        tool_calls:
          - action: end_session
            args:
              session_escalated: false
    expectations:
      - "The agent must do X"
      - "The agent must NOT do Y"
    tags: [P0, HIGH, FR-1.1, auth-routing]
```

**Tool call parameter matching:** Use `$matchType` directives for flexible parameter matching. Supported types: `semantic` (fuzzy meaning match), `ignore` (skip check), `contains` (substring match), `regexp` (regex pattern). Parameters without `$matchType` use exact matching. See `run/references/creating-evals.md` for details.

### 2. Scenario YAML (`evals/scenarios/scenarios.yaml`)

```yaml
- name: eval_name
  prd_id: FR-X.Y
  priority: P0
  severity: HIGH
  description: What this tests
  task: "You are a customer... You MUST cooperate fully. X counts as a successful outcome."
  max_turns: 12
  variables: {account_id: "9820598207", customer_id: "4444444"}
  expect_tools: []
  expect_criteria: [CRITERIA_ALIAS]
  completion: TASK_SATISFIED
  tags: [P0, HIGH, FR-X.Y, category, scenario]
```

### 3. Simulation YAML (`evals/simulations/simulations.yaml`)

```yaml
- name: eval_name
  steps:
    - goal: What the sim user should accomplish
      success_criteria: What counts as success
      response_guide: "How the sim user should behave"
      max_turns: 12
  expectations:
    - "What the agent should do"
    - "The agent must call a tool to check for outages in the customer's area."
    - "The agent must end the session and escalate after exhausting options."
  session_parameters: {account_id: "9820598207", customer_id: "4444444"}
  tags: [P0, HIGH, FR-X.Y, category, simulation]
```

**Sim expectations can verify tool calls** using natural language. The LLM judge evaluates expectations against the full conversation transcript (including tool calls). Phrase tool expectations as behavioral descriptions, not function names — the judge sees resource IDs in the transcript, not display names:
- Good: "The agent must call a tool to check for network outages"
- Bad: "The agent must call diagnostic_lookup_tool" (judge can't match display names to resource IDs)

Include tool expectations alongside behavioral expectations to verify both WHAT the agent says and WHAT tools it calls.

For each scenario eval, always create a matching simulation template so the user can test locally.

### 4. Tool Tests (`evals/tool_tests/*.yaml`)

Test individual tools in isolation — faster and more precise than end-to-end conversation evals for catching tool-level regressions.

```python
from cxas_scrapi.evals.tool_evals import ToolEvals

tool_evals = ToolEvals(app_name=app_name)

# Auto-generate test templates from tool schemas
tool_evals.generate_tool_tests(
    target_dir="evals/tool_tests",
    mine_tool_data=True,        # Populate args from real conversation data
    mine_conversations_limit=50,
)
```

Generated YAML format:
```yaml
tests:
  - name: diagnostic_lookup_test_1
    tool: diagnostic_lookup_tool
    args:
      account_id: "6666666"
      customer_id: "123456"
    expectations:
      response:
        - path: "$.status"
          operator: is_not_null
        - path: "$.issue_type"
          operator: contains
          value: "service"
```

Run tool tests:
```python
test_cases = tool_evals.load_tool_tests_from_dir("evals/tool_tests")
results_df = tool_evals.run_tool_tests(test_cases, debug=True)
report_df = ToolEvals.generate_report(results_df)
```

Operators: `equals`, `contains`, `greater_than`, `less_than`, `length_equals`, `length_greater_than`, `length_less_than`, `is_null`, `is_not_null`.

### 5. Callback Tests (`evals/callback_tests/`)

Test agent callbacks (before_agent, before_model, after_model, etc.) in isolation using pytest. Agent code and tests are separated for maintainability.

**Directory layout:**
```
evals/callback_tests/
├── agents/                    # Raw callback code from platform
│   └── <agent>/<callback_type>/<name>/python_code.py
└── tests/                     # Pytest assertions (symlinked into agents/ for SCRAPI)
    └── <agent>/<callback_type>/<name>/test.py
```

SCRAPI's `test_all_callbacks_in_app_dir` expects `test.py` alongside `python_code.py`, so tests are symlinked into `agents/`. Edit tests in `tests/`, update agent code in `agents/`.

**Running:**
```python
from cxas_scrapi.evals.callback_evals import CallbackEvals

cb = CallbackEvals()
results_df = cb.test_all_callbacks_in_app_dir(app_dir="evals/callback_tests")
```

**Test pattern — the test file handles mock injection:**
```python
import python_code
from unittest.mock import MagicMock, patch

# Inject mock for the 'tools' global that GECX provides at runtime
python_code.tools = MagicMock()
python_code.StatusError = Exception

from python_code import before_agent_callback
from cxas_scrapi.utils.callback_libs import CallbackContext

def test_returns_early_when_authenticated():
    ctx = CallbackContext(state={"auth_status": "authenticated", ...})
    result = before_agent_callback(ctx)
    assert result is None

def test_extracts_customer_id_from_datastore():
    python_code.tools.Read_Customer_Datastore_readDatastore.return_value = mock_resp
    before_agent_callback(ctx)
    assert ctx.state["customer_id"] == "999888"
```

**Adding a new callback test:**
1. Save the raw callback code to `agents/<agent>/<type>/<name>/python_code.py`
2. Write the test file in `tests/<agent>/<type>/<name>/test.py`
3. Symlink: `ln -sf $(pwd)/evals/callback_tests/tests/...test.py agents/.../test.py`

**Every callback change requires a test update.** When you modify a callback (add logic, change tool calls, add a new early-return path), you must:
1. Sync the updated code from the platform to the local `python_code.py`
2. Add tests covering the new/changed behavior
3. Run all callback tests to verify no regressions

**What to test per callback type:**
- `before_agent`: Each early-return condition, tool calls made from the callback, correct text returned, variables set correctly
- `before_model`: Interception conditions (when to bypass LLM), LlmResponse structure, no-op path
- `after_model`: Text injection conditions, no-op when text present, edge cases (whitespace text, multiple tool calls in same response)
- When callbacks call tools directly via `tools.{name}(...)`: verify the tool is called with correct args, verify behavior when the tool call fails

---

## Push and Run

After generating evals, offer to:

1. **Push goldens** — `python .agents/skills/agent-foundry/scripts/scrapi-eval-runner.py push-goldens`
2. **Push scenarios** — `python .agents/skills/agent-foundry/scripts/scrapi-eval-runner.py push`
3. **Run a quick local test** — `python .agents/skills/agent-foundry/scripts/scrapi-sim-runner.py run --priority P0 --parallel 5`
4. **Run platform evals** — goldens + scenarios
5. **Generate combined report** — `python .agents/skills/agent-foundry/scripts/generate-combined-report.py`

---

## Customer Profile Management

Evals need mock customer profiles for session parameters. When creating evals:

1. Check if existing profiles (in a CSV or YAML) match the needed test scenario
2. If not, create a new profile with the right auth status, role, service status, and relevant attributes
3. Document the profile mapping so future evals can reuse them

Profile data typically includes: account ID, customer ID (e.g., phone number or member ID), auth status, user role, service status, and relevant line/subscription counts.

---

## Review Checklist

Before finalizing, verify:

- [ ] Every PRD requirement has at least one eval
- [ ] Deterministic flows use goldens, open-ended flows use scenarios
- [ ] Golden conversations represent ideal PRD behavior (not captured agent behavior)
- [ ] Session parameters only override what the callback can't derive
- [ ] Each scenario has a matching simulation template
- [ ] Success criteria in scenarios end with "X counts as a successful outcome"
- [ ] Tags are consistent (priority, severity, PRD ID, category)
- [ ] Evals cover both happy path and failure/escalation paths
