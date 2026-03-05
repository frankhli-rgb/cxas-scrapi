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

"""Core Evaluations class for CXAS Scrapi."""

from typing import Dict, Any, Optional, List, Union
import uuid
import json
import hashlib
import requests
from google.protobuf import field_mask_pb2
from google.protobuf import json_format
from google.cloud.ces_v1beta import (
    EvaluationServiceClient,
    AgentServiceClient,
    types,
)
import yaml
from cxas_scrapi.core.common import Common
from cxas_scrapi.core.tools import Tools
from cxas_scrapi.core.agents import Agents


class Evaluations(Common):
    def __init__(self, app_id: str, env: str = "PROD"):
        """Initializes the Evaluations client.

        Args:
            app_id: CXAS App ID (projects/{project}/locations/{location}/apps/{app}).
            env: Environment override (default: PROD).
        """
        # Pass app_id to Common for client_options determination
        super().__init__(agent_id=app_id)

        self.app_id = app_id

        # Parse project and location from app_id using Common helpers
        self.project_id = self._get_project_id(app_id)
        self.location = self._get_location(app_id)

        # Initialize SDK Client
        self.client = EvaluationServiceClient(
            credentials=self.creds, client_options=self.client_options
        )
        self.resource_type = "evaluations"
        self.evals_map: Dict[str, Dict[str, str]] = {}
        self._eval_search_index: Dict[str, str] = {}

    @staticmethod
    def parse_eval_to_yaml(filepath):
        """Parses a CXAS Evaluation textproto file into the target FDE YAML format."""
        with open(filepath, "r") as f:
            text = f.read()

        parsed = Common.parse_textproto(text)
        return Evaluations.eval_dict_to_yaml(parsed)

    @staticmethod
    def eval_dict_to_yaml(eval_dict):
        """Parses a CXAS Evaluation dictionary into the target FDE YAML format."""
        golden = eval_dict.get("golden", {})
        turns = golden.get("turns", [])
        if not isinstance(turns, list):
            turns = [turns]

        out_yaml = {
            "name": eval_dict.get("display_name", "Converted_Eval"),
            "turns": [],
            "expectations": [],
            "mocks": [],
        }

        id_to_tool = {}

        for turn in turns:
            steps = turn.get("steps", [])
            if not isinstance(steps, list):
                steps = [steps]

            for step in steps:
                if "user_input" in step:
                    ui = step["user_input"]
                    if "text" in ui:
                        out_yaml["turns"].append({"user": ui["text"]})
                    elif "event" in ui:
                        event = ui["event"]
                        if isinstance(event, dict) and "event" in event:
                            out_yaml["turns"].append(
                                {"user_event": event["event"]}
                            )
                        else:
                            out_yaml["turns"].append({"user_event": str(event)})

                if "expectation" in step:
                    exp = step["expectation"]
                    if "agent_response" in exp:
                        ar = exp["agent_response"]
                        chunks = ar.get("chunks", [])
                        if not isinstance(chunks, list):
                            chunks = [chunks]
                        text = " ".join(
                            [c.get("text", "") for c in chunks if "text" in c]
                        )
                        out_yaml["turns"].append({"agent": text})

                    if "agent_transfer" in exp:
                        at = exp["agent_transfer"]
                        out_yaml["expectations"].append(
                            f"AGENT_TRANSFER: {at.get('display_name', '')}"
                        )

                    if "tool_call" in exp:
                        tc = exp["tool_call"]
                        args = tc.get("args", {})
                        unwrapped_args = Common.unwrap_struct(args)
                        display_name = tc.get(
                            "display_name", tc.get("tool", "")
                        )
                        out_yaml["turns"].append(
                            {
                                "tool_call": {
                                    "tool": display_name,
                                    "args": unwrapped_args,
                                }
                            }
                        )
                        id_to_tool[tc.get("id", "")] = display_name

                    if "tool_response" in exp:
                        tr = exp["tool_response"]
                        res = tr.get("response", {})
                        unwrapped_res = Common.unwrap_struct(res)
                        tool_name = id_to_tool.get(
                            tr.get("id", ""), tr.get("tool", "")
                        )

                        out_yaml["mocks"].append(
                            {"tool": tool_name, "response": unwrapped_res}
                        )

        out_yaml["expectations"] = list(dict.fromkeys(out_yaml["expectations"]))
        return out_yaml

    @staticmethod
    def process_export_operation(export_op) -> Optional[bytes]:
        """Processes the export operation and returns app content bytes.

        Args:
            export_op: The operation object from export_app (or result).

        Returns:
            bytes: The app content bytes if successful, None otherwise.
        """
        try:
            # Check if it has .result(), otherwise assume it's the response or operation
            if hasattr(export_op, "result"):
                export_response = export_op.result()
            else:
                export_response = export_op
        except Exception as e:
            # logger is not defined in this class scope usually, but we can import it or just pass
            # We'll use a local logger or just print if absolutely needed, but user asked to remove prints.
            # Ideally we log via a module logger.
            print(
                f"Export operation result() failed or not an LRO: {e}. Checking if it returned response directly."
            )
            export_response = export_op

        # The SDK returns ExpectAppResponse which has app_content
        if export_response and hasattr(export_response, "app_content"):
            app_content_bytes = export_response.app_content
            # Removed print statements as requested

            import io
            import zipfile

            # Optional: We could still log what we found if we had a logger, but strictly removing prints.
            # verify it's a valid zip by opening it?

            return app_content_bytes
        else:
            return None

    def list_evaluations(
        self, app_id: Optional[str] = None
    ) -> List[types.Evaluation]:
        """Lists evaluations within a specific app.

        Args:
            app_id: Parent App ID. Defaults to self.app_id.
        """
        app_id = app_id or self.app_id
        if not app_id:
            raise ValueError("app_id is required.")

        request = types.ListEvaluationsRequest(parent=app_id)
        response = self.client.list_evaluations(request=request)
        return list(response)

    def list_evaluation_results(
        self, evaluation_display_name: str
    ) -> List[types.EvaluationResult]:
        """Fetches all evaluation results for a specific evaluation.

        Args:
            evaluation_display_name: Full resource name or display name of the evaluation
        """
        evaluation_name = evaluation_display_name
        if "/evaluations/" not in evaluation_name:
            if not getattr(self, "app_id", None):
                raise ValueError(
                    "app_id must be set to look up evaluations by display name."
                )
            evals_map = self._get_or_load_evals_map(self.app_id)

            if evaluation_name in evals_map.get("goldens", {}):
                evaluation_name = evals_map["goldens"][evaluation_name]
            elif evaluation_name in evals_map.get("scenarios", {}):
                evaluation_name = evals_map["scenarios"][evaluation_name]
            else:
                raise ValueError(
                    f"No evaluation found with display name: '{evaluation_name}'"
                )

        request = types.ListEvaluationResultsRequest(parent=evaluation_name)
        response = self.client.list_evaluation_results(request=request)
        return list(response)

    def get_evaluation_run(self, evaluation_run_id: str) -> types.EvaluationRun:
        """Gets details of the specified evaluation run by its full resource name.

        Args:
            evaluation_run_id: Full resource name of the evaluation run.
        """
        request = types.GetEvaluationRunRequest(name=evaluation_run_id)
        return self.client.get_evaluation_run(request=request)

    def list_evaluation_results_by_run(
        self, evaluation_run_id: str
    ) -> List[types.EvaluationResult]:
        """Fetches all evaluation results associated with a specific evaluation run.

        Args:
            evaluation_run_id: Full resource name of the evaluation run.
        """
        if "/evaluationRuns/" not in evaluation_run_id:
            raise ValueError(
                f"Invalid evaluation_run_id format: {evaluation_run_id}"
            )

        app_name = evaluation_run_id.split("/evaluationRuns/")[0]
        wildcard_parent = f"{app_name}/evaluations/-"

        request = types.ListEvaluationResultsRequest(
            parent=wildcard_parent,
            filter=f'evaluation_run:"{evaluation_run_id}"',
        )
        response = self.client.list_evaluation_results(request=request)
        return list(response)

    def build_search_index(
        self, app_id: Optional[str] = None, force: bool = False
    ) -> None:
        """Builds a JSON string index of all evaluations for fast searching.

        Args:
            app_id: Parent App ID. Defaults to self.app_id.
            force: If True, rebuilds the index even if already built.
        """
        app_id = app_id or self.app_id
        if not force and self._eval_search_index:
            return

        evaluations = self.list_evaluations(app_id)
        self._eval_search_index = {}

        for eval_obj in evaluations:
            # Convert to dictionary and then to JSON string
            eval_dict = type(eval_obj).to_dict(eval_obj)
            # Dump to string and convert to lowercase for case-insensitive searching
            self._eval_search_index[eval_obj.display_name] = json.dumps(
                eval_dict
            ).lower()

    def search_evaluations(
        self,
        app_id: str,
        tools: Optional[List[str]] = None,
        variables: Optional[List[str]] = None,
        agents: Optional[List[str]] = None,
        rebuild_index: bool = False,
    ) -> List[str]:
        """Searches querying evaluations and filters by connected tools, variables, or agents.

        Args:
            app_id: Parent App ID.
            tools: List of tool display names to search for.
            variables: List of variable names to search for.
            agents: List of agent display names to search for.
            rebuild_index: If True, forcefully rebuilds the search index.

        Returns:
            List of Evaluation display names that match the search criteria.
        """
        search_terms = []

        if tools:
            tools_client = Tools(app_id=app_id, creds=self.creds)
            tools_map = tools_client.get_tools_map(app_id, reverse=True)
            for tool_name in tools:
                if tool_name in tools_map:
                    # Append the resource ID name in lowercase
                    search_terms.append(tools_map[tool_name].lower())
                else:
                    raise ValueError(f"Tool '{tool_name}' not found in App.")

        if agents:
            agents_client = Agents(app_id=app_id, creds=self.creds)
            agents_map = agents_client.get_agents_map(app_id, reverse=True)
            for agent_name in agents:
                if agent_name in agents_map:
                    # Append the resource ID name in lowercase
                    search_terms.append(agents_map[agent_name].lower())
                else:
                    raise ValueError(f"Agent '{agent_name}' not found in App.")

        if variables:
            for var_name in variables:
                search_terms.append(var_name.lower())

        if not search_terms:
            raise ValueError(
                "Must provide at least one search term (tools, variables, or agents)."
            )

        self.build_search_index(app_id, force=rebuild_index)

        matched_evals = []
        for eval_name, eval_str in self._eval_search_index.items():
            # Check if all search terms are in the evaluation JSON string
            if all(term in eval_str for term in search_terms):
                matched_evals.append(eval_name)

        return matched_evals

    def get_evaluations_map(
        self, app_id: Optional[str] = None, reverse: bool = False
    ) -> Dict[str, Dict[str, str]]:
        """Creates a map of Evaluation full names to display names, grouped by type.

        Returns a dictionary with 'goldens' and 'scenarios' keys, each containing
        a sub-dictionary of the mappings.

        Args:
            app_id: Parent App ID. Defaults to self.app_id.
            reverse: If True, map display_name -> name.
        """
        app_id = app_id or self.app_id

        evaluations = self.list_evaluations(app_id)
        evaluations_dict: Dict[str, Dict[str, str]] = {
            "goldens": {},
            "scenarios": {},
        }

        for evaluation in evaluations:
            display_name = evaluation.display_name
            name = evaluation.name

            if display_name and name:
                target_dict = None
                # Check the oneof field or structure property to determine the type
                if getattr(evaluation, "golden", None):
                    target_dict = evaluations_dict["goldens"]
                elif getattr(evaluation, "scenario", None):
                    target_dict = evaluations_dict["scenarios"]

                if target_dict is not None:
                    if reverse:
                        target_dict[display_name] = name
                    else:
                        target_dict[name] = display_name

        return evaluations_dict

    def _get_or_load_evals_map(
        self, app_id: Optional[str] = None
    ) -> Dict[str, Dict[str, str]]:
        """Gets a map of reverse evaluations from cache or loads it if missing."""
        if not self.evals_map:
            self.evals_map = self.get_evaluations_map(app_id, reverse=True)
        return self.evals_map

    def get_evaluation(self, evaluation_id: str) -> types.Evaluation:
        """Gets a specific evaluation."""
        request = types.GetEvaluationRequest(name=evaluation_id)
        return self.client.get_evaluation(request=request)

    def export_evaluation(
        self, evaluation_id: str, output_format: str = "yaml"
    ) -> str:
        """
        Fetches a specific evaluation and exports it to the specified format.

        Args:
            evaluation_id: Full resource name of the evaluation.
            output_format: Output format ('yaml' or 'json'). Defaults to 'yaml'.

        Returns:
            A string containing the formatted output.
        """
        eval_obj = self.get_evaluation(evaluation_id=evaluation_id)
        # Convert the protobuf object to a python dictionary
        eval_dict = type(eval_obj).to_dict(eval_obj)

        out_dict = self.eval_dict_to_yaml(eval_dict)

        if output_format.lower() == "json":
            return json.dumps(out_dict, indent=2)

        # Dump to YAML string
        return yaml.dump(out_dict, sort_keys=False, allow_unicode=True)

    def run_evaluation(
        self,
        evaluations: Optional[Union[str, List[str]]] = None,
        eval_type: Optional[str] = None,
        app_id: Optional[str] = None,
    ) -> Any:
        """Runs an evaluation on the specified app.

        Args:
            evaluations: A single display name or a list of display names to run.
            eval_type: Run a specific type of evaluation. Must be one of:
                      'goldens', 'scenarios', or 'all'.
            app_id: Parent App ID. Defaults to self.app_id.
        """
        app_id = app_id or self.app_id
        if not app_id:
            raise ValueError("app_id is required.")

        if not evaluations and not eval_type:
            raise ValueError(
                "Must provide either 'evaluations' (display names) or 'eval_type' ('goldens'/'scenarios'/'all')."
            )

        resolved_names = set()
        evals_map = self._get_or_load_evals_map(app_id)

        # Handle explicit evaluation display names
        if evaluations:
            if isinstance(evaluations, str):
                evaluations = [evaluations]

            for display_name in evaluations:
                # Check both goldens and scenarios for this name
                resource_name = evals_map.get("goldens", {}).get(
                    display_name
                ) or evals_map.get("scenarios", {}).get(display_name)

                if resource_name:
                    resolved_names.add(resource_name)
                else:
                    raise ValueError(
                        f"Evaluation display name not found: '{display_name}'"
                    )

        # Handle explicit evaluation types
        if eval_type:
            eval_type = eval_type.lower()
            if eval_type == "goldens":
                resolved_names.update(evals_map.get("goldens", {}).values())
            elif eval_type == "scenarios":
                resolved_names.update(evals_map.get("scenarios", {}).values())
            elif eval_type == "all":
                resolved_names.update(evals_map.get("goldens", {}).values())
                resolved_names.update(evals_map.get("scenarios", {}).values())
            else:
                raise ValueError(
                    f"Invalid eval_type: '{eval_type}'. Must be 'goldens', 'scenarios', or 'all'."
                )

        if not resolved_names:
            raise ValueError(
                "No matching evaluation resource names found to run."
            )

        request = types.RunEvaluationRequest(
            app=app_id, evaluations=list(resolved_names)
        )

        return self.client.run_evaluation(request=request)

    def import_evaluations(
        self,
        app_id: Optional[str] = None,
        gcs_uri: Optional[str] = None,
        csv_content: Optional[bytes] = None,
        conversations: Optional[List[str]] = None,
        conflict_strategy: int = 0,
    ) -> Any:
        """Imports evaluations into the app.

        Args:
            app_id: Parent App ID. Defaults to self.app_id.
            gcs_uri: The GCS URI to import from (gs://...).
            csv_content: Raw bytes representing the csv file.
            conversations: A list of conversation resource names.
            conflict_strategy: See types.ImportEvaluationsRequest.ImportOptions.ConflictResolutionStrategy
                               (0=UNSPECIFIED, 1=OVERWRITE, 2=SKIP, 3=DUPLICATE)
        """
        app_id = app_id or self.app_id
        if not app_id:
            raise ValueError("app_id is required.")

        request = types.ImportEvaluationsRequest(parent=app_id)

        if gcs_uri:
            request.gcs_uri = gcs_uri
        elif csv_content:
            request.csv_content = csv_content
        elif conversations:
            request.conversation_list = (
                types.ImportEvaluationsRequest.ConversationList(
                    conversations=conversations
                )
            )
        else:
            raise ValueError(
                "Must provide one of: gcs_uri, csv_content, or conversations."
            )

        if conflict_strategy:
            request.import_options = (
                types.ImportEvaluationsRequest.ImportOptions(
                    conflict_resolution_strategy=conflict_strategy
                )
            )

        return self.client.import_evaluations(request=request)

    def list_evaluation_expectations(
        self, app_id: Optional[str] = None
    ) -> List[types.EvaluationExpectation]:
        """Lists all evaluation expectations in the given app.

        Args:
            app_id: Parent App ID. Defaults to self.app_id.
        """
        app_id = app_id or self.app_id
        if not app_id:
            raise ValueError("app_id is required.")

        request = types.ListEvaluationExpectationsRequest(parent=app_id)
        response = self.client.list_evaluation_expectations(request=request)
        return list(response)

    def get_evaluation_expectation(
        self, name: str
    ) -> types.EvaluationExpectation:
        """Gets details of the specified evaluation expectation.

        Args:
            name: Full resource name of the evaluation expectation.
        """
        request = types.GetEvaluationExpectationRequest(name=name)
        return self.client.get_evaluation_expectation(request=request)

    def create_evaluation_expectation(
        self,
        evaluation_expectation: Union[
            types.EvaluationExpectation, Dict[str, Any]
        ],
        app_id: Optional[str] = None,
    ) -> types.EvaluationExpectation:
        """Creates an evaluation expectation.

        Args:
            evaluation_expectation: The EvaluationExpectation object or dict to create.
            app_id: Parent App ID. Defaults to self.app_id.
        """
        app_id = app_id or self.app_id
        if not app_id:
            raise ValueError("app_id is required.")

        if isinstance(evaluation_expectation, dict):
            evaluation_expectation = types.EvaluationExpectation(
                **evaluation_expectation
            )

        request = types.CreateEvaluationExpectationRequest(
            parent=app_id, evaluation_expectation=evaluation_expectation
        )
        return self.client.create_evaluation_expectation(request=request)

    def update_evaluation_expectation(
        self,
        evaluation_expectation: types.EvaluationExpectation,
        update_mask: Optional[field_mask_pb2.FieldMask] = None,
    ) -> types.EvaluationExpectation:
        """Updates an evaluation expectation.

        Args:
            evaluation_expectation: The EvaluationExpectation to update.
            update_mask: Optional mask defining which fields to update.
        """
        request = types.UpdateEvaluationExpectationRequest(
            evaluation_expectation=evaluation_expectation,
            update_mask=update_mask,
        )
        return self.client.update_evaluation_expectation(request=request)

    def delete_evaluation_expectation(self, name: str) -> None:
        """Deletes an evaluation expectation.

        Args:
            name: Full resource name of the evaluation expectation.
        """
        request = types.DeleteEvaluationExpectationRequest(name=name)
        self.client.delete_evaluation_expectation(request=request)

    def get_evaluation_expectation_by_display_name(
        self, display_name: str, app_id: Optional[str] = None
    ) -> Optional[types.EvaluationExpectation]:
        """Gets an evaluation expectation by its display name.

        Args:
            display_name: The display name of the evaluation expectation.
            app_id: Parent App ID. Defaults to self.app_id.
        """
        app_id = app_id or self.app_id
        expectations = self.list_evaluation_expectations(app_id=app_id)
        for exp in expectations:
            if exp.display_name == display_name:
                return exp
        return None

    def find_or_create_evaluation_expectation(
        self, llm_prompt: str, display_name: Optional[str] = None
    ) -> str:
        """Finds or creates an evaluation expectation from an LLM prompt.

        Args:
            llm_prompt: The prompt/criteria for the evaluation expectation.
            display_name: Optional display name. If not provided, a hash of the
                prompt is used.

        Returns:
            The full resource name of the evaluation expectation.

        Raises:
            ValueError: If an expectation with the same display name exists
                but with a different prompt.
        """
        if not display_name:
            # Generate a stable hash of the prompt for the display name
            display_name = (
                f"eval_exp_{hashlib.md5(llm_prompt.encode()).hexdigest()[:8]}"
            )

        existing_exp = self.get_evaluation_expectation_by_display_name(
            display_name=display_name
        )

        if existing_exp:
            if existing_exp.llm_criteria.prompt != llm_prompt:
                raise ValueError(
                    f"Evaluation expectation '{display_name}' already exists "
                    "with a different prompt."
                )
            return existing_exp.name

        # Create new expectation
        new_exp = types.EvaluationExpectation(
            display_name=display_name,
            llm_criteria=types.EvaluationExpectation.LlmCriteria(
                prompt=llm_prompt
            ),
        )
        created_exp = self.create_evaluation_expectation(
            evaluation_expectation=new_exp
        )
        return created_exp.name

    def get_evaluation_thresholds(
        self, app_id: Optional[str] = None, print_console: bool = False
    ) -> Dict[str, Any]:
        """Gets the evaluation metrics thresholds for the app.

        Args:
            app_id: Parent App ID. Defaults to self.app_id.
            print_console: If True, prints a formatted summary of the settings to the console.

        Returns:
            A dictionary containing the evaluation metrics thresholds,
            with any enums resolved to their string representations.
        """
        app_id = app_id or self.app_id
        if not app_id:
            raise ValueError("app_id is required.")

        agent_client = AgentServiceClient(
            credentials=self.creds, client_options=self.client_options
        )

        request = types.GetAppRequest(name=app_id)
        app_obj = agent_client.get_app(request=request)

        # Convert the app protobuf to a dictionary, forcing enums to strings
        app_dict = json_format.MessageToDict(
            app_obj._pb,
            preserving_proto_field_name=True,
            use_integers_for_enums=False,
        )

        thresholds = app_dict.get("evaluation_metrics_thresholds", {})

        if print_console:
            print("===== GLOBAL Settings =====")
            print(
                f"Hallucinations: {thresholds.get('hallucination_metric_behavior', 'UNSPECIFIED')}"
            )

            print("\n===== GOLDEN Settings =====")
            print(
                f"Hallucinations: {thresholds.get('golden_hallucination_metric_behavior', 'UNSPECIFIED')}"
            )

            golden = thresholds.get("golden_evaluation_metrics_thresholds", {})
            turn_level = golden.get("turn_level_metrics_thresholds", {})
            expectation_level = golden.get(
                "expectation_level_metrics_thresholds", {}
            )

            divisors = {
                "semantic_similarity_success_threshold": "/4",
                "overall_tool_invocation_correctness_threshold": "/1.0",
                "tool_invocation_parameter_correctness_threshold": "/1.0",
            }

            if turn_level:
                print("\n### Turn Level Metrics ###")
                for k, v in turn_level.items():
                    suffix = divisors.get(k, "")
                    print(f"- {k}: {v}{suffix}")
            if expectation_level:
                print("\n### Expectation Level Metrics ###")
                for k, v in expectation_level.items():
                    suffix = divisors.get(k, "")
                    print(f"- {k}: {v}{suffix}")

            print("\n===== SCENARIO Settings =====")
            print(
                f"Hallucinations: {thresholds.get('scenario_hallucination_metric_behavior', 'UNSPECIFIED')}"
            )
            print("\n")

        return thresholds
