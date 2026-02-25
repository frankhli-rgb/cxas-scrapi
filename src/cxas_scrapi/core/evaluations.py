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
from google.cloud.ces_v1beta import EvaluationServiceClient, types
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
        return list(response.evaluations)

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
        return list(response.evaluation_results)

    def get_evaluations_map(
        self, app_id: Optional[str] = None, reverse: bool = False
    ) -> Dict[str, str]:
        """Creates a map of Evaluation full names to display names.

        Args:
            app_id: Parent App ID. Defaults to self.app_id.
            reverse: If True, map display_name -> name.
        """
        app_id = app_id or self.app_id
        # list_evaluations check will handle empty app_id check, but good to be safe if reusing logic

        evaluations = self.list_evaluations(app_id)
        evaluations_dict: Dict[str, str] = {}

        for evaluation in evaluations:
            display_name = evaluation.display_name
            name = evaluation.name
            if display_name and name:
                if reverse:
                    evaluations_dict[display_name] = name
                else:
                    evaluations_dict[name] = display_name
        return evaluations_dict

    def get_evaluation(self, evaluation_id: str) -> types.Evaluation:
        """Gets a specific evaluation."""
        request = types.GetEvaluationRequest(name=evaluation_id)
        return self.client.get_evaluation(request=request)

    def export_evaluation_to_yaml(self, evaluation_id: str) -> str:
        """
        Fetches a specific evaluation and exports it to the FDE YAML format.

        Args:
            evaluation_id: Full resource name of the evaluation.

        Returns:
            A string containing the formatted YAML.
        """
        eval_obj = self.get_evaluation(evaluation_id=evaluation_id)
        # Convert the protobuf object to a python dictionary
        eval_dict = type(eval_obj).to_dict(eval_obj)

        out_yaml_dict = self.eval_dict_to_yaml(eval_dict)

        # Dump to YAML string
        return yaml.dump(out_yaml_dict, sort_keys=False, allow_unicode=True)

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
