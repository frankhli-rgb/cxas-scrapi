# GECX Agent API Reference (SCRAPI)

How to create and manage GECX agents using the `cxas-scrapi` Python library. This replaces raw curl/REST calls with typed Python methods.

## Authentication

SCRAPI picks up credentials automatically from the environment (application-default credentials or service account). No manual token management needed.

```python
# All clients take project_id + location, or app_name
from cxas_scrapi.core.apps import Apps
apps = Apps(project_id="my-project", location="us")

# Or initialize from an existing app
from cxas_scrapi.core.agents import Agents
agents = Agents(app_name="projects/my-project/locations/us/apps/APP_ID")
```

## Before Making ANY API Call

Check the actual source code — docs may be stale:
```bash
grep -A 20 "def create_" .venv/lib/python3.13/site-packages/cxas_scrapi/core/<module>.py
```

## Build Order (follow this sequence)

1. Set model on app (may fail if no root agent — catch and retry after step 3)
2. Check existing agents with `get_agents_map(reverse=True)` to avoid ALREADY_EXISTS
3. Create agents (skip existing), link sub-agents via `child_agents`
4. Associate system tools (`end_session`) — built-in, do NOT create
5. Create custom tools, associate with agents via `update_agent(tools=[...])`
6. Create variables
7. Create callbacks
8. Set root agent + model on app
9. Pull to local: `cxas-eval pull $APP_NAME --target_dir cxas_app/`
10. Run linter: `python scripts/lint.py`
11. Run build verification gates (see `references/build-verification.md`)

## Agent Proto Fields
`name`, `display_name`, `description`, `model_settings`, `instruction`, `tools`, **`child_agents`**, `before_agent_callbacks`, `after_agent_callbacks`, `before_model_callbacks`, `after_model_callbacks`, `guardrails`, `toolsets`, `transfer_rules`

## Common Mistakes
- `Agents()` needs full resource path as `app_name` — not separate project/app/location args
- `parent_agent` and `sub_agents` do NOT exist — use `child_agents`
- Set model on app BEFORE creating agents — default `gemini-2.5-flash` may not be available
- Check `get_agents_map()` before creating — duplicates cause ALREADY_EXISTS errors
- Tools must be associated via `update_agent(tools=[...])` — creating them is not enough
- `end_session` is a built-in system tool — associate it, don't create it
- `create_callback` APPENDS — be aware when calling multiple times
- Variables: use `variable_name` not `name`, only `STRING`/`BOOLEAN` types, parse counters with `int(val or 0)`

## Creation Flow

### Step 1: Create the App

```python
from cxas_scrapi.core.apps import Apps

apps = Apps(project_id=project_id, location=location)
app = apps.create_app(
    display_name="My Agent App",
    description="Customer support agent",
)
app_name = app.name  # Full resource path
```

### Step 2: Create Agents

```python
from cxas_scrapi.core.agents import Agents

agents = Agents(app_name=app_name)

# Root agent with instruction
root = agents.create_agent(
    display_name="root_agent",
    instruction="""<persona>You are a customer support agent...</persona>
<taskflow>...</taskflow>""",
)

# Sub-agents — create first, then link to root
sub_agent_a = agents.create_agent(
    display_name="sub_agent_a",
    instruction="...",
)
sub_agent_b = agents.create_agent(
    display_name="sub_agent_b",
    instruction="...",
)

# Link sub-agents to root via child_agents field
# NOTE: The proto field is `child_agents` on types.Agent, NOT `sub_agents` or `parent_agent`
agents.update_agent(
    agent_name=root.name,
    child_agents=[sub_agent_a.name, sub_agent_b.name]
)
```

**Key methods:**
- `agents.create_agent(display_name, instruction)` — `parent_agent` param does NOT work, use `child_agents` instead
- `agents.update_agent(agent_name, **fields)` — update instruction, child_agents, tools, etc.
- `agents.get_agents_map(reverse=True)` — `{display_name: resource_name}` mapping (use to check existing before creating)
- `agents.list_agents()` — list all agents in the app

**IMPORTANT:** Always check `get_agents_map(reverse=True)` before creating agents to avoid `ALREADY_EXISTS` errors.

### Step 3: Create Tools

