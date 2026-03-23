"""Single-turn evaluation utility for CXAS Agents.

Provides the primitive testing tools for providing specific user utterances
and validating immediate Agent responses, intent classifications, and Tool calls.
"""

from typing import Any, Dict, List, Optional
import os
import yaml
import logging
import pandas as pd
import enum

from pydantic import BaseModel, Field, TypeAdapter

from cxas_scrapi.core.sessions import Sessions
from cxas_scrapi.core.variables import Variables

logger = logging.getLogger(__name__)


class TurnOperator(str, enum.Enum):
    """Operators for testing single-turn expectations."""

    CONTAINS = "contains"
    EQUALS = "equals"
    TOOL_CALLED = "tool_called"
    TOOL_INPUT = "tool_input"
    TOOL_OUTPUT = "tool_output"
    NO_TOOLS_CALLED = "no_tools_called"
    AGENT_TRANSFER = "agent_transfer"


class TurnExpectation(BaseModel):
    """Data model for a single-turn expectation."""

    type: TurnOperator
    value: Optional[Any] = None


class TurnStep(BaseModel):
    """Data model for a single step inside a multi-turn conversation."""

    turn: str
    user: Optional[str] = None
    event: Optional[str] = None
    variables: Dict[str, Any] = Field(default_factory=dict)
    config: Dict[str, Any] = Field(default_factory=dict)
    expectations: List[TurnExpectation] = Field(default_factory=list)


class TurnTestCase(BaseModel):
    """Data model for a single-turn test case."""

    name: str
    tags: List[str] = Field(default_factory=list)
    user: Optional[str] = None
    event: Optional[str] = None
    variables: Dict[str, Any] = Field(default_factory=dict)
    historical_contexts: Optional[List[Dict[str, Any]] | str] = None
    turn_count: Optional[int] = None
    config: Dict[str, Any] = Field(default_factory=dict)
    config: Dict[str, Any] = Field(default_factory=dict)
    expectations: List[TurnExpectation] = Field(default_factory=list)
    turns: Optional[List[TurnStep]] = None


