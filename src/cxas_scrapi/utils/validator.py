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

"""
Utility class for validating local ces apps.
"""

import os
import json
from pathlib import Path
import yaml
from google.protobuf import json_format
from google.cloud.ces_v1beta import types


class Validator:

    def validate_app(self, app_dir: str) -> bool:
        """
        Validates the app structure aligns with CES exported app structure

        Valid app directory structure:
        ./
          app.yaml or app.json
          global_instructions.txt
          agents/
          tools/
          toolsets/
          guardrails/


        Args:
          app_dir: Path to the app directory. e.g. apps/app-name/

        Returns:
          True if the app structure is valid, throws exception with details if not valid
        """
        loaded_app = self.load_app(app_dir)

        app_path = Path(app_dir)
        agents_dir = app_path / "agents"
        if not agents_dir.exists() or not agents_dir.is_dir():
            raise FileNotFoundError(
                f"Missing agents/ subdirectory in {app_dir}"
            )

        for item in agents_dir.iterdir():
            if item.is_dir():
                self.validate_agent(str(item))

        tools_dir = app_path / "tools"
        if tools_dir.exists() and tools_dir.is_dir():
            for item in tools_dir.iterdir():
                if item.is_dir():
                    self.validate_tool(str(item))

        toolsets_dir = app_path / "toolsets"
        if toolsets_dir.exists() and toolsets_dir.is_dir():
            for item in toolsets_dir.iterdir():
                if item.is_dir():
                    self.validate_toolset(str(item))

        guardrails_dir = app_path / "guardrails"
        if guardrails_dir.exists() and guardrails_dir.is_dir():
            for item in guardrails_dir.iterdir():
                if item.is_dir():
                    self.validate_guardrail(str(item))

        evaluations_dir = app_path / "evaluations"
        if evaluations_dir.exists() and evaluations_dir.is_dir():
            for item in evaluations_dir.iterdir():
                if item.is_dir():
                    self.validate_evaluation(str(item))

        evaluation_expectations_dir = app_path / "evaluation_expectations"
        if (
            evaluation_expectations_dir.exists()
            and evaluation_expectations_dir.is_dir()
        ):
            for item in evaluation_expectations_dir.iterdir():
                if item.is_dir():
                    self.validate_evaluation_expectations(str(item))

        return True

    def load_app(self, app_dir: str) -> types.App:
        """
        Loads app configuration from YAML or JSON.

        Args:
          app_dir: Path to the app directory.

        Returns:
          An App object with resolved file contents.
        """
        app_path = Path(app_dir)
        app_name = app_path.name

        app_dict = self._load_json_or_yaml(app_path, "app")

        app_obj = types.App()
        resolved_dict = self._resolve_paths(
            app_dict, (app_dir,), base_path=app_dir
        )
        json_format.ParseDict(
            resolved_dict, app_obj._pb, ignore_unknown_fields=False
        )
        return app_obj

    def validate_agent(
        self,
        agent_dir: str,
    ) -> bool:
        """
        Validates the agent structure aligns with CES exported app structure

        Valid agent directory structure:
        agents/<agent_name>/:
          <agent_name>.yaml or <agent_name>.json
          instruction.txt
          before_agent_callbacks/
          after_agent_callbacks/
          before_model_callbacks/
          after_model_callbacks/
          before_tool_callbacks/
          after_tool_callbacks/


        Args:
          agent_dir: Path to the agent directory. e.g. agents/agent-name/

        Returns:
          True if the agent structure is valid, throws exception with details if not valid
        """
        loaded_agent = self.load_agent(agent_dir)
        return True if loaded_agent else False

    def load_agent(self, agent_dir: str) -> types.Agent:
        """
        Loads agent configuration from YAML or JSON and resolves file paths.

        Args:
          agent_dir: Path to the agent directory.

        Returns:
          An Agent object with resolved file contents.
        """
        agent_path = Path(agent_dir)
        agent_name = agent_path.name

        agent_dict = self._load_json_or_yaml(agent_path, agent_name)

        resolved_dict = self._resolve_paths(agent_dict, ("agents/",), agent_dir)
        agent_obj = types.Agent()
        json_format.ParseDict(
            resolved_dict, agent_obj._pb, ignore_unknown_fields=False
        )
        return agent_obj

    def validate_tool(self, tool_dir: str) -> bool:
        """
        Validates the tool structure aligns with CES exported tool structure

        Valid tool directory structure:
        tools/<tool_name>/
          <tool_name>.yaml or <tool_name>.json


        Args:
          tool_dir: Path to the tool directory. e.g. tools/tool-name/

        Returns:
          True if the tool structure is valid, throws exception with details if not valid
        """
        loaded_tool = self.load_tool(tool_dir)
        return True if loaded_tool else False

    def load_tool(self, tool_dir: str) -> types.Tool:
        """
        Loads tool configuration from YAML or JSON and resolves file paths.

        Args:
          tool_dir: Path to the tool directory.

        Returns:
          An Tool object with resolved file contents.
        """
        tool_path = Path(tool_dir)
        tool_name = tool_path.name

        tool_dict = self._load_json_or_yaml(tool_path, tool_name)

        resolved_dict = self._resolve_paths(
            tool_dict, ("tools/",), base_path=tool_dir
        )

        tool_obj = types.Tool()
        json_format.ParseDict(
            resolved_dict, tool_obj._pb, ignore_unknown_fields=False
        )
        return tool_obj

    def validate_toolset(self, toolset_dir: str) -> bool:
        """
        Validates the toolset structure aligns with CES exported toolset structure.
        """
        loaded_toolset = self.load_toolset(toolset_dir)
        return True if loaded_toolset else False

    def load_toolset(self, toolset_dir: str) -> types.Toolset:
        """
        Loads toolset configuration from YAML or JSON and resolves file paths.
        """
        toolset_path = Path(toolset_dir)
        toolset_name = toolset_path.name

        toolset_dict = self._load_json_or_yaml(toolset_path, toolset_name)

        resolved_dict = self._resolve_paths(
            toolset_dict, ("toolsets/",), base_path=toolset_dir
        )

        toolset_obj = types.Toolset()
        json_format.ParseDict(
            resolved_dict, toolset_obj._pb, ignore_unknown_fields=False
        )
        return toolset_obj

    def validate_guardrail(self, guardrail_dir: str) -> bool:
        """
        Validates the guardrail structure aligns with CES exported guardrail structure.
        """
        loaded_guardrail = self.load_guardrail(guardrail_dir)
        return True if loaded_guardrail else False

    def load_guardrail(self, guardrail_dir: str) -> types.Guardrail:
        """
        Loads guardrail configuration from YAML or JSON.
        """
        guardrail_path = Path(guardrail_dir)
        guardrail_name = guardrail_path.name

        guardrail_dict = self._load_json_or_yaml(guardrail_path, guardrail_name)

        # Guardrails observed so far do not contain file references.

        guardrail_obj = types.Guardrail()
        json_format.ParseDict(
            guardrail_dict, guardrail_obj._pb, ignore_unknown_fields=False
        )
        return guardrail_obj

    def validate_evaluation(self, evaluation_dir: str) -> bool:
        """
        Validates the evaluation structure aligns with CES exported evaluation structure.
        """
        loaded_evaluation = self.load_evaluation(evaluation_dir)
        return True if loaded_evaluation else False

    def load_evaluation(self, evaluation_dir: str) -> types.Evaluation:
        """
        Loads evaluation configuration from YAML or JSON.
        """
        evaluation_path = Path(evaluation_dir)
        evaluation_name = evaluation_path.name

        evaluation_dict = self._load_json_or_yaml(
            evaluation_path, evaluation_name
        )

        # Evaluations observed so far do not contain file references.

        evaluation_obj = types.Evaluation()
        json_format.ParseDict(
            evaluation_dict, evaluation_obj._pb, ignore_unknown_fields=False
        )
        return evaluation_obj

    def validate_evaluation_expectations(
        self, evaluation_expectations_dir: str
    ) -> bool:
        """
        Validates the evaluation expectations structure aligns with CES exported evaluation expectations structure.
        """
        loaded_evaluation_expectations = self.load_evaluation_expectations(
            evaluation_expectations_dir
        )
        return True if loaded_evaluation_expectations else False

    def load_evaluation_expectations(
        self, evaluation_expectations_dir: str
    ) -> types.EvaluationExpectation:
        """
        Loads evaluation expectations configuration from YAML or JSON.
        """
        evaluation_expectations_path = Path(evaluation_expectations_dir)
        evaluation_expectations_name = evaluation_expectations_path.name

        evaluation_expectations_dict = self._load_json_or_yaml(
            evaluation_expectations_path, evaluation_expectations_name
        )

        # Evaluations observed so far do not contain file references.

        evaluation_expectations_obj = types.EvaluationExpectation()
        json_format.ParseDict(
            evaluation_expectations_dict,
            evaluation_expectations_obj._pb,
            ignore_unknown_fields=False,
        )
        return evaluation_expectations_obj

    def _load_json_or_yaml(self, directory: Path, file_name: str) -> dict:
        """Loads configuration from YAML or JSON.

        Args:
          directory: Path to the directory containing the file.
          file_name: Name of the file without extension.

        Returns:
          A dictionary with the loaded content.
        """
        yaml_path = directory / f"{file_name}.yaml"
        json_path = directory / f"{file_name}.json"

        if yaml_path.exists():
            with open(yaml_path, "r") as f:
                return yaml.safe_load(f)
        elif json_path.exists():
            with open(json_path, "r") as f:
                return json.load(f)
        else:
            raise FileNotFoundError(
                f"Missing {file_name}.yaml or {file_name}.json in {directory}"
            )

    def _resolve_paths(self, data, extra_prefixes=(), base_path=None):
        if isinstance(data, dict):
            return {
                k: self._resolve_paths(v, extra_prefixes, base_path)
                for k, v in data.items()
            }
        elif isinstance(data, list):
            return [
                self._resolve_paths(item, extra_prefixes, base_path)
                for item in data
            ]
        elif isinstance(data, str):
            looks_like_path = False
            if data.endswith((".txt", ".py", ".yaml", ".json")):
                looks_like_path = True

            if looks_like_path:
                path_to_check = Path(data)

                resolved = False

                # Try resolving relative to base_path first
                if base_path:
                    alt_path = Path(base_path) / data
                    if alt_path.exists():
                        path_to_check = alt_path
                        resolved = True

                # Resolve by adding prefix from base_path if data starts with extra_prefix
                if not resolved and extra_prefixes:
                    for prefix in extra_prefixes:
                        if data.startswith(prefix):
                            if base_path and prefix in base_path:
                                parts = base_path.split(prefix)
                                if parts:
                                    prefix_to_add = parts[0]
                                    alt_path = Path(prefix_to_add) / data
                                    if alt_path.exists():
                                        path_to_check = alt_path
                                        resolved = True
                                        break

                if resolved or path_to_check.exists():
                    with open(path_to_check, "r") as f:
                        return f.read()
                else:
                    raise FileNotFoundError(
                        f"Referenced file not found: {data}"
                    )
        return data
