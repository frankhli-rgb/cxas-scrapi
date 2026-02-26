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


class Tools(Apps):
    """Core Class for managing Tool and Toolset Resources."""

    def __init__(
        self,
        project_id: str,
        location: str,
        creds_path: str = None,
        creds_dict: Dict[str, str] = None,
        creds: Any = None,
        scope: List[str] = None,
    ):
        """Initializes the Tools client."""
        super().__init__(
            project_id=project_id,
            location=location,
            creds_path=creds_path,
            creds_dict=creds_dict,
            creds=creds,
            scope=scope,
        )
        self.resource_type = "tools"
        self.client = AgentServiceClient(
            credentials=self.creds, client_options=self.client_options
        )
        self.tool_client = ToolServiceClient(
            credentials=self.creds, client_options=self.client_options
        )
        self.var_client = Variables(
            project_id=project_id,
            location=location,
            creds_path=creds_path,
            creds_dict=creds_dict,
            creds=creds,
            scope=scope,
        )

    def _is_toolset(self, tool_id: str) -> bool:
        """Helper to determine if a full resource name refers to a Toolset."""
        return "/toolsets/" in tool_id

    def list_tools(self, app_id: str) -> List[Any]:
        """Lists both tools and toolsets within a specific app."""
        tools_request = types.ListToolsRequest(parent=app_id)
        tools_response = self.client.list_tools(request=tools_request)

        toolsets_request = types.ListToolsetsRequest(parent=app_id)
        toolsets_response = self.client.list_toolsets(request=toolsets_request)

        return list(tools_response.tools) + list(toolsets_response.toolsets)

    def get_tools_map(self, app_id: str, reverse: bool = False) -> Dict[str, str]:
        """Creates a map of Tool and Toolset full names to display names.

        Args:
            app_id: Parent App ID.
            reverse: If True, map display_name -> name.
        """
        resources = self.list_tools(app_id)
        resources_dict: Dict[str, str] = {}

        for resource in resources:
            display_name = resource.display_name
            name = resource.name
            if self._is_toolset(name):
                # Retrieve display names of tools in the toolsets.
                tools = self.retrieve_tool(name)
                for tool in tools.tools:
                    display_name = self._get_tool_display_name(tool)
                    if display_name and name:
                        if reverse:
                            resources_dict[display_name] = name
                        else:
                            resources_dict[name] = display_name
            else:
                if display_name and name:
                    if reverse:
                        resources_dict[display_name] = name
                    else:
                        resources_dict[name] = display_name
        return resources_dict

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
        args: Dict[str, Any],
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

        tools_map = self.get_tools_map(app_id, reverse=True)
        tool_id = tools_map.get(tool_display_name)

        if "toolsets/" in tool_id:
            payload["toolsetTool"] = {"toolset": tool_id, "toolId": tool_display_name}
        else:
            payload["tool"] = tool_id

        if args:
            payload["args"] = args

        # Variables logic
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

        if final_variables:
            payload["variables"] = final_variables

        print(
            f"[DEBUG_TOOLS] Executing against app_id: {app_id} with request: {payload.get('tool') or payload.get('toolsetTool')} "
        )

        response = requests.post(url, headers=headers, json=payload)
        response.raise_for_status()

        resp_dict = response.json()

        # Make consistent with what the helper script expects
        # variables might naturally be inside resp_dict from the API now
        if final_variables:
            resp_dict["variables"] = final_variables
        return resp_dict

    def retrieve_tool(self, toolset_id: str) -> Any:
        """Retrieves all tools in a toolset."""
        request = types.RetrieveToolsRequest(toolset=toolset_id)
        return self.tool_client.retrieve_tools(request=request)

    def _get_tool_display_name(self, tool: types.Tool) -> Optional[str]:
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
          display_name = tool.connector_tool.name
      elif tool.file_search_tool:
          display_name = tool.file_search_tool.name

      return display_name