class TurnEvals:
    """Class to manage and execute single-turn assertions on CXAS Agents."""

    def __init__(self, app_name: str, creds=None):
        """Initializes the TurnEvals class.

        Args:
            app_name: CXAS App Name
            creds: Optional Google Cloud credentials
        """
        self.app_name = app_name
        self.creds = creds
        self.sessions_client = Sessions(
            app_name=self.app_name, creds=self.creds
        )
        self.var_client = Variables(app_name=self.app_name, creds=self.creds)

    def load_turn_test_cases_from_file(
        self, test_file_path: str
    ) -> List[TurnTestCase]:
        """Loads turn tests from a YAML file."""
        with open(test_file_path, "r", encoding="utf-8") as f:
            return self.load_turn_test_cases_from_yaml(f.read())

    def load_turn_tests_from_dir(
        self, directory_path: str = "turn_tests"
    ) -> List[TurnTestCase]:
        """Recursively loads all YAML turn tests from a directory."""
        all_tests = []
        if not os.path.exists(directory_path):
            print(f"Directory {directory_path} does not exist.")
            return all_tests

        for root, _, files in os.walk(directory_path):
            for file in files:
                if file.endswith(".yaml") or file.endswith(".yml"):
                    file_path = os.path.join(root, file)
                    try:
                        tests = self.load_turn_test_cases_from_file(file_path)
                        all_tests.extend(tests)
                    except Exception as e:
                        logger.error(f"Error loading {file_path}: {e}")

        return all_tests

    def load_turn_test_cases_from_yaml(
        self, yaml_data: str
    ) -> List[TurnTestCase]:
        """Loads turn tests from a YAML string."""
        raw_data = yaml.safe_load(yaml_data)
        if not raw_data:
            return []
        # Support both 'conversations' and 'tests' formats
        raw_tests = raw_data.get("conversations", raw_data.get("tests", []))
        if not raw_tests:
            return []

        # Map 'conversation' to 'name' for Pydantic validation if needed
        for t in raw_tests:
            if "conversation" in t and "name" not in t:
                t["name"] = t["conversation"]

        global_config = raw_data.get("config", {})
        adapter = TypeAdapter(List[TurnTestCase])
        tests = adapter.validate_python(raw_tests)

        for t in tests:
            merged = global_config.copy()
            merged.update(t.config)
            t.config = merged
            if t.turns:
                for step in t.turns:
                    step_merged = merged.copy()
                    step_merged.update(step.config)
                    step.config = step_merged

        return tests

    def _check_dict_subset(self, subset: dict, superset: dict) -> bool:
        """Checks if all key-value pairs in subset exist exactly in superset.
        Supports {} as a wildcard meaning 'the key must exist, but values do not matter'.
        """
        import json

        for k, v in subset.items():
            if k not in superset:
                return False
            # {} acts as a wildcard asserting exists
            if isinstance(v, dict) and not v:
                continue

            super_val = superset[k]

            # If expected is a dict but actual is a JSON string, try to parse the actual
            if isinstance(v, dict) and isinstance(super_val, str):
                try:
                    super_val = json.loads(super_val)
                except json.JSONDecodeError:
                    pass

            # Recursive check if both are dicts
            if isinstance(v, dict) and isinstance(super_val, dict):
                if not self._check_dict_subset(v, super_val):
                    return False
            elif super_val != v:
                if str(super_val) != str(v):
                    return False
        return True

    def _extract_tools_from_span(
        self,
        span: Dict[str, Any],
        called_tools: List[str],
        tool_inputs: Dict[str, Any],
        tool_outputs: Dict[str, Any],
    ):
        """Recursively extract tool calls from a span and its children."""
        if span.get("name") == "Tool":
            attrs = span.get("attributes", {})
            tool_name = attrs.get("name", "")
            if tool_name:
                if tool_name not in called_tools:
                    called_tools.append(tool_name)

                if "args" in attrs and tool_name not in tool_inputs:
                    tool_inputs[tool_name] = attrs["args"]
                if "response" in attrs and tool_name not in tool_outputs:
                    tool_outputs[tool_name] = attrs["response"]

        for child in span.get("childSpans", []):
            self._extract_tools_from_span(
                child, called_tools, tool_inputs, tool_outputs
            )

    def validate_turn_test(self, test_case: Any, turn_response: Any):
        """Validates the turn response against defined expectations."""
        errors = []
        expected_vals = []
        actual_vals = []

        # Extract meaningful data from turn_response protobuf/dict
        from google.protobuf.json_format import MessageToDict

        try:
            resp_dict = MessageToDict(turn_response._pb)
        except AttributeError:
            resp_dict = (
                MessageToDict(turn_response)
                if hasattr(turn_response, "DESCRIPTOR")
                else (turn_response if isinstance(turn_response, dict) else {})
            )

        outputs = resp_dict.get("outputs", [])

        # Aggregate text, tools, and transfers
        full_text = ""
        called_tools = []
        tool_inputs = {}
        tool_outputs = {}
        target_agent = ""

        # Some payloads might be simpler dicts depending on the cxas core
        if not outputs and "text" in resp_dict:
            full_text = str(resp_dict["text"])

        def add_snippet(snippet: str):
            nonlocal full_text
            snippet = str(snippet).strip()
            if not snippet:
                return
            if snippet not in full_text:
                if full_text and not full_text.endswith(" "):
                    full_text += " "
                full_text += snippet

        for out in outputs:
            # only collect the raw output text for this turn, avoiding trace history
            if "text" in out:
                add_snippet(out["text"])

            diag = out.get("diagnosticInfo", {})
            messages = diag.get("messages", [])

            # Extract any nested tools from rootSpan
            root_span = diag.get("rootSpan", {})
            if root_span:
                self._extract_tools_from_span(
                    root_span, called_tools, tool_inputs, tool_outputs
                )

            for msg in messages:
                if msg.get("role") == "user":
                    continue

                for chunk in msg.get("chunks", []):
                    if "text" in chunk:
                        add_snippet(chunk["text"])
                    if "transcript" in chunk:
                        add_snippet(chunk["transcript"])
                    if "toolCall" in chunk:
                        tc = chunk["toolCall"]
                        tool_name = tc.get("displayName", tc.get("tool", ""))
                        if tool_name and tool_name not in called_tools:
                            called_tools.append(tool_name)
                        if tool_name not in tool_inputs:
                            tool_inputs[tool_name] = tc.get("args", {})
                    if "toolResponse" in chunk:
                        tr = chunk["toolResponse"]
                        tool_name = tr.get("displayName", tr.get("tool", ""))
                        if tool_name not in tool_outputs:
                            tool_outputs[tool_name] = tr.get("response", {})
                    if "agentTransfer" in chunk:
                        at = chunk["agentTransfer"]
                        target_agent = at.get("displayName", "")
                        if not target_agent:
                            agent_str = at.get(
                                "agent", at.get("targetAgent", "")
                            )
                            target_agent = (
                                agent_str.split("/")[-1]
                                if "/" in agent_str
                                else agent_str
                            )

            # Fallback to high-level outputs if no diagnostic trace is available
            if not messages:
                if "text" in out:
                    full_text += str(out["text"]) + " "
                # Check top-level toolCalls and agentTransfers
                tcs_msg = out.get("toolCalls", {})
                for tc in tcs_msg.get("toolCalls", []):
                    tool_name = tc.get("displayName", tc.get("tool", ""))
                    if tool_name and tool_name not in called_tools:
                        called_tools.append(tool_name)
                    if tool_name not in tool_inputs:
                        tool_inputs[tool_name] = tc.get("args", {})

        for exp in test_case.expectations:
            op = exp.type
            expected = exp.value

            expected_vals.append(str(expected))

            if op == TurnOperator.EQUALS:
                actual_vals.append(full_text.strip())
                if full_text.strip() != str(expected).strip():
                    errors.append(
                        f"EQUALS failed: Expected '{expected}', Got '{full_text.strip()}'"
                    )
            elif op == TurnOperator.CONTAINS:
                actual_vals.append(full_text.strip())
                if str(expected) not in full_text:
                    errors.append(
                        f"CONTAINS failed: '{expected}' not found in '{full_text.strip()}'"
                    )
            elif op == TurnOperator.TOOL_CALLED:
                actual_vals.append(str(called_tools))
                found = any(
                    expected == t or t.endswith(expected) for t in called_tools
                )
                if not found:
                    errors.append(
                        f"TOOL_CALLED failed: Expected tool '{expected}' was not called. Tools called: {called_tools}"
                    )
            elif op == TurnOperator.NO_TOOLS_CALLED:
                actual_vals.append(str(called_tools))
                if called_tools:
                    errors.append(
                        f"NO_TOOLS_CALLED failed: Tools were called: {called_tools}"
                    )
            elif op == TurnOperator.AGENT_TRANSFER:
                actual_vals.append(target_agent)
                if target_agent != expected and not target_agent.endswith(
                    expected
                ):
                    errors.append(
                        f"AGENT_TRANSFER failed: Expected transfer to '{expected}', actually transferred to '{target_agent}'"
                    )
            elif op == TurnOperator.TOOL_INPUT:
                actual_vals.append(str(tool_inputs))
                if not isinstance(expected, dict):
                    errors.append(
                        f"TOOL_INPUT failed: expectation value must be a dictionary."
                    )
                    continue
                # 1) Try matching against the top-level tool_inputs container
                if self._check_dict_subset(expected, tool_inputs):
                    continue

                # 2) Fallback to checking nested argument dicts for any tool
                match_found = False
                for t_name, t_args in tool_inputs.items():
                    if self._check_dict_subset(expected, t_args):
                        match_found = True
                        break
                if not match_found:
                    errors.append(
                        f"TOOL_INPUT failed: No tool call contained matching arguments {expected}. Actual tool inputs: {tool_inputs}"
                    )
            elif op == TurnOperator.TOOL_OUTPUT:
                actual_vals.append(str(tool_outputs))
                if not isinstance(expected, dict):
                    errors.append(
                        f"TOOL_OUTPUT failed: expectation value must be a dictionary."
                    )
                    continue
                # 1) Try matching against the top-level tool_outputs container
                if self._check_dict_subset(expected, tool_outputs):
                    continue

                # 2) Fallback to checking nested response dicts for any tool
                match_found = False
                for t_name, t_resp in tool_outputs.items():
                    if self._check_dict_subset(expected, t_resp):
                        match_found = True
                        break
                if not match_found:
                    errors.append(
                        f"TOOL_OUTPUT failed: No tool response contained matching outputs {expected}. Actual tool outputs: {tool_outputs}"
                    )

        return errors, expected_vals, actual_vals

    def run_turn_tests(
        self,
        test_cases: List[TurnTestCase],
        debug: bool = False,
        session_id_prefix: str = "turn_eval_",
    ) -> pd.DataFrame:
        """Runs a list of single-turn tests. Every test runs in a brand new session."""
        import uuid

        results = []

        for case in test_cases:
            print(f"Running Turn Test: {case.name}")

            # 1. Create a brand new session ID for true stateless execution
            test_session_id = f"{session_id_prefix}{uuid.uuid4().hex[:8]}"

            try:
                if case.turns:
                    # Multi-turn sequence
                    for step in case.turns:
                        if debug:
                            input_str = (
                                step.user
                                if step.user
                                else f"<event>{step.event}</event>"
                            )
                            print(
                                f"[DEBUG] Step: {step.turn} | Input: {input_str}"
                            )
                            print(f"[DEBUG] Session ID: {test_session_id}")
                            print(f"[DEBUG] Variables: {step.variables}")

                        # Merge config
                        merged_config = case.config.copy()
                        merged_config.update(step.config)

                        turn_response = self.sessions_client.run(
                            session_id=test_session_id,
                            text=step.user,
                            event=step.event,
                            variables=step.variables,
                            historical_contexts=None,
                            **merged_config,
                        )

                        errors, expected_vals, actual_vals = (
                            self.validate_turn_test(step, turn_response)
                        )

                        status = "SUCCESS"
                        if errors:
                            status = "FAILURE"

                        print(f"{status}: {case.name} - {step.turn}")
                        if errors:
                            for err in errors:
                                print(f"  - {err}")

                        results.append(
                            {
                                "test_name": case.name,
                                "turn": step.turn,
                                "user": step.user or f"Event: {step.event}",
                                "status": status,
                                "errors": "; ".join(errors) if errors else "",
                                "expected": (
                                    "\n".join(expected_vals)
                                    if expected_vals
                                    else ""
                                ),
                                "actual": (
                                    "\n".join(actual_vals)
                                    if actual_vals
                                    else ""
                                ),
                                "session_id": test_session_id,
                            }
                        )

                        if errors:
                            print(
                                f"Aborting multi-turn sequence '{case.name}' due to failure at '{step.turn}'."
                            )
                            break
                        print("-" * 30)
                else:
                    # 2. Run the single turn
                    if debug:
                        input_str = (
                            case.user
                            if case.user
                            else f"<event>{case.event}</event>"
                        )
                        print(f"[DEBUG] Input: {input_str}")
                        print(f"[DEBUG] Session ID: {test_session_id}")
                        print(f"[DEBUG] Variables: {case.variables}")

                    turn_response = self.sessions_client.run(
                        session_id=test_session_id,
                        text=case.user,
                        event=case.event,
                        variables=case.variables,
                        historical_contexts=(
                            case.historical_contexts
                            if case.historical_contexts
                            else None
                        ),
                        turn_count=(
                            case.turn_count
                            if case.turn_count is not None
                            else None
                        ),
                        **case.config,
                    )

                    # 3. Validate expectations
                    errors, expected_vals, actual_vals = (
                        self.validate_turn_test(case, turn_response)
                    )

                    status = "SUCCESS"
                    if errors:
                        status = "FAILURE"

                    print(f"{status}: {case.name}")
                    if errors:
                        for err in errors:
                            print(f"  - {err}")

                    results.append(
                        {
                            "test_name": case.name,
                            "turn": "",
                            "user": case.user or f"Event: {case.event}",
                            "status": status,
                            "errors": "; ".join(errors) if errors else "",
                            "expected": (
                                "\n".join(expected_vals)
                                if expected_vals
                                else ""
                            ),
                            "actual": (
                                "\n".join(actual_vals) if actual_vals else ""
                            ),
                            "session_id": test_session_id,
                        }
                    )

            except Exception as e:
                print(f"FAILURE: Exception {e}")
                results.append(
                    {
                        "test_name": case.name,
                        "turn": "",
                        "user": case.user,
                        "status": "FAILURE",
                        "errors": str(e),
                        "expected": "",
                        "actual": "",
                        "session_id": test_session_id,
                    }
                )

            print("=" * 30)

        return pd.DataFrame(results)
