"""Exporter module for Dialogflow CX resources."""

import concurrent.futures
import io
import json
import logging
import re
import traceback
import zipfile
from typing import Any, Dict, List, Optional

from google.api_core import exceptions as api_exceptions
from google.cloud.dialogflowcx_v3beta1 import services as cx_services
from google.cloud.dialogflowcx_v3beta1 import types as cx_types
from google.protobuf import json_format
from google.protobuf.json_format import MessageToDict

logger = logging.getLogger(__name__)


class BaseDFCXClient:
    """Base class for Dialogflow CX API clients to handle common logic."""

    def _get_client_options(self, resource_id: str) -> Optional[Dict[str, str]]:
        """Extracts region and returns client options with the regional endpoint."""
        if not isinstance(resource_id, str):
            return None
        match = re.search(r"projects/[^/]+/locations/([^/]+)/", resource_id)
        region = match.group(1) if match else "global"  # Default to global
        if not region:
            logger.error(
                f"Error: Could not parse region from resource ID: {resource_id}"
            )
            return None

        if region != "global":
            endpoint = {"api_endpoint": f"{region}-dialogflow.googleapis.com"}
        else:
            endpoint = {"api_endpoint": "dialogflow.googleapis.com"}
        return endpoint


class DFCXAgentExporter(BaseDFCXClient):
    """Client for exporting Dialogflow CX Agents."""

    def process_zip_content(
        self, zip_content: bytes, agent_id_fallback: str
    ) -> Optional[Dict[str, Any]]:
        """Parses raw ZIP bytes into the full agent JSON structure."""
        full_agent_data = {}
        try:
            with zipfile.ZipFile(io.BytesIO(zip_content), "r") as zip_file:
                logger.info("Zip file opened in memory. Parsing contents...")
                namelist = zip_file.namelist()

                if "agent.json" in namelist:
                    with zip_file.open("agent.json") as f:
                        full_agent_data = json.load(f)

                    # If the local export doesn't have the full name (project/loc/agent), use fallback
                    if (
                        "name" not in full_agent_data
                        or not full_agent_data["name"]
                    ):
                        full_agent_data["name"] = agent_id_fallback

                    # Ensure we have a consistent ID to use for mapping
                    agent_id = full_agent_data["name"]
                    logger.info(
                        f"Successfully loaded agent.json. Using ID: {agent_id}"
                    )
                else:
                    logger.error(
                        "ERROR: agent.json not found in the zip. Cannot build full agent structure."
                    )
                    return None

                # --- MODIFIED: Added maps for Flows and Pages ---
                intent_map, playbook_map, tool_map, entity_map, webhook_map, flow_map = (
                    {},
                    {},
                    {},
                    {},
                    {},
                    {},
                )
                dir_name_to_full_name, display_name_to_id = {}, {}

                def get_full_name(
                    resource_type: str, resource_id: str
                ) -> str:
                    return f"{agent_id}/{resource_type}/{resource_id}"

                # First pass: Load main components and build maps for all resource types
                for filename in sorted(namelist):
                    if (
                        not filename.endswith(".json")
                        or filename == "agent.json"
                    ):
                        continue

                    path_parts = filename.split("/")

                    # DFCX stores webhooks directly in the webhooks/ directory without a subfolder
                    is_webhook = (
                        len(path_parts) == 2 and path_parts[0] == "webhooks"
                    )

                    # Other resources are in subfolders: type/name/name.json
                    is_standard_resource = (
                        len(path_parts) >= 2
                        and path_parts[-2]
                        == path_parts[-1].replace(".json", "")
                    )

                    if is_standard_resource or is_webhook:
                        resource_type = path_parts[0]
                        resource_dir_name = (
                            path_parts[-2]
                            if is_standard_resource
                            else path_parts[-1].replace(".json", "")
                        )

                        try:
                            with zip_file.open(filename) as f:
                                content = json.load(f)

                            # Handle different ID keys ('name' vs. 'flowId')
                            resource_id = content.get("name") or content.get(
                                "flowId"
                            )
                            if not resource_id:
                                # Webhooks sometimes only have displayName at the root
                                if is_webhook and content.get("displayName"):
                                    resource_id = content["displayName"]
                                else:
                                    logger.warning(
                                        f"  Warning: Missing 'name' or 'flowId' in {filename}. Skipping."
                                    )
                                    continue

                            full_name = get_full_name(
                                resource_type, resource_id
                            )
                            content["name"] = full_name

                            if resource_type == "intents":
                                intent_map[full_name] = content
                            elif resource_type == "playbooks":
                                playbook_map[full_name] = content
                            elif resource_type == "tools":
                                tool_map[full_name] = content
                            elif resource_type == "entityTypes":
                                entity_map[full_name] = content
                            elif resource_type == "webhooks":
                                webhook_map[full_name] = content
                            elif resource_type == "flows":
                                flow_map[full_name] = {
                                    "flow": content,
                                    "pages": [],
                                }

                            dir_name_to_full_name[
                                resource_dir_name
                            ] = full_name
                            if content.get("displayName"):
                                display_name_to_id[
                                    content["displayName"]
                                ] = resource_id
                        except Exception as e:
                            logger.error(
                                f"    -> ERROR pre-loading {filename}: {e}"
                            )

                # Second pass: Merge sub-components (training phrases, pages, examples, etc.)
                for filename in sorted(namelist):
                    if filename == "generativeSettings/en.json":
                        with zip_file.open(filename) as f:
                            full_agent_data["generativeSettings"] = json.load(f)
                        continue

                    path_parts = filename.split("/")
                    if len(path_parts) < 2:
                        continue

                    resource_dir_name = path_parts[1]
                    full_resource_name = dir_name_to_full_name.get(
                        resource_dir_name
                    )
                    if not full_resource_name:
                        continue

                    # --- MODIFIED: Handle sub-components for ALL resource types ---
                    resource_type = path_parts[0]

                    # Handle Training Phrases for Intents
                    if (
                        resource_type == "intents"
                        and path_parts[-2] == "trainingPhrases"
                        and filename.endswith(".json")
                    ):
                        if full_resource_name in intent_map:
                            with zip_file.open(filename) as f:
                                tp_content = json.load(f)
                            intent_map[full_resource_name].setdefault(
                                "trainingPhrases", []
                            ).extend(tp_content.get("trainingPhrases", []))

                    # Handle Entities for EntityTypes
                    elif (
                        resource_type == "entityTypes"
                        and path_parts[-2] == "entities"
                        and filename.endswith(".json")
                    ):
                        if full_resource_name in entity_map:
                            with zip_file.open(filename) as f:
                                entity_content = json.load(f)
                            entity_map[full_resource_name].setdefault(
                                "entities", []
                            ).extend(entity_content.get("entities", []))

                    # Handle Pages for Flows
                    elif (
                        resource_type == "flows"
                        and path_parts[-2] == "pages"
                        and filename.endswith(".json")
                    ):
                        if full_resource_name in flow_map:
                            with zip_file.open(filename) as f:
                                page_content = json.load(f)
                            page_key = page_content.get("name")
                            if page_key:
                                flow_map[full_resource_name]["pages"].append(
                                    {"key": page_key, "value": page_content}
                                )

                    # Handle Examples for Playbooks
                    elif (
                        resource_type == "playbooks"
                        and path_parts[-2] == "examples"
                        and filename.endswith(".json")
                    ):
                        if full_resource_name in playbook_map:
                            with zip_file.open(filename) as f:
                                ex_content = json.load(f)
                            if "name" in ex_content:
                                ex_content[
                                    "name"
                                ] = f"{full_resource_name}/examples/{ex_content['name']}"
                            playbook_map[full_resource_name].setdefault(
                                "examples", []
                            ).append(ex_content)

                    # Handle OpenAPI Schemas for Tools
                    elif (
                        resource_type == "tools"
                        and path_parts[-1] == "schema.yaml"
                    ):
                        if full_resource_name in tool_map:
                            try:
                                with zip_file.open(filename) as f:
                                    schema_content = f.read().decode("utf-8")
                                tool_map[full_resource_name].setdefault(
                                    "openApiSpec", {}
                                )["textSchema"] = schema_content
                            except Exception as e:
                                logger.error(
                                    f"    -> ERROR reading schema {filename}: {e}"
                                )

                # Finalize and assemble the full agent object
                full_agent_data["intents"] = list(intent_map.values())
                full_agent_data["tools"] = list(tool_map.values())
                full_agent_data["entityTypes"] = list(entity_map.values())
                full_agent_data["webhooks"] = list(webhook_map.values())
                full_agent_data["flows"] = list(flow_map.values())

                # (Playbook processing logic remains the same)
                processed_playbooks = []
                for pb_name, pb_data in playbook_map.items():
                    if "referencedPlaybooks" in pb_data:
                        resolved_refs = [
                            get_full_name(
                                "playbooks", display_name_to_id[dn]
                            )
                            for dn in pb_data["referencedPlaybooks"]
                            if dn in display_name_to_id
                        ]
                        pb_data["referencedPlaybooks"] = resolved_refs
                    if "referencedTools" in pb_data:
                        resolved_refs = [
                            get_full_name("tools", display_name_to_id[dn])
                            for dn in pb_data["referencedTools"]
                            if dn in display_name_to_id
                        ]
                        pb_data["referencedTools"] = resolved_refs
                    processed_playbooks.append(pb_data)

                start_pb_display_name = full_agent_data.get("startPlaybook")
                if (
                    start_pb_display_name
                    and start_pb_display_name in display_name_to_id
                ):
                    start_playbook_full_name = get_full_name(
                        "playbooks", display_name_to_id[start_pb_display_name]
                    )
                    full_agent_data["startPlaybook"] = start_playbook_full_name
                    try:
                        start_pb_index = next(
                            i
                            for i, pb in enumerate(processed_playbooks)
                            if pb["name"] == start_playbook_full_name
                        )
                        start_pb_obj = processed_playbooks.pop(start_pb_index)
                        processed_playbooks.insert(0, start_pb_obj)
                        logger.info(
                            f"  -> Reordered playbooks list to place start playbook '{start_pb_display_name}' first."
                        )
                    except StopIteration:
                        pass  # Already handled by other logic or not found

                full_agent_data["playbooks"] = processed_playbooks

                # --- ADDED: Resolve startFlow display name to full resource name ---
                start_flow_display_name = full_agent_data.get("startFlow")
                if (
                    start_flow_display_name
                    and start_flow_display_name in display_name_to_id
                ):
                    full_agent_data["startFlow"] = get_full_name(
                        "flows", display_name_to_id[start_flow_display_name]
                    )

                logger.info("Successfully merged all JSON contents.")
                return full_agent_data
        except Exception as e:
            logger.error(f"Error processing zip content: {e}")
            traceback.print_exc()
            return None

    def export_agent_to_json(self, agent_id: str) -> Optional[Dict[str, Any]]:
        """Exports the agent and returns its contents as a JSON object by merging all JSON files in the zip."""
        client_options = self._get_client_options(agent_id)
        if not client_options:
            return None
        client = cx_services.agents.AgentsClient(client_options=client_options)
        request = cx_types.ExportAgentRequest(
            name=agent_id,
            data_format=cx_types.ExportAgentRequest.DataFormat.JSON_PACKAGE,
        )
        logger.info(f"Initiating agent export for {agent_id}...")
        operation = client.export_agent(request=request)

        logger.info("Waiting for export operation to complete...")
        response = operation.result(timeout=300)
        logger.info("Export operation finished.")

        if not response.agent_content:
            raise Exception("Agent export returned empty content.")

        logger.info(
            f"Agent export completed. Size: {len(response.agent_content)} bytes."
        )

        # Delegate to the shared processing method
        return self.process_zip_content(response.agent_content, agent_id)


