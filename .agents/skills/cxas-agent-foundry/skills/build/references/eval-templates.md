# Eval Templates & Patterns

YAML templates, code patterns, and detailed guidance for creating goldens, simulations, tool tests, and callback tests.

## Contents

- [Golden YAML Template](#golden-yaml-template)
- [Simulation YAML Template](#simulation-yaml-template)
- [Tool Tests](#tool-tests)
- [Callback Tests](#callback-tests)
- [Customer Profile Management](#customer-profile-management)

---

## Golden YAML Template

**Prerequisite variables:** Goldens and sims need to include all session variables that the agent's callbacks read at startup — missing variables cause the callback to crash with a KeyError and fall through to default behavior. Read the `before_agent_callback` source code to identify which variables it accesses from `callback_context.state`, and provide all of them in session parameters.

**Watch for case sensitivity** — if the callback reads `callback_context.state["AccountID"]` (PascalCase), the session parameter must match that exact casing. A mismatch causes a silent KeyError.

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

### Golden Design Rules

These rules are enforced by the linter (E007, E008) and cause automatic FAIL if violated:

1. **Every turn MUST have an `agent` field.** If a turn has `user` but no `agent`, any agent response on that turn is flagged as "UNEXPECTED RESPONSE" and the golden automatically fails. Even if the agent's exact phrasing varies, include approximate text — the platform uses semantic comparison.

2. **`agent` MUST be a plain string.** Never use `$matchType` dicts on the `agent` field — `$matchType` is only valid inside `tool_calls.args`. The platform rejects dicts with a Pydantic validation error on push.

3. **End goldens before sub-agent transfers.** In multi-agent apps, when the root agent transfers to a sub-agent, the sub-agent's response creates turns the golden can't express (only one `agent` field per turn). This causes "UNEXPECTED RESPONSE" failures. End the golden at or before the turn that triggers the transfer.

4. **Callback-enforced responses use exact text.** Greeting, silence handling, and other callback-driven responses are deterministic — use the exact text from the callback code. LLM-driven responses vary — use approximate text and let the platform's semantic similarity scorer handle the comparison.

5. **Use `$matchType: "ignore"` for dates.** The LLM reformats dates unpredictably ("1948-07-12" vs "July 12, 1948"). Use `ignore` for date parameters in tool_calls.args.

---

## Simulation YAML Template

```yaml
- name: eval_name
  tags: [P0, HIGH, category]
  steps:
    - goal: What the sim user should accomplish
      success_criteria: What counts as success
      response_guide: "How the sim user should behave — include auth details the sim user should provide when asked"
      max_turns: 12
  expectations:
    - "What the agent should do"
    - "The agent must call a tool to check for outages in the customer's area."
    - "The agent must end the session and escalate after exhausting options."
  session_parameters: {account_id: "9820598207", customer_id: "4444444"}
```

**`tags` is required** — the sim runner filters by `--priority P0`/`P1`/`P2` using the tags field. Sims without tags are invisible to priority filters and silently skipped.

**Sim expectations can verify tool calls** using natural language. The LLM judge evaluates expectations against the full conversation transcript (including tool calls). Phrase tool expectations as behavioral descriptions, not function names — the judge sees resource IDs in the transcript, not display names:
- Good: "The agent must call a tool to check for network outages"
- Bad: "The agent must call diagnostic_lookup_tool" (judge can't match display names to resource IDs)

Include tool expectations alongside behavioral expectations to verify both WHAT the agent says and WHAT tools it calls.

For each scenario eval, create a matching simulation template — this lets the user test locally before pushing to the platform.

---

## Tool Tests

Test individual tools in isolation — faster and more precise than end-to-end conversation evals for catching tool-level regressions.

### CRITICAL: Read tool code before writing expectations

**Before writing any tool test**, you MUST read the tool's Python source code to understand the exact response structure. Tool test failures are most commonly caused by JSONPath expectations that don't match the actual keys returned by the tool.

1. Read the tool's `python_function/python_code.py` file
2. Find all `return` statements to understand the response dict structure
3. Use the exact keys from the return dict in your `$.result.<key>` paths
4. For error cases, check what key the error response uses (e.g., `$.result.agent_action` vs `$.result.error`)

**Example workflow:**
```python
# Tool code returns:
return {"member_name": "Dorothy", "active_plans": [...], "status": "success"}

# CORRECT test expectation:
expectations:
  response:
    - path: "$.result.member_name"   # matches actual key
      operator: is_not_null

# WRONG (common mistake — guessing at keys):
expectations:
  response:
    - path: "$.result.authenticated"  # key doesn't exist in response!
      operator: is_not_null
```

### Auto-generating test templates

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

### YAML format

```yaml
tests:
  - name: diagnostic_lookup_test_1
    tool: diagnostic_lookup_tool
    args:
      account_id: "6666666"
      customer_id: "123456"
    variables: {auth_status: "authenticated"}
    expectations:
      response:
        - path: "$.result.status"
          operator: is_not_null
        - path: "$.result.issue_type"
          operator: contains
          value: "service"
```

**Common pitfalls:**
- The top-level key MUST be `tests:` — using `test_cases:` causes SCRAPI to silently load 0 tests with no error.
- Each test case needs `tool:` (display name) — don't use a top-level `tool_name:` key.
- **Session state:** Tool tests run in isolation with no session state. If a tool checks `context.state` (e.g., for auth), use `variables: {auth_status: "authenticated"}` to populate state. The `context` field also exists but `variables` is more reliable for state propagation.
- Response paths MUST start with `$.result.` — tool responses are nested under `result`.

### Running tool tests

```python
test_cases = tool_evals.load_tool_tests_from_dir("evals/tool_tests")
results_df = tool_evals.run_tool_tests(test_cases, debug=True)
report_df = ToolEvals.generate_report(results_df)
```

### Operators

`equals`, `contains`, `greater_than`, `less_than`, `length_equals`, `length_greater_than`, `length_less_than`, `is_null`, `is_not_null`.

---

## Callback Tests

Test agent callbacks (before_agent, before_model, after_model, etc.) in isolation using pytest. Agent code and tests are separated for maintainability.

### Directory layout

```
evals/callback_tests/
├── agents/                    # Raw callback code from platform
│   └── <agent>/<callback_type>/<name>/python_code.py
└── tests/                     # Pytest assertions (symlinked into agents/ for SCRAPI)
    └── <agent>/<callback_type>/<name>/test.py
```

SCRAPI's `test_all_callbacks_in_app_dir` expects `test.py` alongside `python_code.py`, so tests are symlinked into `agents/`. Edit tests in `tests/`, update agent code in `agents/`.

### Running

```python
from cxas_scrapi.evals.callback_evals import CallbackEvals

cb = CallbackEvals()
results_df = cb.test_all_callbacks_in_app_dir(app_dir="evals/callback_tests")
```

### Test pattern — mock injection

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

### Adding a new callback test

1. Save the raw callback code to `agents/<agent>/<type>/<name>/python_code.py`
2. Write the test file in `tests/<agent>/<type>/<name>/test.py`
3. Symlink: `ln -sf $(pwd)/evals/callback_tests/tests/...test.py agents/.../test.py`

### Update tests when callbacks change

When you modify a callback (add logic, change tool calls, add a new early-return path), untested changes silently break — so follow up with:
1. Sync the updated code from the platform to the local `python_code.py`
2. Add tests covering the new/changed behavior
3. Run all callback tests to verify no regressions

### What to test per callback type

- `before_agent`: Each early-return condition, tool calls made from the callback, correct text returned, variables set correctly
- `before_model`: Interception conditions (when to bypass LLM), LlmResponse structure, no-op path
- `after_model`: Text injection conditions, no-op when text present, edge cases (whitespace text, multiple tool calls in same response)
- When callbacks call tools directly via `tools.{name}(...)`: verify the tool is called with correct args, verify behavior when the tool call fails

---

## Customer Profile Management

Evals need mock customer profiles for session parameters. When creating evals:

1. Check if existing profiles (in a CSV or YAML) match the needed test scenario
2. If not, create a new profile with the right auth status, role, service status, and relevant attributes
3. Document the profile mapping so future evals can reuse them

Profile data typically includes: account ID, customer ID (e.g., phone number or member ID), auth status, user role, service status, and relevant line/subscription counts.
