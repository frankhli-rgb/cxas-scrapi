# Copyright 2026 Google LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     https://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Utility functions for processing and exporting CXAS Evaluation Results."""

from typing import List, Dict, Any, Optional, Annotated
import zipfile
import io
import logging
from google.cloud.ces_v1beta import types
from cxas_scrapi.core.evaluations import Evaluations
from cxas_scrapi.core.variables import Variables
from cxas_scrapi.core.tools import Tools
import pandas as pd
from pydantic import BaseModel, Field, AliasChoices, AliasPath, TypeAdapter, BeforeValidator
import enum
import yaml
from jsonpath_ng import parse
import pprint

logger = logging.getLogger(__name__)

class EvalUtils(Evaluations):
    def __init__(self, app_id: str, env: str = "PROD"):
        """Initializes the EvalUtils class for processing Evaluation Results.
        
        Args:
            app_id: CXAS App ID (projects/{project}/locations/{location}/apps/{app}).
            env: Environment override (default: PROD).
        """
        super().__init__(app_id=app_id, env=env)
        self.app_id = app_id
        self.tools_client = Tools(project_id=self.project_id, location=self.location, creds=self.creds)
        self.var_client = Variables(project_id=self.project_id, location=self.location, creds=self.creds)
        self.tool_map = self.tools_client.get_tools_map(self.app_id, reverse=True)

    @staticmethod
    def compute_semantic_similarity(text1: str, text2: str, model_name: str = "all-MiniLM-L6-v2") -> float:
        """Computes basic embedding-based semantic similarity between two strings.
        
        This uses the local 'sentence-transformers' library rather than an LLM.
        The default model ('all-MiniLM-L6-v2') is small, fast, and effective.
        
        Args:
            text1: The first string to compare.
            text2: The second string to compare.
            model_name: The sentence-transformers model to use.
            
        Returns:
            A float between -1.0 and 1.0 representing the cosine similarity.
        """
        try:
            from sentence_transformers import SentenceTransformer, util
        except ImportError:
            raise ImportError(
                "The 'sentence-transformers' library is required for basic local embeddings.\n"
                "Please install it using 'pip install sentence-transformers'."
            )
            
        # Load the local embedding model (downloads automatically on first run)
        model = SentenceTransformer(model_name)
        
        # Generate embeddings
        emb1 = model.encode(text1, convert_to_tensor=True)
        emb2 = model.encode(text2, convert_to_tensor=True)
        
        # Compute cosine similarity
        cosine_score = util.cos_sim(emb1, emb2).item()
        return cosine_score

    def evals_to_dataframe(
        self, 
        results: Optional[List[types.EvaluationResult]] = None,
        eval_names: Optional[List[str]] = None
    ) -> Any:
        """Parses a list of EvaluationResult objects into a flattened pandas DataFrame.
        
        If results is not provided, automatically fetches all evaluation results for the app.
        If eval_names is provided, filters the fetched results to only those matching the display names.
        
        Args:
            results: A list of EvaluationResult objects from the CES API. Optional.
            eval_names: A list of evaluation display names to filter by. Optional.
            
        Returns:
            A pandas DataFrame with flattened metrics.
        """
        if results is None:
            results = []
            evaluations = self.list_evaluations(self.app_id)
            for evaluation in evaluations:
                if eval_names and evaluation.display_name not in eval_names:
                    continue
                results.extend(self.list_evaluation_results(evaluation.name))
                
        # pandas import removed as it is now at top level

        def _map_outcome(val):
            if isinstance(val, int):
                return {0: "UNSPECIFIED", 1: "PASS", 2: "FAIL"}.get(val, f"UNKNOWN_{val}")
            return str(val) if val is not None else None

        flattened_data = []
        eval_cache = {}

        for result in results:
            res_dict = type(result).to_dict(result)
            result_name = res_dict.get("name", "")
            
            # Extract parent Evaluation name to lookup display_name
            # result_name format: projects/*/locations/*/apps/*/evaluations/*/results/*
            eval_name = "/".join(result_name.split("/")[:-2])
            display_name = "Unknown Evaluation"
            if eval_name:
                if eval_name not in eval_cache:
                    try:
                        eval_obj = self.get_evaluation(eval_name)
                        eval_cache[eval_name] = eval_obj.display_name
                    except Exception:
                        eval_cache[eval_name] = "Unknown Evaluation"
                display_name = eval_cache[eval_name]
            
            # Map enum integer to string for readability
            raw_status = res_dict.get("evaluation_status", 0)
            if isinstance(raw_status, int):
                status_map = {0: "UNSPECIFIED", 1: "PASSED", 2: "FAILED"}
                status_str = status_map.get(raw_status, f"UNKNOWN_{raw_status}")
            else:
                status_str = str(raw_status)
                
            base_info = {
                "eval_result_id": result_name,
                "display_name": display_name,
                "evaluation_status": status_str,
                "create_time": res_dict.get("create_time", ""),
                "update_time": res_dict.get("update_time", ""),
            }

            golden = res_dict.get("golden_result", {})
            metrics = golden.get("metrics", {}) if golden else {}
            
            # Overall evaluation metrics (apply to all rows for this specific eval result)
            semantic_res = metrics.get("semantic_similarity_result", {})
            tool_res = metrics.get("overall_tool_invocation_result", {})
            
            overall_info = base_info.copy()
            overall_info.update({
                "semantic_score": semantic_res.get("score"),
                "semantic_label": semantic_res.get("label", ""),
                "semantic_explanation": semantic_res.get("explanation", ""),
                "tool_invocation_score": _map_outcome(tool_res.get("tool_invocation_score"))
            })

            expectationList = metrics.get("expectation_results", [])
            
            for exp_item in expectationList:
                row = overall_info.copy()
                row["record_type"] = "summary_expectation"
                row["expectation"] = str(exp_item.get("expectation", ""))
                row["met_count"] = exp_item.get("met_count", 0)
                row["not_met_count"] = exp_item.get("not_met_count", 0)
                row["met_percentage"] = exp_item.get("met_percentage", 0.0)
                row["not_met_percentage"] = exp_item.get("not_met_percentage", 0.0)
                
                flattened_data.append(row)

            turnList = golden.get("turn_replay_results", [])
            if isinstance(turnList, list):
                for i, turn in enumerate(turnList):
                    if not isinstance(turn, dict):
                        continue
                    row = overall_info.copy()
                    row["record_type"] = "turn_replay"
                    row["turn_index"] = i
                    row["conversation_id"] = turn.get("conversation", "")
                    
                    lat = turn.get("turn_latency", {})
                    if isinstance(lat, dict):
                        row["turn_latency_seconds"] = lat.get("seconds", 0)
                    
                    sem_res = turn.get("semantic_similarity_result", {})
                    if isinstance(sem_res, dict):
                        row["turn_semantic_score"] = sem_res.get("score")
                        row["turn_semantic_label"] = sem_res.get("label", "")
                        row["turn_semantic_explanation"] = sem_res.get("explanation", "")
                        row["turn_semantic_outcome"] = _map_outcome(sem_res.get("outcome"))
                    
                    hal_res = turn.get("hallucination_result", {})
                    if isinstance(hal_res, dict):
                        row["turn_hallucination_score"] = hal_res.get("score")
                        row["turn_hallucination_label"] = hal_res.get("label", "")
                        row["turn_hallucination_explanation"] = hal_res.get("explanation", "")
                    
                    row["turn_tool_ordered_invocation_score"] = _map_outcome(turn.get("tool_ordered_invocation_score"))
                    row["turn_tool_invocation_score"] = _map_outcome(turn.get("tool_invocation_score"))
                    
                    # Store expectation outcomes as JSON string to keep the table flat
                    outcomes = turn.get("expectation_outcome", [])
                    import json
                    row["expectation_outcomes"] = json.dumps(outcomes)
                        
                    flattened_data.append(row)
            
            if not expectationList and not turnList:
                row = overall_info.copy()
                row["record_type"] = "overall_only"
                flattened_data.append(row)
                
        df = pd.DataFrame(flattened_data)
        
        # Ensure timestamp types are parsed correctly
        if "create_time" in df.columns:
            df["create_time"] = pd.to_datetime(df["create_time"])
        if "update_time" in df.columns:
            df["update_time"] = pd.to_datetime(df["update_time"])

        return df

    def to_bigquery(self, df: Any, dataset_table: str, project_id: Optional[str] = None, if_exists: str = "append"):
        """Exports a pandas DataFrame to a Google BigQuery table.
        
        Args:
            df: The pandas DataFrame to upload.
            dataset_table: The BigQuery target in 'dataset.table' format.
            project_id: The GCP Project ID override (defaults to the app's project).
            if_exists: Behavior when the table exists ('fail', 'replace', 'append').
        """
        try:
            from google.cloud import bigquery
            import pandas_gbq
        except ImportError:
            raise ImportError(
                "The 'google-cloud-bigquery' and 'pandas-gbq' libraries are required "
                "to export to BigQuery. Please install them."
            )

        target_project = project_id or self._get_project_id(self.app_id)
        
        # Let pandas_gbq handle the upload utilizing the application default credentials
        df.to_gbq(
            destination_table=dataset_table,
            project_id=target_project,
            if_exists=if_exists,
            credentials=self.creds
        )
        print(f"Successfully uploaded {len(df)} rows to {target_project}.{dataset_table}")

    def get_run_summaries(self, df: Any) -> Any:
        """Takes a flattened DataFrame from evals_to_dataframe and returns a simplified summary.
        
        The summary contains one row per evaluation run, quickly extracting 
        the run ID, date, status, and overall metrics.
        
        Args:
            df: The pandas DataFrame generated by evals_to_dataframe.
            
        Returns:
            A simplified pandas DataFrame with one row per unique evaluation run.
        """
        # pandas import removed as it is now at top level
            
        if df is None or df.empty or "eval_result_id" not in df.columns:
            return pd.DataFrame()
            
        cols_to_keep = [
            "display_name",
            "eval_result_id", 
            "evaluation_status", 
            "semantic_score", 
            "tool_invocation_score",
            "create_time", 
            "update_time"
        ]
        
        # Group by the unique run identifier and take the first row's overall stats
        summary_df = df.groupby("eval_result_id", as_index=False).first()
        
        existing_cols = [c for c in cols_to_keep if c in summary_df.columns]
        summary_df = summary_df[existing_cols]
        
        # Sort by update_time descending so newer runs are at the top
        if "update_time" in summary_df.columns:
            summary_df = summary_df.sort_values(by="update_time", ascending=False).reset_index(drop=True)
            
        return summary_df

    def load_tool_test_cases(self, test_file_path: str) -> List['TestCase']:
        """Loads tool tests from a YAML file."""
        with open(test_file_path, 'r') as f:
            return self.load_tool_test_cases_from_yaml(f.read())

    def load_tool_test_cases_from_yaml(self, yaml_data: str) -> List['TestCase']:
        """Loads tool tests from a YAML string."""
        raw_data = yaml.safe_load(yaml_data)
        if not raw_data or 'tests' not in raw_data:
            return []

        return self.load_tool_test_cases_from_data(raw_data['tests'])

    def load_tool_test_cases_from_data(self, test_data: List[Dict[str, Any]]) -> List['TestCase']:
        """Loads tool tests from a list of dictionaries."""
        # Pre-process data to handle VariableDeclaration objects
        cleaned_data = []
        for case in test_data:
            case_copy = case.copy()
            if "variables" in case_copy and isinstance(case_copy["variables"], dict):
                cleaned_vars = {}
                for k, v in case_copy["variables"].items():
                    cleaned_vars[k] = self.variable_to_dict(v)
                case_copy["variables"] = cleaned_vars
            cleaned_data.append(case_copy)

        adapter = TypeAdapter(List[TestCase])
        return adapter.validate_python(cleaned_data)

    @staticmethod
    def variable_to_dict(variable: Any) -> Any:
        """Converts a VariableDeclaration object or other types to a dictionary/value."""
        from proto.marshal.collections import repeated, maps

        # 1. Handle RepeatedComposite (List)
        if isinstance(variable, repeated.RepeatedComposite):
            return [EvalUtils.variable_to_dict(v) for v in variable]

        # 2. Handle MapComposite (Dict)
        if isinstance(variable, maps.MapComposite):
            return {k: EvalUtils.variable_to_dict(v) for k, v in variable.items()}

        # 3. If it's already a dict or primitive, return as is
        if isinstance(variable, (dict, list, str, int, float, bool, type(None))):
             return variable
        
        # 4. Priority: Check for schema.default (VariableDeclaration pattern)
        try:
             if hasattr(variable, "schema") and hasattr(variable.schema, "default"):
                 return EvalUtils.variable_to_dict(variable.schema.default)
        except Exception:
             pass

        # 5. Check if it has a to_dict method (common in Google Protobufs)
        if hasattr(variable, "to_dict"):
             return variable.to_dict()
             
        # 6. Check if it has a to_dict method on the type
        if hasattr(type(variable), "to_dict"):
             return type(variable).to_dict(variable)

        return variable

    def _get_value_at_path(self, data: Any, path: str) -> Any:
        """Retrieves value from data using dot notation (e.g., 'a.b.c' or 'list.0.item')."""
        jsonpath_expression = parse(path)
        matches = jsonpath_expression.find(data)
        if matches:
            return [m.value for m in matches] if len(matches) > 1 else matches[0].value
        return None

    def _check_expectation(
        self, actual: Any, expectation: 'Expectation'
    ) -> bool:
        """Checks if actual value meets the expectation."""
        op = expectation.operator
        expected = expectation.value

        if op == Operator.EQUALS:
            return actual == expected
        elif op == Operator.CONTAINS:
            if isinstance(actual, (str, list, dict)):
                return expected in actual
            return False
        elif op == Operator.GREATER_THAN:
            try:
                return actual > expected
            except TypeError:
                return False
        elif op == Operator.LESS_THAN:
            try:
                return actual < expected
            except TypeError:
                return False
        elif op == Operator.LENGTH_EQUALS:
            try:
                return len(actual) == expected
            except TypeError:
                return False
        elif op == Operator.LENGTH_GREATER_THAN:
            try:
                return len(actual) > expected
            except TypeError:
                return False
        elif op == Operator.LENGTH_LESS_THAN:
            try:
                return len(actual) < expected
            except TypeError:
                return False
        elif op == Operator.IS_NULL:
            return actual is None
        elif op == Operator.IS_NOT_NULL:
            return actual is not None
        return False

    def validate_tool_test(
        self,
        test_case: 'TestCase',
        tool_response: Any,
    ) -> List[str]:
        """Validates the tool response and variables against expectations.

        Returns:
            List of error messages. Empty list if all expectations pass.
        """
        updated_variables = {}
        if isinstance(tool_response, dict) and "variables" in tool_response:
             updated_variables = tool_response["variables"]
        
        # If response is just the JSON from API, it might have 'toolResponse' key or be flat
        # The execute_tool returns JSON.
        # Assuming typical tool response structure.
        # If 'response' key exists in test expectations, we check against tool_response directly or tool_response['response']?
        # The original code checked `tool_response["response"]`.
        # We'll assume the API returns something like {response: ..., variables: ...} or we adapt.
        # For now, following original logic: expects "response" key in tool_response.
        
        errors = []
        # Validate response
        for exp in test_case.response_expectations:
            # Safe access
            resp_data = tool_response.get("response") if isinstance(tool_response, dict) else tool_response
            # If "response" key is missing, maybe the whole thing is the response?
            # Adjust based on observed API behavior.
            actual_value = self._get_value_at_path(resp_data, exp.path)
            if not self._check_expectation(actual_value, exp):
                errors.append(
                    f"Response expectation failed: path='{exp.path}',"
                    f" actual='{actual_value}', expected='{exp.value}',"
                    f" operator='{exp.operator}'"
                )

        # Validate variables
        for exp in test_case.variable_expectations:
            actual_value = self._get_value_at_path(updated_variables, exp.path)
            if not self._check_expectation(actual_value, exp):
                errors.append(
                    f"Variable expectation failed: path='{exp.path}',"
                    f" actual='{actual_value}', expected='{exp.value}',"
                    f" operator='{exp.operator}'"
                )

        return errors

    def run_tool_tests(self, test_cases: List['TestCase'], debug: bool = False) -> Any:
        """Runs a list of tool tests.
        
        Returns:
            A list of results (dicts) with status and errors.
        """
        from google.protobuf.json_format import MessageToDict
        
        tool_map = self.tools_client.get_tools_map(self.app_id, reverse=True)

        # Fetch and unwrap app variables once
        raw_app_vars = self.var_client.list_variables(self.app_id)
        app_vars_cache = {}
        for var in raw_app_vars:
            try:
                var_dict = MessageToDict(var._pb)
            except AttributeError:
                var_dict = MessageToDict(var)

            schema = var_dict.get("schema", {})
            actual_data = schema.get("default") or var_dict.get("value") or {}
            app_vars_cache[var.name] = actual_data

        results = []
        for test_case in test_cases:
            print(f"Running test: {test_case.name} ({test_case.tool})")
            
            tool_id = tool_map.get(test_case.tool)
            if not tool_id:
                error = f"Tool '{test_case.tool}' not found in app."
                print(f"FAILURE: {error}")
                results.append({
                    "test": test_case.name,
                    "tool": test_case.tool,
                    "status": "FAILURE",
                    "errors": [error]
                })
                continue

            # 3. Filter and merge variables for this specific test case
            final_variables = {}
            for var_name, custom_val in test_case.variables.items():
                if custom_val is None:
                    # User requested an existing app variable by name
                    if var_name in app_vars_cache:
                        final_variables[var_name] = app_vars_cache[var_name]
                    else:
                        print(f"[WARNING] App variable '{var_name}' requested but not found in app.")
                else:
                    # User provided their own custom mock data
                    final_variables[var_name] = custom_val

            try:
                # Calculate tool_display_name or toolset key logic
                # execute_tool needs tool_display_name? 
                # In original script: tool_id = self.tool_display_name_id_map[test_case.tool]
                # execute_tool(..., tool_id, test_case.tool, ...)
                # So test_case.tool IS the display name.
                
                if debug:
                    print(f"[DEBUG] Executing tool: {test_case.tool}")
                    print(f"[DEBUG] Tool ID: {tool_id}")
                    print(f"[DEBUG] Args: {test_case.args}")
                    print(f"[DEBUG] Variables: {final_variables}")
                    
                tool_response = self.tools_client.execute_tool(
                    app_id=self.app_id,
                    tool_display_name=test_case.tool,
                    args=test_case.args,
                    variables=final_variables
                )
                
                if debug:
                    print(f"[DEBUG] Tool Response: {tool_response}")
                
                errors = self.validate_tool_test(test_case, tool_response)
                status = "SUCCESS"
                if errors:
                    status = "FAILURE"
                
                print(f"{status}: {test_case.tool} --> {test_case.name}")
                if errors:
                    print(errors)
                    
                results.append({
                    "test": test_case.name,
                    "tool": test_case.tool,
                    "status": status,
                    "errors": errors,
                    "response": tool_response
                })
                
            except Exception as e:
                print(f"FAILURE: Exception {e}")
                results.append({
                    "test": test_case.name,
                    "tool": test_case.tool,
                    "status": "FAILURE",
                    "errors": [str(e)]
                })
                
            print("-" * 30)

        return results


