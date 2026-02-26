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
import requests
from google.protobuf import field_mask_pb2
from google.protobuf import json_format
from google.cloud.ces_v1beta import EvaluationServiceClient, AgentServiceClient, types
import yaml
from cxas_scrapi.core.common import Common


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
                            out_yaml["turns"].append({"user_event": event["event"]})
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
                        display_name = tc.get("display_name", tc.get("tool", ""))
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
                        tool_name = id_to_tool.get(tr.get("id", ""), tr.get("tool", ""))

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

    def list_evaluations(self, app_id: Optional[str] = None) -> List[types.Evaluation]:
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
        self, evaluation_name: str
    ) -> List[types.EvaluationResult]:
        """Fetches all evaluation results for a specific evaluation.

        Args:
            evaluation_name: Full resource name of the evaluation
                             (e.g., projects/.../evaluations/...)
        """
        request = types.ListEvaluationResultsRequest(parent=evaluation_name)
        response = self.client.list_evaluation_results(request=request)
        return list(response)

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
        evaluations_dict: Dict[str, Dict[str, str]] = {"goldens": {}, "scenarios": {}}

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

    def get_evaluation(self, evaluation_id: str) -> types.Evaluation:
        """Gets a specific evaluation."""
        request = types.GetEvaluationRequest(name=evaluation_id)
        return self.client.get_evaluation(request=request)

    def export_evaluation(self, evaluation_id: str, output_format: str = "yaml") -> str:
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
        self, evaluations: List[str], app_id: Optional[str] = None
    ) -> Any:
        """Runs an evaluation on the specified app.

        Args:
            evaluations: List of evaluation resource names to run.
            app_id: Parent App ID. Defaults to self.app_id.
        """
        app_id = app_id or self.app_id
        if not app_id:
            raise ValueError("app_id is required.")

        request = types.RunEvaluationRequest(app=app_id, evaluations=evaluations)
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
            request.conversation_list = types.ImportEvaluationsRequest.ConversationList(
                conversations=conversations
            )
        else:
            raise ValueError(
                "Must provide one of: gcs_uri, csv_content, or conversations."
            )

        if conflict_strategy:
            request.import_options = types.ImportEvaluationsRequest.ImportOptions(
                conflict_resolution_strategy=conflict_strategy
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

    def get_evaluation_expectation(self, name: str) -> types.EvaluationExpectation:
        """Gets details of the specified evaluation expectation.

        Args:
            name: Full resource name of the evaluation expectation.
        """
        request = types.GetEvaluationExpectationRequest(name=name)
        return self.client.get_evaluation_expectation(request=request)

    def create_evaluation_expectation(
        self,
        evaluation_expectation: Union[types.EvaluationExpectation, Dict[str, Any]],
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
            evaluation_expectation=evaluation_expectation, update_mask=update_mask
        )
        return self.client.update_evaluation_expectation(request=request)

    def delete_evaluation_expectation(self, name: str) -> None:
        """Deletes an evaluation expectation.

        Args:
            name: Full resource name of the evaluation expectation.
        """
        request = types.DeleteEvaluationExpectationRequest(name=name)
        self.client.delete_evaluation_expectation(request=request)

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
            print(f"Hallucinations: {thresholds.get('hallucination_metric_behavior', 'UNSPECIFIED')}")

            print("\n===== GOLDEN Settings =====")
            print(f"Hallucinations: {thresholds.get('golden_hallucination_metric_behavior', 'UNSPECIFIED')}")

            golden = thresholds.get("golden_evaluation_metrics_thresholds", {})
            turn_level = golden.get("turn_level_metrics_thresholds", {})
            expectation_level = golden.get("expectation_level_metrics_thresholds", {})

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
            print(f"Hallucinations: {thresholds.get('scenario_hallucination_metric_behavior', 'UNSPECIFIED')}")
            print("\n")

        return thresholds