class DFCXAgents(BaseDFCXClient):
    """Client for interacting with Dialogflow CX Agents."""

    def get_agent(self, agent_id: str) -> Optional[Dict[str, Any]]:
        """Retrieves the full details of a Dialogflow CX Agent."""
        client_options = self._get_client_options(agent_id)
        if not client_options:
            return None
        try:
            client = cx_services.agents.AgentsClient(
                client_options=client_options
            )
            request = cx_types.GetAgentRequest(name=agent_id)
            response = client.get_agent(request=request)
            return MessageToDict(response._pb)
        except Exception as e:
            logger.error(f"Error getting agent '{agent_id}': {e}")
            return None


class DFCXPlaybooks(BaseDFCXClient):
    """Client for interacting with Dialogflow CX Playbooks."""

    def list_playbooks(self, agent_id: str) -> List[Dict[str, Any]]:
        """Lists all playbooks for a given agent."""
        client_options = self._get_client_options(agent_id)
        if not client_options:
            return []
        try:
            client = cx_services.playbooks.PlaybooksClient(
                client_options=client_options
            )
            request = cx_types.ListPlaybooksRequest(parent=agent_id)
            playbooks = client.list_playbooks(request=request)
            return [MessageToDict(pb._pb) for pb in playbooks]
        except Exception as e:
            logger.error(f"Error listing playbooks for agent '{agent_id}': {e}")
            return []


