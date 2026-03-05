"""Apps class for CXAS Scrapi."""

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

import logging
from typing import Dict, List, Optional, Any
from google.cloud.ces_v1beta import AgentServiceClient, types
from google.protobuf import field_mask_pb2

from cxas_scrapi.core.common import Common


class Apps(Common):
    """Core Class for managing App Resources."""

    def __init__(
        self,
        project_id: str,
        location: str,
        creds_path: str = None,
        creds_dict: Dict[str, str] = None,
        creds: Any = None,
        scope: List[str] = None, **kwargs
    ):
        super().__init__(
            creds_path=creds_path,
            creds_dict=creds_dict,
            creds=creds,
            scope=scope, **kwargs
        )
        self.project_id = project_id
        self.location = location
        self.parent = f"projects/{project_id}/locations/{location}"

        self.client_options = self._get_client_options(self.parent)
        self.client = AgentServiceClient(
            credentials=self.creds, client_options=self.client_options
        )

    def list_apps(self) -> List[types.App]:
        """Lists apps in the configured project and location."""
        request = types.ListAppsRequest(parent=self.parent)
        response = self.client.list_apps(request=request)
        return list(response)

    def get_apps_map(self, reverse: bool = False) -> Dict[str, str]:
        """Creates a map of App full names to display names.

        Args:
            reverse: If True, map display_name -> name.
        """
        apps = self.list_apps()
        apps_dict: Dict[str, str] = {}

        for app in apps:
            display_name = app.display_name
            name = app.name
            if display_name and name:
                if reverse:
                    apps_dict[display_name] = name
                else:
                    apps_dict[name] = display_name
        return apps_dict

    def get_app(self, app_id: str) -> types.App:
        """Gets a specific app by its full resource name."""
        request = types.GetAppRequest(name=app_id)
        return self.client.get_app(request=request)

    def get_app_by_display_name(self, display_name: str) -> Optional[types.App]:
        """Get CX Agent Studio App by its human readable display name.

        Args:
            display_name: human-readable display name of CX Agent Studio App as string.

        Returns:
            CX Agent Studio App resource object. If no app is found, returns None.
        """
        apps_list = self.list_apps()

        possible_app = None
        matched_app = None

        for app in apps_list:
            if app.display_name == display_name and not matched_app:
                matched_app = app
            elif app.display_name == display_name and matched_app:
                possible_app = app
            elif app.display_name.lower() == display_name.lower():
                possible_app = app

        if possible_app and not matched_app:
            logging.warning(
                'display_name is case-sensitive. Did you mean "%s"?',
                possible_app.display_name,
            )
        elif possible_app and matched_app:
            logging.warning(
                'Found multiple apps with the display name "%s".',
                possible_app.display_name,
            )
            matched_app = None

        return matched_app

    def create_app(
        self,
        app_id: str,
        display_name: str,
        description: str = None,
        root_agent: str = None,
    ) -> types.App:
        """Creates a new app."""
        app = types.App(display_name=display_name)
        if description:
            app.description = description
        if root_agent:
            app.root_agent = root_agent

        request = types.CreateAppRequest(
            parent=self.parent, app=app, app_id=app_id
        )
        return self.client.create_app(request=request)

    def update_app(self, app_id: str, **kwargs) -> types.App:
        """Updates specific fields of an existing App."""
        app = types.App(name=app_id)
        mask_paths = []

        for key, value in kwargs.items():
            setattr(app, key, value)
            mask_paths.append(key)

        request = types.UpdateAppRequest(
            app=app, update_mask=field_mask_pb2.FieldMask(paths=mask_paths)
        )
        return self.client.update_app(request=request)

    def delete_app(self, app_id: str, force: bool = False) -> None:
        """Deletes a specific app."""
        request = types.DeleteAppRequest(name=app_id, force=force)
        self.client.delete_app(request=request)

    def export_app(
        self,
        app_id: str,
        gcs_uri: str = None,
        export_format: str = "JSON",
    ) -> Any:
        # TODO: Fix return type hint to Operation or specific LRO type
        """Exports the specified app.

        Args:
            app_id: The resource name of the app to export.
            gcs_uri: Optional. The Google Cloud Storage URI to export to.
            export_format: The format to export the app in ('JSON' or 'YAML').
        """
        # Map string formats to enum
        # Note: types.ExportAppRequest.ExportFormat might be an enum, strictly speaking.
        # But SDK usually accepts string/int if compatible.
        # Inspecting types usually reveals enum values.
        # Assuming defaults for now, or passing as kwargs if strict typing issues arise.

        request = types.ExportAppRequest(
            name=app_id,
            gcs_uri=gcs_uri if gcs_uri else None,
            export_format=export_format,  # defaults to JSON if not passed, but we pass it.
        )
        return self.client.export_app(request=request)

    def import_app(
        self,
        app_content: bytes,
        display_name: str,
    ) -> Any:
        """Imports an app into the specified project and location.

        Args:
            app_content: The raw bytes of the zip archive of the app.
            display_name: The display name for the new app.
        """
        request = types.ImportAppRequest(
            parent=self.parent,
            app_content=app_content,
            display_name=display_name,
        )
        return self.client.import_app(request=request)