# --- Tool Testing Classes ---

# Helper function to convert None (from YAML) into an empty dict
def parse_variables_input(v: Any) -> Dict[str, Any]:
    """Allows YAML to accept a list of strings OR a custom dictionary."""
    if v is None:
        return {}
    if isinstance(v, list):
        # Convert list of names to a dict flagged for fetching (None)
        return {str(item): None for item in v}
    if isinstance(v, dict):
        return v
    return {}

# Helper function to convert None (from YAML) into an empty dict
def empty_to_dict(v: Any) -> Any:
    return v if v is not None else {}

# Helper function to convert None (from YAML) into an empty list
def empty_to_list(v: Any) -> Any:
    return v if v is not None else []

class Operator(str, enum.Enum):
    EQUALS = 'equals'
    CONTAINS = 'contains'
    GREATER_THAN = 'greater_than'
    LESS_THAN = 'less_than'
    LENGTH_EQUALS = 'length_equals'
    LENGTH_GREATER_THAN = 'length_greater_than'
    LENGTH_LESS_THAN = 'length_less_than'
    IS_NULL = 'is_null'
    IS_NOT_NULL = 'is_not_null'

class Expectation(BaseModel):
    path: str
    operator: Operator
    value: Optional[Any] = None

class TestCase(BaseModel):
    name: str
    tool: str

    # We wrap the type in Annotated to add the BeforeValidator
    args: Annotated[Dict[str, Any], BeforeValidator(empty_to_dict)] = Field(
        default_factory=dict,
        validation_alias=AliasChoices("args", "agrs")
    )

    variables: Annotated[Dict[str, Any], BeforeValidator(parse_variables_input)] = Field(
        default_factory=dict
    )

    response_expectations: Annotated[List[Expectation], BeforeValidator(empty_to_list)] = Field(
        default_factory=list,
        validation_alias=AliasPath("expectations", "response")
    )

    variable_expectations: Annotated[List[Expectation], BeforeValidator(empty_to_list)] = Field(
        default_factory=list,
        validation_alias=AliasPath("expectations", "variables")
    )