class DFCXTools(BaseDFCXClient):
    """Client for interacting with Dialogflow CX Tools."""

    def list_tools(self, agent_id: str) -> List[Dict[str, Any]]:
        """Lists all tools for a given agent."""
        client_options = self._get_client_options(agent_id)
        if not client_options:
            return []
        try:
            client = cx_services.tools.ToolsClient(
                client_options=client_options
            )
            request = cx_types.ListToolsRequest(parent=agent_id)
            tools = client.list_tools(request=request)
            return [MessageToDict(t._pb) for t in tools]
        except Exception as e:
            logger.error(f"Error listing tools for agent '{agent_id}': {e}")
            return []


class DFCXGenerativeSettings(BaseDFCXClient):
    """Client for interacting with Dialogflow CX Agent GenerativeSettings."""

    def get_generative_settings(
        self, agent_id: str, language_code: str
    ) -> Optional[Dict[str, Any]]:
        """Retrieves the generative settings for a given agent."""
        client_options = self._get_client_options(agent_id)
        if not client_options:
            return None
        try:
            # The resource name for generative settings is the agent ID + "/generativeSettings"
            settings_name = f"{agent_id}/generativeSettings"
            client = cx_services.agents.AgentsClient(
                client_options=client_options
            )
            request = cx_types.GetGenerativeSettingsRequest(
                name=settings_name, language_code=language_code
            )
            response = client.get_generative_settings(request=request)
            return MessageToDict(response._pb)
        except api_exceptions.NotFound:
            # Not an error; it just means no custom settings are configured.
            logger.info(
                "No custom generative settings found for this agent. Using defaults."
            )
            return None
        except Exception as e:
            logger.error(
                f"Error getting generative settings for agent '{agent_id}': {e}"
            )
            return None


