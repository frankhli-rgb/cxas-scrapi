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

"""Core Guardrails class for CXAS Scrapi."""

import logging
from typing import Dict, List, Optional, Any
from google.cloud.ces_v1beta import types
from google.protobuf import field_mask_pb2

from cxas_scrapi.core.apps import Apps


class Guardrails(Apps):
    """Core Class for managing Guardrail Resources."""

    def __init__(
        self,
        app_id: str,
        creds_path: str = None,
        creds_dict: Dict[str, str] = None,
        creds: Any = None,
        scope: List[str] = None,
    ):
        """Initializes the Guardrails client."""
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
        self.resource_type = "guardrails"
        self.app_id = app_id

    def list_guardrails(self, app_id: str) -> List[types.Guardrail]:
        """Lists guardrails within a specific app."""
        request = types.ListGuardrailsRequest(parent=app_id)
        response = self.client.list_guardrails(request=request)
        return list(response)

    def get_guardrails_map(
        self, app_id: str, reverse: bool = False
    ) -> Dict[str, str]:
        """Creates a map of Guardrail full names to display names.

        Args:
            app_id: Parent App ID.
            reverse: If True, map display_name -> name.
        """
        guardrails = self.list_guardrails(app_id)
        guardrails_dict: Dict[str, str] = {}

        for guardrail in guardrails:
            display_name = guardrail.display_name
            name = guardrail.name
            if display_name and name:
                if reverse:
                    guardrails_dict[display_name] = name
                else:
                    guardrails_dict[name] = display_name
        return guardrails_dict

    def get_guardrail(self, guardrail_id: str) -> types.Guardrail:
        """Gets a specific guardrail."""
        request = types.GetGuardrailRequest(name=guardrail_id)
        return self.client.get_guardrail(request=request)

    def create_guardrail(
        self,
        app_id: str,
        guardrail_id: str,
        display_name: str,
        payload: Dict[str, Any],
        action: str = "DENY",
        description: str = "",
        enabled: bool = True,
    ) -> types.Guardrail:
        """Creates a new guardrail given a specific payload dictionary.

        The payload controls which of the 5 mutually exclusive guardrail types is instantiated
        (content_filter, llm_policy, llm_prompt_security, model_safety, code_callback).
        """
        # Ensure any existing basic field inside payload doesn't conflict
        if "display_name" in payload:
            payload.pop("display_name")
        if "description" in payload:
            payload.pop("description")

        guardrail = types.Guardrail(
            display_name=display_name,
            description=description,
            action=action,
            enabled=enabled,
            **payload
        )

        request = types.CreateGuardrailRequest(
            parent=app_id, guardrail_id=guardrail_id, guardrail=guardrail
        )
        return self.client.create_guardrail(request=request)

    def update_guardrail(self, guardrail_id: str, **kwargs) -> types.Guardrail:
        """Updates specific fields of an existing Guardrail."""
        guardrail = types.Guardrail(name=guardrail_id)
        mask_paths = []

        for key, value in kwargs.items():
            setattr(guardrail, key, value)
            mask_paths.append(key)

        request = types.UpdateGuardrailRequest(
            guardrail=guardrail,
            update_mask=field_mask_pb2.FieldMask(paths=mask_paths),
        )
        return self.client.update_guardrail(request=request)

    def delete_guardrail(self, guardrail_id: str) -> None:
        """Deletes a specific guardrail."""
        request = types.DeleteGuardrailRequest(name=guardrail_id)
        self.client.delete_guardrail(request=request)
