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

"""Core Changelogs class for CXAS Scrapi."""

from typing import List, Optional
from google.cloud.ces_v1beta import types
from cxas_scrapi.core.agents import Agents


class Changelogs(Agents):
    """Core Class for managing Changelog Resources."""

    def __init__(self, app_id: str, env: str = "PROD"):
        """Initializes the Changelogs client.

        Args:
            app_id: The full resource name of the parent App (projects/P/locations/L/apps/A).
        """
        # We inherit from Agents because it holds the AgentServiceClient which contains changelog methods
        super().__init__(app_id=app_id, env=env)
        self.resource_type = "changelogs"

    def list_changelogs(self, app_id: Optional[str] = None) -> List[types.Changelog]:
        """Lists changelogs within a specific app.

        Args:
            app_id: Parent App ID. Defaults to self.app_id.
        """
        app_id = app_id or self.app_id
        if not app_id:
            raise ValueError("app_id is required.")

        request = types.ListChangelogsRequest(parent=app_id)
        response = self.client.list_changelogs(request=request)
        return list(response.changelogs)

    def get_changelog(self, changelog_id: str) -> types.Changelog:
        """Gets a specific changelog."""
        request = types.GetChangelogRequest(name=changelog_id)
        return self.client.get_changelog(request=request)
