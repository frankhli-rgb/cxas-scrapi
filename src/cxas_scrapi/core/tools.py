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

from typing import Dict, List, Any
from google.cloud.ces_v1beta import types
from google.protobuf import field_mask_pb2

from cxas_scrapi.core.apps import Apps

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
        description: str = ""
    ) -> Any:
        """Creates a new tool or toolset.
        
        If tool_type implies a toolset, it creates a Toolset wrapper (e.g. open_api_toolset).
        Otherwise it creates a standard Tool wrapper (e.g. python_function).
        """
        is_toolset = tool_type in ["open_api_toolset", "connector_toolset", "mcp_toolset"]
        
        payload_copy = payload.copy()
        payload_copy.pop("display_name", None)
        
        if is_toolset:
            desc = payload_copy.pop("description", description)
            kwargs = {
                "display_name": display_name,
                "description": desc,
                tool_type: payload_copy
            }
            toolset = types.Toolset(**kwargs)
            request = types.CreateToolsetRequest(
                parent=app_id,
                toolset_id=tool_id,
                toolset=toolset
            )
            return self.client.create_toolset(request=request)
        else:
            if description and "description" not in payload_copy:
                payload_copy["description"] = description
                
            kwargs = {
                "display_name": display_name,
                tool_type: payload_copy
            }
            tool = types.Tool(**kwargs)
            request = types.CreateToolRequest(
                parent=app_id,
                tool_id=tool_id,
                tool=tool
            )
            return self.client.create_tool(request=request)

    def update_tool(self, tool_id: str, **kwargs) -> Any:
        """Updates specific fields of an existing Tool or Toolset."""
        mask_paths = list(kwargs.keys())
        
        if self._is_toolset(tool_id):
            toolset = types.Toolset(name=tool_id)
            for key, value in kwargs.items():
                setattr(toolset, key, value)
            
            request = types.UpdateToolsetRequest(
                toolset=toolset,
                update_mask=field_mask_pb2.FieldMask(paths=mask_paths)
            )
            return self.client.update_toolset(request=request)
        else:
            tool = types.Tool(name=tool_id)
            for key, value in kwargs.items():
                setattr(tool, key, value)
                
            request = types.UpdateToolRequest(
                tool=tool,
                update_mask=field_mask_pb2.FieldMask(paths=mask_paths)
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