```python
from cxas_scrapi.core.tools import Tools

tools = Tools(app_name=app_name)

# Python function tool (use for mock/stub tools when no real backend exists)
tool = tools.create_tool(
    display_name="authenticate_customer",
    tool_type="PYTHON_FUNCTION",
    python_function_code='''
def authenticate_customer(account_id: str, zip_code: str) -> dict:
    """Authenticates a customer using their account information."""
    return {"status": "authenticated", "customer_name": "Test Customer"}
'''
)
```

**System tools (`end_session`, `customize_response`, `transfer_to_agent`) are built-in — do NOT create them.**
They are always on the platform. Associate them with agents via `update_agent(tools=[...])` and reference in instructions or callbacks. The root agent MUST have `end_session`. Only add it to sub-agents if the TDD requires them to terminate calls directly — most sub-agents transfer back to root instead.

**Tool creation rules (for custom tools only):**
- `create_tool(tool_id, display_name, payload, tool_type)` — the `payload` dict key must match the proto field name for that tool type
- Valid `tool_type` values for custom tools: `python_function`, `data_store_tool`, `google_search_tool`, `connector_tool`, `open_api_tool`, `client_function`
- For `python_function`: payload has `python_code` key — function MUST have explicit return type (e.g., `-> dict`) and MUST NOT use `*args`/`**kwargs`

**Key methods:**
- `tools.create_tool(tool_id, display_name, payload, tool_type)` — create a new tool
- `tools.list_tools()` — list all tools in the app
- `tools.get_tools_map(reverse=True)` — `{display_name: resource_name}` mapping

### Step 3b: Associate Tools with Agents (CRITICAL)

Creating tools only adds them to the app. Agents CANNOT use tools until explicitly associated:

```python
# Get tool resource names
tools_map = {t.display_name: t.name for t in tools.list_tools()}

# Associate specific tools with an agent
agents.update_agent(
    agent_name=agent_resource_name,
    tools=[tools_map["my_tool"], tools_map["another_tool"]]
)
```

### Step 4: Set Variables

```python
from cxas_scrapi.core.variables import Variables

variables = Variables(app_name=app_name)

# create_variable takes: variable_name, variable_type, variable_value
variables.create_variable(
    variable_name="auth_status",     # NOT "name" — use "variable_name"
    variable_type="STRING",
    variable_value="unauthenticated"
)
```

**Key methods:**
- `variables.create_variable(variable_name, variable_type, variable_value)`
- `variables.list_variables()`

**Valid variable types:** `STRING`, `BOOLEAN` only. `INT`/`INTEGER`/`NUMBER` are NOT valid and will raise `ValueError: Invalid schema type`.

### Step 5: Create Guardrails

```python
from cxas_scrapi.core.guardrails import Guardrails

guardrails = Guardrails(app_name=app_name)

guardrail = guardrails.create_guardrail(
    display_name="profanity_filter",
    config={...},
)
```

**Key methods:**
- `guardrails.create_guardrail(display_name, config)`
- `guardrails.update_guardrail(guardrail)`
- `guardrails.list_guardrails()`
- `guardrails.get_guardrails_map()`

### Step 6: Create Callbacks

```python
from cxas_scrapi.core.callbacks import Callbacks
from google.protobuf import field_mask_pb2  # MUST import — SDK has a bug without it

callbacks = Callbacks(app_name=app_name)

# create_callback takes: agent_id (full resource path), callback_type (lowercase), python_code
callback = callbacks.create_callback(
    agent_id=root.name,           # Full resource path, NOT just UUID
    callback_type="before_agent",  # lowercase: before_agent, after_agent, before_model, after_model
    python_code="""
def before_agent_callback(callback_context):
    # Auth lookup, variable setup, etc.
    account_id = callback_context.state["account_id"]
    response = tools.Authenticate_Customer(...)
    callback_context.state["auth_status"] = response["auth_status"]
""",
)
```

**Callback rules:**
- MUST `from google.protobuf import field_mask_pb2` before using Callbacks (SDK bug)
- `agent_id` must be full resource path (e.g., `projects/.../agents/UUID`)
- `callback_type` is lowercase: `before_model`, `after_model`, `before_agent`, `after_agent`
- Function name MUST match type: `before_model_callback`, `after_model_callback`, etc.
- `before_model_callback(callback_context, llm_request)` — takes TWO args
- `after_model_callback(callback_context, llm_response)` — takes TWO args
- `before_agent_callback(callback_context)` — takes ONE arg
- `after_agent_callback(callback_context)` — takes ONE arg

