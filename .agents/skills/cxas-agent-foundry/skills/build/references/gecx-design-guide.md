[EXTERNAL] GECX Agent Design Guide
Author:  

## Contents

- [Background](#background)
- [Summary of best practices](#summary-of-best-practices)
  - [Instructions](#instructions)
  - [Architecture](#architecture)
  - [Variables and state management](#variables-and-state-management)
  - [Tool design](#tool-design)
  - [Error handling](#error-handling)
  - [Advanced patterns](#advanced-patterns)
- [Instructions Format](#instructions-format)
  - [Role](#role)
  - [Persona](#persona)
  - [Ambiguity](#ambiguity)
- [Agent Architecture](#agent-architecture)
  - [Single-Agent](#single-agent)
  - [Multi-Agent](#multi-agent)
  - [Using the multi-agent framework](#using-the-multi-agent-framework)
- [Variables](#variables)
- [Tool Design](#tool-design-1)
  - [Common Tooling Pitfalls](#common-tooling-pitfalls)
  - [Tool wrappers](#tool-wrappers)
- [Error Handling](#error-handling-1)
  - [Callback Patterns for Deterministic Behavior](#callback-patterns-for-deterministic-behavior)
  - [Instruction Design Anti-Patterns](#instruction-design-anti-patterns)
  - [Common Error Handling Pitfalls](#common-error-handling-pitfalls)
- [Callbacks](#callbacks)
- [Source Control](#source-control)
- [Advanced techniques](#advanced-techniques)
  - [Dynamic Prompting](#dynamic-prompting)
  - [Instructions in a tool response](#instructions-in-a-tool-response)

## Background
LLMs today are highly capable and serve as fundamental building blocks for agent building. Providing the right context will enable them to solve complex problems. By orchestrating multiple LLM calls together as autonomous agents, developers can automate human-level reasoning tasks. 

However, building an enterprise-grade agentic system is not a simple task given the following model limitations that we see today:
Faithfulness: The agent may hallucinate
Instruction Following: The agent may not always follow the instructions; specifically:
It may skip instruction steps
It may follow the steps in the wrong order
It may follow the wrong instructions
It may only do parts of the tasks you instructed
Tool calling: The agent might not 
It may not call a tool when it is required to
It may call the right tool, but with the wrong parameters
It may call the right tool, but with extra, unneeded parameters

These problems get magnified as the instructions grow bigger, or as conversation goes longer. Because of this, we generally advocate for a multi-agent architecture that uses tools to maintain state and dynamically inject instructions during the flow of the conversation.

While writing clear and unambiguous instructions is the most critical component to mitigating these factors as much as possible, there are also other techniques that have been proven to work. This guide synthesizes some of the practices that have worked for agents in production. 

When we treat prompts as "vibes" or polite requests and let Gemini figure it out, we will get inconsistent results. When we treat them as software, with explicit well defined algorithms, inputs, outputs, and error handling, we achieve higher reliability and consistency. 
## Summary of best practices
### Instructions
XML Formatting: Use structured tags (e.g., <role>, <step>) to improve instruction following and model parsing.
Unambiguous Instructions: Be clear and concise; ambiguity is the enemy of execution.
### Architecture
Start Simple: Begin with a single-agent architecture for prototypes and linear flows to maintain lower latency and speed; then pivot to a multi-agent architecture once you introduce 2+ capabilities
Modular Design: Build reusable sub-agents (e.g., an "Authentication" agent) and isolate them to specific use cases to minimize lossy handoffs.
Determinism: Find opportunities to offload logic from instructions to callbacks and tool calls.
Agents as Code: Utilize standard versioning and peer review processes.
Test Driven Development: Create evals even before you create your agent to guide the efficacy of your prompts.

### Variables and state management
JSON Schemas: Use structured schemas rather than a long list of individual variables to prevent "variable explosion" and context degradation.
Semantic Naming: Name variables descriptively so the model understands their contextual importance.

### Tool design
Tools Wrappers: Favor tool wrappers over sequentially calling tools in instructions and high cardinality OpenAPI tools to mitigate latency and cascading failures.
Descriptive Docstrings: Treat tool descriptions as core instructions for accurate invocation routing.

### Error handling
Early Validation: Verify mandatory inputs and prerequisites before calling external services.
Actionable Recovery: Return an agent_action key in failures to provide the model with deterministic recovery steps.

### Advanced patterns
Dynamic Prompting: Update instructions via callbacks to minimize active context
Progressive Disclosure: Embed instructions in tool responses to trigger rules only when relevant.

## Instructions Format
While you can write your instructions in natural language, your agent will perform better if you format instructions using an XML structure, which can help the model better follow instructions. Use the following XML tags when building your instructions: 



See our public docs for more information, and utilize Gemini for XML parsing. 

Familiarize yourself with the published best practices before starting. 
### Role
Define a unique and highly specific role for each agent to ensure clarity. Maintain the highest level of specificity possible, leveraging Gemini to brainstorm a robust persona definition that makes it clear what the purpose of the agent is and avoids ambiguity.

#### Bad Role Example

You are a Store agent.

#### Good Role Example

<role>
    You are a Troubleshooting Support Specialist. Your primary goal is to understand a user's problem thoroughly, and then guide them through the appropriate troubleshooting and support actions to resolve their issues effectively.

    You are NOT a robot reading a script; you are a professional and empathetic support specialist whose job is to partner with the user to deeply understand their problem and guide them to the right solution.
</role>

### Persona
The persona should be set globally so that the agent is consistent across the entire conversation. Similar to a goal, be specific as to how you want your agent to behave. Here is a good starting point. 

<persona>
    - Your tone MUST be professional, warm, and helpful.
    - Use clear, simple, and direct language that is easy to follow.
    - Favor being direct. When an acknowledgment is necessary, cycle through a wide variety of phrases (e.g., "Sure,", "Got it," "Okay") to keep the conversation natural and avoid using the exact same phrase multiple times.
    - Speak with a slow, rhythmic cadence appropriate for a phone conversation.
    - You speak with a standard American English accent and female voice. Your pronunciation, enunciation, and prosody must consistently reflect a standard US accent at all times. <-- MODIFY THIS FOR YOUR LOCALE AND GENDER
</persona>


### Ambiguity
Write your instructions to be as clear as possible. When in doubt, use gemini to help you iterate on your prompt. 

#### Ambiguous Example

<subtask name="Clarification_and_Disambiguation">
        <step name="Assess_Input_Quality">
            <trigger>User input received.</trigger>
            <action>
                1. **IF VAGUE:** Ask a clarifying question.
                2. **IF SPECIFIC:** IMMEDIATELY trigger `Formulate_and_Execute_Query`. Do not attempt to answer.
            </action>
        </step>
</subtask>
Rationate: We do not define what is vague and what is specific, which leaves the LLM to get overly creative, which leads to agent instability.








#### Clear Example

<step name="Clarify_User_Problem">
        <trigger>User states their problem.</trigger>
        <action>
          1. **Analyze user's problem for specificity (The Actionability Test):** thoroughly analyze the user's problem synthesized across `{user_problem}` and the full conversation history. Apply the "Actionability Test": *If you handed this problem statement to another support agent with no other context, would they know exactly how to troubleshoot without needing to ask more clarifying questions?*
            - **FAIL (Generic/Vague):**
              - "It's broken", "It's not working", "It's acting weird", "It's glitching".
              - "It is slow" or "It's lagging" (Without context: i.e. what is slow? boot up? a specific app?).
              - "It's showing an error message" (What error message?)
            - **PASS (Specific/Actionable):**
              - [Component] + [Symptom] (e.g., "Laptop screen has black spots", "iPad Screen is cracked", "Printer is making a grinding noise", "Laptop keyboard keys are physically stuck").
              - [Function] + [Failure] (e.g., "My laptop says it is connected to the WiFi, but no websites will load", "Microsoft Word crashes on startup", "iPad is completely unresponsive to touch and button presses").
            - **Critical:** This test is mandatory for ALL product and device types without exception.
          2. **Decision Logic:**
            - If the problem **FAILS** the Actionability Test: Proceed to Action 3.
            - If the problem **PASSES** the Actionability Test: transition to `Classify_Problem_And_Route`.
          3. **Multi-Turn Clarification Loop:** Your primary goal here is deep understanding. You MUST continue asking targeted, empathetic follow-up questions until the problem is specific enough to pass the Actionability Test. It is expected that this may take more than one turn.
              <inline_examples>
			...
              </inline_examples>
          4. **Synthesize and Update:** Once the user's problem is fully clarified and passes the Actionability Test:
            - **Synthesize:** Combine the original problem statement and the newly clarified details into a rich problem statement.
            - **Update:** Silently call `{@TOOL: set_user_problem}` with the new complete problem description.
            - Proceed to `Classify_Problem_And_Route`.
        </action>
      </step>
Rationale: There is clear guidance for what queries need additional clarification. 

## Agent Architecture
When you begin agent building, one of the most critical decisions is whether you will build a single agent framework or a multi-agent framework.

Single Agent: Implement a single, comprehensive instruction set supported by multiple tools to maintain unified agent logic.
Multi Agent: Decompose the system into specialized sub-agents, each governed by a dedicated prompt, utilizing handoffs to manage distinct taskflows. The multi-agent framework has a root agent with intent detection, which then passes off to a sub-agent to execute any particular use case.

You should start with a single agent, then decompose into specialized agents as conversational complexity increases or if instruction following begins to degrade. Breaking up agent logic into more “bite sized” pieces helps improve context management for the agent, which will lead to better performance. 

To illustrate, imagine a retail agent that has 100 capabilities. However, it doesn’t need access to all those capabilities at once; if a customer asks “where is my order?” the agent only needs to access the logic for handling order status. If you give the agent that context, but also the context for the 99 other intents, the agent is likely to make a mistake, because it might not know which instructions to follow.

So, while starting with a single agent approach is the simplest, note that if you have many use cases on your customer roadmap, you will likely need to pivot to a multi-agent architecture.




### Single-Agent
A single agent uses one single prompt to define all agent behaviors at the root level.

A single agent framework is best in the following circumstances:
Quick prototypes and testing
Simple and straightforward conversations (ex: show my cart items, status of an order, etc.)
Linear conversation flows (simple branches and start/end states)
Simple state definitions and transitions

Examples for Single Agents: A Password Reset Assistant or an Order Status Checker. Single-agent architectures excel when interactions require a linear task flow and straightforward conversation without complex cognitive branching.


#### Benefits of Single Agent
Higher implementation velocity: A single agent framework can be built rapidly
Lower turn latency: Since logic is contained in a single LLM call, this will typically be faster than a multi-agent approach

#### Limitations of Single Agent
Behavior Drift: The model's output or personality may inconsistently shift over the course of an interaction
Tool Call Issues: Model may fail to execute tools or provide incorrect parameters during the invocation
Context Rot: As the history length increases, conversational coherence and instruction following degrades
Instruction Overload: The model starts to ignore or skip logic as instructions become more complex, too many rules, ambiguity, conflicting instructions
Collaboration: Hard for multiple people to make changes to the same agent

### Multi-Agent
A multi-agent architecture is the preferred architecture for agents that have multiple (2+ capabilities). This is best in the following circumstances:
If the role/persona are meaningfully different between use cases
If you have multiple disjoint CUJs that do not need to share context
A CUJ is highly complex and can be broken down by multiple distinct (ideally sequential) logical steps
When your single-agent is still having trouble following instructions even after extensive quality hill climbing

#### Benefits of Multi-Agent Architectures:
Debugging: Provides precise isolation and resolution of logic failures within specific sub-agent contexts (Use code tree walk from root agent to sub agents/tools to identify failure points)
Targeted Evaluation: Enables the implementation of specialized evals(golden and scenarios) for individual agent states.
Instruction Modularity: Promotes loose coupling of instruction sets, mitigating the risk of context rot and instruction overload.
Enhanced Encapsulation: Provides control over tool invocation routing and functional parameter precision through dedicated sub-agents
Architectural Scalability: Establishes a modular design that efficiently scales to accommodate increasing conversational complexity through specialized sub-agents.

#### Limitations of Multi Agent
Latency: Passing context from one agent to another can add latency
Context loss: While variables can preserved, some context will be lost when handing off from one sub-agent to another
Development time: A multi-agent framework is more complex, which leads to longer development time


A simple test is to offload part of the agent logic (instruction + tool def) to a standalone LLM call with specialized prompt - if that yields better results, it may hint towards splitting off into a specialized agent

### Using the multi-agent framework
With the benefits of the multi-agent framework in mind, it is best to think about how to break up the business logic into individual use cases. The best way to think about this is to follow two best practices:
Build sub-agents that can be re-used across multiple intents (e.g., an “authentication” agent that could be used across various secure use cases for a banking agent)
Isolate sub-agents to specific use cases that reflect the customer journey to minimize a sub-agent handing off to another sub-agent (which will introduce context loss)

Below are some examples illustrating both bad and good ways to use the multi-agent framework.

#### Bad usage of multi-agents



Why this is bad:
Flow Fragmentation: The underlying CUJ represents a single, fluid conversational flow that does not necessitate agent decomposition (that being scheduling an appointment)
Context Degradation: Agent handoffs are inherently lossy, significantly increasing the probability that critical conversational context is lost during the transfer.
Experience Disruption: Excessive transfer of control creates a disjointed customer experience, forcing users to repeat data while simultaneously escalating architectural complexity and turn latency.
#### Good usage 


#### Architectural Rationale
Functional Specialization: Decomposes agents only when roles or personas are distinctly different to ensure focused, unambiguous logic.
Contextual Isolation: Targets disjointed Customer User Journeys (CUJs) that do not require shared context, effectively mitigating lossy handoff risks.
Operational Reliability: Segments complex CUJs into discrete, sequential logical steps to maintain high-fidelity instruction following.
Architectural Scalability: Enables scaling across multiple specialized specialists while facilitating precise evaluation and debugging within isolated contexts.

## Variables
Variables serve as the foundational architecture for maintaining agent state, providing the necessary visibility and structure for robust management. They are key for dynamic prompting. Adhere to the following patterns when defining your variables:
Observability Variables: Best practices for internal monitoring
Lenses into State: View these as diagnostic debug windows that provide insight into the internal logic of your agent.
Naming Conventions: Apply consistent patterns, such as underscore prefixes, to distinguish them from core logic variables.
JSON Schemas: Capture complex state data within structured schemas rather than managing a fragmented list of individual variables.
State Management: Guidelines for efficient state control
Variable names: Important to note that variable values are not substituted in prompts, changes to variable values are provided as part of conversation history. It is important to give semantically descriptive names for the model to understand the importance of variables in the context.
When to use State Variables: Use state variables to collect/update information, perform routing/state transitions, remember checkpoints
Variable Explosion: Implement JSON schemas to mitigate the complexity and "context rot" caused by an excessive number of state variables.
Feature Encapsulation: Consolidate variables related to a specific tool or logical feature into a single, unified JSON state variable.
Deterministic Steering: Use state variables as the primary mechanism for directing tool calls and callback triggers.
Dynamic Prompting: Leverage variables to enable advanced, context-aware prompt updates programmatically.
Instruction Density: Since variables determine instruction complexity, retain only those vital for decision-making and eliminate "ghost" variables.


Contrary to common belief, variables are not directly substituted into the prompt; instead, the agent tracks the entire history of variable updates to maintain state. 
## Tool Design
An agent is only as capable as its environment. A good tool design bridges the gap between reasoning and action, transforming a static model into a dynamic problem-solver. A good tool design prioritizes low latency and high reliability.

Implement tools to encapsulate deterministic logic or manage external system integrations required by your agent. Transactional tools, informational tools, orchestration tools. 

Adhere to the following guidelines when defining your tool architecture:
Tool Name: Utilize a semantically descriptive identifier that clarifies the tool's function, as the model relies on this for invocation routing.
Tool Description: Provide a comprehensive explanation of the tool’s core utility. The model uses this to determine when to call the tool.
Input Arguments: Define the specific parameters required for execution. The model uses this to decide how to call the tool. As a thumb rule, practice designing tool inputs that are easily expressible by humans in voice mode. Try saying the example inputs out loud and estimate difficulty for a human to express these inputs without mistakes/errors. 
Output Schema: Specify a structured format for returned data to maintain logic consistency. This output schema should only include data that is needed by the LLM.
Examples: Include few-shot scenarios to reinforce correct tool utilization patterns. This helps the model call the tool properly and reduces erroneous invocations.
Mocks: Figure out how to test your tool if it is making a real call

Tool docstrings are equivalent to instructions. You should treat them with utmost importance. See our public docs for more information.

#### Bad tool design

def check_info(id):
  return db.fetch_balance(id)
Rationale: Without meaningful docs, named parameters and return values, the LLM will not know how to appropriately call the tool. E.g. if you have multiple "ids" in your context, the LLM may get confused as to which one to use here.
#### Good tool design

def retrieve_customer_account_balance(customer_id: str) -> dict:
  """Retrieves the current outstanding balance for a specific customer.
  
  Args:
    customer_id: The unique alphanumeric identifier for the customer.
    
  Returns:
    A dictionary containing the 'balance' (float) and 'currency' (str).
  """
  return db.fetch_balance(customer_id)


### Common Tooling Pitfalls
Ambiguous Tool Naming: Employing semantically similar identifiers (e.g., "check_appointment" vs. "check_booking") introduces ambiguity that significantly degrades invocation routing accuracy.
Complex Input Arguments: Constructing intricate schemas—such as dictionaries, lists, or free-form strings—increases the probability of the model supplying erroneous parameters during tool execution.
High Cardinality Arguments: Providing parameters with an extensive range of potential values can reduce the model's ability to select tools deterministically. Avoid using input arguments that expect values in a continuous scale or have high cardinality (bad examples: exact_timestamp_ms, raw_latitude_longitude, or unique_session_id). Design good arguments that a human can express in voice mode as a thumb rule(Ex: region/country, last_n_days, topic_category etc).
Tool Explosion: Exposing an excessive volume of tools within a single agent context often leads to instruction overload and diminished routing precision.
Execution Latency: High-latency operations result in "dead air"; utilize filler statements to maintain engagement when long-running tool calls are unavoidable.
Tool Return Value Explosion: The LLM sees the entire tool response. Returning excessive volumes of data, specially data that the LLM does not need can bloat the context and can result in degraded performance
Sequential tool calls in instructions: Relying on the model to execute multiple tools in a specific order through natural language instructions can often lead to skipped steps, incorrect sequencing, or the use of wrong parameters when tool calls are chained in prompts.

### Tool wrappers
Write "unified" tool wrappers to encapsulate multiple operations and sequential API calls within a single execution block. You can also use a similar pattern for wrapping OpenAPI tool calls that return irrelevant data to the LLM.

Utilize the following functional consolidation patterns:
Functional Orchestration: Replace fragmented `get_available_slots` and `create_event` tools with a comprehensive `schedule_event` tool to handle availability and reservation logic in one turn
Contextual Filtering: Prefer a specialized `search_logs` tool that isolates high-relevance log segments and diagnostic context over a raw, high-cardinality `list_logs` invocation and filtering in the instructions.
State Aggregation: Consolidate `get_customer_by_id`, `list_transactions` and `list_notes` into a single `get_customer_context` tool to provide a unified, structured data schema immediately.
See our docs for more information.
## Error handling
### Architecting for Robust Error Handling
Early Prerequisite Validation: Prioritize the verification of mandatory inputs and context variables before executing core logic or initiating external service calls. Design variables specifically for information gathering and error capturing to ensure complete context before proceeding.
Graceful Exception Handling: Implement structured try-except blocks for all external integrations, including API calls, database operations, and file systems. Ensure the agent handles exceptions gracefully to prevent logic degradation.
Failure Categorization: Explicitly distinguish between tool invocation failures and logical errors returned in the response to maintain high routing precision and appropriate recovery behavior.
Deterministic Recovery Actions: When an error occurs, the tool MUST return a dictionary with an agent_action key. This provides the model with exact instructions on what to communicate to the user and how to transition to a corrective taskflow.
Enhanced Observability: Log granular failure details and update internal state variables during error handling. Use these observability lenses as diagnostic windows for debugging agent performance.
Docstring Failure Schematics: Clearly define the structured format of the failure response within the tool's docstring to guide the model's understanding of failure states.

### Callback Patterns for Deterministic Behavior

Use callbacks when behavior MUST be deterministic — don't rely on instructions alone for critical flows like escalation, goodbye messages, or session termination.

#### Deterministic farewell before end_session: Use `after_model_callback` to inject text before the session terminates. The LLM often calls `end_session` without saying anything first.

#### Multi-model-call turns: The LLM can split a single turn across multiple model calls (e.g., text in call 1, a payload update tool in call 2, end_session in call 3). The `after_model_callback` fires on EACH model call separately. A naive check for "no text in this response" would inject text on call 3 even though text was already produced in call 1 — causing double-text.

#### Fix: Use `Part.text_or_transcript()` for audio-safe text detection, and `callback_context.events` to check if the agent already produced text in a prior model call within the same turn. This eliminates the need for state variable hacks.

```python
def after_model_callback(callback_context, llm_response):
    has_end_session = False
    has_text_this_call = False
    for part in llm_response.content.parts:
        if part.has_function_call('end_session'):
            has_end_session = True
        else:
            # text_or_transcript() handles both text and audio transcripts
            content = part.text_or_transcript()
            if content and len(content.strip()) > 0:
                has_text_this_call = True
    if not has_end_session or has_text_this_call:
        return None
    # Check if agent already produced text in an earlier model call
    for event in reversed(callback_context.events):
        if event.is_user():
            break  # reached last user message — no prior agent text
        if event.is_agent():
            for p in event.parts():
                content = p.text_or_transcript()
                if content and len(content.strip()) > 0:
                    return None  # agent already said something
    # No text anywhere — inject farewell
    new_parts = [Part.from_text(text="Please hold while I transfer you.")]
    new_parts.extend(llm_response.content.parts)
    return LlmResponse.from_parts(parts=new_parts)
```

#### Key built-in methods (see [Python runtime reference](https://docs.cloud.google.com/customer-engagement-ai/conversational-agents/ps/reference/python)):
- `Part.text_or_transcript()` — returns text if available, otherwise audio transcript. Use instead of `part.text` for audio-safe detection.
- `Part.from_end_session(reason, escalated)` — creates end_session Part without manual function_call construction.
- `Part.from_agent_transfer(agent)` — creates agent transfer Part.
- `CallbackContext.events` — full session event history. Use `event.is_user()` / `event.is_agent()` / `event.parts()` to inspect.
- `CallbackContext.agent_name` — current agent's display name.
- `Event.is_agent(agent_name)` — check if event is from a specific agent.

#### Deterministic escalation with text: Use `LlmResponse.from_parts` to combine text + agent transfer in a single response.

```python
return LlmResponse.from_parts(parts=[
    Part.from_text('Let me transfer you to a specialist.'),
    Part.from_agent_transfer(agent='escalation_agent')
])
```

#### Deterministic greeting: Use `before_model_callback` to intercept the first turn and return a static greeting, saving model calls.

```python
def before_model_callback(callback_context, llm_request):
    for part in callback_context.get_last_user_input():
        if part.text == "<event>session start</event>":
            return LlmResponse.from_parts(parts=[
                Part.from_text(text="Hello, how can I help you today?")
            ])
    return None
```

#### Silence handling (voice agents): Use `before_model_callback` to detect "no user activity" signals and respond deterministically. The platform sends `<context>no user activity detected for X seconds.</context>` when the user is silent. Without a callback, the LLM may hallucinate a response or ask unrelated questions.

Pattern: track a `no_input_counter` in state. On 1st silence, repeat the last agent message ("Sorry, I didn't hear anything. [last message]"). On 2nd, repeat again with different prefix. On 3rd, end the session gracefully. Reset the counter whenever the user speaks.

```python
def before_model_callback(callback_context, llm_request):
    import re
    silence_pattern = r"<context>no user activity detected for \d+ seconds\.</context>"
    contents = llm_request.contents
    is_silent = len(contents) > 1 and any(
        re.search(silence_pattern, p.text, re.IGNORECASE)
        for p in contents[-1].parts if p.text
    )
    if not is_silent:
        callback_context.state["no_input_counter"] = "0"
        return None

    count = int(callback_context.state.get("no_input_counter", 0)) + 1
    callback_context.state["no_input_counter"] = str(count)

    if count < 3:
        # Repeat last agent message with a prefix
        return LlmResponse.from_parts(parts=[
            Part.from_text(text="Sorry, I didn't hear anything. Can you repeat that?")
        ])
    else:
        return LlmResponse.from_parts(parts=[
            Part.from_text(text="I'm unable to hear you. Please try calling again later."),
            Part.from_end_session(reason="no_input_limit"),
        ])
```

See `assets/project-template/` for a full implementation with message repetition.

#### Calling tools from callbacks: Callbacks can call tools directly via the `tools` global — not just return text. This lets you move entire deterministic flows (flag check → tool call → text response) into a single callback, bypassing the LLM completely.

```python
def before_agent_callback(callback_context):
    # Fully deterministic: flag check → tool call → escalation text
    if str(callback_context.state.get("api_failed", False)).lower() == "true":
        tools.payload_update_tool({
            "summary": "Escalated due to API failure",
            "escalation_reason": "API failure",
            "main_topic": "Customer Issue"
        })
        return Content(parts=[Part.from_text(
            text="Please hold while I transfer you to a customer representative."
        )])
    return None
```

#### Tool naming in callbacks: The callable name depends on the tool type:
- **Python function tools** (custom code): `tools.{function_name}(args)` — use the function name directly (e.g., `tools.payload_update_tool(...)`)
- **API connector tools** (OpenAPI): `tools.{DisplayName}_{OperationId}(args)` — concatenate the display name and operation (e.g., `tools.Read_Customer_Datastore_readDatastore(...)`)
- **System tools** (`end_session`): Cannot be called from callbacks — these are platform-level actions

#### Platform tool resolution errors bypass Python try/except. If you use the wrong tool name, the platform throws an error before your Python code executes — `try/except` won't catch it. Always verify the exact tool name from the platform before using it in callbacks.

#### When to move logic from instruction to callback: If the behavior is a simple check (variable/flag) followed by a fixed response and tool calls — with no LLM judgment needed — it belongs entirely in a callback. If the behavior requires interpreting user intent (e.g., detecting a specific issue category in free text), the detection stays in the instruction but the action can be callback-driven via a flag.

#### Trigger pattern for deterministic tool calls: The LLM decides WHAT to do (detection), the callback decides HOW (execution). The instruction tells the LLM to set a state variable (via a state-setting tool), then the `before_model_callback` intercepts the next model call and returns the tool calls with correct args — bypassing the LLM entirely. This prevents missing tools, empty args, and unwanted agent transfers. The state-setting tool and trigger variable name are project-specific — create a tool that writes to session state, and pick a trigger key name (e.g., `_action_trigger`).

#### Critical: The state-setting tool MUST be in the agent's tool list. If the instruction references a tool the agent can't access, the LLM will silently improvise — calling other tools directly or skipping the action entirely. Always verify tool availability.

```python
# In the instruction:
# "Then call {@TOOL: state_setting_tool} with _action_trigger='some_action'"

# In before_model_callback:
trigger = callback_context.state.get("_action_trigger", "")
if trigger:
    callback_context.state["_action_trigger"] = ""
    return LlmResponse.from_parts(parts=[
        Part.from_function_call(name="my_tool", args={"key": "derived_value"}),
        Part.from_function_call(name="end_session", args={...})
    ])
```

#### Preventing empty tool args: The LLM sometimes calls tools with `{}` args. Defense in depth:
1. **Better docstrings** — mark parameters as `(REQUIRED)` with concrete examples. The LLM reads tool schemas when deciding what args to pass. This is the most important fix.
2. **Tool-level fallback** — modify the tool's Python code to read from state when args are empty or missing required keys.
3. **Trigger pattern** — the `before_model_callback` provides the tool with correct args as a backup when the LLM sets the trigger.

```python
# In the tool's Python code — state fallback:
def my_tool(arg1, arg2):
    if not arg1:  # empty arg fallback
        arg1 = context.state.get("_fallback_arg1", "default")
```

#### Avoid `hide_tool()` as a primary strategy. While `llm_request.config.hide_tool()` prevents the LLM from calling a tool directly, it reduces the LLM's overall tool awareness and causes worse instruction-following. The LLM performs best when it sees all available tools. Use `hide_tool()` only for tools the LLM should genuinely never call (internal system tools), not as a workaround for empty args.

#### Trigger recovery: When the LLM says the expected text but forgets to call the state-setting tool, the `after_model_callback` can detect the agent's own output and set the trigger for the next model call. This is not overfitting — it detects the agent's instruction-driven text, not user input.

#### Multi-agent callbacks: In multi-agent architectures, the trigger-handling `before_model_callback` must exist on ALL agents that handle user messages — not just the root agent. When the user's message goes to a sub-agent, the root's callbacks don't fire.

#### Don't overfit with callbacks. Callbacks should enforce EXECUTION, not reimpliment DETECTION. Signs of overfitting:
- Hardcoded phrase lists in callbacks (e.g., `["unacceptable", "ridiculous"]`) — these miss natural variations like "I'm fed up" or "this is frustrating"
- Callbacks that bypass the LLM for intent classification — a customer saying "connect me to someone" won't match a hardcoded "live agent" phrase
- Overly specific trigger text in dynamic instructions (e.g., "If customer EXPLICITLY said 'current line'") — the LLM should understand intent, not match keywords

The agent might pass goldens with phrase matching, but it will fail on real customer conversations that use different words. Sims (which allow natural conversation variance) are a better proxy for real-world performance than goldens.

#### Simpler instructions outperform complex ones. Adding programmatic logic to instructions (state-tracked counters, multi-step conditionals, explicit keyword requirements) confuses the LLM. A simple "On the FIRST attempt... On the SECOND attempt..." works better than "First call the state-setting tool to increment count, then check count value and branch." The LLM handles natural language patterns better than code-like logic.

#### Don't fight the LLM. Approaches that PREVENT the LLM from doing things consistently perform worse than approaches that GUIDE it:
- `hide_tool()` reduces tool awareness → worse instruction-following overall
- "Do NOT call this tool" in instructions → confuses the LLM
- Removing tools from agent config → breaks instructions and goldens that reference them
- Complex programmatic logic in instructions → LLM handles natural language better

Instead, GUIDE the LLM: clear instructions, good tool docstrings with `(REQUIRED)` markers, and callbacks as a safety net (trigger pattern, text injection, tool-level state fallback).

#### Tool docstrings guide the LLM: The LLM reads tool descriptions and parameter docstrings when deciding what args to pass. Clear docstrings with `(REQUIRED)` markers and concrete examples reduce empty-arg calls. Fix typos in arg names — the LLM uses them for parameter matching.

#### Never remove tools without auditing instructions first. Removing a tool from an agent config breaks any instruction, golden, or sub-agent constraint that references it. Audit ALL agents' instructions and goldens before removing.

#### Key principle: Instructions tell the LLM WHAT to do (detection), callbacks ENFORCE HOW (execution). Keep detection generative and natural. Make execution deterministic and reliable.

### Instruction Design Anti-Patterns

These patterns cause regressions in practice. Avoid them.

| Anti-Pattern | Why It Fails | Do This Instead |
|-------------|-------------|----------------|
| Wholesale instruction rewrites | LLM relies on verbose context; "cleaner" versions lose information the model needs | Make small, targeted edits. Test after each change. |
| `conditional_logic` for intent classification | LLM gets confused by priority-ordered conditionals and falls back to generic refusals | Use separate `<step>` elements with distinct triggers |
| Negative conditions in triggers ("NOT [excluded category]") | LLM treats the negative as something to check, gets confused | Use positive triggers only; put the excluded case as an earlier, separate step |
| Eager follow-up triggers ("After answering any question") | Fires after sub-agent returns, causing wrong responses | Use specific triggers tied to resolution points |
| Relying on instruction for text-before-escalation | LLM calls tools without speaking first, ignoring "First Respond" text | Use `after_model_callback` to inject text before `end_session` |
| Simplifying instructions by removing examples/context | LLM loses the context it was depending on for correct behavior | Keep examples and context; reduce redundancy instead |
| Hardcoded phrase lists in callbacks for detection | Misses natural variations ("I'm fed up" won't match `["unacceptable"]`). Agent overfits to evals, fails real conversations | Keep detection in instructions (LLM understands intent). Use callbacks only for execution (trigger pattern) |
| Complex programmatic logic in instructions | State-tracked counters, multi-step conditionals confuse the LLM and reduce reliability | Use simple natural language: "On the FIRST... On the SECOND..." The LLM handles this better than code-like logic |
| Overly specific trigger keywords ("EXPLICITLY said 'current line'") | Makes the agent rigid and keyword-dependent instead of understanding intent naturally | Use natural language triggers. Trust the LLM's understanding of context |
| Escalation tool calls in instruction only | LLM sometimes says text but forgets to call tools, or calls them with empty args | Use trigger pattern: instruction sets a state trigger via a state-setting tool, callback returns tools |
| Escalation trigger callbacks on root agent only | Sub-agent flows bypass root callbacks — trigger never fires | Add trigger-handling `before_model_callback` to ALL agents |
| Using `hide_tool()` to prevent empty-arg calls | Reduces LLM's tool awareness, causes worse instruction-following overall | Use better docstrings + tool-level state fallback + trigger pattern instead |
| "Do NOT call this tool" in instructions | Confuses the LLM, often reduces tool calling reliability | Guide with positive instructions ("call {@TOOL: state_setting_tool} with...") not negative constraints |

### Common Error Handling Pitfalls
Ambiguous Error Feedback: Utilizing generic messaging such as "An error occurred" or "Failed to receive data" provides no actionable guidance for the agent to execute a deterministic recovery.
Schematic Inconsistency: Discrepancies between a tool's docstring and its actual failure response structure significantly degrade the model's ability to route and interpret error states correctly.
Inadequate Observability: Failing to implement granular logging for tool executions and internal state updates obscures the diagnostic windows required for robust debugging.
API Response Neglect: Validating only the HTTP status code while skipping content validation of the response payload prevents the agent from identifying and acting upon critical logical errors.
Generic Exception Swallowing: Implementing broad exception catches can mask underlying failures, preventing the agent from performing graceful degradation or corrective taskflows.
Context Completeness Bias: Assuming that mandatory prerequisites and state variables are always present without proactive verification leads to degradation in instruction following.

### Example: Tool Error Handling
## Callbacks
A callback is a python function which the system then triggers automatically when a specific event occurs. There are multiple different events that callbacks support (e.g. model callbacks, agent callbacks and tool callbacks). 

Callbacks are a mechanism to add predictability into the agent that would have otherwise been approximated via instructions. You should find opportunities to use offload instructions to callback when possible. 

These can include cases like:
Greetings upon agent start
Silence handling
Handoff messages
Triggering a tool on agent transfers for seeding agent context

See our documentation for some creative examples on how to use callbacks.
## Source Control
You can use the UI to build agents, but you must get them checked into source control (github, gitlab, etc) for easier management. Use SCRAPI to help you sync back and forth between the UI and source control.


# Pull an App
# Download and unpack an app into a local directory:
```bash
cxas pull {app_identifier} --project_id {project_id} --location {location} --target_dir {local_dir}
```

# Push Local Files
# Upload the local agent directory to CXAS:
```bash
cxas push --app-dir {local_dir} --to {app_identifier} --project_id {project_id} --location {location}
```

# Branch an App
# Duplicate an existing app (pulls source -> creates new -> pushes content):
```bash
cxas branch "{source_app}" --new_name "{new_display_name}" --project_id {project_id} --location {location}
```

Using source control also enables multiple developers to work on the same app and maintain a single source of truth without stepping on other people's toes. The recommended pattern is for every developer is to mimic software engineering best practices. i.e.:
Branch: Create a branch of the agent, so that they have their own sandbox
Modify: Implement the feature that they're working on, including adding evals
Review: Get a code review from someone on your team
Merge:  Push the agents back to the main source repository

## Advanced techniques
Even after writing your instructions clearly and unambiguously, if your agent is having difficulty following instructions, tool calling accuracy or other general issues, here are some advanced patterns that you can use. If you do have to use any of these patterns, book office hours with the experts.

### Dynamic Prompting
This pattern involves leveraging variables within the instructions and programmatically updating them through a callback function. We recommend dynamic prompting be used for multi-step flows to reduce the agent’s context window. If your agent has nested conditions, this will improve instruction following.
Example:
Prior to the implementation of dynamic instructions, prompts typically contain complex nested conditions contingent on the user state, which can degrade the reliability of instruction following.

       <step name="Offer_Appointment">
            <trigger>Immediately on entering `Handle_Appointment`</trigger>
            <action>
                1. You **MUST** check if the value of {premium_user} is null or empty. If it is, then say exactly "You can Schedule an appointment on our self service page on mywebsite.com." Then you **MUST** silently and immediately transition to the `Goodbye` step. Do not continue with the `Offer_Appointment` step.
                2. **ONLY** if {premium_user} is true, execute the matching condition:
                  2a. **Store ID exists:** If {store_id} is non-null and non-empty, say exactly, "Let's get this taken care of for you! The best option is to bring it to a store to diagnose the problem. I can help you schedule a service appointment at {store_name} that's convenient for you. What date and time work best for you?"
                  2b. **No store ID:** Else, say exactly, "Let's get this taken care of for you! The best option is to bring it to a store to diagnose. I can help you schedule a service appointment at a location that's convenient for you. Can you provide your zipcode so I can search for the next available appointment near you?"
                3. If the user declines the offer to schedule an appointment, say exactly "No problem. To schedule an appointment online, use our Schedule a Service page on mywebsite.com." Then silently and immediately transition to the `Send_Self_Service_SMS` step.
            </action>
        </step>


After dynamic instructions:
   <subtask name="Schedule_Appointment">
      Follow the following instruction set exactly: {schedule_appointment_instruction}
    </subtask>
Associated before_agent_callback where this is updated:

from typing import Optional

SCHEDULE_TEMPLATE = "..."
OFFER_WITH_STORE = "..."
OFFER_WITHOUT_STORE = "...."
LOCATION_PREFERENCE_WITHOUT_STORE = "..."

def before_agent_callback(
    callback_context: CallbackContext,
) -> Optional[Content]:
  variables = callback_context.variables
  # ONLY update the instruction variable once.
  if not variables.get("schedule_appointment_instruction"):
    if variables.get("premium_user"):
      if variables.get("store_id") and variables.get("store_name"):
        instruction = SCHEDULE_TEMPLATE.substitute(
            offer_appointment=OFFER_WITH_STORE.format(
                store_name=variables["store_name"]
            ),
            location_preference=LOCATION_PREFERENCE_WITH_STORE.format(
                store_name=variables["store_name"]
            ),
        )
      else:
        instruction = SCHEDULE_TEMPLATE.substitute(
            offer_appointment=OFFER_WITHOUT_STORE,
            location_preference=LOCATION_PREFERENCE_WITHOUT_STORE,
        )
    else:
      instruction = SELF_SERVICE_ONLY
    variables["schedule_appointment_instruction"] = instruction

### Instructions in a tool response
Embed instructions directly within the tool response to enhance model reliability by emulating a progressive disclosure pattern.
When to use?
You know that certain instructions only matter after a certain step is achieved (e.g. an action can only be taken after certain information is collected from the user)  
Graceful error handing of tool calls
Example

Instructions

<step name="Execute_Entitlement_Check">
        <trigger>Immediately on entering `Check_Entitlement`.</trigger>
        <action>
        1. Silently call `{@TOOL: check_support_entitlement}`
        2. You MUST follow the instructions in the tool's response.
        </action>
      </step>



IN_WARRANTY_INSTRUCTIONS = (
    "The device is under warranty. Proceed to the `Troubleshooting` subtask and"
    " attempt to fix the problem remotely. Offer a free replacement if"
    " troubleshooting fails."
)
OUT_OF_WARRANTY_INSTRUCTIONS = (
    "The device is out of warranty. Inform the user that repairs will incur a"
    " fee, and then ask if they would like to proceed with paid remote"
    " troubleshooting or schedule an in-person repair."
)


def check_warranty_status(context: Any) -> str:
  """Determines the next conversational step based on the user's device warranty status.

  This demonstrates embedding instructions in a tool response to control
  progressive disclosure
  and enhance model reliability, as described in prompt-guidance.md.

  The Agent MUST strictly execute the instructions returned by this tool without
  deviation.

  ### PRE-REQUISITES:
  Before calling this tool, the agent MUST have collected the device's
  `serial_number`.

  Returns:
      str: A mandatory instruction set that the agent MUST follow to continue
      the conversation flow.
  """
  serial_number = context.state.get("serial_number")

  # Logic for determining warranty.
  if is_in_warranty(serial_number):
    return IN_WARRANTY_INSTRUCTIONS
  else:
    return OUT_OF_WARRANTY_INSTRUCTIONS

#### Self healing from errors

...


def check_warranty_status(context: Any) -> str:
  """
  ...
  """
  serial_number = context.state.get("serial_number")

  if not serial_number:
    return (
        "agent_action: You must ask the user for their serial number before"
        " calling `check_warranty_status`."
    )

  # Rest of code


More Examples:

### Single Agent Example: Password Reset Agent
### Multi Agent Example: Healthcare Scheduling Agent
