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

"""Tests for dfcx_exporter module."""

import io
import json
import zipfile
import pytest
from cxas_scrapi.migration.dfcx_exporter import DFCXAgentExporter


def test_process_zip_content_minimal():
    extractor = DFCXAgentExporter()
    agent_id = (
        "projects/test-project/locations/global/agents/test-agent"
    )

    # Create a minimal zip in memory
    zip_buffer = io.BytesIO()
    with zipfile.ZipFile(
        zip_buffer, "a", zipfile.ZIP_DEFLATED, False
    ) as zip_file:
        agent_json = {
            "name": agent_id,
            "displayName": "Test Agent",
            "defaultLanguageCode": "en",
        }
        zip_file.writestr("agent.json", json.dumps(agent_json))

    zip_content = zip_buffer.getvalue()

    result = extractor.process_zip_content(zip_content, agent_id)

    assert result is not None
    assert result["name"] == agent_id
    assert result["displayName"] == "Test Agent"
    assert "intents" in result
    assert "tools" in result
    assert "entityTypes" in result
    assert "webhooks" in result
    assert "flows" in result
    assert "playbooks" in result