**Note:** `create_callback` APPENDS — it does not replace existing callbacks.

**Key methods:**
- `callbacks.create_callback(agent_id, callback_type, code)` — appends a new callback
- `callbacks.update_callback(agent_id, callback_type, index=0, code=new_code)` — updates existing by index
- `callbacks.delete_callback(agent_id, callback_type, index=0)` — deletes by index
- `callbacks.list_callbacks(agent_id)` — returns `{field_name: [Callback, ...]}` dict

**To replace a callback:**
```python
# Delete existing, then create new
cbs = callbacks.list_callbacks(agent_id)
while len(cbs.get("before_model_callbacks", [])) > 0:
    callbacks.delete_callback(agent_id, "before_model", 0)
    cbs = callbacks.list_callbacks(agent_id)
callbacks.create_callback(agent_id, "before_model", code=fixed_code)
```

**Callback runtime API (inside callback code on the platform):**
- Access variables via `callback_context.state` (a dict), NOT `callback_context.session`
- `callback_context.state.get("key", "default")` to read, `callback_context.state["key"] = value` to write
- `llm_request.messages` (plural) NOT `llm_request.message`
- Return `None` from before_model to let LLM proceed — do NOT return `llm_request` (causes type error)
- To skip the model, return an `LlmResponse` object — `LlmResponse` and `Part` are available as globals, do NOT import them
- Parse counter variables safely: `int(callback_context.state.get("llm_steps") or 0)` — vars init to `""` which crashes `int()`
- There is no `types.CallbackContext` or `types.Content` in the SDK — do not try to introspect them

## Inspecting an Existing App

```python
from cxas_scrapi.core.apps import Apps
from cxas_scrapi.core.agents import Agents
from cxas_scrapi.core.tools import Tools
from cxas_scrapi.core.variables import Variables

app_name = "projects/.../apps/APP_ID"

# Get everything
apps = Apps(project_id=project_id, location=location)
app = apps.get_app(app_name)

agents = Agents(app_name=app_name)
agents_map = agents.get_agents_map()          # {resource_path: display_name}
agents_map_rev = agents.get_agents_map(reverse=True)  # {display_name: resource_path}

tools = Tools(app_name=app_name)
tools_map = tools.get_tools_map()

# Get a specific agent's instruction
agent = agents.get_agent(agent_resource_path)
print(agent.instruction)

# Get callback code
from cxas_scrapi.core.callbacks import Callbacks
cbs = Callbacks(app_name=app_name)
for cb in cbs.list_callbacks():
    print(cb.python_code)
```

## Testing Sessions

```python
from cxas_scrapi.core.sessions import Sessions

sessions = Sessions(app_name=app_name)

# Send a message
response = sessions.run(
    session_id="test-1",
    text="Hi, I need help with my account",
    variables={"account_id": "9820598207", "customer_id": "4444444"},
)

# Parse the response
sessions.parse_result(response)  # Pretty-prints to console

# Audio mode
response = sessions.run(
    session_id="test-2",
    text="I need help with my service",
    modality="audio",
)
```

## Evaluations

See the `eval-manager` sub-skill (`skills/run/SKILL.md`) for evaluation creation, running, and reporting. SCRAPI evaluation methods:

```python
from cxas_scrapi.core.evaluations import Evaluations

evals = Evaluations(app_name=app_name)

# List existing evals
evals_map = evals.get_evaluations_map()  # {"goldens": {...}, "scenarios": {...}}

# Create an eval
eval_obj = evals.create_evaluation({"displayName": "my_eval", "scenario": {...}})

# Run evals
run = evals.run_evaluation(evaluations=["eval_name"], modality="audio", run_count=5)

# Get results
results = evals.list_evaluation_results_by_run(run_id)
```

## Legacy REST API

If SCRAPI has issues, fall back to raw REST calls:

```bash
TOKEN=$(gcloud auth print-access-token)
BASE="https://ces.googleapis.com/v1beta/projects/${PROJECT}/locations/${LOCATION}/apps/${APP_ID}"

# List agents
curl -s "${BASE}/agents" -H "Authorization: Bearer ${TOKEN}"

# Create agent
curl -s -X POST "${BASE}/agents" \
  -H "Authorization: Bearer ${TOKEN}" \
  -H "Content-Type: application/json" \
  -d '{"displayName": "my_agent", "instruction": "..."}'
```
