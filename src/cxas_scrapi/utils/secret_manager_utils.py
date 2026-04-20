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

"""Utility class for managing Google Cloud Secret Manager Secrets."""

from google.cloud import secretmanager


class SecretManagerUtils:
    """Utility Class for Creating and Retrieving Secret Manager Secrets."""

    def __init__(self, project_id: str):
        self.project_id = project_id
        self.client = secretmanager.SecretManagerServiceClient()

    def create_or_get_secret(self, secret_id: str, payload: str = None) -> str:
        """Retrieves a Secret via Secret ID, or creates a new one if it
        doesn't exist.

        Args:
            secret_id: The ID of the Secret to retrieve or create.
            payload: The string payload to add as a new Secret Version if
                     creating a new secret.

        Returns:
            The full resource name path to the latest version of the
            Secret, e.g.
            `projects/{project_id}/secrets/{secret_id}/versions/latest`.
        """
        parent = f"projects/{self.project_id}"

        # Check if secret already exists
        request = {"parent": parent}
        secrets = self.client.list_secrets(request=request)

        for secret in secrets:
            display_name = secret.name.split("/")[-1]
            if display_name == secret_id:
                print(f"Found existing secret: {secret_id}")
                return f"{secret.name}/versions/latest"

        # Secret doesn't exist, create it
        if payload is None:
            raise ValueError(
                "Secret does not exist and no payload was provided to "
                "create one."
            )

        print(f"Creating new secret: {secret_id}")
        created_secret = self.client.create_secret(
            request={
                "parent": parent,
                "secret_id": secret_id,
                "secret": {"replication": {"automatic": {}}},
            }
        )

        # Add the initial version (payload)
        payload_bytes = payload.encode("UTF-8")
        self.client.add_secret_version(
            request={
                "parent": created_secret.name,
                "payload": {"data": payload_bytes},
            }
        )

        return f"{created_secret.name}/versions/latest"
