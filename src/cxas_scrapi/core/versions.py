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

"""Core Versions class for CXAS Scrapi."""

from typing import Dict, List, Any
from google.cloud.ces_v1beta import types

from cxas_scrapi.core.apps import Apps


class Versions(Apps):
    """Core Class for managing AppVersion Resources."""

    def __init__(
        self,
        project_id: str,
        location: str,
        creds_path: str = None,
        creds_dict: Dict[str, str] = None,
        creds: Any = None,
        scope: List[str] = None,
    ):
        """Initializes the Versions client."""
        super().__init__(
            project_id=project_id,
            location=location,
            creds_path=creds_path,
            creds_dict=creds_dict,
            creds=creds,
            scope=scope,
        )
        self.resource_type = "versions"

    def list_versions(self, app_id: str) -> List[types.AppVersion]:
        """Lists versions within a specific app."""
        request = types.ListAppVersionsRequest(parent=app_id)
        response = self.client.list_app_versions(request=request)
        return list(response.app_versions)

    def get_versions_map(self, app_id: str, reverse: bool = False) -> Dict[str, str]:
        """Returns a map of version display names to full resource names.

        Args:
            app_id: Parent App ID.
            reverse: If True, map display_name -> name.
        """
        versions = self.list_versions(app_id)
        versions_map: Dict[str, str] = {}

        for version in versions:
            display_name = version.display_name
            name = version.name
            if display_name and name:
                if reverse:
                    versions_map[display_name] = name
                else:
                    versions_map[name] = display_name

        return versions_map

    def get_version(self, version_id: str) -> types.AppVersion:
        """Gets a specific version."""
        request = types.GetAppVersionRequest(name=version_id)
        return self.client.get_app_version(request=request)

    def delete_version(self, version_id: str) -> None:
        """Deletes a specific version."""
        request = types.DeleteAppVersionRequest(name=version_id)
        self.client.delete_app_version(request=request)

    def revert_version(self, version_id: str) -> Any:
        """Reverts (Restores) a specific version."""
        request = types.RestoreAppVersionRequest(name=version_id)
        # restore_app_version theoretically returns a RestoreAppVersionResponse, let's just return it
        return self.client.restore_app_version(request=request)