class ConversationalAgentsAPI:
    """Facade class to access all Dialogflow CX resources for migration."""

    def __init__(self):
        self.agents = DFCXAgents()
        self.playbooks = DFCXPlaybooks()
        self.tools = DFCXTools()
        self.generative_settings = DFCXGenerativeSettings()
        self.export_agent = DFCXAgentExporter()

    def fetch_full_agent_details(
        self, agent_id: str, use_export: bool = False
    ) -> Optional[Dict[str, Any]]:
        """Fetches the complete agent configuration, including all nested resources.

        Uses either parallel API calls or the ExportAgent method.
        """
        if use_export:
            logger.info(
                f"Starting import for agent via ExportAgent: {agent_id}..."
            )
            return self.export_agent.export_agent_to_json(agent_id)

        logger.info(f"Starting import for agent via API calls: {agent_id}...")
        with concurrent.futures.ThreadPoolExecutor() as executor:
            future_agent = executor.submit(self.agents.get_agent, agent_id)
            future_tools = executor.submit(self.tools.list_tools, agent_id)
            future_playbooks = executor.submit(
                self.playbooks.list_playbooks, agent_id
            )

            agent_details = future_agent.result()
            if not agent_details:
                logger.error(
                    "Failed to fetch core agent details. Aborting migration."
                )
                return None

            # Get the required defaultLanguageCode to make the GenerativeSettings call
            language_code = agent_details.get(
                "defaultLanguageCode", "en"
            )  # Default to 'en' just in case
            future_gen_settings = executor.submit(
                self.generative_settings.get_generative_settings,
                agent_id,
                language_code,
            )

            tools_list = future_tools.result()
            playbooks_list = future_playbooks.result()
            gen_settings = future_gen_settings.result()
            if gen_settings:
                agent_details["generativeSettings"] = gen_settings

            agent_details["tools"] = tools_list
            agent_details["playbooks"] = playbooks_list
            logger.info("Successfully imported all agent components.")
            return agent_details

    def process_local_agent_zip(
        self, zip_bytes: bytes
    ) -> Optional[Dict[str, Any]]:
        """Processes a local zip file without calling the API."""
        # Use a dummy ID for local uploads so the migration logic has a base path
        dummy_id = (
            "projects/local-upload/locations/global/agents/uploaded-agent"
        )
        return self.export_agent.process_zip_content(zip_bytes, dummy_id)
