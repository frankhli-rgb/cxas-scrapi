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

"""Core Tools class for CXAS Scrapi."""

from typing import Dict, List, Any, Optional
from google.protobuf import struct_pb2, json_format, field_mask_pb2
from google.cloud.ces_v1beta import types, ToolServiceClient, AgentServiceClient, types
from google.protobuf.json_format import MessageToDict

from cxas_scrapi.core.apps import Apps
from cxas_scrapi.core.variables import Variables
import yaml


class Tools(Apps):
    """Core Class for managing Tool and Toolset Resources."""

    def __init__(
        self,
        app_id: str,
        creds_path: str = None,
        creds_dict: Dict[str, str] = None,
        creds: Any = None,
        scope: List[str] = None,
    ):
        """Initializes the Tools client."""
        project_id = app_id.split("/")[1]
        location = app_id.split("/")[3]

        super().__init__(
            project_id=project_id,
            location=location,
            creds_path=creds_path,
            creds_dict=creds_dict,
            creds=creds,
            scope=scope,
        )
        self.app_id = app_id
        self.resource_type = "tools"
        self.client = AgentServiceClient(
            credentials=self.creds, client_options=self.client_options
        )
        self.tool_client = ToolServiceClient(
            credentials=self.creds, client_options=self.client_options
        )
        self.var_client = Variables(
            app_id=self.app_id,
            creds_path=creds_path,
            creds_dict=creds_dict,
            creds=creds,
            scope=scope,
        )
        self.tools_map: Dict[str, str] = {}

    @staticmethod
    def _get_tool_display_name(tool: types.Tool) -> Optional[str]:
        """Helper to get the display name of a tool."""
        display_name = ""
        if tool.python_function:
            display_name = tool.python_function.name
        elif tool.data_store_tool:
            display_name = tool.data_store_tool.name
        elif tool.open_api_tool:
            display_name = tool.open_api_tool.name
        elif tool.google_search_tool:
            display_name = tool.google_search_tool.name
        elif tool.connector_tool:
            display_name = tool.connector_tool.name
        elif tool.mcp_tool:
            display_name = tool.mcp_tool.name
        elif tool.file_search_tool:
            display_name = tool.file_search_tool.name

        return display_name

    @staticmethod
    def _is_toolset(tool_id: str) -> bool:
        """Helper to determine if a full resource name refers to a Toolset."""
        return "/toolsets/" in tool_id

    @staticmethod
    def _parse_openapi_schema(
        schema_str: str, display_name: str, name: str, reverse: bool
    ) -> Dict[str, str]:
        """Parses an OpenAPI schema to extract tool endpoints locally."""
        parsed_tools: Dict[str, str] = {}
        try:
            schema = yaml.safe_load(schema_str)
            for path, methods in schema.get("paths", {}).items():
                if not isinstance(methods, dict):
                    continue
                for method, details in methods.items():
                    if not isinstance(details, dict):
                        continue
                    op_id = details.get("operationId")
                    if op_id:
                        tool_display_name = f"{display_name}_{op_id}"
                        tool_name = name
                        if reverse:
                            parsed_tools[tool_display_name] = tool_name
                        else:
                            parsed_tools[tool_name] = tool_display_name
        except Exception as e:
            print(f"[WARNING] Failed to parse OpenAPI schema for {display_name}: {e}")
        return parsed_tools

    def _get_final_variables(
        self, app_id: str, variables: Optional[Any]
    ) -> Dict[str, Any]:
        """Resolves the variables to pass to the tool payload."""
        final_variables = {}

        if isinstance(variables, dict):
            final_variables = variables

        elif variables is None or isinstance(variables, list):
            # Fetch variables from the app and filter by this list of names.
            raw_app_vars = self.var_client.list_variables(app_id)

            app_vars_cache = {}
            for var in raw_app_vars:
                try:
                    var_dict = MessageToDict(var._pb)
                except AttributeError:
                    var_dict = MessageToDict(var)

                schema = var_dict.get("schema", {})
                actual_data = schema.get("default") or var_dict.get("value") or {}
                app_vars_cache[var.name] = actual_data

            if variables is None:
                final_variables = app_vars_cache
            else:
                for var_name in variables:
                    if var_name in app_vars_cache:
                        final_variables[var_name] = app_vars_cache[var_name]
                    else:
                        print(
                            f"[WARNING] App variable '{var_name}' requested but not found in app."
                        )

        return final_variables

    def get_tools_map(self, app_id: str, reverse: bool = False) -> Dict[str, str]:
        """Creates a map of Tool and Toolset full names to display names.

        Args:
            app_id: Parent App ID.
            reverse: If True, map display_name -> name.
        """
        resources = self.list_tools(app_id)
        resources_dict: Dict[str, str] = {}

        for resource in resources:
            display_name = getattr(resource, "display_name", None)
            name = getattr(resource, "name", None)

            if not display_name or not name:
                continue

            if self._is_toolset(name):
                # Try to parse OpenAPI toolsets locally to avoid N+1 API calls
                schema_str = None
                if getattr(resource, "open_api_toolset", None):
                    schema_str = getattr(
                        resource.open_api_toolset, "open_api_schema", None
                    )

                if schema_str:
                    openapi_tools = self._parse_openapi_schema(
                        schema_str, display_name, name, reverse
                    )
                    resources_dict.update(openapi_tools)
                else:
                    # Fallback to API for MCP/Connector toolsets where tools are abstract
                    try:
                        tools = self.retrieve_tool(name)
                        for tool in tools.tools:
                            tool_display_name = self._get_tool_display_name(tool)
                            if tool_display_name and tool.name:
                                tool_display_name = (
                                    f"{display_name}_{tool_display_name}"
                                )
                                if reverse:
                                    resources_dict[tool_display_name] = tool.name
                                else:
                                    resources_dict[tool.name] = tool_display_name
                    except Exception as e:
                        print(
                            f"[WARNING] Failed to retrieve tools for toolset {display_name}: {e}"
                        )
            else:
                if reverse:
                    resources_dict[display_name] = name
                else:
                    resources_dict[name] = display_name

        return resources_dict

    def _get_or_load_tools_map(self, app_id: str) -> Dict[str, str]:
        """Gets a reverse map of tools from cache or loads it if missing."""
        if not self.tools_map:
            self.tools_map = self.get_tools_map(app_id, reverse=True)
        return self.tools_map

    def list_tools(self, app_id: str) -> List[Any]:
        """Lists both tools and toolsets within a specific app."""
        tools_request = types.ListToolsRequest(parent=app_id)
        tools_response = self.client.list_tools(request=tools_request)

        toolsets_request = types.ListToolsetsRequest(parent=app_id)
        toolsets_response = self.client.list_toolsets(request=toolsets_request)

        return list(tools_response) + list(toolsets_response)

    def get_tool(self, tool_id: str) -> Any:
        """Gets a specific tool or toolset by full resource name."""
        if self._is_toolset(tool_id):
            request = types.GetToolsetRequest(name=tool_id)
            return self.client.get_toolset(request=request)
        else:
            request = types.GetToolRequest(name=tool_id)
            return self.client.get_tool(request=request)

    def create_tool(
        self,
        app_id: str,
        tool_id: str,
        display_name: str,
        payload: Dict[str, Any],
        tool_type: str = "python_function",
        description: str = "",
    ) -> Any:
        """Creates a new tool or toolset.

        If tool_type implies a toolset, it creates a Toolset wrapper (e.g. open_api_toolset).
        Otherwise it creates a standard Tool wrapper (e.g. python_function).
        """
        is_toolset = tool_type in [
            "open_api_toolset",
            "connector_toolset",
            "mcp_toolset",
        ]

        payload_copy = payload.copy()
        payload_copy.pop("display_name", None)

        if is_toolset:
            desc = payload_copy.pop("description", description)
            kwargs = {
                "display_name": display_name,
                "description": desc,
                tool_type: payload_copy,
            }
            toolset = types.Toolset(**kwargs)
            request = types.CreateToolsetRequest(
                parent=app_id, toolset_id=tool_id, toolset=toolset
            )
            return self.client.create_toolset(request=request)
        else:
            if description and "description" not in payload_copy:
                payload_copy["description"] = description

            kwargs = {"display_name": display_name, tool_type: payload_copy}
            tool = types.Tool(**kwargs)
            request = types.CreateToolRequest(parent=app_id, tool_id=tool_id, tool=tool)
            return self.client.create_tool(request=request)

    def update_tool(self, tool_id: str, **kwargs) -> Any:
        """Updates specific fields of an existing Tool or Toolset."""
        mask_paths = list(kwargs.keys())

        if self._is_toolset(tool_id):
            toolset = types.Toolset(name=tool_id)
            for key, value in kwargs.items():
                setattr(toolset, key, value)

            request = types.UpdateToolsetRequest(
                toolset=toolset, update_mask=field_mask_pb2.FieldMask(paths=mask_paths)
            )
            return self.client.update_toolset(request=request)
        else:
            tool = types.Tool(name=tool_id)
            for key, value in kwargs.items():
                setattr(tool, key, value)

            request = types.UpdateToolRequest(
                tool=tool, update_mask=field_mask_pb2.FieldMask(paths=mask_paths)
            )
            return self.client.update_tool(request=request)

    def delete_tool(self, tool_id: str) -> None:
        """Deletes a specific tool or toolset."""
        if self._is_toolset(tool_id):
            request = types.DeleteToolsetRequest(name=tool_id)
            self.client.delete_toolset(request=request)
        else:
            request = types.DeleteToolRequest(name=tool_id)
            self.client.delete_tool(request=request)

    def execute_tool(
        self,
        app_id: str,
        tool_display_name: str,
        args: Optional[Dict[str, Any]] = None,
        variables: Optional[Any] = None,  # Accepts Dict, List[str], or None
    ) -> Any:
        """Executes a tool directly via the CES API.

        Args:
            app_id: The full App resource name (e.g. projects/.../apps/...).
            tool_display_name: The display name of the tool (or toolset key).
            args: Dictionary of arguments for the tool.
            variables: Can be:
                - None: Fetches and passes ALL variables from the app.
                - List[str]: Fetches variables from the app and filters by this list of names.
                - Dict[str, Any]: Uses the provided dictionary directly (e.g. from Evals).

        Returns:
            The tool execution response (JSON or Object).
        """
        # Use HTTP REST request instead of SDK because the current SDK version
        # is missing the 'variables' field in ExecuteToolRequest proto
        import requests

        url = f"https://ces.googleapis.com/v1beta/{app_id}:executeTool"

        headers = {
            "Authorization": f"Bearer {self.creds.token}",
            "Content-Type": "application/json",
            "x-goog-user-project": self.project_id,
        }

        payload = {}

        tools_map = self._get_or_load_tools_map(app_id)
        tool_id = tools_map.get(tool_display_name)

        if not tool_id:
            raise ValueError(
                f"Tool '{tool_display_name}' not found in App '{app_id}'. "
            )

        if "toolsets/" in tool_id and "/tools/" in tool_id:
            toolset_name, operation_id = tool_id.split("/tools/")
            payload["toolsetTool"] = {"toolset": toolset_name, "toolId": operation_id}
        elif "toolsets/" in tool_id:  # fallback for generic toolsets
            payload["toolsetTool"] = {
                "toolset": tool_id,
                "toolId": tool_display_name.split("_")[-1],
            }
        else:
            payload["tool"] = tool_id

        payload["args"] = args or {}

        final_variables = self._get_final_variables(app_id, variables)

        if final_variables:
            payload["variables"] = final_variables

        response = requests.post(url, headers=headers, json=payload)
        response.raise_for_status()

        resp_dict = response.json()

        if final_variables:
            resp_dict["variables"] = final_variables
        return resp_dict

    def retrieve_tool(self, toolset_id: str) -> Any:
        """Retrieves all tools in a toolset."""
        request = types.RetrieveToolsRequest(toolset=toolset_id)
        return self.tool_client.retrieve_tools(request=request)
