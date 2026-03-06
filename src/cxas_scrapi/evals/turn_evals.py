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

class TurnTestCase(BaseModel):
    """Data model for a single-turn test case."""
    name: str
    user: str
    variables: Dict[str, Any] = Field(default_factory=dict)
    expectations: List[TurnExpectation] = Field(default_factory=list)

class TurnEvals:
    """Class to manage and execute single-turn assertions on CXAS Agents."""
    
    def __init__(self, app_id: str, creds=None):
        """Initializes the TurnEvals class.

        Args:
            app_id: CXAS App ID
            creds: Optional Google Cloud credentials
        """
        self.app_id = app_id
        self.creds = creds
        self.sessions_client = Sessions(app_id=self.app_id, creds=self.creds)
        self.var_client = Variables(app_id=self.app_id, creds=self.creds)

    def load_turn_test_cases_from_file(self, test_file_path: str) -> List[TurnTestCase]:
        """Loads turn tests from a YAML file."""
        with open(test_file_path, "r", encoding="utf-8") as f:
            return self.load_turn_test_cases_from_yaml(f.read())

    def load_turn_tests_from_dir(self, directory_path: str = "turn_tests") -> List[TurnTestCase]:
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

    def load_turn_test_cases_from_yaml(self, yaml_data: str) -> List[TurnTestCase]:
        """Loads turn tests from a YAML string."""
        raw_data = yaml.safe_load(yaml_data)
        if not raw_data or "tests" not in raw_data:
            return []
        
        adapter = TypeAdapter(List[TurnTestCase])
        return adapter.validate_python(raw_data["tests"])

    def _check_dict_subset(self, subset: dict, superset: dict) -> bool:
        """Checks if all key-value pairs in subset exist exactly in superset.
        Supports {} as a wildcard meaning 'the key must exist, but values do not matter'.
        """
        for k, v in subset.items():
            if k not in superset:
                return False
            # {} acts as a wildcard asserting exists
            if isinstance(v, dict) and not v:
                continue
            # Recursive check if both are dicts
            if isinstance(v, dict) and isinstance(superset[k], dict):
                if not self._check_dict_subset(v, superset[k]):
                    return False
            elif superset[k] != v:
                return False
        return True

    def validate_turn_test(self, test_case: TurnTestCase, turn_response: Any) -> List[str]:
        """Validates the turn response against defined expectations."""
        errors = []
        
        # Extract meaningful data from turn_response protobuf/dict
        from google.protobuf.json_format import MessageToDict
        try:
            resp_dict = MessageToDict(turn_response._pb)
        except AttributeError:
            resp_dict = MessageToDict(turn_response) if hasattr(turn_response, "DESCRIPTOR") else (turn_response if isinstance(turn_response, dict) else {})
            
        outputs = resp_dict.get("outputs", [])
        
        # Aggregate text, tools, and transfers
        full_text = ""
        called_tools = []
        tool_inputs = {}
        tool_outputs = {}
        target_agent = ""

        # Some payloads might be simpler dicts depending on the cxas core
        if not outputs and "text" in resp_dict:
            full_text = resp_dict["text"]

        for out in outputs:
            diag = out.get("diagnosticInfo", {})
            messages = diag.get("messages", [])
            for msg in messages:
                for chunk in msg.get("chunks", []):
                    if "text" in chunk:
                        full_text += str(chunk["text"]) + " "
                    if "toolCall" in chunk:
                        tc = chunk["toolCall"]
                        tool_name = tc.get("displayName", tc.get("tool", ""))
                        called_tools.append(tool_name)
                        tool_inputs[tool_name] = tc.get("args", {})
                    if "toolResponse" in chunk:
                        tr = chunk["toolResponse"]
                        tool_name = tr.get("displayName", tr.get("tool", ""))
                        tool_outputs[tool_name] = tr.get("response", {})
                    if "agentTransfer" in chunk:
                        at = chunk["agentTransfer"]
                        target_agent = at.get("displayName", "")
                        if not target_agent:
                            agent_str = at.get("agent", at.get("targetAgent", ""))
                            target_agent = agent_str.split("/")[-1] if "/" in agent_str else agent_str
                        
            # Fallback to high-level outputs if no diagnostic trace is available
            if not messages:
                if "text" in out:
                    full_text += str(out["text"]) + " "
                
                # Check top-level toolCalls and agentTransfers
                tcs_msg = out.get("toolCalls", {})
                for tc in tcs_msg.get("toolCalls", []):
                    tool_name = tc.get("displayName", tc.get("tool", ""))
                    called_tools.append(tool_name)
                    tool_inputs[tool_name] = tc.get("args", {})

        for exp in test_case.expectations:
            op = exp.type
            expected = exp.value
            
            if op == TurnOperator.EQUALS:
                if full_text.strip() != str(expected).strip():
                    errors.append(f"EQUALS failed: Expected '{expected}', Got '{full_text.strip()}'")
            elif op == TurnOperator.CONTAINS:
                if str(expected) not in full_text:
                    errors.append(f"CONTAINS failed: '{expected}' not found in '{full_text.strip()}'")
            elif op == TurnOperator.TOOL_CALLED:
                found = any(expected == t or t.endswith(expected) for t in called_tools)
                if not found:
                    errors.append(f"TOOL_CALLED failed: Expected tool '{expected}' was not called. Tools called: {called_tools}")
            elif op == TurnOperator.NO_TOOLS_CALLED:
                if called_tools:
                    errors.append(f"NO_TOOLS_CALLED failed: Tools were called: {called_tools}")
            elif op == TurnOperator.AGENT_TRANSFER:
                if target_agent != expected and not target_agent.endswith(expected):
                    errors.append(f"AGENT_TRANSFER failed: Expected transfer to '{expected}', actually transferred to '{target_agent}'")
            elif op == TurnOperator.TOOL_INPUT:
                if not isinstance(expected, dict):
                    errors.append(f"TOOL_INPUT failed: expectation value must be a dictionary.")
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
                    errors.append(f"TOOL_INPUT failed: No tool call contained matching arguments {expected}. Actual tool inputs: {tool_inputs}")
            elif op == TurnOperator.TOOL_OUTPUT:
                if not isinstance(expected, dict):
                    errors.append(f"TOOL_OUTPUT failed: expectation value must be a dictionary.")
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
                    errors.append(f"TOOL_OUTPUT failed: No tool response contained matching outputs {expected}. Actual tool outputs: {tool_outputs}")
                    
        return errors

    def run_turn_tests(self, test_cases: List[TurnTestCase], debug: bool = False, session_id_prefix: str = "turn_eval_") -> pd.DataFrame:
        """Runs a list of single-turn tests. Every test runs in a brand new session."""
        import uuid
        results = []
        
        for case in test_cases:
            print(f"Running Turn Test: {case.name}")
            
            # 1. Create a brand new session ID for true stateless execution
            test_session_id = f"{session_id_prefix}{uuid.uuid4().hex[:8]}"
            
            try:
                # 2. Run the single turn
                if debug:
                    print(f"[DEBUG] Input: {case.user}")
                    print(f"[DEBUG] Session ID: {test_session_id}")
                    print(f"[DEBUG] Variables: {case.variables}")

                turn_response = self.sessions_client.run(
                    session_id=test_session_id,
                    text=case.user,
                    variables=case.variables
                )
                
                # 3. Validate expectations
                errors = self.validate_turn_test(case, turn_response)
                
                status = "SUCCESS"
                if errors:
                    status = "FAILURE"
                    
                print(f"{status}: {case.name}")
                if errors:
                    for err in errors:
                        print(f"  - {err}")
                    
                results.append({
                    "test_name": case.name,
                    "user": case.user,
                    "status": status,
                    "errors": "; ".join(errors) if errors else "",
                })
                
            except Exception as e:
                print(f"FAILURE: Exception {e}")
                results.append({
                    "test_name": case.name,
                    "user": case.user,
                    "status": "FAILURE",
                    "errors": str(e)
                })
                
            print("-" * 30)
            
        return pd.DataFrame(results)
